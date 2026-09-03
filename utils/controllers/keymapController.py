from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QKeySequence

from ..data.preferences import Preferences, COMMANDS


class KeymapController(QObject):
    """Owns the user's Preferences (persisted keybinds) and one QAction
    per known Command (see utils/data/preferences.py), kept in sync with
    them - the single source of truth for both "what shortcut fires
    this" and "what a menu shows next to this item's label", since a
    QAction covers both at once. A view (MenuBar, right now) just adds
    these actions directly rather than building its own parallel ones,
    so there's exactly one shortcut registration per command, not two
    competing for the same key press.

    Each action's handler resolves AppController.activeController at the
    moment it fires - the same pattern ToolController uses for tool
    presses - rather than binding to one fixed CanvasController, since
    which project a command should act on can change while the app is
    open (or be nothing at all, if no project is open, in which case the
    action is simply a no-op)."""

    keybindsChanged = Signal()

    # command id -> what it actually does, given a ProjectController.
    # Add an entry here (and to preferences.COMMANDS) to make a new
    # command bindable - this is deliberately the only place that maps a
    # command id to real behavior, so "what does this command do" always
    # has exactly one answer.
    _HANDLERS = {
        "selectAll": lambda controller: controller.canvasController.selectAll(),
        "deselectAll": lambda controller: controller.canvasController.deselectAll(),
        "invertSelection": lambda controller: controller.canvasController.invertSelection(),
    }

    def __init__(self, appController, preferences: Preferences = None, parent=None):
        super().__init__(parent)
        self._appController = appController
        self.preferences = preferences or Preferences.load()

        self.actions = {}
        for command in COMMANDS:
            action = QAction(command.label, self)
            action.triggered.connect(lambda checked=False, commandId=command.id: self._trigger(commandId))
            self.actions[command.id] = action
        self._applyShortcuts()

    def _applyShortcuts(self):
        for command in COMMANDS:
            self.actions[command.id].setShortcut(QKeySequence(self.preferences.keybind(command.id)))

    def _trigger(self, commandId):
        controller = self._appController.activeController
        handler = self._HANDLERS.get(commandId)
        if controller is not None and handler is not None:
            handler(controller)

    def setKeybind(self, commandId, sequence):
        """`sequence` is a Qt key-sequence string ("Ctrl+A"), or "" to
        leave the command unbound. Persists immediately - a rebind here
        isn't part of any project, so there's no separate "save" step
        for the user to remember. Raises KeybindConflictError (from
        Preferences.setKeybind), changing nothing, if `sequence` is
        already bound to a different command - it's the caller's job
        (SettingsWindow's KeybindRow, right now) to catch that and tell
        the user, e.g. by reverting whatever UI control they just edited."""
        self.preferences.setKeybind(commandId, sequence)
        self.preferences.save()
        self._applyShortcuts()
        self.keybindsChanged.emit()

    def resetKeybind(self, commandId):
        """Same conflict behavior as setKeybind (see Preferences.
        resetKeybind) - resetting to default can itself collide with
        another command's current binding."""
        self.preferences.resetKeybind(commandId)
        self.preferences.save()
        self._applyShortcuts()
        self.keybindsChanged.emit()
