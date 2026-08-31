from PySide6.QtCore import QObject, Signal

from ..tools.tool import ToolRegistry
from ..tools.wandTool import WandTool
from ..tools.brushSelectTool import BrushSelectTool


class ToolController(QObject):
    """Owns the ToolRegistry and routes canvas press/drag/release events
    to the active tool. Lives on AppController, not ProjectController -
    the selected tool and its options (e.g. "contiguous" on) persist
    across tabs, like a normal image editor's tool state does.

    A press/drag/.../release sequence is one gesture: press resolves and
    holds onto whichever ProjectController is active at that moment and
    brackets the whole sequence in beginGesture()/endGesture() so it
    undoes as one step, and every call in between - even if the active
    tab somehow changes mid-drag - keeps targeting that same controller
    rather than re-resolving a possibly different one. Tools themselves
    only ever call canvasController methods (selection, height, hollow/
    margin - see CanvasController), so that's what actually gets handed
    to onPress/onDrag/onRelease, not the ProjectController itself."""

    activeToolChanged = Signal(object)  # Tool

    def __init__(self, appController, parent=None):
        super().__init__(parent)
        self.appController = appController
        self.registry = ToolRegistry([WandTool(), BrushSelectTool()])
        self._gestureController = None

    def setActiveTool(self, name):
        self.registry.setActiveTool(name)
        self.activeToolChanged.emit(self.registry.activeTool)

    def press(self, pos):
        self._gestureController = self.appController.activeController
        if self._gestureController is not None:
            self._gestureController.beginGesture()
        self._dispatch("onPress", pos)

    def drag(self, pos):
        self._dispatch("onDrag", pos)

    def release(self, pos):
        self._dispatch("onRelease", pos)
        if self._gestureController is not None:
            self._gestureController.endGesture()
        self._gestureController = None

    def _dispatch(self, handlerName, pos):
        tool = self.registry.activeTool
        controller = self._gestureController or self.appController.activeController
        if tool is None or controller is None:
            return
        getattr(tool, handlerName)(controller.canvasController, pos)
