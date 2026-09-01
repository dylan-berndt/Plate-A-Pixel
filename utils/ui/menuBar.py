from PySide6.QtWidgets import QMenuBar, QFileDialog, QMessageBox
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtCore import Signal

from ..data.objExport import unnamedColorIndices


class MenuBar(QMenuBar):
    """File/Edit/View. Every File action that mutates project state routes
    through AppController so it stays on the same undo/dirty/mesh
    pipeline as everything else - this class never touches a Project or
    Canvas directly.

    Save is guarded: every palette entry needs a name before a project
    can be saved, since export (see objExport.py) names each printed part
    after its color's layer name - an unnamed color would either collide
    with another unnamed one or produce a meaningless filename. Save
    blocks and tells the user which colors need naming rather than saving
    something export can't cleanly use later."""

    exportRequested = Signal()

    def __init__(self, appController, **kwargs):
        super().__init__(**kwargs)
        self._appController = appController

        fileMenu = self.addMenu("File")
        newAction = fileMenu.addAction("New From Image...")
        newAction.triggered.connect(self._newFromImage)
        openAction = fileMenu.addAction("Open...")
        openAction.setShortcut(QKeySequence.Open)
        openAction.triggered.connect(self._openProject)
        fileMenu.addSeparator()
        saveAction = fileMenu.addAction("Save")
        saveAction.setShortcut(QKeySequence.Save)
        saveAction.triggered.connect(self._save)
        saveAsAction = fileMenu.addAction("Save As...")
        saveAsAction.setShortcut(QKeySequence.SaveAs)
        saveAsAction.triggered.connect(self._saveAs)
        fileMenu.addSeparator()
        exportAction = fileMenu.addAction("Export...")
        exportAction.triggered.connect(self.exportRequested.emit)
        fileMenu.addSeparator()
        closeAction = fileMenu.addAction("Close Tab")
        closeAction.setShortcut(QKeySequence.Close)
        closeAction.triggered.connect(self._closeActiveTab)

        editMenu = self.addMenu("Edit")
        self._undoAction = editMenu.addAction("Undo")
        self._undoAction.setShortcut(QKeySequence.Undo)
        self._undoAction.triggered.connect(self._undo)
        self._redoAction = editMenu.addAction("Redo")
        self._redoAction.setShortcut(QKeySequence.Redo)
        self._redoAction.triggered.connect(self._redo)

        self._viewMenu = self.addMenu("View")

    def viewMenu(self):
        """Lets a later-built widget (the canvas view, in particular) add
        its own View actions (zoom to fit, grid toggle, ...) without this
        class needing to know about it."""
        return self._viewMenu

    # -- File --------------------------------------------------------------

    def _newFromImage(self):
        filePath, _ = QFileDialog.getOpenFileName(self, "Import Image", "", "PNG Files (*.png)")
        if filePath:
            self._appController.newProjectFromImage(filePath)

    def _openProject(self):
        filePath, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "Plate-A-Pixel Files (*.pap)")
        if filePath:
            self._appController.openProject(filePath)

    def _unnamedColors(self):
        controller = self._appController.activeController
        if controller is None:
            return []
        palette = controller.project.canvas.palette
        return [f"color {i}" for i in unnamedColorIndices(palette)]

    def _blockedByUnnamedColors(self):
        unnamed = self._unnamedColors()
        if not unnamed:
            return False
        QMessageBox.warning(
            self, "Name every color before saving",
            "Every palette color needs a name before this project can be saved "
            "(export names each printed part after its color's name):\n\n"
            + "\n".join(f"- {name}" for name in unnamed),
        )
        return True

    def _save(self):
        controller = self._appController.activeController
        if controller is None or self._blockedByUnnamedColors():
            return
        if controller.project.filePath is None:
            self._saveAs()
            return
        controller.save()

    def _saveAs(self):
        controller = self._appController.activeController
        if controller is None or self._blockedByUnnamedColors():
            return
        filePath, _ = QFileDialog.getSaveFileName(self, "Save Project", "", "Plate-A-Pixel Files (*.pap)")
        if filePath:
            controller.save(filePath)

    def _closeActiveTab(self):
        appController = self._appController
        controller = appController.activeController
        if controller is not None:
            appController.closeProject(appController.projectControllers.index(controller))

    # -- Edit --------------------------------------------------------------

    def _undo(self):
        controller = self._appController.activeController
        if controller is not None:
            controller.undo()

    def _redo(self):
        controller = self._appController.activeController
        if controller is not None:
            controller.redo()

    def refreshUndoRedo(self):
        controller = self._appController.activeController
        self._undoAction.setEnabled(controller is not None and controller.canUndo)
        self._redoAction.setEnabled(controller is not None and controller.canRedo)
