import pygame
from .elements import *


class Window:
    def __init__(self, screenSize, root: Element, theme: Theme = None):
        pygame.init()
        self.screen = pygame.display.set_mode(screenSize)

        self.root = root
        self.theme = theme or Theme()

        self._popupStack: list[Popup] = []
        self._state: State = None

        self._clock = pygame.time.Clock()

    def update(self):
        dt = self._clock.tick(120) / 1000.0

        texture = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        self._state = State(
            texture, self.theme, self.screen.get_rect(), dt
        )

        events = pygame.event.get()
        for e in events:
            if e.type == pygame.QUIT:
                pygame.quit(); return
            
        inputs = Inputs(events)

        self.root._input(inputs, self._state)
            
        self.render()

    def render(self):
        self.screen.fill(self.theme.background)
        self.root._render(self._state)
        self.screen.blit(self._state.surface, (0, 0))
        pygame.display.flip()