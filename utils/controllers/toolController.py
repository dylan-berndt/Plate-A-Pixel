from ..tools.tool import ToolRegistry
from ..tools.wandTool import WandTool


class ToolController:
    """Owns the ToolRegistry and routes canvas press/drag/release events
    to the active tool. Lives on AppController, not ProjectController -
    the selected tool and its options (e.g. "contiguous" on) persist
    across tabs, like a normal image editor's tool state does.

    Each dispatch resolves AppController's *current* activeController and
    hands it to the tool directly - the tool never stores a controller
    itself, since the active project can change out from under a
    selected tool on a tab switch."""

    def __init__(self, appController):
        self.appController = appController
        self.registry = ToolRegistry([WandTool()])

    def press(self, pos):
        self._dispatch("onPress", pos)

    def drag(self, pos):
        self._dispatch("onDrag", pos)

    def release(self, pos):
        self._dispatch("onRelease", pos)

    def _dispatch(self, handlerName, pos):
        tool = self.registry.activeTool
        controller = self.appController.activeController
        if tool is None or controller is None:
            return
        getattr(tool, handlerName)(controller, pos)
