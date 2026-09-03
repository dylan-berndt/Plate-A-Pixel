import pytest

from utils.data.preferences import Preferences, COMMANDS, KeybindConflictError


@pytest.fixture
def prefsPath(tmp_path):
    return str(tmp_path / "preferences.json")


def test_fresh_preferences_default_every_known_command():
    prefs = Preferences()

    for command in COMMANDS:
        assert prefs.keybind(command.id) == command.default


def test_set_keybind_overrides_just_that_command():
    prefs = Preferences()
    other = [c for c in COMMANDS if c.id != "selectAll"][0]

    prefs.setKeybind("selectAll", "Ctrl+Shift+A")

    assert prefs.keybind("selectAll") == "Ctrl+Shift+A"
    assert prefs.keybind(other.id) == other.default


def test_set_keybind_rejects_an_unknown_command():
    prefs = Preferences()
    with pytest.raises(ValueError):
        prefs.setKeybind("nonexistent", "Ctrl+X")


def test_reset_keybind_restores_the_default():
    prefs = Preferences()
    prefs.setKeybind("invertSelection", "Ctrl+Shift+I")

    prefs.resetKeybind("invertSelection")

    assert prefs.keybind("invertSelection") == "Ctrl+I"


def test_save_then_load_round_trips_a_rebind(prefsPath):
    prefs = Preferences(path=prefsPath)
    prefs.setKeybind("deselectAll", "Ctrl+Shift+D")
    prefs.save()

    reloaded = Preferences.load(prefsPath)

    assert reloaded.keybind("deselectAll") == "Ctrl+Shift+D"
    assert reloaded.keybind("selectAll") == "Ctrl+A"  # untouched command still defaults


def test_load_missing_file_returns_defaults_without_creating_it(prefsPath):
    prefs = Preferences.load(prefsPath)

    for command in COMMANDS:
        assert prefs.keybind(command.id) == command.default
    import os
    assert not os.path.exists(prefsPath)


def test_save_with_no_path_writes_back_to_where_it_was_loaded_from(prefsPath):
    Preferences(path=prefsPath).save()  # seed a file with all defaults
    prefs = Preferences.load(prefsPath)

    prefs.setKeybind("selectAll", "Ctrl+Shift+A")
    prefs.save()  # no explicit path - must still land in prefsPath

    reloaded = Preferences.load(prefsPath)
    assert reloaded.keybind("selectAll") == "Ctrl+Shift+A"


def test_load_backfills_a_command_missing_from_an_older_saved_file(prefsPath):
    import json
    with open(prefsPath, "w") as f:
        json.dump({"formatVersion": 1, "keybinds": {"selectAll": "Ctrl+Shift+A"}}, f)

    prefs = Preferences.load(prefsPath)

    assert prefs.keybind("selectAll") == "Ctrl+Shift+A"
    assert prefs.keybind("deselectAll") == "Ctrl+D"  # backfilled from default
    assert prefs.keybind("invertSelection") == "Ctrl+I"


# -- conflict checking -----------------------------------------------------

def test_conflicting_command_is_none_when_nothing_uses_that_sequence():
    prefs = Preferences()
    assert prefs.conflictingCommand("selectAll", "Ctrl+Shift+Z") is None


def test_conflicting_command_finds_the_other_command_holding_it():
    prefs = Preferences()
    assert prefs.conflictingCommand("selectAll", "Ctrl+D") == "deselectAll"


def test_conflicting_command_ignores_the_commands_own_current_binding():
    prefs = Preferences()
    # selectAll is already "Ctrl+A" - re-setting it to the same sequence
    # must not read as a conflict with itself.
    assert prefs.conflictingCommand("selectAll", "Ctrl+A") is None


def test_conflicting_command_never_flags_an_empty_sequence():
    prefs = Preferences()
    prefs.setKeybind("deselectAll", "")
    assert prefs.conflictingCommand("invertSelection", "") is None


def test_set_keybind_rejects_a_sequence_already_bound_elsewhere():
    prefs = Preferences()
    with pytest.raises(KeybindConflictError) as excInfo:
        prefs.setKeybind("selectAll", "Ctrl+D")

    error = excInfo.value
    assert error.commandId == "selectAll"
    assert error.conflictingCommandId == "deselectAll"
    assert error.conflictingLabel == "Deselect All"
    assert error.sequence == "Ctrl+D"


def test_set_keybind_conflict_leaves_both_bindings_unchanged():
    prefs = Preferences()
    with pytest.raises(KeybindConflictError):
        prefs.setKeybind("selectAll", "Ctrl+D")

    assert prefs.keybind("selectAll") == "Ctrl+A"
    assert prefs.keybind("deselectAll") == "Ctrl+D"


def test_set_keybind_to_an_empty_sequence_never_conflicts_even_when_another_command_is_also_unbound():
    prefs = Preferences()
    prefs.setKeybind("selectAll", "")

    prefs.setKeybind("deselectAll", "")  # must not raise

    assert prefs.keybind("selectAll") == ""
    assert prefs.keybind("deselectAll") == ""


def test_reset_keybind_rejects_a_default_that_collides_with_another_commands_current_binding():
    prefs = Preferences()
    # Free up selectAll's default by moving it elsewhere, then let
    # deselectAll claim it - resetting selectAll back to "Ctrl+A" must
    # now collide with deselectAll.
    prefs.setKeybind("selectAll", "Ctrl+Shift+A")
    prefs.setKeybind("deselectAll", "Ctrl+A")

    with pytest.raises(KeybindConflictError) as excInfo:
        prefs.resetKeybind("selectAll")

    assert excInfo.value.conflictingCommandId == "deselectAll"
    assert prefs.keybind("selectAll") == "Ctrl+Shift+A"  # unchanged
