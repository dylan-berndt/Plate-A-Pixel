from .ui import *
from .data import *


class MeshElement(Element):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.position = Vector3(0, 0, 1)
        self.units = "mm"

        self.mesh: Mesh = None

    def _calculateView(self):
        pass

    def travel(self, position, delta):
        pass

    def render(self, state: State):
        if self.mesh is None:
            return

    def input(self, inputs, state: State):
        pass