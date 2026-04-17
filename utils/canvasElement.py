from .ui import *
from .data import *


class CanvasElement(Element):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.zoom = 1
        self.position = Vector2(0, 0)

    def render(self, state: State):
        pass