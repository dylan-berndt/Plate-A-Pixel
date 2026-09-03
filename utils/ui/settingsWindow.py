from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QKeySequenceEdit, QPushButton,
)
from PySide6.QtGui import QKeySequence

from .base import Theme
from .elements import SectionLabel
from ..data.preferences import COMMANDS


class KeybindRow(QWidget):
    """One Command's row in the Keybinds tab: its label, a QKeySequenceEdit
    for capturing a new shortcut, and a Reset button back to that
    command's own default. Capped to a single chord (setMaximumSequenceLength)
    - Qt supports multi-step "Ctrl+K, Ctrl+S"-style sequences, but nothing
    in this app uses one and every default here is already a single
    chord, so allowing more would just make it easy to record a sequence
    by accident.

    Doesn't check for conflicts with another command's binding - a
    plausible follow-up, not attempted here (this is a first sketch of
    the keybind system, not the final word on it)."""

    def __init__(self, command, keymapController, theme: Theme = None, **kwargs):
        super().__init__(**kwargs)
        theme = theme or Theme()
        self._command = command
        self._keymapController = keymapController

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)

        label = SectionLabel(command.label, theme=theme)
        layout.addWidget(label, 1)

        self._edit = QKeySequenceEdit(QKeySequence(keymapController.preferences.keybind(command.id)))
        self._edit.setMaximumSequenceLength(1)
        self._edit.setClearButtonEnabled(True)  # lets a user unbind a command entirely
        self._edit.setFixedWidth(140)
        self._edit.editingFinished.connect(self._onEdited)
        layout.addWidget(self._edit)

        resetButton = QPushButton("Reset")
        resetButton.clicked.connect(self._onReset)
        layout.addWidget(resetButton)

    def _onEdited(self):
        self._keymapController.setKeybind(self._command.id, self._edit.keySequence().toString())

    def _onReset(self):
        self._keymapController.resetKeybind(self._command.id)
        self._edit.setKeySequence(QKeySequence(self._keymapController.preferences.keybind(self._command.id)))


class KeybindsTab(QWidget):
    """Lists every known Command (see utils/data/preferences.py) with an
    editable shortcut - the only settings tab that exists right now (see
    SettingsWindow); a future settings category is just another tab
    added there, not a change to this class."""

    def __init__(self, keymapController, theme: Theme = None, **kwargs):
        super().__init__(**kwargs)
        theme = theme or Theme()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)
        for command in COMMANDS:
            layout.addWidget(KeybindRow(command, keymapController, theme=theme))
        layout.addStretch(1)


class SettingsWindow(QDialog):
    """The Settings window: a QTabWidget so a future settings category is
    just another addTab() call, not a restructure - Keybinds is the only
    tab that exists yet. Modeless-friendly (plain QDialog, not exec()'d
    by the caller) since every edit here commits immediately through
    KeymapController rather than needing an explicit Save/Cancel."""

    def __init__(self, keymapController, theme: Theme = None, **kwargs):
        super().__init__(**kwargs)
        theme = theme or Theme()
        self.setWindowTitle("Settings")
        self.resize(420, 320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        tabs = QTabWidget()
        tabs.addTab(KeybindsTab(keymapController, theme=theme), "Keybinds")
        layout.addWidget(tabs, 1)

        closeRow = QHBoxLayout()
        closeRow.setContentsMargins(12, 8, 12, 12)
        closeRow.addStretch(1)
        closeButton = QPushButton("Close")
        closeButton.clicked.connect(self.accept)
        closeRow.addWidget(closeButton)
        layout.addLayout(closeRow)
