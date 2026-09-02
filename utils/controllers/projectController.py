import sys
import traceback
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from ..data.project import Project
from ..data.mesh import Mesh
from .canvasController import CanvasController


class _CanvasSnapshot:
    """A frozen stand-in for Canvas carrying only what Mesh._calculateMesh
    actually reads (map, layers, len(palette)). Built once when a rebuild
    is requested so the background thread computing it never touches the
    live Canvas, which may keep changing while that computation runs."""

    def __init__(self, canvas):
        self.map = canvas.map.copy()
        self.layers = canvas.layers.copy()
        self.palette = range(len(canvas.palette))


class _MeshWorker(QThread):
    """Runs one Mesh._calculateMesh() off the UI thread against a frozen
    snapshot, then hands the finished Mesh back via a queued signal."""

    meshComputed = Signal(object)  # Mesh

    def __init__(self, snapshot, viewSettings, parent=None):
        super().__init__(parent)
        self._snapshot = snapshot
        # A plain-dataclass copy (see rebuildMesh) - cellWidth/cellHeight
        # ride along unused (export-only, see objExport.py) but a whole
        # ViewSettings is simpler to carry than an ever-growing list of
        # individual mesh-geometry parameters.
        self._viewSettings = viewSettings

    def run(self):
        mesh = Mesh()
        mesh.canvas = self._snapshot
        mesh.hollow = self._viewSettings.hollow
        mesh.baseMargin = self._viewSettings.baseMargin
        mesh.tubeMargin = self._viewSettings.tubeMargin
        mesh.wallThickness = self._viewSettings.wallThickness
        mesh.bulgeSize = self._viewSettings.bulgeSize
        try:
            mesh._calculateMesh()
        except Exception:
            # An exception here (e.g. trimesh hitting a boolean-op case
            # its installed backends can't handle) must never be silently
            # swallowed by the thread and left there: without this,
            # meshComputed never fires, self._meshWorker (in
            # ProjectController) never clears, and every future
            # rebuildMesh() call just queues behind a worker that has
            # already died - the mesh view goes stale forever with no
            # visible sign why. Emitting the still-empty Mesh keeps the
            # pipeline alive; the traceback at least says why nothing's
            # there instead of nothing at all.
            traceback.print_exc(file=sys.stderr)
        self.meshComputed.emit(mesh)


class ProjectController(QObject):
    """Wraps one Project, translating UI-facing intents into domain-layer
    calls and announcing the result as a Qt signal. Nothing here touches
    a QWidget.

    Undo is a plain stack of whole-state snapshots (layers, selection,
    palette, view settings) - there isn't enough data in a Project to
    justify a command pattern with a do/undo pair per operation. Every
    mutating method (here, on canvasController, and on the Tool
    subclasses) pushes one snapshot before it acts via pushUndo(), usually
    through the editing() context manager below; undo()/redo() pop a
    snapshot and restore it wholesale, then just re-emit everything rather
    than tracking what specifically changed. Whether undo/redo are
    currently available is for the view to check (canUndo/canRedo) - no
    signal fires just for that.

    A multi-call gesture (a tool's onPress/onDrag/.../onRelease sequence)
    should undo as one step, not one step per call - beginGesture()/
    endGesture() bracket that: only the first pushUndo() inside a
    gesture actually pushes a snapshot, so a BrushSelectTool drag calling
    editing() fifty times still costs one undo entry.

    Mesh recomputation runs on a background QThread (~0.6s for a full
    image is long enough to visibly stall the UI otherwise): calling
    rebuildMesh() fires meshInvalidated immediately, then meshReady(mesh)
    once the worker finishes. Starting the actual computation is debounced
    (MESH_DEBOUNCE_MS) rather than immediate: a background QThread keeps
    the *app* responsive, but CPython's GIL still means the computation and
    the UI's own Python-level rendering callbacks (paintGL/paintEvent) take
    turns on one core, and a chain of rebuilds - e.g. mashing a layer's "+"
    button - visibly stutters if each one starts the instant the edit
    happens. Repeated edits within the debounce window just keep replacing
    the pending request and pushing the start back, so a whole burst
    collapses into one recompute of wherever the user ends up, not one per
    click; a computation already running when the window elapses is left
    to finish on its own and picks up the latest pending request the
    instant it does (see _onMeshComputed) rather than waiting out a second
    debounce window on top.

    This class owns no editing methods of its own - it's the shared
    infrastructure (undo stack, editing(), the mesh worker, save/dirty
    state) that everything else edits through, not a second command
    surface competing with canvasController. Every actual edit
    (selection, height, hollow/margin, cell scale, palette naming) lives
    on canvasController (CanvasController) or, for selection, directly on
    the FunctionalTool subclasses in ..tools - both call back into
    editing()/pushUndo()/rebuildMesh() here to stay on this same undo
    stack and mesh pipeline rather than owning their own. Turning a click
    into one of those calls isn't this class's job either - see
    ToolController in this package."""

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
            # A worker from before this debounce window is still running -
            # _onMeshComputed checks isActive() on this same timer, sees it
            # no longer running, and starts the pending request itself the
            # moment that worker finishes, rather than this timer having to
            # fire a second time.
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
        # meshComputed is the last thing run() does, so by the time this
        # queued slot fires the thread has already returned in practice -
        # but Qt's own "is this thread finished" bookkeeping isn't
        # guaranteed to have settled yet, and deleteLater()-ing a QThread
        # Qt still considers running aborts the process outright (see
        # AppController.closeProject for the same hazard on the app-exit
        # path). wait() here is a no-op wait in the normal case and closes
        # that race in the rare one - this is exactly the kind of race a
        # much faster mesh recompute (see Mesh._calculateMesh) makes far
        # easier to actually hit.
        worker.wait()
        worker.deleteLater()
        self.meshReady.emit(mesh)
        # Only start the pending request immediately if the debounce window
        # has already elapsed (it fired while this worker was still busy,
        # found _meshWorker set, and left the request for us here) - if the
        # timer is still counting down, edits are still coming in, and
        # _onMeshDebounceElapsed will start it once they actually stop.
        if self._pendingMeshRequest is not None and not self._meshDebounceTimer.isActive():
            request, self._pendingMeshRequest = self._pendingMeshRequest, None
            self._startMeshWorker(request)

