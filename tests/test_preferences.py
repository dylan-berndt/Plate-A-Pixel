import pytest

from utils.data.preferences import Preferences, COMMANDS


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
