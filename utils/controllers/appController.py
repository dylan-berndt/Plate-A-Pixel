from PySide6.QtCore import QObject, Signal

from ..data.project import Project
from .projectController import ProjectController
from .toolController import ToolController
from .keymapController import KeymapController


class AppController(QObject):
    """Owns the list of open projects (each wrapped in its own
    ProjectController) and which one is active - "the tabs" - plus the
    single ToolController and KeymapController shared across all of them,
    since the selected tool (and its options) and the user's keybinds
    persist across tabs rather than belonging to any one project. Nothing
    here touches a QWidget or a menu; routing actual File/Edit/View menu
    actions to the active ProjectController is a UI-layer concern for
    whatever eventually builds the menu bar."""

    projectOpened = Signal(object)         # ProjectController
    projectClosed = Signal(object)         # ProjectController
    activeProjectChanged = Signal(object)  # ProjectController, or None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.projectControllers = []
        self._activeIndex = None
        self.toolController = ToolController(self, parent=self)
        self.keymapController = KeymapController(self, parent=self)

    @property
    def activeController(self):
        return self.projectControllers[self._activeIndex] if self._activeIndex is not None else None

    def newProjectFromImage(self, filePath, name=None):
        return self._openProject(Project.fromImagePath(filePath, name=name))

    def openProject(self, filePath):
        return self._openProject(Project.load(filePath))

    def _openProject(self, project):
        controller = ProjectController(project, parent=self)
        self.projectControllers.append(controller)
        self.projectOpened.emit(controller)
        self.setActiveProject(len(self.projectControllers) - 1)
        return controller

    def setActiveProject(self, index):
        if index is not None and not (0 <= index < len(self.projectControllers)):
            raise IndexError(f"No open project at index {index}")
        self._activeIndex = index
        self.activeProjectChanged.emit(self.activeController)

    def closeProject(self, index):
        controller = self.projectControllers.pop(index)

        if self._activeIndex is not None:
            if self._activeIndex == index:
                remaining = len(self.projectControllers)
                nextIndex = index if index < remaining else remaining - 1
                self.setActiveProject(nextIndex if nextIndex >= 0 else None)
            elif self._activeIndex > index:
                self._activeIndex -= 1

        # A running QThread must not be destroyed out from under itself -
        # Qt aborts the process ("Destroyed while thread is still
        # running") if that happens, so block briefly here rather than
        # risk a crash on close.
        if controller._meshWorker is not None:
            controller._meshWorker.wait()

        self.projectClosed.emit(controller)
        controller.setParent(None)

    def saveActiveProject(self, filePath=None):
        if self.activeController is None:
            raise RuntimeError("No active project to save.")
        self.activeController.save(filePath)
