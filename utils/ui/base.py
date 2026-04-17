import pygame
from dataclasses import dataclass, field
from copy import copy


class Theme:
    def __init__(self, **kwargs):
        self.background = (30, 30, 30)
        self.surface = (45, 45, 45)
        self.hover = (60, 60, 60)
        self.pressed = (25, 25, 25)
        self.disabled = (38, 38, 38)

        self.text = (220, 220, 220)

        self.fontFamily = "Arial"
        self.fontSize = 16

        self.overlay = (0, 0, 0, 140)

        self.unit = None

        for k, v in kwargs.items():
            setattr(self, k, v)

    @property
    def font(self):
        pass

    def override(self, **kwargs):
        t = copy(self)
        for k, v in kwargs.items():
            setattr(t, k, v)
        return t


class Padding:
    def __init__(self, left=0, right=0, bottom=0, top=0):
        self.left = left
        self.right = right
        self.bottom = bottom
        self.top = top


class Margin:
    def __init__(self, left=0, right=0, bottom=0, top=0):
        self.left = left
        self.right = right
        self.bottom = bottom
        self.top = top


@dataclass
class InteractiveState:
    hovered: bool = False
    pressed: bool = False
    focused: bool = False
    disabled: bool = False


def interactive(cls):
    # Original input function of the class
    originalInput = cls.input if hasattr(cls, "input") else lambda self, inp, state: None

    # Handle hovering, pressing, etc. before using element's input functions
    def _input(self, inputs: Inputs, state: State):
        if self.istate.disabled:
            return
        
        hit = state.rect.collidepoint(inputs.mousePos)
        self.istate.hovered = hit

        if hit and inputs.click:
            self.istate.pressed = True
            self.istate.focused = True
        elif inputs.release:
            self.istate.pressed = False
        elif inputs.click and not hit:
            self.istate.focused = False

        originalInput(self, inputs, state)

    originalInit = cls.__init__

    # Add interactive state to element for tracking
    def _init(self, *args, disabled: bool=False, **kwargs):
        originalInit(self, *args, **kwargs)
        self.istate = InteractiveState(disabled=disabled)

    cls.__init__ = _init
    cls.input = _input

    return cls


# TODO: Track hold time for keys and mouse?
class Inputs:
    def __init__(self, events: list[pygame.event.Event]):
        self.events = events
        self.mousePos = pygame.mouse.get_pos()
        self.mouseButtons = pygame.mouse.get_pressed()

    @property
    def click(self):
        return any(e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 for e in self.events)
    
    @property
    def release(self):
        return any(e.type == pygame.MOUSEBUTTONUP and e.button == 1 for e in self.events)
    
    def keyDown(self, key):
        return any(e.type == pygame.KEYDOWN and e.key == key for e in self.events)
    

class State:
    def __init__(self, surface: pygame.Surface, theme: Theme, rect: pygame.Rect, dt: float = 0.0):
        self.surface = surface
        self.theme = theme
        self.rect = rect
        self.dt = dt

    def withRect(self, rect: pygame.Rect):
        s = copy(self)
        s.rect = rect
        return s
    
    def shrinkRect(self, box: Padding | Margin):
        s = copy(self)
        s.rect = pygame.Rect(
            s.rect.x + box.left,
            s.rect.y + box.top,
            s.rect.width  - box.left - box.right,
            s.rect.height - box.top  - box.bottom,
        )
        return s
    
    def updateTheme(self, **kwargs):
        t = self.theme.override(**kwargs)
        s = copy(self)
        s.theme = t
        return s


class Element:
    def __init__(self, padding=Padding(), margin=Margin(), **kwargs):
        self.padding = padding
        self.margin = margin
        self.themeOverrides = kwargs
        self.children: list[Element] = []

    def add(self, element):
        self.children.append(element)
        return self

    # Handles drawing of the Element itself within the rect defined by state
    def render(self, state: State):
        pass

    # Handles rect transformations and queues rendering of children
    def _render(self, state: State):
        state = state.updateTheme(**self.themeOverrides).shrinkRect(self.padding)

        self.render(state)

        for child in self.children:
            child._render(state.shrinkRect(self.margin))
    
    # Handles input for this Element, returns True when this element blocks input
    def input(self, inputs, state: State) -> bool:
        pass

    def _input(self, inputs: Inputs, state: State) -> bool:
        state = state.updateTheme(**self.themeOverrides).shrinkRect(self.padding)

        self.input(inputs, state)

        for child in self.children:
            child._input(inputs, state.shrinkRect(self.margin))


class GridElement(Element):
    def __init__(self, child, position, size, **kwargs):
        super().__init__(**kwargs)

        self.position = position
        self.size = size
        self.children = [child]


class Grid(Element):
    def __init__(self, gridPadding: Padding, **kwargs):
        super().__init__(**kwargs)

        self.gridPadding = gridPadding
        self.rows = 0
        self.columns = 0

    def calculateLayout(self):
        for child in self.children:
            self.rows = max(self.rows, child.position[1] + child.size[1])
            self.columns = max(self.rows, child.position[0] + child.size[0])

    def gridRect(self, state: State, element: GridElement):
        cellWidth = state.rect.width / self.columns
        elementWidth = int(cellWidth * element.size[0])

        cellHeight = state.rect.height / self.rows
        elementHeight = int(cellHeight * element.size[1])
        rect = pygame.Rect(
            state.rect.x + int(cellWidth * element.position[0]),
            state.rect.y + int(cellHeight * element.position[1]),
            elementWidth,
            elementHeight,
        )
        return state.withRect(rect)

    def add(self, element: GridElement):
        element.padding = self.gridPadding
        self.children.append(element)
        self.calculateLayout()
        return self
    
    def add(self, element: Element, position, size):
        self.children.append(GridElement(element, position, size, padding=self.gridPadding))
        self.calculateLayout()
        return self

    def render(self, state: State):
        pass

    def _render(self, state: State):
        state = state.updateTheme(**self.themeOverrides).shrinkRect(self.padding)

        for child in self.children:
            child._render(self.gridRect(state.shrinkRect(self.margin), child))

    def input(self, inputs, state: State) -> bool:
        pass

    def _input(self, inputs: Inputs, state: State) -> bool:
        state = state.updateTheme(**self.themeOverrides).shrinkRect(self.padding)

        self.input(inputs, state)

        for child in self.children:
            child._input(inputs, self.gridRect(state.shrinkRect(self.margin), child))