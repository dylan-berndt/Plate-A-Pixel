import pygame


class Inputs:
    def __init__(self):
        pass


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


class Element:
    def __init__(self, padding=Padding(), margin=Margin()):
        self.padding = padding
        self.margin = margin

    def calculateRect(self, state):
        pass

    def render(self, state):
        raise NotImplementedError(f"This Element has not implemented rendering: {type(self)}")
    
    def input(self, inputs):
        pass


class Grid(Element):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def render(self, state):
        pass

    def add(self, element: Element):
        pass

    def input(self, inputs):
        pass