from ui import *
from data import *


class MeshElement(Element):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.position = Vector3(0, 0, 1)
        self.units = "mm"

    def travel(self, d):
        pass

    def render(self, state):
        pass

    def input(self, inputs):
        pass