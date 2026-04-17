from .base import *


class Text(Element):
    def __init__(self, text, **kwargs):
        super().__init__(**kwargs)
        self.text = text

    def render(self, state: State):
        pass


@interactive
class TextInput(Element):
    def __init__(self, placeholder, **kwargs):
        super().__init__(**kwargs)

    def render(self, state: State):
        pass

    def input(self, inputs: Inputs, state: State) -> bool:
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

    def input(self, inputs: Inputs, state: State) -> bool:
        inside = state.rect.collidepoint(*inputs.mousePos)
        clicked = inside and inputs.click
        if clicked:
            self.onClick()
        return clicked


@interactive
class Dropdown(Element):
    def __init__(self, options, **kwargs):
        super().__init__(**kwargs)

    def render(self, state):
        pass

    def input(self, inputs, state: State) -> bool:
        pass


class Popup(Element):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def render(self, state: State):
        pass

    def input(self, inputs, state: State) -> bool:
        pass