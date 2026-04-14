from base import *


class Text(Element):
    def __init__(self, text, **kwargs):
        super().__init__(**kwargs)

    def render(self, state):
        pass


class Button(Element):
    def __init__(self, onClick, **kwargs):
        super().__init__(**kwargs)

        self.onClick = onClick

    def render(self, state):
        pass

    def input(self, inputs):
        pass


class Dropdown(Element):
    def __init__(self, options, **kwargs):
        super().__init__(**kwargs)

    def render(self, state):
        pass


class Popup(Element):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def render(self, state):
        pass

    def input(self, inputs):
        pass