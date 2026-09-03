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
        self.path = path or DEFAULT_PREFERENCES_PATH
        self.keybinds = {command.id: command.default for command in COMMANDS}
        if keybinds:
            self.keybinds.update({k: v for k, v in keybinds.items() if k in _COMMANDS_BY_ID})

    def keybind(self, commandId):
        return self.keybinds.get(commandId, "")

    def setKeybind(self, commandId, sequence):
        """`sequence` is a Qt key-sequence string ("Ctrl+A"), or "" to
        leave the command unbound."""
        if commandId not in _COMMANDS_BY_ID:
            raise ValueError(f"Unknown command '{commandId}'")
        self.keybinds[commandId] = sequence

    def resetKeybind(self, commandId):
        command = _COMMANDS_BY_ID.get(commandId)
        if command is None:
            raise ValueError(f"Unknown command '{commandId}'")
        self.keybinds[commandId] = command.default

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
