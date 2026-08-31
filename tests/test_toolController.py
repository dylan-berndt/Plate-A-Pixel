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


def test_full_brush_gesture_produces_exactly_one_undo_step(app):
    app.toolController.registry.setActiveTool("brushSelect")
    app.toolController.registry.activeTool.selections["size"] = 0

    app.toolController.press((0, 0))
    app.toolController.drag((0, 1))
    app.toolController.drag((1, 0))
    app.toolController.release((1, 0))

    controller = app.activeController
    assert controller.project.canvas.selection.sum() == 3
    assert len(controller._undoStack) == 1


def test_drag_and_release_keep_targeting_the_project_active_at_press_time(app, imagePath):
    app.toolController.registry.setActiveTool("brushSelect")
    app.toolController.registry.activeTool.selections["size"] = 0
    first = app.activeController

    app.toolController.press((0, 0))
    app.newProjectFromImage(imagePath)  # active project changes mid-gesture
    app.toolController.drag((1, 1))
    app.toolController.release((1, 1))

    assert first.project.canvas.selection.sum() == 2
    assert app.activeController.project.canvas.selection.sum() == 0
