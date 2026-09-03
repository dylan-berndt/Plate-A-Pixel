import pytest
from PySide6.QtTest import QTest

from utils.data.canvas import Canvas
from utils.data.mesh import Mesh
from utils.data.project import Project, ViewSettings
from utils.controllers.canvasController import CanvasController
from utils.controllers.projectController import ProjectController, _MeshWorker
from .fixtures import RED_BLOCK, RED_ISLAND, make_pixel_art
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


def test_save_auto_names_unnamed_palette_entries_first(controller, tmp_path):
    palette = controller.project.canvas.palette
    assert any(not entry.name for entry in palette)  # fixture starts unnamed

    controller.save(str(tmp_path / "test.pap"))

    assert all(entry.name for entry in palette)


def test_save_does_not_touch_already_named_entries(controller, tmp_path):
    controller.canvasController.renameColor(0, "My Custom Name")

    controller.save(str(tmp_path / "test.pap"))

    assert controller.project.canvas.palette[0].name == "My Custom Name"


def test_save_without_a_path_raises_before_auto_naming_anything(controller):
    palette = controller.project.canvas.palette

    with pytest.raises(ValueError):
        controller.save()

    # No path to save to at all - nothing should have been touched.
    assert all(not entry.name for entry in palette)


def test_project_controller_owns_a_canvas_controller(controller):
    assert isinstance(controller.canvasController, CanvasController)
    assert controller.canvasController.project is controller.project


def test_a_failing_mesh_computation_does_not_wedge_the_pipeline(controller, monkeypatch):
    # A worker whose computation raises (e.g. a trimesh boolean op needing
    # a graph engine backend that isn't installed, or the worker process
    # itself dying) must not leave _meshWorker permanently set - every
    # future rebuildMesh() call would otherwise just queue behind a worker
    # that has already died, silently going stale forever with no visible
    # sign why. Patches _MeshWorker's own method rather than
    # Mesh._calculateMesh - the real computation now runs in a separate
    # process (see projectController.py), which a patch in this process's
    # Mesh class can't reach.
    def alwaysFails(self):
        raise RuntimeError("simulated computation failure")

    monkeypatch.setattr(_MeshWorker, "_computeMeshData", alwaysFails)

    ready = spy(controller.meshReady)
    controller.canvasController.setMargin(1)
    waitForMeshWorker(controller)

    assert controller._meshWorker is None
    assert len(ready) == 1
    assert controller.project.mesh.meshes == []

    # the pipeline must still work for the next edit, once computation
    # can actually succeed again
    monkeypatch.undo()
    controller.canvasController.setMargin(2)
    waitForMeshWorker(controller)

    assert controller._meshWorker is None
    assert len(ready) == 2


# -- rebuildMesh() debouncing --------------------------------------------
# The shared `controller` fixture zeroes MESH_DEBOUNCE_MS so every other
# test above keeps its old "one edit -> one recompute" behavior. These
# build their own controller with a small but real, non-zero window
# instead, to test the debouncing itself - see ProjectController's class
# docstring for why it exists (mashing a layer's "+" button visibly
# stutters if every click starts its own recompute).

@pytest.fixture
def debounced_controller():
    canvas = Canvas(make_pixel_art())
    project = Project(canvas, viewSettings=ViewSettings(hollow=False, baseMargin=0))
    c = ProjectController(project)
    c._meshDebounceTimer.setInterval(60)
    yield c
    c._meshDebounceTimer.stop()
    if c._meshWorker is not None:
        c._meshWorker.wait()


def test_a_burst_of_edits_within_the_debounce_window_produces_one_recompute(debounced_controller):
    ready = spy(debounced_controller.meshReady)
    invalidated = spy(debounced_controller.meshInvalidated)

    for margin in (1, 2, 3):
        debounced_controller.canvasController.setMargin(margin)
        QTest.qWait(10)  # well under the 60ms window - still one burst

    # meshInvalidated still fires per-edit (immediate stale feedback), but
    # nothing has actually started yet - the debounce window hasn't
    # elapsed since the last edit.
    assert len(invalidated) == 3
    assert debounced_controller._meshWorker is None
    assert len(ready) == 0

    waitForMeshWorker(debounced_controller)

    # one recompute, reflecting the *last* edit (margin=3), not one per click
    assert len(ready) == 1
    assert debounced_controller.project.viewSettings.baseMargin == 3


def test_edits_spaced_out_past_the_debounce_window_each_get_their_own_recompute(debounced_controller):
    ready = spy(debounced_controller.meshReady)

    debounced_controller.canvasController.setMargin(1)
    waitForMeshWorker(debounced_controller)
    debounced_controller.canvasController.setMargin(2)
    waitForMeshWorker(debounced_controller)

    # debouncing only coalesces edits *within* the window - it doesn't
    # suppress or merge recomputes that were already, genuinely separate.
    assert len(ready) == 2


def test_an_edit_that_lands_while_the_previous_worker_is_still_running_still_gets_picked_up(
    debounced_controller, monkeypatch
):
    # A tiny test canvas computes fast enough that the first worker could
    # plausibly finish (and its queued meshComputed could even be
    # delivered, since qWait below pumps events) before this gets a chance
    # to check - so make it artificially slow instead of racing a real one.
    # Patches _MeshWorker's own method rather than Mesh._calculateMesh -
    # see test_a_failing_mesh_computation_does_not_wedge_the_pipeline for why.
    realComputeMeshData = _MeshWorker._computeMeshData

    def slowComputeMeshData(self):
        import time
        time.sleep(0.1)
        return realComputeMeshData(self)

    monkeypatch.setattr(_MeshWorker, "_computeMeshData", slowComputeMeshData)
    ready = spy(debounced_controller.meshReady)

    debounced_controller.canvasController.setMargin(1)
    QTest.qWait(80)  # past the 60ms debounce window - the first worker has started...
    assert debounced_controller._meshWorker is not None  # ...and is still in its 100ms sleep
    debounced_controller.canvasController.setMargin(2)  # arrives while it's still running

    waitForMeshWorker(debounced_controller)

    assert len(ready) == 2
    assert debounced_controller.project.viewSettings.baseMargin == 2
