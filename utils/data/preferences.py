import json
import os
from dataclasses import dataclass
from pathlib import Path

# Bumped whenever the saved shape changes in a way Preferences.load needs
# to branch on - same convention as Project's own FORMAT_VERSION.
FORMAT_VERSION = 1

DEFAULT_PREFERENCES_PATH = str(Path.home() / ".plate_a_pixel" / "preferences.json")


@dataclass
class Command:
    """One user-triggerable action the keybind system can bind a shortcut
    to. `default` is a Qt key-sequence string ("Ctrl+D"), kept as a plain
    string rather than QKeySequence since this is domain layer (no Qt
    imports at all, same rule as the rest of utils/data/) - the
    controller layer (KeymapController) is what turns it into an actual
    QAction/QKeySequence."""

    id: str
    label: str
    default: str


# Every command the keybind system currently knows about - add an entry
# here to make a new action bindable; KeymapController
# (utils/controllers/keymapController.py) is where its id gets wired to
# an actual handler.
COMMANDS = [
    Command("selectAll", "Select All", "Ctrl+A"),
    Command("deselectAll", "Deselect All", "Ctrl+D"),
    Command("invertSelection", "Invert Selection", "Ctrl+I"),
]

_COMMANDS_BY_ID = {command.id: command for command in COMMANDS}


class KeybindConflictError(ValueError):
    """Raised by Preferences.setKeybind/resetKeybind when `sequence` is
    already bound to a different command - Preferences enforces that two
    commands can never share a shortcut itself, rather than leaving that
    up to whichever caller happens to invoke setKeybind (KeymapController,
    a test, or anything else)."""

    def __init__(self, commandId, conflictingCommandId, conflictingLabel, sequence):
        self.commandId = commandId
        self.conflictingCommandId = conflictingCommandId
        self.conflictingLabel = conflictingLabel
        self.sequence = sequence
        super().__init__(f"'{sequence}' is already bound to '{conflictingLabel}'")


class Preferences:
    """User-level settings, round-tripped to a single small JSON file
    outside any project (see DEFAULT_PREFERENCES_PATH) - right now just
    keybinds (command id -> key sequence string), but this is the one
    file a future non-keybind preference would also live in, the same
    way ViewSettings is the one place per-project settings live.

    `keybinds` always has an entry for every command in COMMANDS,
    backfilled from that command's own default for anything a saved
    file predates or never had - so a new command added in a later
    version doesn't need a migration, and a caller never has to fall
    back to COMMANDS itself just to find a binding.

    Remembers the path it was loaded from (`path`) so a later save()
    with no argument writes back to that same file rather than always
    the global default - both the more obviously correct behavior for a
    caller that loaded from somewhere specific, and what lets tests use
    an isolated tmp_path file without ever touching a real user's
    preferences on disk."""

    def __init__(self, keybinds: dict = None, path: str = None):
        # Not conflict-checked here (unlike setKeybind/resetKeybind below) -
        # every COMMANDS default is already distinct, so a bare
        # Preferences() can't start in a conflicting state, and a saved
        # file loaded with a genuine conflict (hand-edited, or written by
        # some future version with different defaults) shouldn't fail to
        # even open the app; going forward, setKeybind is what actually
        # enforces "two commands can't share a shortcut".
        self.path = path or DEFAULT_PREFERENCES_PATH
        self.keybinds = {command.id: command.default for command in COMMANDS}
        if keybinds:
            self.keybinds.update({k: v for k, v in keybinds.items() if k in _COMMANDS_BY_ID})

    def keybind(self, commandId):
        return self.keybinds.get(commandId, "")

    def conflictingCommand(self, commandId, sequence):
        """The id of whichever *other* command is already bound to
        `sequence`, or None. An empty `sequence` (unbound) never
        conflicts - any number of commands can all be unbound at once."""
        if not sequence:
            return None
        for otherId, otherSequence in self.keybinds.items():
            if otherId != commandId and otherSequence == sequence:
                return otherId
        return None

    def setKeybind(self, commandId, sequence):
        """`sequence` is a Qt key-sequence string ("Ctrl+A"), or "" to
        leave the command unbound. Raises KeybindConflictError, changing
        nothing, if `sequence` is already bound to a different command -
        two commands can never share a shortcut."""
        if commandId not in _COMMANDS_BY_ID:
            raise ValueError(f"Unknown command '{commandId}'")
        conflict = self.conflictingCommand(commandId, sequence)
        if conflict is not None:
            raise KeybindConflictError(commandId, conflict, _COMMANDS_BY_ID[conflict].label, sequence)
        self.keybinds[commandId] = sequence

    def resetKeybind(self, commandId):
        """Routed through setKeybind (not a direct dict write) so
        resetting still enforces the same no-conflict invariant: another
        command could have been rebound to *this* command's default
        while it was pointed elsewhere, in which case resetting back to
        default would collide with it."""
        command = _COMMANDS_BY_ID.get(commandId)
        if command is None:
            raise ValueError(f"Unknown command '{commandId}'")
        self.setKeybind(commandId, command.default)

    def to_dict(self):
        return {"formatVersion": FORMAT_VERSION, "keybinds": self.keybinds}

    @staticmethod
    def from_dict(d, path: str = None):
        return Preferences(keybinds=d.get("keybinds", {}), path=path)

    @staticmethod
    def load(path: str = None):
        """Missing file (first run, or a fresh install) is not an error -
        just the all-defaults Preferences() a bare constructor already
        gives, remembering `path` all the same so a later save() still
        lands in the right place."""
        path = path or DEFAULT_PREFERENCES_PATH
        if not os.path.exists(path):
            return Preferences(path=path)
        with open(path) as f:
            data = json.load(f)
        return Preferences.from_dict(data, path=path)

    def save(self, path: str = None):
        path = path or self.path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
