import numpy as np
import pytest

from utils.data.canvas import Canvas
from utils.data.project import Project, ViewSettings
from utils.data.mesh import Mesh
from utils.controllers.projectController import ProjectController
from utils.controllers.canvasController import CanvasController
from .fixtures import make_pixel_art, RED, RED_BLOCK, RED_ISLAND
from .conftest import waitForMeshWorker


@pytest.fixture
def controller():
    canvas = Canvas(make_pixel_art())
    project = Project(canvas, viewSettings=ViewSettings(hollow=False, baseMargin=0))
    c = ProjectController(project)
    yield c
    if c._meshWorker is not None:
        c._meshWorker.wait()  # don't leave a running QThread dangling past the test


def _spy(signal):
    calls = []
    signal.connect(lambda *args: calls.append(args))
    return calls


def test_bucket_select_non_contiguous_selects_every_matching_color_and_emits(controller):
    calls = _spy(controller.selectionChanged)

    controller.canvasController.bucketSelect((0, 0), contiguous=False, mode="replace")

    canvas = controller.project.canvas
    for pos in RED_BLOCK:
        assert canvas.selection[pos]
    assert canvas.selection[RED_ISLAND]
    assert len(calls) == 1


def test_bucket_select_undo_restores_previous_selection(controller):
    controller.canvasController.bucketSelect((0, 0), contiguous=False, mode="replace")
    assert controller.project.canvas.selection.sum() == len(RED_BLOCK) + 1

    controller.undo()

    assert controller.project.canvas.selection.sum() == 0


def test_bucket_select_selects_contiguous_region(controller):
    controller.canvasController.bucketSelect((0, 0), contiguous=True, diagonal=True, mode="replace")

    canvas = controller.project.canvas
    for pos in RED_BLOCK:
        assert canvas.selection[pos]
    assert not canvas.selection[RED_ISLAND]


def test_transform_selection_layer_raises_selected_pixels_and_rebuilds_mesh(controller):
    invalidated = _spy(controller.meshInvalidated)
    ready = _spy(controller.meshReady)
    controller.canvasController.bucketSelect((0, 0), contiguous=False, mode="replace")

    controller.canvasController.transformSelectionLayer(3)
    waitForMeshWorker(controller)

    canvas = controller.project.canvas
    for pos in RED_BLOCK:
        assert canvas.layers[pos] == 2  # started at -1 (empty), +3
    assert len(invalidated) == 1
    assert len(ready) == 1
    assert isinstance(ready[0][0], Mesh)


def test_transform_selection_layer_undo_restores_heights_and_rebuilds(controller):
    controller.canvasController.bucketSelect((0, 0), contiguous=False, mode="replace")
    controller.canvasController.transformSelectionLayer(3)
    waitForMeshWorker(controller)  # let that rebuild settle before triggering another

    controller.undo()

    canvas = controller.project.canvas
    for pos in RED_BLOCK:
        assert canvas.layers[pos] == -1


def test_set_hollow_updates_view_settings_and_rebuilds_mesh(controller):
    ready = _spy(controller.meshReady)

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
    ready = _spy(controller.meshReady)

    controller.canvasController.setMargin(2)
    waitForMeshWorker(controller)

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


def test_brush_select_selects_and_emits(controller):
    calls = _spy(controller.selectionChanged)

    controller.canvasController.brushSelect((0, 0), radius=1, mode="replace")

    assert controller.project.canvas.selection.sum() == 3
    assert len(calls) == 1


def test_gesture_collapses_repeated_edits_into_one_undo_step(controller):
    controller.beginGesture()
    controller.canvasController.brushSelect((0, 0), radius=0, mode="add")
    controller.canvasController.brushSelect((0, 1), radius=0, mode="add")
    controller.canvasController.brushSelect((1, 0), radius=0, mode="add")
    controller.endGesture()

    assert controller.project.canvas.selection.sum() == 3
    assert len(controller._undoStack) == 1

    controller.undo()

    assert controller.project.canvas.selection.sum() == 0


def test_calls_outside_a_gesture_each_push_their_own_undo_step(controller):
    controller.canvasController.brushSelect((0, 0), radius=0, mode="add")
    controller.canvasController.brushSelect((0, 1), radius=0, mode="add")

    assert len(controller._undoStack) == 2


def test_nested_gesture_calls_only_push_one_snapshot(controller):
    controller.beginGesture()
    controller.beginGesture()
    controller.canvasController.brushSelect((0, 0), radius=0, mode="add")
    controller.endGesture()
    controller.canvasController.brushSelect((0, 1), radius=0, mode="add")  # still inside the outer gesture
    controller.endGesture()

    assert len(controller._undoStack) == 1


def test_can_undo_and_can_redo_reflect_the_stacks(controller):
    assert controller.canUndo is False
    assert controller.canRedo is False

    controller.canvasController.brushSelect((0, 0), radius=0, mode="add")
    assert controller.canUndo is True
    assert controller.canRedo is False

    controller.undo()
    assert controller.canUndo is False
    assert controller.canRedo is True

    controller.redo()
    assert controller.canUndo is True
    assert controller.canRedo is False


def test_new_controller_is_not_dirty(controller):
    assert controller.isDirty is False


def test_an_edit_marks_the_controller_dirty(controller):
    controller.canvasController.brushSelect((0, 0), radius=0, mode="add")

    assert controller.isDirty is True


def test_undo_also_marks_the_controller_dirty(controller, tmp_path):
    controller.canvasController.brushSelect((0, 0), radius=0, mode="add")
    controller.save(str(tmp_path / "test.pap"))
    assert controller.isDirty is False

    controller.undo()

    assert controller.isDirty is True


def test_save_without_a_path_or_prior_save_raises(controller):
    with pytest.raises(ValueError):
        controller.save()


def test_save_writes_to_the_given_path_and_clears_dirty(controller, tmp_path):
    controller.canvasController.brushSelect((0, 0), radius=0, mode="add")
    assert controller.isDirty is True
    path = str(tmp_path / "test.pap")

    controller.save(path)

    assert controller.isDirty is False
    assert controller.project.filePath == path


def test_save_with_no_path_reuses_the_last_saved_path(controller, tmp_path):
    path = str(tmp_path / "test.pap")
    controller.save(path)

    controller.canvasController.brushSelect((0, 0), radius=0, mode="add")
    controller.save()

    assert controller.isDirty is False


def test_project_controller_owns_a_canvas_controller(controller):
    assert isinstance(controller.canvasController, CanvasController)
    assert controller.canvasController.project is controller.project
