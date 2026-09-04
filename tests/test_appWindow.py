from unittest.mock import patch

import pytest
from PIL import Image
from PySide6.QtWidgets import QMessageBox

from utils.controllers.appController import AppController
from utils.ui.appWindow import AppWindow
from .fixtures import make_pixel_art


@pytest.fixture
def imagePath(tmp_path):
    path = tmp_path / "sprite.png"
    Image.fromarray(make_pixel_art()).save(path)
    return str(path)


@pytest.fixture
def appController(imagePath):
    app = AppController()
    app.newProjectFromImage(imagePath)
    return app


@pytest.fixture
def window(appController):
    # No setCanvasArea/setLayerCanvasArea/setMeshElement - _closeTab/
    # closeEvent/the confirmation flow never touch those (each use is
    # guarded with an `is not None` check for exactly this reason - see
    # _onActiveProjectChanged), so a bare AppWindow is enough here.
    return AppWindow(appController)


def _dirty(controller):
    with controller.editing(signal=controller.selectionChanged):
        controller.project.canvas.brushSelect((0, 0), radius=0, mode="add")


# -- _closeTab / _confirmDiscardingChanges --------------------------------

def test_close_tab_with_no_unsaved_changes_closes_immediately_without_a_dialog(window, appController):
    with patch.object(QMessageBox, "exec") as execMock:
        window._closeTab(0)

    execMock.assert_not_called()
    assert len(appController.projectControllers) == 0


def test_close_tab_discard_closes_without_saving(window, appController, tmp_path):
    _dirty(appController.activeController)

    with patch.object(QMessageBox, "exec", return_value=QMessageBox.Discard):
        window._closeTab(0)

    assert len(appController.projectControllers) == 0


def test_close_tab_cancel_leaves_the_project_open(window, appController):
    _dirty(appController.activeController)

    with patch.object(QMessageBox, "exec", return_value=QMessageBox.Cancel):
        window._closeTab(0)

    assert len(appController.projectControllers) == 1


def test_close_tab_save_writes_to_the_existing_path_then_closes(window, appController, tmp_path):
    controller = appController.activeController
    controller.save(str(tmp_path / "existing.pap"))
    _dirty(controller)

    with patch.object(QMessageBox, "exec", return_value=QMessageBox.Save):
        window._closeTab(0)

    assert len(appController.projectControllers) == 0


def test_close_tab_save_with_no_prior_path_prompts_and_closes(window, appController, tmp_path):
    _dirty(appController.activeController)
    savePath = str(tmp_path / "new_project.pap")

    with patch.object(QMessageBox, "exec", return_value=QMessageBox.Save), \
         patch("utils.ui.appWindow.QFileDialog.getSaveFileName", return_value=(savePath, "")):
        window._closeTab(0)

    assert len(appController.projectControllers) == 0


def test_close_tab_save_cancelled_at_the_file_dialog_leaves_the_project_open(window, appController):
    _dirty(appController.activeController)

    with patch.object(QMessageBox, "exec", return_value=QMessageBox.Save), \
         patch("utils.ui.appWindow.QFileDialog.getSaveFileName", return_value=("", "")):
        window._closeTab(0)

    assert len(appController.projectControllers) == 1


def test_close_active_tab_from_menu_goes_through_the_same_confirmation(window, appController):
    _dirty(appController.activeController)

    with patch.object(QMessageBox, "exec", return_value=QMessageBox.Cancel) as execMock:
        window._closeActiveTabFromMenu()

    execMock.assert_called_once()
    assert len(appController.projectControllers) == 1


# -- closeEvent -------------------------------------------------------------

class _FakeCloseEvent:
    def __init__(self):
        self.accepted = None

    def accept(self):
        self.accepted = True

    def ignore(self):
        self.accepted = False


def test_close_event_with_nothing_dirty_accepts_without_a_dialog(window):
    event = _FakeCloseEvent()

    with patch.object(QMessageBox, "exec") as execMock:
        window.closeEvent(event)

    execMock.assert_not_called()
    assert event.accepted is True


def test_close_event_cancelling_any_dirty_project_ignores_the_close(window, appController, imagePath):
    _dirty(appController.activeController)
    appController.newProjectFromImage(imagePath)
    _dirty(appController.activeController)
    event = _FakeCloseEvent()

    with patch.object(QMessageBox, "exec", return_value=QMessageBox.Cancel):
        window.closeEvent(event)

    assert event.accepted is False


def test_close_event_discarding_every_dirty_project_accepts_the_close(window, appController, imagePath):
    _dirty(appController.activeController)
    appController.newProjectFromImage(imagePath)
    _dirty(appController.activeController)
    event = _FakeCloseEvent()

    with patch.object(QMessageBox, "exec", return_value=QMessageBox.Discard):
        window.closeEvent(event)

    assert event.accepted is True
