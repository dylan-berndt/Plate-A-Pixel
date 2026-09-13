import numpy as np
import pytest
from PIL import Image

from utils.data.canvas import Canvas
from .fixtures import make_pixel_art, RED_BLOCK, RED_ISLAND, GREEN_DIAGONAL_PAIR


def test_detect_scale_recovers_logical_grid(canvas):
    assert canvas.scale == 4
    assert canvas.image.shape == (6, 6, 3)


def test_palette_has_three_colors(canvas):
    assert len(canvas.palette) == 3


def test_palette_entries_are_auto_named_on_import(canvas):
    # Every entry gets a real name the moment a fresh image is imported
    # (colorNaming.autoNamesForUnnamed), not left blank until the user
    # renames it by hand or saves.
    assert all(entry.name for entry in canvas.palette)
    # Each of RED/GREEN/BACKGROUND is the only member of its own color
    # family here, so each gets just the family name, no "N" suffix.
    assert canvas.palette[canvas.palette.indexOf((220, 40, 40))].name == "Red"
    assert canvas.palette[canvas.palette.indexOf((40, 180, 90))].name == "Green"


def test_loading_a_saved_palette_does_not_re_auto_name_it(canvas):
    # A caller supplying `palette` explicitly (Project.load, reopening a
    # saved *.pap) is reconstructing exactly what was saved, blank names
    # included if that's genuinely what was saved - auto-naming only
    # ever applies to a *freshly detected* palette, not one already
    # given.
    from utils.data.palette import Palette, PaletteEntry
    palette = Palette(colors=None, entries=[PaletteEntry(color=(220, 40, 40), name="")])
    reloaded = Canvas(canvas.image, scale=canvas.scale, palette=palette, layers=canvas.layers)
    assert reloaded.palette[0].name == ""


def test_from_file_path_round_trip(tmp_path, pixel_art_image):
    path = tmp_path / "fixture.png"
    Image.fromarray(pixel_art_image).save(path)

    canvas = Canvas.fromFilePath(str(path))

    assert canvas.scale == 4
    assert canvas.image.shape == (6, 6, 3)


def test_from_file_path_converts_grayscale_source_to_rgb(tmp_path):
    # A grayscale PNG loads via PIL as a 2D (H, W) array with no channel
    # axis at all; detectScale and the rest of Canvas assume 3-channel
    # (H, W, 3) throughout, so this must be normalized on the way in.
    gray = np.zeros((20, 20), dtype=np.uint8)
    gray[:10, :10] = 50
    gray[:10, 10:] = 150
    gray[10:, :10] = 200
    gray[10:, 10:] = 250
    path = tmp_path / "gray.png"
    Image.fromarray(gray, mode="L").save(path)

    canvas = Canvas.fromFilePath(str(path))

    assert canvas.image.shape == (2, 2, 3)


def test_bucket_select_contiguous_stops_at_color_boundary(canvas):
    canvas.bucketSelect((0, 0), mode="replace", contiguous=True, diagonal=True)

    for pos in RED_BLOCK:
        assert canvas.selection[pos]
    assert not canvas.selection[RED_ISLAND]
    assert canvas.selection.sum() == len(RED_BLOCK)


def test_bucket_select_source_groups_by_that_array_instead_of_color(canvas):
    # RED_BLOCK and RED_ISLAND are the same color but not the same layer
    # height here - passing source=canvas.layers must group purely by
    # that shared height, ignoring the color match bucketSelect's default
    # (source=canvas.map) would otherwise use.
    canvas.layers[:] = 1
    canvas.layers[RED_ISLAND] = 9

    canvas.bucketSelect((0, 0), mode="replace", contiguous=False, source=canvas.layers)

    for pos in RED_BLOCK:
        assert canvas.selection[pos]
    assert not canvas.selection[RED_ISLAND]  # different height, excluded despite matching color
    assert canvas.selection[5, 0]  # background pixel, but shares height 1 - included


def test_bucket_select_noncontiguous_grabs_disconnected_same_color(canvas):
    canvas.bucketSelect((0, 0), mode="replace", contiguous=False, diagonal=True)

    for pos in RED_BLOCK:
        assert canvas.selection[pos]
    assert canvas.selection[RED_ISLAND]
    assert canvas.selection.sum() == len(RED_BLOCK) + 1


def test_bucket_select_diagonal_connects_dithered_pixels(canvas):
    canvas.bucketSelect(GREEN_DIAGONAL_PAIR[0], mode="replace", contiguous=True, diagonal=True)

    for pos in GREEN_DIAGONAL_PAIR:
        assert canvas.selection[pos]
    assert canvas.selection.sum() == len(GREEN_DIAGONAL_PAIR)


def test_bucket_select_without_diagonal_leaves_dithered_pixels_disconnected(canvas):
    canvas.bucketSelect(GREEN_DIAGONAL_PAIR[0], mode="replace", contiguous=True, diagonal=False)

    assert canvas.selection[GREEN_DIAGONAL_PAIR[0]]
    assert not canvas.selection[GREEN_DIAGONAL_PAIR[1]]
    assert canvas.selection.sum() == 1


def test_add_mode_unions_separate_bucket_selects(canvas):
    canvas.bucketSelect((0, 0), mode="add", contiguous=False, diagonal=True)
    canvas.bucketSelect(GREEN_DIAGONAL_PAIR[0], mode="add", contiguous=False, diagonal=True)

    assert canvas.selection.sum() == len(RED_BLOCK) + 1 + len(GREEN_DIAGONAL_PAIR)


def test_replace_mode_clears_previous_selection(canvas):
    canvas.bucketSelect((0, 0), mode="add", contiguous=False, diagonal=True)
    canvas.bucketSelect(GREEN_DIAGONAL_PAIR[0], mode="replace", contiguous=False, diagonal=True)

    assert canvas.selection.sum() == len(GREEN_DIAGONAL_PAIR)
    assert not canvas.selection[RED_ISLAND]


def test_intersect_mode_on_disjoint_colors_is_empty(canvas):
    canvas.bucketSelect((0, 0), mode="replace", contiguous=False, diagonal=True)
    canvas.bucketSelect(GREEN_DIAGONAL_PAIR[0], mode="intersect", contiguous=False, diagonal=True)

    assert canvas.selection.sum() == 0


def test_contiguous_subtract_clears_the_whole_connected_region(canvas):
    # The flood fill's visited-tracking is now local to newSelection, not
    # tied to self.selection, so a contiguous subtract walks the full
    # connected region regardless of what was already selected.
    canvas.bucketSelect((0, 0), mode="add", contiguous=False, diagonal=True)
    canvas.bucketSelect((0, 0), mode="subtract", contiguous=True, diagonal=True)

    for pos in RED_BLOCK:
        assert not canvas.selection[pos]


def test_subtract_over_an_unselected_region_leaves_it_unselected(canvas):
    # alterSelection's "subtract" branch used XOR, which toggles: a cell
    # in the subtracted region that wasn't already selected would flip
    # ON instead of staying off. Subtraction must only ever turn cells
    # off, never on.
    canvas.bucketSelect(GREEN_DIAGONAL_PAIR[0], mode="subtract", contiguous=False, diagonal=True)

    for pos in GREEN_DIAGONAL_PAIR:
        assert not canvas.selection[pos]
    assert canvas.selection.sum() == 0


def test_invalid_mode_raises():
    canvas = Canvas(make_pixel_art())
    with pytest.raises(NotImplementedError):
        canvas.alterSelection(np.zeros((6, 6), dtype=bool), "nonsense")


def test_select_all_selects_every_cell(canvas):
    canvas.selectAll()

    assert canvas.selection.all()


def test_deselect_all_clears_every_cell(canvas):
    canvas.bucketSelect((0, 0), mode="replace", contiguous=False)

    canvas.deselectAll()

    assert not canvas.selection.any()


def test_invert_selection_flips_every_cell(canvas):
    canvas.bucketSelect((0, 0), mode="replace", contiguous=True)
    before = canvas.selection.copy()

    canvas.invertSelection()

    assert (canvas.selection == ~before).all()
    for pos in RED_BLOCK:
        assert not canvas.selection[pos]
    assert canvas.selection[RED_ISLAND]


def test_valid_neighbors_at_corner_respects_canvas_bounds(canvas):
    assert len(canvas.validNeighbors((0, 0), diagonal=False)) == 2
    assert len(canvas.validNeighbors((0, 0), diagonal=True)) == 3


def test_brush_select_ignores_color(canvas):
    # At radius 2 (reachable from the real tool - see the radius=1 test
    # below for the slider's actual minimum), (0, 0)'s neighborhood
    # spans both RED_BLOCK and background - the stamp shouldn't care.
    canvas.brushSelect((0, 0), radius=2, mode="replace")

    assert canvas.selection[0, 0]
    assert canvas.selection[0, 1]
    assert canvas.selection[1, 0]
    assert canvas.selection[1, 1]
    assert canvas.selection.sum() == 4  # a solid 2x2 block - see test_brush_outline_mask_is_circular... for a radius large enough to actually show curvature


def test_brush_select_radius_one_selects_only_the_center_cell(canvas):
    # The smallest a real brush can be (BrushSelectTool's "size" slider
    # bottoms out at 1). Strict `<` (see Canvas._circleMask) means this
    # doesn't also catch the four cardinal neighbors (distance exactly
    # 1) the way `<=` used to - that stamped a 5-cell plus shape for
    # what should read as a single pixel.
    canvas.brushSelect((2, 2), radius=1, mode="replace")

    assert canvas.selection.sum() == 1
    assert canvas.selection[2, 2]


def test_brush_select_radius_zero_selects_nothing(canvas):
    # Not reachable through the real brush tool (its slider's minimum is
    # 1) - Canvas.brushSelect's own contract is a strict "<", so distance
    # 0 no longer counts as "within" a radius of 0 either. See
    # Canvas._circleMask's docstring for why this trade-off is fine.
    canvas.brushSelect((2, 2), radius=0, mode="replace")

    assert canvas.selection.sum() == 0


def test_brush_select_add_mode_unions_with_the_existing_selection(canvas):
    canvas.brushSelect((0, 0), radius=1, mode="replace")

    canvas.brushSelect((5, 5), radius=1, mode="add")

    assert canvas.selection.sum() == 2
    assert canvas.selection[0, 0]
    assert canvas.selection[5, 5]


def test_brush_outline_mask_is_circular_not_square_at_larger_radii():
    # A plain square brush would fill every corner of its bounding box;
    # a circular one (strict `<` - see Canvas._circleMask) does not. A
    # fresh larger canvas, not the shared 6x6 fixture, so the full
    # (2*radius+1)-square bounding box fits without being clipped by the
    # canvas edge.
    big = Canvas(np.zeros((20, 20, 3), dtype=np.uint8), scale=1)

    mask, top, left = big.brushOutlineMask((10, 10), radius=4)

    assert mask.shape == (9, 9)
    assert mask[4, 4]  # center
    assert not mask[0, 0]  # every corner of the bounding box...
    assert not mask[0, -1]
    assert not mask[-1, 0]
    assert not mask[-1, -1]  # ...is outside the circle
