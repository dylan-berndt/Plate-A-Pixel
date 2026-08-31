from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QUndoStack, QUndoCommand

from ..data.project import Project


class _CallbackCommand(QUndoCommand):
    """A QUndoCommand built from two closures instead of a bespoke
    subclass per operation. Every mutation ProjectController makes is a
    direct read-modify-write on a numpy array or a Palette entry, so a
    snapshot-and-restore closure pair is simpler than reimplementing each
    domain call's inverse by hand."""

    def __init__(self, text, do, undo):
        super().__init__(text)
        self._do = do
        self._undo = undo

    def redo(self):
        self._do()

    def undo(self):
        self._undo()


class ProjectController(QObject):
    """Wraps one Project, translating UI-facing intents into domain-layer
    calls, pushing each as an undoable command, and announcing the result
    as a Qt signal. Nothing here touches a QWidget.

    Mesh recomputation is synchronous: any edit that can change mesh
    geometry rebuilds it immediately and emits meshReady before the call
    returns - no debouncing or worker thread yet, so a large image's
    recompute (~0.6s) blocks whatever thread calls the slot.

    applyTool exists only as a placeholder until a real Tool/ToolRegistry
    layer exists (see ARCHITECTURE.md's tool-layer proposal) - it dispatches
    a bare tool-name string to the selection methods already implemented
    below, and will be replaced once Tool objects exist."""

    selectionChanged = Signal()
    paletteChanged = Signal()
    viewSettingsChanged = Signal()
    meshInvalidated = Signal()
    meshReady = Signal(object)  # Mesh

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.undoStack = QUndoStack(self)

    # -- selection ----------------------------------------------------

    def wandSelect(self, color, mode="replace"):
        """`color` is an RGB tuple identifying the palette color to
        select, matching Canvas.wandSelect's own (documented, working)
        color-triple path."""
        canvas = self.project.canvas
        previous = canvas.selection.copy()

        def do():
            canvas.wandSelect(color, mode=mode)
            self.selectionChanged.emit()

        def undo():
            canvas.selection = previous
            self.selectionChanged.emit()

        self.undoStack.push(_CallbackCommand("Wand Select", do, undo))

    def bucketSelect(self, pos, contiguous=True, diagonal=False, mode="replace"):
        canvas = self.project.canvas
        previous = canvas.selection.copy()

        def do():
            canvas.bucketSelect(pos, contiguous=contiguous, diagonal=diagonal, mode=mode)
            self.selectionChanged.emit()

        def undo():
            canvas.selection = previous
            self.selectionChanged.emit()

        self.undoStack.push(_CallbackCommand("Bucket Select", do, undo))

    def applyTool(self, toolName, pos, mode="replace", **kwargs):
        if toolName == "wand":
            canvas = self.project.canvas
            color = tuple(canvas.palette.colors[canvas.map[pos]])
            self.wandSelect(color, mode=mode)
        elif toolName == "bucket":
            self.bucketSelect(pos, mode=mode, **kwargs)
        else:
            raise ValueError(f"Unknown tool '{toolName}' - no Tool layer exists yet to define custom tools.")

    # -- height (mesh-affecting) ----------------------------------------

    def transformSelectionLayer(self, delta):
        canvas = self.project.canvas
        previous = canvas.layers.copy()

        def do():
            canvas.transformSelection(delta)
            self._rebuildMesh()

        def undo():
            canvas.layers = previous
            self._rebuildMesh()

        self.undoStack.push(_CallbackCommand("Change Height", do, undo))

    def setHollow(self, hollow):
        previous = self.project.viewSettings.hollow

        def do():
            self.project.viewSettings.hollow = hollow
            self._rebuildMesh()

        def undo():
            self.project.viewSettings.hollow = previous
            self._rebuildMesh()

        self.undoStack.push(_CallbackCommand("Set Hollow", do, undo))

    def setMargin(self, margin):
        previous = self.project.viewSettings.baseMargin

        def do():
            self.project.viewSettings.baseMargin = margin
            self._rebuildMesh()

        def undo():
            self.project.viewSettings.baseMargin = previous
            self._rebuildMesh()

        self.undoStack.push(_CallbackCommand("Set Margin", do, undo))

    def _rebuildMesh(self):
        self.meshInvalidated.emit()
        mesh = self.project.rebuildMesh()
        self.meshReady.emit(mesh)

    # -- export-only view settings (no mesh geometry change) -------------
    # cellWidth/cellHeight only scale coordinates on export (objExport) -
    # Mesh's own triangles are unit-based and don't depend on either, so
    # these don't touch the mesh at all.

    def setCellWidth(self, mm):
        previous = self.project.viewSettings.cellWidth

        def do():
            self.project.viewSettings.cellWidth = mm
            self.viewSettingsChanged.emit()

        def undo():
            self.project.viewSettings.cellWidth = previous
            self.viewSettingsChanged.emit()

        self.undoStack.push(_CallbackCommand("Set Cell Width", do, undo))

    def setCellHeight(self, mm):
        previous = self.project.viewSettings.cellHeight

        def do():
            self.project.viewSettings.cellHeight = mm
            self.viewSettingsChanged.emit()

        def undo():
            self.project.viewSettings.cellHeight = previous
            self.viewSettingsChanged.emit()

        self.undoStack.push(_CallbackCommand("Set Cell Height", do, undo))

    # -- palette ----------------------------------------------------------

    def renameColor(self, index, name):
        previous = self.project.canvas.palette[index].name

        def do():
            self.project.canvas.palette.rename(index, name)
            self.paletteChanged.emit()

        def undo():
            self.project.canvas.palette.rename(index, previous)
            self.paletteChanged.emit()

        self.undoStack.push(_CallbackCommand("Rename Color", do, undo))

    def recolorColor(self, index, rgb):
        previous = self.project.canvas.palette[index].color

        def do():
            self.project.canvas.palette.setColor(index, rgb)
            self.paletteChanged.emit()

        def undo():
            self.project.canvas.palette.setColor(index, previous)
            self.paletteChanged.emit()

        self.undoStack.push(_CallbackCommand("Recolor", do, undo))
