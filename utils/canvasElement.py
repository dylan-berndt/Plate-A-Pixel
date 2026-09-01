from PySide6.QtWidgets import QWidget
from .ui import *
from .data import *


class CanvasArea(QWidget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # TODO: Create grid and buttons, and artist. Tool state lives in
        # AppController.toolController (see controllers/toolController.py) -
        # this widget's job is to turn a mouse event into a canvas position
        # and call toolController.press/drag/release with it.

    def mousePressEvent(self, event):
        # TODO: Alter state to influence CanvasArtist
        pass

    def paintEvent(self, event):
        pass


class CanvasArtist(QWidget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Zoom represents percentage of canvas area taken up by longest side of image
        self.zoom = 1
        self.position = Vector2(0, 0)

    def mousePressEvent(self, event):
        pass

    def _mouseToCanvas(self, position: Vector2):
        pass
