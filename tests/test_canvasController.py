from utils.data.mesh import Mesh
from .fixtures import RED, RED_BLOCK
from .conftest import waitForMeshWorker, spy


def test_transform_selection_layer_raises_selected_pixels_and_rebuilds_mesh(controller):
    invalidated = spy(controller.meshInvalidated)
    ready = spy(controller.meshReady)
    controller.project.canvas.bucketSelect((0, 0), contiguous=False, mode="replace")  # setup, not under test

    controller.canvasController.transformSelectionLayer(3)
    waitForMeshWorker(controller)

    canvas = controller.project.canvas
    for pos in RED_BLOCK:
        assert canvas.layers[pos] == 2  # started at -1 (empty), +3
    assert len(invalidated) == 1
    assert len(ready) == 1
    assert isinstance(ready[0][0], Mesh)


def test_transform_selection_layer_undo_restores_heights_and_rebuilds(controller):
    controller.project.canvas.bucketSelect((0, 0), contiguous=False, mode="replace")  # setup, not under test
    controller.canvasController.transformSelectionLayer(3)
    waitForMeshWorker(controller)  # let that rebuild settle before triggering another

    controller.undo()

    canvas = controller.project.canvas
    for pos in RED_BLOCK:
        assert canvas.layers[pos] == -1


def test_set_hollow_updates_view_settings_and_rebuilds_mesh(controller):
    ready = spy(controller.meshReady)

    controller.canvasController.setHollow(True)
    waitForMeshWorker(controller)

    assert controller.project.viewSettings.hollow is True
    assert len(ready) == 1


def test_set_hollow_undo_reverts(controller):
    controller.canvasController.setHollow(True)
    waitForMeshWorker(controller)

    controller.undo()

    assert controller.project.viewSettings.hollow is False


def test_set_margin_updates_view_settings_and_rebuilds_mesh(controller):
    ready = spy(controller.meshReady)

    controller.canvasController.setMargin(2)
    waitForMeshWorker(controller)

    assert controller.project.viewSettings.baseMargin == 2
    assert len(ready) == 1


def test_set_cell_width_does_not_touch_the_mesh(controller):
    invalidated = spy(controller.meshInvalidated)
    ready = spy(controller.meshReady)
    settingsChanged = spy(controller.viewSettingsChanged)

    controller.canvasController.setCellWidth(12.0)

    assert controller.project.viewSettings.cellWidth == 12.0
    assert len(invalidated) == 0
    assert len(ready) == 0
    assert len(settingsChanged) == 1


def test_set_cell_width_undo_reverts(controller):
    controller.canvasController.setCellWidth(12.0)

    controller.undo()

    assert controller.project.viewSettings.cellWidth != 12.0


def test_set_cell_height_does_not_touch_the_mesh(controller):
    ready = spy(controller.meshReady)

    controller.canvasController.setCellHeight(3.5)

    assert controller.project.viewSettings.cellHeight == 3.5
    assert len(ready) == 0


def test_rename_color_updates_palette_and_emits(controller):
    calls = spy(controller.paletteChanged)
    index = controller.project.canvas.palette.indexOf(RED)

    controller.canvasController.renameColor(index, "Fire Red")

    assert controller.project.canvas.palette[index].name == "Fire Red"
    assert len(calls) == 1


def test_rename_color_undo_reverts(controller):
    index = controller.project.canvas.palette.indexOf(RED)
    controller.canvasController.renameColor(index, "Fire Red")

    controller.undo()

    assert controller.project.canvas.palette[index].name == ""


def test_recolor_color_updates_palette_and_emits(controller):
    calls = spy(controller.paletteChanged)
    index = controller.project.canvas.palette.indexOf(RED)

    controller.canvasController.recolorColor(index, (10, 20, 30))

    assert controller.project.canvas.palette[index].color == (10, 20, 30)
    assert len(calls) == 1


def test_recolor_color_undo_reverts(controller):
    index = controller.project.canvas.palette.indexOf(RED)
    controller.canvasController.recolorColor(index, (10, 20, 30))

    controller.undo()

    assert controller.project.canvas.palette[index].color == RED
