from PySide6.QtOpenGLWidgets import QOpenGLWidget
from .ui import *
from .data import *


class MeshElement(QOpenGLWidget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.position = Vector3(0, 0, 1)
        self.units = "mm"

        self.mesh: Mesh = None

    def _calculateView(self):
        pass

    def travel(self, position, delta):
        pass

    # Qt's OpenGL widget calls initializeGL/resizeGL/paintGL on its own
    # render loop, replacing the manual render(state) call the pygame
    # Element tree used to make each frame.
    def initializeGL(self):
        pass

    def resizeGL(self, w, h):
        pass

    def paintGL(self):
        if self.mesh is None:
            return

    def mousePressEvent(self, event):
        pass
