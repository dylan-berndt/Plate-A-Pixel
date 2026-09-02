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


def test_valid_neighbors_at_corner_respects_canvas_bounds(canvas):
    assert len(canvas.validNeighbors((0, 0), diagonal=False)) == 2
    assert len(canvas.validNeighbors((0, 0), diagonal=True)) == 3


def test_brush_select_grabs_every_cell_within_radius_regardless_of_color(canvas):
    canvas.brushSelect((0, 0), radius=1, mode="replace")

    assert canvas.selection[0, 0]
    assert canvas.selection[0, 1]
    assert canvas.selection[1, 0]
    assert not canvas.selection[1, 1]  # sqrt(2) > 1
    assert canvas.selection.sum() == 3


def test_brush_select_radius_zero_selects_only_the_center_cell(canvas):
    canvas.brushSelect((2, 2), radius=0, mode="replace")

    assert canvas.selection.sum() == 1
    assert canvas.selection[2, 2]


def test_brush_select_add_mode_unions_with_the_existing_selection(canvas):
    canvas.brushSelect((0, 0), radius=0, mode="replace")

    canvas.brushSelect((5, 5), radius=0, mode="add")

    assert canvas.selection.sum() == 2
    assert canvas.selection[0, 0]
    assert canvas.selection[5, 5]
