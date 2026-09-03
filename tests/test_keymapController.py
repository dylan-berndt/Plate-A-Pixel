import pytest
from PIL import Image
from PySide6.QtGui import QKeySequence

from utils.controllers.appController import AppController
from utils.controllers.keymapController import KeymapController
from utils.data.preferences import Preferences, COMMANDS, KeybindConflictError
from .fixtures import make_pixel_art, RED_BLOCK, RED_ISLAND


@pytest.fixture
def prefsPath(tmp_path):
    return str(tmp_path / "preferences.json")


@pytest.fixture
def imagePath(tmp_path):
    path = tmp_path / "sprite.png"
    Image.fromarray(make_pixel_art()).save(path)
    return str(path)


@pytest.fixture
def app(imagePath):
    """An AppController with a KeymapController pointed at an isolated
    tmp_path preferences file - never the real default path, so this
    (like every other test here) can't touch a real user's saved
    keybinds."""
    appController = AppController()
    appController.newProjectFromImage(imagePath)
    return appController


@pytest.fixture
def isolatedKeymap(app, prefsPath):
    keymap = KeymapController(app, preferences=Preferences(path=prefsPath))
    app.keymapController = keymap
    return keymap


def test_builds_one_action_per_known_command(isolatedKeymap):
    assert set(isolatedKeymap.actions.keys()) == {c.id for c in COMMANDS}


def test_actions_start_shortcut_at_each_commands_default(isolatedKeymap):
    for command in COMMANDS:
        assert isolatedKeymap.actions[command.id].shortcut() == QKeySequence(command.default)


def test_set_keybind_updates_the_actions_shortcut(isolatedKeymap):
    isolatedKeymap.setKeybind("selectAll", "Ctrl+Shift+A")

    assert isolatedKeymap.actions["selectAll"].shortcut() == QKeySequence("Ctrl+Shift+A")


def test_set_keybind_persists_to_the_preferences_path(isolatedKeymap, prefsPath):
    isolatedKeymap.setKeybind("selectAll", "Ctrl+Shift+A")

    reloaded = Preferences.load(prefsPath)
    assert reloaded.keybind("selectAll") == "Ctrl+Shift+A"


def test_set_keybind_emits_keybinds_changed(isolatedKeymap):
    calls = []
    isolatedKeymap.keybindsChanged.connect(lambda: calls.append(True))

    isolatedKeymap.setKeybind("selectAll", "Ctrl+Shift+A")

    assert len(calls) == 1


def test_reset_keybind_restores_the_default_shortcut(isolatedKeymap):
    isolatedKeymap.setKeybind("invertSelection", "Ctrl+Shift+I")

    isolatedKeymap.resetKeybind("invertSelection")

    assert isolatedKeymap.actions["invertSelection"].shortcut() == QKeySequence("Ctrl+I")


def test_triggering_select_all_action_selects_the_active_project(app, isolatedKeymap):
    isolatedKeymap.actions["selectAll"].trigger()

    assert app.activeController.project.canvas.selection.all()


def test_triggering_deselect_all_action_clears_the_active_project(app, isolatedKeymap):
    app.activeController.project.canvas.selectAll()

    isolatedKeymap.actions["deselectAll"].trigger()

    assert not app.activeController.project.canvas.selection.any()


def test_triggering_invert_selection_action_flips_the_active_project(app, isolatedKeymap):
    app.activeController.project.canvas.bucketSelect((0, 0), contiguous=True, mode="replace")
    before = app.activeController.project.canvas.selection.copy()

    isolatedKeymap.actions["invertSelection"].trigger()

    assert (app.activeController.project.canvas.selection == ~before).all()


def test_triggering_with_no_active_project_is_a_no_op():
    appController = AppController()
    keymap = KeymapController(appController)

    keymap.actions["selectAll"].trigger()  # should not raise


def test_set_keybind_rejects_a_conflict_and_leaves_the_actions_shortcut_alone(isolatedKeymap):
    with pytest.raises(KeybindConflictError):
        isolatedKeymap.setKeybind("selectAll", "Ctrl+D")

    assert isolatedKeymap.actions["selectAll"].shortcut() == QKeySequence("Ctrl+A")
    assert isolatedKeymap.actions["deselectAll"].shortcut() == QKeySequence("Ctrl+D")


def test_set_keybind_conflict_does_not_persist_or_emit(isolatedKeymap, prefsPath):
    # A real, successful rebind first, so the file on disk has known
    # content the failed attempt below must not have touched.
    isolatedKeymap.setKeybind("invertSelection", "Ctrl+Shift+I")
    calls = []
    isolatedKeymap.keybindsChanged.connect(lambda: calls.append(True))

    with pytest.raises(KeybindConflictError):
        isolatedKeymap.setKeybind("selectAll", "Ctrl+D")

    assert len(calls) == 0
    reloaded = Preferences.load(prefsPath)
    assert reloaded.keybind("selectAll") == "Ctrl+A"
    assert reloaded.keybind("invertSelection") == "Ctrl+Shift+I"  # the real edit, untouched
