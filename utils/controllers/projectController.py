import atexit
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from ..data.project import Project
from ..data.mesh import Mesh, computeMeshDataPacked, unpackMeshes
from .canvasController import CanvasController

# A live recompute previously ran computeMeshData() on the QThread itself -
# off the *thread* the UI runs on, but still inside the same process, so it
# still held the GIL against the main thread's own Python/Qt work for its
# entire duration (CPython only hands the GIL to a waiting thread between
# bytecode instructions, and a single manifold3d CSG call - or a long run of
# pure-Python loops - doesn't yield it at all until it returns). A separate
# process has its own GIL, so submitting the real work there and blocking
# this thread on the result (a blocking wait releases the GIL properly,
# same as any other blocking I/O) leaves the main thread fully free for the
# whole computation, not just between calls into it.
#
# One shared, lazily-started, single-worker pool (not one per project or
# per recompute) - starting a process costs real time, so this pays that
# cost once per app run rather than once per edit.
_meshProcessPool = None


def _getMeshProcessPool():
    global _meshProcessPool
    if _meshProcessPool is None:
        _meshProcessPool = ProcessPoolExecutor(max_workers=1)
        atexit.register(_meshProcessPool.shutdown, cancel_futures=True)
    return _meshProcessPool


class _CanvasSnapshot:
    """A frozen stand-in for Canvas carrying only what computeMeshData
    actually reads (map, layers, len(palette)). Built once when a rebuild
    is requested so the worker process computing it never touches the
    live Canvas, which may keep changing while that computation runs."""

    def __init__(self, canvas):
        self.map = canvas.map.copy()
        self.layers = canvas.layers.copy()
        self.palette = range(len(canvas.palette))


class _MeshWorker(QThread):
    """Runs one mesh recompute off the UI thread against a frozen
    snapshot, then hands the finished Mesh back via a queued signal.
    Always computes with fastPreview on - the live viewport doesn't need
    (and can't afford, per-edit) a mesh that's actually watertight; export
    forces a fresh, exact recompute of its own (see Project.rebuildMesh)."""

    meshComputed = Signal(object)  # Mesh

    def __init__(self, snapshot, viewSettings, parent=None):
        super().__init__(parent)
        self._snapshot = snapshot
        # A plain-dataclass copy (see rebuildMesh) - cellWidth/cellHeight
        # ride along unused (export-only, see objExport.py) but a whole
        # ViewSettings is simpler to carry than an ever-growing list of
        # individual mesh-geometry parameters.
        self._viewSettings = viewSettings

    def _computeMeshData(self):
        """Submits the real computation to the shared worker process and
        blocks for its result - split out from run() so tests can
        monkeypatch just this one method (to simulate failure or slowness)
        without needing to reach into a separate process to do it.

        Submits computeMeshDataPacked, not computeMeshData directly - its
        meshes come back as compact numpy arrays rather than lists of
        individual Vector3 objects, since pickling thousands of those
        pays their full per-instance overhead once per vertex (measured:
        on the order of a second for a real mesh, more than the
        computation itself), unpacked back on this side."""
        future = _getMeshProcessPool().submit(
            computeMeshDataPacked,
            self._snapshot.map, self._snapshot.layers, len(self._snapshot.palette),
            self._viewSettings.hollow, True,
            self._viewSettings.baseMargin, self._viewSettings.tubeMargin,
            self._viewSettings.wallThickness, self._viewSettings.bulgeSize,
        )
        packedMeshes, warnings = future.result()
        return unpackMeshes(packedMeshes), warnings

    def run(self):
        mesh = Mesh()
        mesh.canvas = self._snapshot
        mesh.hollow = self._viewSettings.hollow
        mesh.fastPreview = True
        mesh.baseMargin = self._viewSettings.baseMargin
        mesh.tubeMargin = self._viewSettings.tubeMargin
        mesh.wallThickness = self._viewSettings.wallThickness
        mesh.bulgeSize = self._viewSettings.bulgeSize
        try:
            mesh._refreshCaches()
            mesh.meshes, mesh.warnings = self._computeMeshData()
        except Exception:
            # An exception here (e.g. trimesh hitting a boolean-op case
            # its installed backends can't handle, or the worker process
            # itself dying) must never be silently swallowed and left
            # there: without this, meshComputed never fires,
            # self._meshWorker (in ProjectController) never clears, and
            # every future rebuildMesh() call just queues behind a worker
            # that has already died - the mesh view goes stale forever
            # with no visible sign why. Emitting the still-empty Mesh
            # keeps the pipeline alive; the traceback at least says why
            # nothing's there instead of nothing at all.
            traceback.print_exc(file=sys.stderr)
        self.meshComputed.emit(mesh)


class ProjectController(QObject):
    """Wraps one Project, translating UI-facing intents into domain-layer
    calls and announcing the result as a Qt signal. Nothing here touches
    a QWidget.

    Undo is a plain stack of whole-state snapshots (layers, selection,
    palette, view settings) rather than a command pattern - there isn't
    enough data in a Project to justify one. Every mutating method pushes
    one snapshot via pushUndo() (usually through editing() below);
    undo()/redo() pop a snapshot and restore it wholesale, re-emitting
    everything rather than tracking what changed. canUndo/canRedo are
    polled by the view - no signal fires just for that.

    A multi-call gesture (onPress/onDrag/.../onRelease) should undo as
    one step - beginGesture()/endGesture() bracket that, so only the
    first pushUndo() inside a gesture actually pushes a snapshot.

    Mesh recomputation runs on a background QThread (~0.6s for a full
    image is long enough to visibly stall the UI otherwise): calling
    rebuildMesh() fires meshInvalidated immediately, then meshReady(mesh)
    once the worker finishes. Starting the actual computation is debounced
    (MESH_DEBOUNCE_MS) rather than immediate - CPython's GIL means the
    computation and the UI's own rendering callbacks still take turns on
    one core, so a chain of rebuilds (e.g. mashing a layer's "+" button)
    visibly stutters if each edit starts its own recompute immediately.
    Repeated edits within the window replace the pending request and push
    the start back, so a burst collapses into one recompute; a computation
    already running when the window elapses finishes on its own and picks
    up the latest pending request itself (see _onMeshComputed).

    This class owns no editing methods of its own - it's the shared
    infrastructure (undo stack, editing(), the mesh worker, save/dirty
    state) that canvasController and the FunctionalTool subclasses in
    ..tools edit through, so they share one undo stack and mesh pipeline.
    Turning a click into one of those calls is ToolController's job."""

    selectionChanged = Signal()
    paletteChanged = Signal()
    viewSettingsChanged = Signal()
    meshInvalidated = Signal()
    meshReady = Signal(object)  # Mesh

    # How long rebuildMesh() waits for edits to stop arriving before it
    # actually starts a worker - see the class docstring. Tests that want
    # rebuildMesh()'s old fire-immediately behavior set this to 0 (see the
    # `controller` fixture in conftest.py).
    MESH_DEBOUNCE_MS = 250

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.canvasController = CanvasController(self)
        self._undoStack = []
        self._redoStack = []
        self._gestureDepth = 0
        self._dirty = False
        self._meshWorker = None
        self._pendingMeshRequest = None
        self._meshDebounceTimer = QTimer(self)
        self._meshDebounceTimer.setSingleShot(True)
        self._meshDebounceTimer.setInterval(self.MESH_DEBOUNCE_MS)
        self._meshDebounceTimer.timeout.connect(self._onMeshDebounceElapsed)

    # -- undo/redo ------------------------------------------------------

    @property
    def canUndo(self):
        return bool(self._undoStack)

    @property
    def canRedo(self):
        return bool(self._redoStack)

    @property
    def isDirty(self):
        """Whether anything has changed since the project was last saved
        (or, for a never-saved project, since it was created)."""
        return self._dirty

    def beginGesture(self):
        """Start a multi-call gesture: pushes one undo snapshot now (if
        not already inside a gesture) and suppresses pushUndo() until a
        matching endGesture()."""
        if self._gestureDepth == 0:
            self._pushUndoNow()
        self._gestureDepth += 1

    def endGesture(self):
        self._gestureDepth = max(0, self._gestureDepth - 1)

    def _snapshot(self):
        canvas = self.project.canvas
        return (
            canvas.layers.copy(),
            canvas.selection.copy(),
            deepcopy(canvas.palette),
            replace(self.project.viewSettings),
        )

    def _restore(self, snapshot):
        canvas = self.project.canvas
        canvas.layers, canvas.selection, canvas.palette, self.project.viewSettings = snapshot
        self._dirty = True
        self.rebuildMesh()
        self.selectionChanged.emit()
        self.paletteChanged.emit()
        self.viewSettingsChanged.emit()

    def pushUndo(self):
        """Record an undo point before a mutation. Called by this class's
        own mutating methods and by canvasController's - respects an
        in-progress gesture (see beginGesture) either way."""
        if self._gestureDepth > 0:
            return
        self._pushUndoNow()

    @contextmanager
    def editing(self, affectsMesh=False, signal=None):
        """Wrap one undoable edit: pushUndo() on entry, then either
        rebuildMesh() (if affectsMesh) or the given signal's .emit() on
        exit. Exactly one of affectsMesh/signal applies - there's no
        implicit default signal, since different canvasController methods
        announce themselves differently (selectionChanged, paletteChanged,
        viewSettingsChanged). Used by canvasController's methods, and by
        the FunctionalTool subclasses, so each is a single `with` block
        instead of repeating pushUndo()/emit-or-rebuild by hand."""
        assert affectsMesh or signal is not None, "editing() needs affectsMesh=True or an explicit signal"
        self.pushUndo()
        yield
        if affectsMesh:
            self.rebuildMesh()
        else:
            signal.emit()

    def _pushUndoNow(self):
        self._undoStack.append(self._snapshot())
        self._redoStack.clear()
        self._dirty = True

    def undo(self):
        if not self._undoStack:
            return
        self._redoStack.append(self._snapshot())
        self._restore(self._undoStack.pop())

    def redo(self):
        if not self._redoStack:
            return
        self._undoStack.append(self._snapshot())
        self._restore(self._redoStack.pop())

    # -- persistence ------------------------------------------------------

    def save(self, filePath=None):
        """Writes the project to disk, defaulting to the path it was last
        loaded from or saved to ("Save"); pass filePath for "Save As"."""
        filePath = filePath or self.project.filePath
        if filePath is None:
            raise ValueError("This project has never been saved - a filePath is required.")
        self.project.save(filePath)
        self._dirty = False

    def rebuildMesh(self):
        """Recompute the mesh from the project's current state - called by
        canvasController after any edit that can change mesh geometry
        (height, hollow, baseMargin, tubeMargin, wallThickness, bulgeSize).
        Invalidates immediately but debounces the actual worker start - see
        the class docstring."""
        self.meshInvalidated.emit()
        self._pendingMeshRequest = (_CanvasSnapshot(self.project.canvas), replace(self.project.viewSettings))
        self._meshDebounceTimer.start()

    def _onMeshDebounceElapsed(self):
        if self._pendingMeshRequest is None:
            return
        if self._meshWorker is not None:
            # A worker from before this window is still running -
            # _onMeshComputed starts the pending request itself once it
            # finishes (it checks isActive() on this same timer).
            return
        request, self._pendingMeshRequest = self._pendingMeshRequest, None
        self._startMeshWorker(request)

    def _startMeshWorker(self, request):
        snapshot, viewSettings = request
        self._meshWorker = _MeshWorker(snapshot, viewSettings, parent=self)
        self._meshWorker.meshComputed.connect(self._onMeshComputed)
        self._meshWorker.start()

    def _onMeshComputed(self, mesh):
        self.project.mesh = mesh
        worker, self._meshWorker = self._meshWorker, None
        # Qt's "is this thread finished" bookkeeping can lag behind
        # run() actually returning, and deleteLater()-ing a QThread Qt
        # still considers running aborts the process (see
        # AppController.closeProject for the same hazard on app exit).
        # wait() is a no-op in the normal case and closes that race in
        # the rare one.
        worker.wait()
        worker.deleteLater()
        self.meshReady.emit(mesh)
        # Start the pending request now only if the debounce window has
        # already elapsed (it fired while this worker was busy and left
        # the request here) - otherwise edits are still coming in, and
        # _onMeshDebounceElapsed will start it once they stop.
        if self._pendingMeshRequest is not None and not self._meshDebounceTimer.isActive():
            request, self._pendingMeshRequest = self._pendingMeshRequest, None
            self._startMeshWorker(request)

