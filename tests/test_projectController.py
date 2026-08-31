import numpy as np
import pytest

from utils.data.canvas import Canvas
from utils.data.project import Project, ViewSettings
from utils.data.mesh import Mesh
from utils.controllers.projectController import ProjectController
from .fixtures import make_pixel_art, RED, RED_BLOCK, RED_ISLAND


@pytest.fixture
def controller():
    canvas = Canvas(make_pixel_art())
    project = Project(canvas, viewSettings=ViewSettings(hollow=False, baseMargin=0))
    return ProjectController(project)


def _spy(signal):
    calls = []
    signal.connect(lambda *args: calls.append(args))
    return calls


def test_wand_select_selects_matching_color_and_emits(controller):
    calls = _spy(controller.selectionChanged)

    controller.wandSelect(RED, mode="replace")

    canvas = controller.project.canvas
    for pos in RED_BLOCK:
        assert canvas.selection[pos]
    assert len(calls) == 1


def test_wand_select_undo_restores_previous_selection(controller):
    controller.wandSelect(RED, mode="replace")
    assert controller.project.canvas.selection.sum() == len(RED_BLOCK) + 1  # wand also grabs RED_ISLAND

    controller.undo()

    assert controller.project.canvas.selection.sum() == 0


def test_bucket_select_selects_contiguous_region(controller):
    controller.bucketSelect((0, 0), contiguous=True, diagonal=True, mode="replace")

    canvas = controller.project.canvas
    for pos in RED_BLOCK:
        assert canvas.selection[pos]
    assert not canvas.selection[RED_ISLAND]


def test_transform_selection_layer_raises_selected_pixels_and_rebuilds_mesh(controller):
    invalidated = _spy(controller.meshInvalidated)
    ready = _spy(controller.meshReady)
    controller.wandSelect(RED, mode="replace")

    controller.transformSelectionLayer(3)

    canvas = controller.project.canvas
    for pos in RED_BLOCK:
        assert canvas.layers[pos] == 2  # started at -1 (empty), +3
    assert len(invalidated) == 1
    assert len(ready) == 1
    assert isinstance(ready[0][0], Mesh)


def test_transform_selection_layer_undo_restores_heights_and_rebuilds(controller):
    controller.wandSelect(RED, mode="replace")
    controller.transformSelectionLayer(3)

    controller.undo()

    canvas = controller.project.canvas
    for pos in RED_BLOCK:
        assert canvas.layers[pos] == -1


def test_set_hollow_updates_view_settings_and_rebuilds_mesh(controller):
    ready = _spy(controller.meshReady)

    controller.setHollow(True)

    assert controller.project.viewSettings.hollow is True
    assert len(ready) == 1


def test_set_hollow_undo_reverts(controller):
    controller.setHollow(True)
    controller.undo()

    assert controller.project.viewSettings.hollow is False


def test_set_margin_updates_view_settings_and_rebuilds_mesh(controller):
    ready = _spy(controller.meshReady)

    controller.setMargin(2)

    assert controller.project.viewSettings.baseMargin == 2
    assert len(ready) == 1


def test_set_cell_width_does_not_touch_the_mesh(controller):
    invalidated = _spy(controller.meshInvalidated)
    ready = _spy(controller.meshReady)
    settingsChanged = _spy(controller.viewSettingsChanged)

    controller.setCellWidth(12.0)

    assert controller.project.viewSettings.cellWidth == 12.0
    assert len(invalidated) == 0
    assert len(ready) == 0
    assert len(settingsChanged) == 1


def test_set_cell_height_does_not_touch_the_mesh(controller):
    ready = _spy(controller.meshReady)

    controller.setCellHeight(3.5)

    assert controller.project.viewSettings.cellHeight == 3.5
    assert len(ready) == 0


def test_rename_color_updates_palette_and_emits(controller):
    calls = _spy(controller.paletteChanged)
    index = controller.project.canvas.palette.indexOf(RED)

    controller.renameColor(index, "Fire Red")

    assert controller.project.canvas.palette[index].name == "Fire Red"
    assert len(calls) == 1


def test_rename_color_undo_reverts(controller):
    index = controller.project.canvas.palette.indexOf(RED)
    controller.renameColor(index, "Fire Red")

    controller.undo()

    assert controller.project.canvas.palette[index].name == ""


def test_recolor_color_updates_palette_and_emits(controller):
    calls = _spy(controller.paletteChanged)
    index = controller.project.canvas.palette.indexOf(RED)

    controller.recolorColor(index, (10, 20, 30))

    assert controller.project.canvas.palette[index].color == (10, 20, 30)
    assert len(calls) == 1


def test_recolor_color_undo_reverts(controller):
    index = controller.project.canvas.palette.indexOf(RED)
    controller.recolorColor(index, (10, 20, 30))

    controller.undo()

    assert controller.project.canvas.palette[index].color == RED
