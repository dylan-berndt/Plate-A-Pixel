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

    def __getattribute__(self, name):
        pass

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
    def __init__(self, screen: pygame.Surface, theme: Theme, rect: pygame.Rect, dt: float = 0.0):
        self.screen = screen
        self.theme = theme
        self.rect = rect
        self.dt = dt

    def withRect(self, rect: pygame.Rect):
        s = copy(self)
        s.rect = rect
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

    def calculateRect(self, state: State):
        pass

    def add(self, element):
        pass

    def render(self, state: State):
        raise NotImplementedError(f"{type(self)} has not implemented render()")
    
    def input(self, inputs, state: State):
        pass


class Grid(Element):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def render(self, state: State):
        pass

    def input(self, inputs, state: State):
        pass