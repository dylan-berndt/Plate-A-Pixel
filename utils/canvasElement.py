from .ui import *
from .data import *


@dataclass
class Options:
    name: str
    optionType: str
    options: dict


@dataclass
class Tool:
    name: str
    options: dict[Options]
    selections: dict


class CanvasArea(Element):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.wand = Tool("wand", 
                           {"mode": 
                            Options("Selection Mode", "dropdown", 
                                    {"Addition": "add", "Subtraction": "subtract", "Replacement": "replace", "Intersection": "intersect"}),
                            "diagonal": 
                            Options("Use Diagonals", "dropdown",
                                    {"True": True, "False": False})}, 
                           {"mode": "add", "diagonal": True})
        
        self.tools = [self.wand]

        self.tool = self.wand

        # TODO: Create grid and buttons, tools, and artist

    def input(self, inputs: Inputs, state: State):
        # TODO: Alter state to influence CanvasArtist
        pass

    def render(self, state: State):
        pass


class CanvasArtist(Element):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Zoom represents percentage of canvas area taken up by longest side of image
        self.zoom = 1
        self.position = Vector2(0, 0)

    def _mouseToCanvas(self, position: Vector2, state: State):
        pass