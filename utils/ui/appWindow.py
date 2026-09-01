from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QFileDialog

from .base import Theme
from .menuBar import MenuBar
from .toolOptionsBar import ToolOptionsBar
from .toolRail import ToolRail
from .paletteRail import PaletteRail
from .meshSettingsPanel import MeshSettingsPanel
from .statusBar import StatusBar
from .elements import TabBar


class AppWindow(QMainWindow):
    """Assembles every top-level piece (menu bar, tab strip, tool options
    bar, tool rail, palette rail, mesh settings, status bar) around an
    AppController and keeps them all in sync with it. The 2D canvas view
    and 3D mesh view aren't built yet (see canvasElement.py/meshElement.py)
    - setCanvasArea/setMeshElement slot them in once they exist, so this
    class doesn't need to change when they land.

    ProjectController has no dedicated "dirty changed" or "undo state
    changed" signal (see ARCHITECTURE.md - isDirty/canUndo/canRedo are
    plain properties the view polls), so this class re-polls them after
    every one of a project's editing signals rather than waiting for a
    signal that doesn't exist."""

    def __init__(self, appController, theme: Theme = None, **kwargs):
        super().__init__(**kwargs)
        self._appController = appController
        self.theme = theme or Theme()
        self._exportHandler = None

        self.setWindowTitle("Plate-A-Pixel")
        self.setStyleSheet(self.theme.stylesheet())

        self._menuBar = MenuBar(appController)
        self._menuBar.exportRequested.connect(self._onExportRequested)
        self.setMenuBar(self._menuBar)

        central = QWidget()
        rootLayout = QVBoxLayout(central)
        rootLayout.setContentsMargins(0, 0, 0, 0)
        rootLayout.setSpacing(0)

        self._tabBar = TabBar(
            onSelect=self._selectTab, onClose=self._closeTab, onNewTab=self._newTab, theme=self.theme,
        )
        rootLayout.addWidget(self._tabBar)

        self._optionsBar = ToolOptionsBar(appController, appController.toolController, theme=self.theme)
        rootLayout.addWidget(self._optionsBar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._toolRail = ToolRail(appController, appController.toolController, theme=self.theme)
        body.addWidget(self._toolRail)

        # Filled in by setCanvasArea/setMeshElement once those views exist.
        self._canvasSlot = QWidget()
        self._canvasSlotLayout = QVBoxLayout(self._canvasSlot)
        self._canvasSlotLayout.setContentsMargins(0, 0, 0, 0)
        body.addWidget(self._canvasSlot, 1)
        self.canvasArea = None

        self._meshSlot = QWidget()
        self._meshSlotLayout = QVBoxLayout(self._meshSlot)
        self._meshSlotLayout.setContentsMargins(0, 0, 0, 0)
        body.addWidget(self._meshSlot, 1)
        self.meshElement = None

        rightContainer = QWidget()
        # 216 (the mockup's own rail width) is too narrow now that
        # MeshSettingsPanel has 3 more rows than the mockup did - "Wall
        # Thickness" alone doesn't fit its label column at that width even
        # word-wrapped, since a single word can't wrap further. Widened
        # just enough for that; see MeshSettingsPanel.CARD_CONTENT_WIDTH.
        rightContainer.setFixedWidth(250)
        rightContainer.setStyleSheet(f"background: {self.theme.clay300};")
        rightLayout = QVBoxLayout(rightContainer)
        rightLayout.setContentsMargins(0, 0, 0, 0)
        rightLayout.setSpacing(0)
        self._paletteRail = PaletteRail(theme=self.theme)
        self._meshSettingsPanel = MeshSettingsPanel(theme=self.theme)
        rightLayout.addWidget(self._paletteRail)
        rightLayout.addWidget(self._meshSettingsPanel)
        body.addWidget(rightContainer)

        rootLayout.addLayout(body, 1)

        self._statusBar = StatusBar(theme=self.theme)
        rootLayout.addWidget(self._statusBar)

        self.setCentralWidget(central)
        self.resize(1440, 900)

        appController.projectOpened.connect(self._onProjectOpened)
        appController.projectClosed.connect(self._onProjectClosed)
        appController.activeProjectChanged.connect(self._onActiveProjectChanged)

        self._onActiveProjectChanged(None)

    # -- slotting in the 2D/3D views once they exist ----------------------

    def setCanvasArea(self, widget):
        self._canvasSlotLayout.addWidget(widget)
        self.canvasArea = widget
        if hasattr(widget, "zoomChanged"):
            widget.zoomChanged.connect(self._onZoomChanged)
        if hasattr(widget, "resetView"):
            self._menuBar.viewMenu().addAction("Zoom to Fit", widget.resetView)
        if self._appController.activeController is not None and hasattr(widget, "bindProject"):
            widget.bindProject(self._appController.activeController)

    def _onZoomChanged(self, percent):
        self._statusBar.refresh(self._appController.activeController, zoomPercent=percent)

    def setMeshElement(self, widget):
        self._meshSlotLayout.addWidget(widget)
        self.meshElement = widget
        if self._appController.activeController is not None and hasattr(widget, "bindProject"):
            widget.bindProject(self._appController.activeController)

    def setExportHandler(self, handler):
        """`handler` is called with no arguments when File > Export is
        chosen - the export dialog isn't built yet (see objExport.py's
        rework and the Export window task); this is the seam it plugs
        into."""
        self._exportHandler = handler

    def _onExportRequested(self):
        if self._exportHandler is not None:
            self._exportHandler()

    # -- tab strip -----------------------------------------------------

    def _newTab(self):
        filePath, _ = QFileDialog.getOpenFileName(self, "Import Image", "", "PNG Files (*.png)")
        if filePath:
            self._appController.newProjectFromImage(filePath)

    def _selectTab(self, index):
        self._appController.setActiveProject(index)

    def _closeTab(self, index):
        self._appController.closeProject(index)

    def _rebuildTabs(self):
        activeController = self._appController.activeController
        entries = [
            (controller.project.name, controller is activeController, controller.isDirty)
            for controller in self._appController.projectControllers
        ]
        self._tabBar.setTabs(entries)

    # -- AppController signals ------------------------------------------

    def _onProjectOpened(self, controller):
        handler = lambda: self._onProjectEdited(controller)
        controller.selectionChanged.connect(handler)
        controller.paletteChanged.connect(handler)
        controller.viewSettingsChanged.connect(handler)
        controller.meshReady.connect(handler)
        self._rebuildTabs()
        # A brand-new ProjectController's mesh is never computed until
        # something edits through editing(affectsMesh=True) - without this,
        # the 3D view stays empty until the user's first height edit.
        controller.rebuildMesh()

    def _onProjectClosed(self, controller):
        self._rebuildTabs()

    def _onActiveProjectChanged(self, controller):
        self._rebuildTabs()
        self._toolRail.bindProject(controller)
        self._paletteRail.bindProject(controller)
        self._meshSettingsPanel.bindProject(controller)
        if self.canvasArea is not None and hasattr(self.canvasArea, "bindProject"):
            self.canvasArea.bindProject(controller)
        if self.meshElement is not None and hasattr(self.meshElement, "bindProject"):
            self.meshElement.bindProject(controller)
        self._statusBar.refresh(controller, zoomPercent=self._currentZoomPercent())
        self._menuBar.refreshUndoRedo()
        self._optionsBar.refreshUndoRedo()

    def _onProjectEdited(self, controller):
        if controller in self._appController.projectControllers:
            index = self._appController.projectControllers.index(controller)
            self._tabBar.setDirty(index, controller.isDirty)
        if controller is self._appController.activeController:
            self._statusBar.refresh(controller, zoomPercent=self._currentZoomPercent())
            self._menuBar.refreshUndoRedo()
            self._optionsBar.refreshUndoRedo()

    def _currentZoomPercent(self):
        if self.canvasArea is not None and hasattr(self.canvasArea, "artist"):
            return self.canvasArea.artist.zoom * 100
        return 100
