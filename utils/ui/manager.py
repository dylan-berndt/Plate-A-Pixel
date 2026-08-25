from PySide6.QtWidgets import QMainWindow
from .elements import *


class Window(QMainWindow):
    def __init__(self, screenSize, root: QWidget, theme: Theme = None, caption: str = "Default Window"):
        super().__init__()

        self.setWindowTitle(caption)
        self.resize(*screenSize)

        self.theme = theme or Theme()
        self.setStyleSheet(self.theme.stylesheet())

        self.setCentralWidget(root)
