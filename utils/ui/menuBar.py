from PySide6.QtWidgets import QMenuBar, QFileDialog
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtCore import Signal, Qt

from .base import Theme


class MenuBar(QMenuBar):
    """File/Edit/View. Every File action that mutates project state routes
    through AppController so it stays on the same undo/dirty/mesh
    pipeline as everything else - this class never touches a Project or
    Canvas directly.

    Save/Save As aren't guarded on unnamed colors the way Export still is
    (see ExportDialog) - ProjectController.save() auto-names anything
    still blank right before writing (CanvasController.
    autoNameUnnamedColors), so there's nothing for this class to block
    on; it just calls save() the same as any other edit path.

    "Close Tab" doesn't close anything itself - it emits
    closeActiveTabRequested, which AppWindow connects to its own
    _closeTab (the same method the tab strip's own close button calls),
    so there's exactly one place that actually closes a tab and confirms
    unsaved changes first, not two copies of that logic.

    The Edit menu's Select All / Deselect All / Invert Selection entries
    are AppController.keymapController's own QAction objects (see
    KeymapController), not built here - adding the same action a menu
    shows and a shortcut fires keeps both in sync automatically (the
    label always reflects the current keybind), rather than this class
    maintaining a second copy of "what shortcut does this" that could
    drift from what KeymapController/SettingsWindow actually have bound."""

    exportRequested = Signal()
    settingsRequested = Signal()
    closeActiveTabRequested = Signal()

    def __init__(self, appController, theme: Theme = None, **kwargs):
        super().__init__(**kwargs)
        self._appController = appController
        theme = theme or Theme()

        # The mockup's top bar is the darkest brown in the app - distinct
        # from the lighter clay-800 tab strip directly below it (see
        # TabBar) - and it needs its own stylesheet to get that at all,
        # since the app-wide QWidget{background:...} rule (see Theme.
        # stylesheet) is light and would otherwise cascade here too.
        self.setStyleSheet(f"""
            QMenuBar {{ background: {theme.clay950}; color: {theme.paper}; padding: 2px 6px; }}
            QMenuBar::item {{ background: transparent; padding: 4px 10px; border-radius: 3px; }}
            QMenuBar::item:selected {{ background: rgba(255, 255, 255, 0.12); }}
            QMenu {{ background: {theme.paper}; color: {theme.ink}; border: 1.5px solid {theme.ink}; }}
            QMenu::item {{ padding: 5px 20px; }}
            QMenu::item:selected {{ background: {theme.clay200}; }}
        """)

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
        closeAction.triggered.connect(self.closeActiveTabRequested.emit)

        editMenu = self.addMenu("Edit")
        self._undoAction = editMenu.addAction("Undo")
        self._undoAction.setShortcut(QKeySequence.Undo)
        self._undoAction.triggered.connect(self._undo)
        self._redoAction = editMenu.addAction("Redo")
        self._redoAction.setShortcut(QKeySequence.Redo)
        self._redoAction.triggered.connect(self._redo)

        editMenu.addSeparator()
        keymapController = appController.keymapController
        editMenu.addAction(keymapController.actions["selectAll"])
        editMenu.addAction(keymapController.actions["deselectAll"])
        editMenu.addAction(keymapController.actions["invertSelection"])

        editMenu.addSeparator()
        settingsAction = editMenu.addAction("Settings...")
        settingsAction.triggered.connect(self.settingsRequested.emit)

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

    def _save(self):
        controller = self._appController.activeController
        if controller is None:
            return
        if controller.project.filePath is None:
            self._saveAs()
            return
        controller.save()

    def _saveAs(self):
        controller = self._appController.activeController
        if controller is None:
            return
        filePath, _ = QFileDialog.getSaveFileName(self, "Save Project", "", "Plate-A-Pixel Files (*.pap)")
        if filePath:
            controller.save(filePath)

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
