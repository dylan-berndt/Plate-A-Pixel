from .base import *


class Text(Element):
    def __init__(self, text, **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.font = None

    def render(self, state: State):
        theme = state.theme
        if self.font is None:
            self.font = pygame.font.SysFont(theme.fontFamily, theme.fontSize)

        surf = self.font.render(self.text, True, theme.text)
        r = state.rect
        x = r.x + (r.width  - surf.get_width())  // 2
        y = r.y + (r.height - surf.get_height()) // 2
        state.surface.blit(surf, (x, y))


@interactive
class TextInput(Element):
    def __init__(self, placeholder, **kwargs):
        super().__init__(**kwargs)

    def render(self, state: State):
        pass

    def input(self, inputs: Inputs, state: State) -> bool:
        pass


@interactive
class Slider(Element):
    def __init__(self, values: tuple, handleValue, defaultValue = None, **kwargs):
        super().__init__(**kwargs)
        self.sliding = False
        self.value = values[0] if defaultValue is None else defaultValue
        self.handleValue = handleValue
        self.values = values

    def input(self, inputs: Inputs, state: State):
        if self.istate.pressed:
            self.sliding = True

        # TODO: State management in Inputs
    
    def render(self, state: State):
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
        istate = self.istate
        r = state.rect

        if istate.disabled:
            bg = state.theme.disabled
        elif istate.pressed:
            bg = state.theme.pressed
        elif istate.hovered:
            bg = state.theme.hover
        else:
            bg = state.theme.surface
        
        pygame.draw.rect(state.surface, bg, r)

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