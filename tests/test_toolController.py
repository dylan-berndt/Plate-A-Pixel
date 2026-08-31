import pytest
from PIL import Image

from utils.controllers.appController import AppController
from .fixtures import make_pixel_art, RED_BLOCK, RED_ISLAND


@pytest.fixture
def imagePath(tmp_path):
    path = tmp_path / "sprite.png"
    Image.fromarray(make_pixel_art()).save(path)
    return str(path)


@pytest.fixture
def app(imagePath):
    app = AppController()
    app.newProjectFromImage(imagePath)
    return app


def test_app_controller_owns_a_tool_controller_with_the_wand_tool_active(app):
    assert app.toolController.registry.activeTool.name == "wand"


def test_press_dispatches_to_the_active_project(app):
    app.toolController.registry.activeTool.selections["contiguous"] = False

    app.toolController.press((0, 0))

    canvas = app.activeController.project.canvas
    for pos in RED_BLOCK:
        assert canvas.selection[pos]
    assert canvas.selection[RED_ISLAND]


def test_press_targets_whichever_project_is_currently_active(app, imagePath):
    first = app.activeController
    second = app.newProjectFromImage(imagePath)
    assert app.activeController is second

    app.toolController.press((0, 0))

    assert second.project.canvas.selection.sum() > 0
    assert first.project.canvas.selection.sum() == 0


def test_press_with_no_open_project_is_a_no_op():
    app = AppController()

    app.toolController.press((0, 0))  # should not raise


def test_drag_and_release_are_no_ops_for_the_wand_tool(app):
    app.toolController.drag((0, 0))
    app.toolController.release((0, 0))

    assert app.activeController.project.canvas.selection.sum() == 0
