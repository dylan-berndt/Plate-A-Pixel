from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace

from PySide6.QtCore import QObject, QThread, Signal

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

    def __init__(self, snapshot, hollow, baseMargin, parent=None):
        super().__init__(parent)
        self._snapshot = snapshot
        self._hollow = hollow
        self._baseMargin = baseMargin

    def run(self):
        mesh = Mesh()
        mesh.canvas = self._snapshot
        mesh.hollow = self._hollow
        mesh.baseMargin = self._baseMargin
        mesh._calculateMesh()
        self.meshComputed.emit(mesh)


class ProjectController(QObject):
    """Wraps one Project, translating UI-facing intents into domain-layer
    calls and announcing the result as a Qt signal. Nothing here touches
    a QWidget.

    Undo is a plain stack of whole-state snapshots (layers, selection,
    palette, view settings) - there isn't enough data in a Project to
    justify a command pattern with a do/undo pair per operation. Every
    mutating method (here and on canvasController) pushes one snapshot
    before it acts via pushUndo(); undo()/redo() pop a snapshot and
    restore it wholesale, then just re-emit everything rather than
    tracking what specifically changed. Whether undo/redo are currently
    available is for the view to check (canUndo/canRedo) - no signal
    fires just for that.

    A multi-call gesture (a tool's onPress/onDrag/.../onRelease sequence)
    should undo as one step, not one step per call - beginGesture()/
    endGesture() bracket that: only the first pushUndo() inside a
    gesture actually pushes a snapshot, so a drag calling
    canvasController.bucketSelect fifty times still costs one undo entry.

    Mesh recomputation runs on a background QThread (~0.6s for a full
    image is long enough to visibly stall the UI otherwise): calling
    rebuildMesh() fires meshInvalidated immediately, then meshReady(mesh)
    once the worker finishes. If another edit arrives while a computation
    is already running, only the latest request is kept and started when
    the current one finishes - a burst of edits collapses into a single
    follow-up recompute rather than queuing one per edit.

    Canvas editing (selection, height, hollow/margin) isn't this class's
    job - see canvasController (CanvasController), which calls back into
    pushUndo()/rebuildMesh() here to stay on this same undo stack and
    mesh pipeline rather than owning its own. Turning a click into a
    canvasController call isn't this class's job either - see
    ToolController and Tool in ..tools."""

    selectionChanged = Signal()
    paletteChanged = Signal()
    viewSettingsChanged = Signal()
    meshInvalidated = Signal()
    meshReady = Signal(object)  # Mesh

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
    def editing(self, affectsMesh=False):
        """Wrap one undoable canvas edit: pushUndo() on entry, then either
        rebuildMesh() or selectionChanged.emit() on exit depending on
        whether this particular edit can change mesh geometry. Used by
        canvasController's methods so each one is a single `with` block
        instead of repeating pushUndo()/emit-or-rebuild by hand."""
        self.pushUndo()
        yield
        if affectsMesh:
            self.rebuildMesh()
        else:
            self.selectionChanged.emit()

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
        """Recompute the mesh on a background thread from the project's
        current state - called by canvasController after any edit that
        can change mesh geometry (height, hollow, baseMargin)."""
        self.meshInvalidated.emit()
        request = (
            _CanvasSnapshot(self.project.canvas),
            self.project.viewSettings.hollow,
            self.project.viewSettings.baseMargin,
        )
        if self._meshWorker is not None:
            self._pendingMeshRequest = request
            return
        self._startMeshWorker(request)

    def _startMeshWorker(self, request):
        snapshot, hollow, baseMargin = request
        self._meshWorker = _MeshWorker(snapshot, hollow, baseMargin, parent=self)
        self._meshWorker.meshComputed.connect(self._onMeshComputed)
        self._meshWorker.start()

    def _onMeshComputed(self, mesh):
        self.project.mesh = mesh
        worker, self._meshWorker = self._meshWorker, None
        worker.deleteLater()
        self.meshReady.emit(mesh)
        if self._pendingMeshRequest is not None:
            request, self._pendingMeshRequest = self._pendingMeshRequest, None
            self._startMeshWorker(request)

    # -- export-only view settings (no mesh geometry change) -------------
    # cellWidth/cellHeight only scale coordinates on export (objExport) -
    # Mesh's own triangles are unit-based and don't depend on either, so
    # these don't touch the mesh at all.

    def setCellWidth(self, mm):
        self.pushUndo()
        self.project.viewSettings.cellWidth = mm
        self.viewSettingsChanged.emit()

    def setCellHeight(self, mm):
        self.pushUndo()
        self.project.viewSettings.cellHeight = mm
        self.viewSettingsChanged.emit()

    # -- palette ----------------------------------------------------------

    def renameColor(self, index, name):
        self.pushUndo()
        self.project.canvas.palette.rename(index, name)
        self.paletteChanged.emit()

    def recolorColor(self, index, rgb):
        self.pushUndo()
        self.project.canvas.palette.setColor(index, rgb)
        self.paletteChanged.emit()
