from copy import deepcopy
from dataclasses import replace

from PySide6.QtCore import QObject, Signal

from ..data.project import Project


class ProjectController(QObject):
    """Wraps one Project, translating UI-facing intents into domain-layer
    calls and announcing the result as a Qt signal. Nothing here touches
    a QWidget.

    Undo is a plain stack of whole-state snapshots (layers, selection,
    palette, view settings) - there isn't enough data in a Project to
    justify a command pattern with a do/undo pair per operation. Every
    mutating method pushes one snapshot before it acts; undo()/redo() pop
    a snapshot and restore it wholesale, then just re-emit everything
    rather than tracking what specifically changed.

    Mesh recomputation is synchronous: any edit that can change mesh
    geometry rebuilds it immediately and emits meshReady before the call
    returns - no debouncing or worker thread yet, so a large image's
    recompute (~0.6s) blocks whatever thread calls the slot.

    Canvas interaction (turning a click into one of the calls below)
    isn't this class's job - see ToolController and Tool in ..tools."""

    selectionChanged = Signal()
    paletteChanged = Signal()
    viewSettingsChanged = Signal()
    meshInvalidated = Signal()
    meshReady = Signal(object)  # Mesh

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self._undoStack = []
        self._redoStack = []

    # -- undo/redo ------------------------------------------------------

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
        self._rebuildMesh()
        self.selectionChanged.emit()
        self.paletteChanged.emit()
        self.viewSettingsChanged.emit()

    def _pushUndo(self):
        self._undoStack.append(self._snapshot())
        self._redoStack.clear()

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

    # -- selection ----------------------------------------------------

    def bucketSelect(self, pos, contiguous=True, diagonal=False, mode="replace"):
        self._pushUndo()
        self.project.canvas.bucketSelect(pos, contiguous=contiguous, diagonal=diagonal, mode=mode)
        self.selectionChanged.emit()

    # -- height (mesh-affecting) ----------------------------------------

    def transformSelectionLayer(self, delta):
        self._pushUndo()
        self.project.canvas.transformSelection(delta)
        self._rebuildMesh()

    def setHollow(self, hollow):
        self._pushUndo()
        self.project.viewSettings.hollow = hollow
        self._rebuildMesh()

    def setMargin(self, margin):
        self._pushUndo()
        self.project.viewSettings.baseMargin = margin
        self._rebuildMesh()

    def _rebuildMesh(self):
        self.meshInvalidated.emit()
        mesh = self.project.rebuildMesh()
        self.meshReady.emit(mesh)

    # -- export-only view settings (no mesh geometry change) -------------
    # cellWidth/cellHeight only scale coordinates on export (objExport) -
    # Mesh's own triangles are unit-based and don't depend on either, so
    # these don't touch the mesh at all.

    def setCellWidth(self, mm):
        self._pushUndo()
        self.project.viewSettings.cellWidth = mm
        self.viewSettingsChanged.emit()

    def setCellHeight(self, mm):
        self._pushUndo()
        self.project.viewSettings.cellHeight = mm
        self.viewSettingsChanged.emit()

    # -- palette ----------------------------------------------------------

    def renameColor(self, index, name):
        self._pushUndo()
        self.project.canvas.palette.rename(index, name)
        self.paletteChanged.emit()

    def recolorColor(self, index, rgb):
        self._pushUndo()
        self.project.canvas.palette.setColor(index, rgb)
        self.paletteChanged.emit()
