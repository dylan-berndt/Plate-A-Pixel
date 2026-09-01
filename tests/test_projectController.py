import pytest

from utils.data.mesh import Mesh
from utils.controllers.canvasController import CanvasController
from .fixtures import RED_BLOCK, RED_ISLAND
from .conftest import waitForMeshWorker, spy


# -- editing() itself -----------------------------------------------------
# Selection (bucketSelect/brushSelect) lives directly on WandTool/
# BrushSelectTool now (see test_tools.py for that coverage), and the
# other canvasController methods have their own tests in
# test_canvasController.py - these exercise editing()'s own contract
# (push undo, then emit-or-rebuild) using Canvas's real bucketSelect as a
# representative call.

def test_editing_pushes_undo_and_emits_the_given_signal(controller):
    calls = spy(controller.selectionChanged)

    with controller.editing(signal=controller.selectionChanged):
        controller.project.canvas.bucketSelect((0, 0), contiguous=False, mode="replace")

    canvas = controller.project.canvas
    for pos in RED_BLOCK:
        assert canvas.selection[pos]
    assert canvas.selection[RED_ISLAND]
    assert len(calls) == 1
    assert len(controller._undoStack) == 1


def test_editing_requires_affects_mesh_or_a_signal(controller):
    with pytest.raises(AssertionError):
        with controller.editing():
            pass


def test_editing_undo_restores_previous_selection(controller):
    with controller.editing(signal=controller.selectionChanged):
        controller.project.canvas.bucketSelect((0, 0), contiguous=False, mode="replace")
    assert controller.project.canvas.selection.sum() == len(RED_BLOCK) + 1

    controller.undo()

    assert controller.project.canvas.selection.sum() == 0


def test_editing_affects_mesh_rebuilds_the_mesh(controller):
    invalidated = spy(controller.meshInvalidated)
    ready = spy(controller.meshReady)

    with controller.editing(affectsMesh=True):
        controller.project.canvas.transformSelection(1)
    waitForMeshWorker(controller)

    assert len(invalidated) == 1
    assert len(ready) == 1
    assert isinstance(ready[0][0], Mesh)


# -- gestures ---------------------------------------------------------------

def test_gesture_collapses_repeated_edits_into_one_undo_step(controller):
    canvas = controller.project.canvas
    controller.beginGesture()
    with controller.editing(signal=controller.selectionChanged):
        canvas.brushSelect((0, 0), radius=0, mode="add")
    with controller.editing(signal=controller.selectionChanged):
        canvas.brushSelect((0, 1), radius=0, mode="add")
    with controller.editing(signal=controller.selectionChanged):
        canvas.brushSelect((1, 0), radius=0, mode="add")
    controller.endGesture()

    assert canvas.selection.sum() == 3
    assert len(controller._undoStack) == 1

    controller.undo()

    assert canvas.selection.sum() == 0


def test_calls_outside_a_gesture_each_push_their_own_undo_step(controller):
    canvas = controller.project.canvas
    with controller.editing(signal=controller.selectionChanged):
        canvas.brushSelect((0, 0), radius=0, mode="add")
    with controller.editing(signal=controller.selectionChanged):
        canvas.brushSelect((0, 1), radius=0, mode="add")

    assert len(controller._undoStack) == 2


def test_nested_gesture_calls_only_push_one_snapshot(controller):
    canvas = controller.project.canvas
    controller.beginGesture()
    controller.beginGesture()
    with controller.editing(signal=controller.selectionChanged):
        canvas.brushSelect((0, 0), radius=0, mode="add")
    controller.endGesture()
    with controller.editing(signal=controller.selectionChanged):
        canvas.brushSelect((0, 1), radius=0, mode="add")  # still inside the outer gesture
    controller.endGesture()

    assert len(controller._undoStack) == 1


# -- undo/redo availability, dirty tracking, persistence --------------------

def test_can_undo_and_can_redo_reflect_the_stacks(controller):
    assert controller.canUndo is False
    assert controller.canRedo is False

    with controller.editing(signal=controller.selectionChanged):
        controller.project.canvas.brushSelect((0, 0), radius=0, mode="add")
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
    with controller.editing(signal=controller.selectionChanged):
        controller.project.canvas.brushSelect((0, 0), radius=0, mode="add")

    assert controller.isDirty is True


def test_undo_also_marks_the_controller_dirty(controller, tmp_path):
    with controller.editing(signal=controller.selectionChanged):
        controller.project.canvas.brushSelect((0, 0), radius=0, mode="add")
    controller.save(str(tmp_path / "test.pap"))
    assert controller.isDirty is False

    controller.undo()

    assert controller.isDirty is True


def test_save_without_a_path_or_prior_save_raises(controller):
    with pytest.raises(ValueError):
        controller.save()


def test_save_writes_to_the_given_path_and_clears_dirty(controller, tmp_path):
    with controller.editing(signal=controller.selectionChanged):
        controller.project.canvas.brushSelect((0, 0), radius=0, mode="add")
    assert controller.isDirty is True
    path = str(tmp_path / "test.pap")

    controller.save(path)

    assert controller.isDirty is False
    assert controller.project.filePath == path


def test_save_with_no_path_reuses_the_last_saved_path(controller, tmp_path):
    path = str(tmp_path / "test.pap")
    controller.save(path)

    with controller.editing(signal=controller.selectionChanged):
        controller.project.canvas.brushSelect((0, 0), radius=0, mode="add")
    controller.save()

    assert controller.isDirty is False


def test_project_controller_owns_a_canvas_controller(controller):
    assert isinstance(controller.canvasController, CanvasController)
    assert controller.canvasController.project is controller.project
