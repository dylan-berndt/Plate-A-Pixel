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


def test_set_tube_margin_updates_view_settings_and_rebuilds_mesh(controller):
    ready = spy(controller.meshReady)

    controller.canvasController.setTubeMargin(0.2)
    waitForMeshWorker(controller)

    assert controller.project.viewSettings.tubeMargin == 0.2
    assert len(ready) == 1


def test_set_wall_thickness_updates_view_settings_and_rebuilds_mesh(controller):
    ready = spy(controller.meshReady)

    controller.canvasController.setWallThickness(0.25)
    waitForMeshWorker(controller)

    assert controller.project.viewSettings.wallThickness == 0.25
    assert len(ready) == 1


def test_set_bulge_size_updates_view_settings_and_rebuilds_mesh(controller):
    ready = spy(controller.meshReady)

    controller.canvasController.setBulgeSize(0.3)
    waitForMeshWorker(controller)

    assert controller.project.viewSettings.bulgeSize == 0.3
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
    # Canvas auto-names every entry on import (see colorNaming.py), so
    # the pre-rename name isn't blank - capture whatever it actually is
    # rather than assuming "".
    originalName = controller.project.canvas.palette[index].name
    controller.canvasController.renameColor(index, "Fire Red")

    controller.undo()

    assert controller.project.canvas.palette[index].name == originalName


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


def test_select_all_selects_every_cell_and_emits(controller):
    calls = spy(controller.selectionChanged)

    controller.canvasController.selectAll()

    assert controller.project.canvas.selection.all()
    assert len(calls) == 1


def test_deselect_all_clears_the_selection_and_emits(controller):
    controller.project.canvas.bucketSelect((0, 0), contiguous=False, mode="replace")  # setup, not under test
    calls = spy(controller.selectionChanged)

    controller.canvasController.deselectAll()

    assert not controller.project.canvas.selection.any()
    assert len(calls) == 1


def test_invert_selection_flips_every_cell_and_emits(controller):
    controller.project.canvas.bucketSelect((0, 0), contiguous=False, mode="replace")  # setup, not under test
    before = controller.project.canvas.selection.copy()
    calls = spy(controller.selectionChanged)

    controller.canvasController.invertSelection()

    assert (controller.project.canvas.selection == ~before).all()
    assert len(calls) == 1


def test_select_all_undo_reverts(controller):
    controller.canvasController.selectAll()

    controller.undo()

    assert not controller.project.canvas.selection.any()


def test_auto_name_unnamed_colors_fills_in_every_blank_name(controller):
    # Canvas already auto-names every entry on import (see colorNaming.py
    # and test_canvas.py's own coverage of that) - blank a couple back
    # out here to set up the "still unnamed" precondition this method is
    # actually meant to backfill (a user clearing a name by hand, e.g.).
    palette = controller.project.canvas.palette
    controller.canvasController.renameColor(0, "")
    controller.canvasController.renameColor(1, "")
    calls = spy(controller.paletteChanged)

    controller.canvasController.autoNameUnnamedColors()

    assert all(entry.name for entry in palette)
    assert len(calls) == 1


def test_auto_name_unnamed_colors_leaves_existing_names_alone(controller):
    palette = controller.project.canvas.palette
    controller.canvasController.renameColor(0, "My Custom Name")

    controller.canvasController.autoNameUnnamedColors()

    assert palette[0].name == "My Custom Name"


def test_auto_name_unnamed_colors_is_a_no_op_when_everything_is_named(controller):
    palette = controller.project.canvas.palette
    for i in range(len(palette)):
        controller.canvasController.renameColor(i, f"Color {i}")
    calls = spy(controller.paletteChanged)

    controller.canvasController.autoNameUnnamedColors()

    assert len(calls) == 0


def test_auto_name_unnamed_colors_undoes_as_one_step(controller):
    controller.canvasController.renameColor(0, "")  # set up an actual blank to fill in
    controller.canvasController.renameColor(1, "")

    controller.canvasController.autoNameUnnamedColors()
    controller.undo()

    # undo() replaces canvas.palette wholesale (see ProjectController.
    # _restore) - re-fetch it rather than reusing a pre-undo reference.
    # One undo() must land back on "both blanked out", not "auto-named" -
    # if autoNameUnnamedColors() pushed more than the one undo snapshot
    # its own docstring promises, this would still show the filled-in
    # names after a single undo.
    palette = controller.project.canvas.palette
    assert palette[0].name == ""
    assert palette[1].name == ""
