from PySide6.QtWidgets import (
    QLabel, QLineEdit, QSlider, QPushButton, QComboBox, QDialog, QWidget, QGridLayout
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from .base import *


class Text(QLabel):
    def __init__(self, text, **kwargs):
        super().__init__(text, **kwargs)
        self.setAlignment(Qt.AlignCenter)


class TextInput(QLineEdit):
    def __init__(self, placeholder="", **kwargs):
        super().__init__(**kwargs)
        self.setPlaceholderText(placeholder)


class Slider(QSlider):
    def __init__(self, values: tuple, handleValue, defaultValue=None, **kwargs):
        super().__init__(Qt.Horizontal, **kwargs)
        self.setMinimum(values[0])
        self.setMaximum(values[1])
        self.setValue(values[0] if defaultValue is None else defaultValue)

        self.handleValue = handleValue
        self.valueChanged.connect(self.handleValue)


class Image(QLabel):
    def __init__(self, pixmap: QPixmap, **kwargs):
        super().__init__(**kwargs)
        self.setPixmap(pixmap)


class Button(QPushButton):
    def __init__(self, onClick, **kwargs):
        super().__init__(**kwargs)

        self.onClick = onClick
        self.clicked.connect(self.onClick)

    # Kept to mirror the old Button(...).add(Text(...)) call pattern from
    # main.py; a QPushButton just takes its label as text directly.
    def add(self, element: QLabel):
        self.setText(element.text())
        return self


class Dropdown(QComboBox):
    def __init__(self, options: dict, **kwargs):
        super().__init__(**kwargs)
        for label, value in options.items():
            self.addItem(label, value)


class Popup(QDialog):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class Grid(QWidget):
    def __init__(self, margins=(0, 0, 0, 0), **kwargs):
        super().__init__(**kwargs)

        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(*margins)

    def add(self, element: QWidget, position, size):
        self._layout.addWidget(element, position[1], position[0], size[1], size[0])
        return self
