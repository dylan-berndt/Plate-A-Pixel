from base import *


class Text(Element):
    def __init__(self, text, **kwargs):
        super().__init__(**kwargs)

    def render(self, state: State):
        pass


@interactive
class TextInput(Element):
    def __init__(self, placeholder, **kwargs):
        super().__init__(**kwargs)

    def render(self, state: State):
        pass

    def input(self, inputs: Inputs, state: State):
        pass


class Image(Element):
    def __init__(self, surface: pygame.Surface, **kwargs):
        super().__init__(**kwargs)

    def render(self, state: State):
        pass


@interactive
class Button(Element):
    def __init__(self, onClick, **kwargs):
        super().__init__(**kwargs)

        self.onClick = onClick

    def render(self, state: State):
        pass

    def input(self, inputs, state: State):
        pass


@interactive
class Dropdown(Element):
    def __init__(self, options, **kwargs):
        super().__init__(**kwargs)

    def render(self, state):
        pass

    def input(self, inputs, state: State):
        pass


class Popup(Element):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def render(self, state: State):
        pass

    def input(self, inputs, state: State):
        pass