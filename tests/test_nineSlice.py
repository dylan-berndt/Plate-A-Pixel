import pytest
from PySide6.QtGui import QImage, QPainter, QColor
from PySide6.QtCore import QRect, Qt

from utils.ui.nineSlice import NineSlice, NineSliceFrame, NineSliceEdge, DEFAULT_SLICE_PATH

INK = (16, 18, 28, 255)
FILL = (176, 167, 184, 255)
TRANSPARENT = (0, 0, 0, 0)


def _px(pixmap, x, y):
    return pixmap.toImage().pixelColor(x, y).getRgb()


@pytest.fixture
def nineSlice():
    return NineSlice(DEFAULT_SLICE_PATH, cornerSize=2)


def test_slices_are_sized_from_the_8x8_source_and_corner_size(nineSlice):
    assert nineSlice.topLeft.size().toTuple() == (2, 2)
    assert nineSlice.topRight.size().toTuple() == (2, 2)
    assert nineSlice.bottomLeft.size().toTuple() == (2, 2)
    assert nineSlice.bottomRight.size().toTuple() == (2, 2)
    assert nineSlice.top.size().toTuple() == (4, 2)
    assert nineSlice.bottom.size().toTuple() == (4, 2)
    assert nineSlice.left.size().toTuple() == (2, 4)
    assert nineSlice.right.size().toTuple() == (2, 4)
    assert nineSlice.center.size().toTuple() == (4, 4)


def test_top_left_corner_has_the_rounded_transparent_pixel(nineSlice):
    # slice.png's actual corner pixel is cut away for a rounded look -
    # the other three of the 2x2 corner block are the dark outline.
    assert _px(nineSlice.topLeft, 0, 0) == TRANSPARENT
    assert _px(nineSlice.topLeft, 1, 0) == INK
    assert _px(nineSlice.topLeft, 0, 1) == INK
    assert _px(nineSlice.topLeft, 1, 1) == INK


def test_top_edge_is_ink_outline_over_fill_highlight(nineSlice):
    img = nineSlice.top.toImage()
    for x in range(4):
        assert img.pixelColor(x, 0).getRgb() == INK
        assert img.pixelColor(x, 1).getRgb() == FILL


def test_center_is_fully_transparent(nineSlice):
    img = nineSlice.center.toImage()
    for y in range(4):
        for x in range(4):
            assert img.pixelColor(x, y).getRgb() == TRANSPARENT


def test_border_thickness_scales_with_the_scale_factor(nineSlice):
    assert nineSlice.borderThickness(1) == 2
    assert nineSlice.borderThickness(3) == 6


def test_unknown_source_path_raises():
    with pytest.raises(ValueError):
        NineSlice("/nonexistent/path/to/nothing.png")


def test_corner_size_leaving_no_room_for_edges_raises():
    with pytest.raises(ValueError):
        NineSlice(DEFAULT_SLICE_PATH, cornerSize=4)  # 8 / 2 sides = no edge room


def test_paint_places_scaled_corners_at_each_corner_of_the_rect(nineSlice):
    scale = 3
    size = 8 * scale
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    nineSlice.paint(painter, QRect(0, 0, size, size), scale=scale)
    painter.end()

    c = nineSlice.borderThickness(scale)
    # Corner pixel of each of the four corners should still be the
    # transparent "rounded" pixel, scaled up (a c x c block, not just one
    # pixel).
    assert image.pixelColor(0, 0).alpha() == 0
    assert image.pixelColor(size - 1, 0).alpha() == 0
    assert image.pixelColor(0, size - 1).alpha() == 0
    assert image.pixelColor(size - 1, size - 1).alpha() == 0
    # Just inside that transparent corner pixel, within the same scaled
    # corner block, should be the dark outline.
    assert image.pixelColor(c - 1, 0).getRgb() == INK
    assert image.pixelColor(size - c, 0).getRgb() == INK


def test_paint_tiles_edges_rather_than_stretching(nineSlice):
    # A rect much wider than the source edge tile - if the edge were
    # stretched instead of tiled, the outline row would just be one
    # solid smear; tiled, the pattern repeats every (edge width * scale)
    # pixels, so sampling at that period should reproduce the same color
    # sequence, not a smoothly-interpolated gradient.
    scale = 2
    width = 200
    height = 8 * scale
    image = QImage(width, height, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    nineSlice.paint(painter, QRect(0, 0, width, height), scale=scale)
    painter.end()

    c = nineSlice.borderThickness(scale)
    period = nineSlice.top.width() * scale
    # Sample the top-edge outline row (y=0, within the mid span) at two
    # points one tile-period apart - both should be part of the outline
    # (the top edge's row 0 is solid ink across its whole width), and at
    # a point half a period later on the *fill* row (y=1 scaled), which
    # should differ, proving this is a repeating 2-row tile, not a plain
    # fill.
    x = c + 10
    assert image.pixelColor(x, 0).getRgb() == INK
    assert image.pixelColor(x + period, 0).getRgb() == INK
    assert image.pixelColor(x, scale).getRgb() == FILL


# -- NineSliceFrame ---------------------------------------------------------

def test_nine_slice_frame_shares_one_nine_slice_per_source():
    a = NineSliceFrame(backgroundColor="#ffffff")
    b = NineSliceFrame(backgroundColor="#000000")
    assert a._nineSlice is b._nineSlice


def test_nine_slice_frame_border_thickness_matches_its_scale():
    frame = NineSliceFrame(backgroundColor="#ffffff", scale=4)
    assert frame.borderThickness() == 2 * 4


def test_nine_slice_frame_paints_its_background_behind_the_transparent_center():
    frame = NineSliceFrame(backgroundColor="#ff00ff", scale=2)
    frame.resize(40, 40)
    image = QImage(40, 40, QImage.Format_ARGB32)
    frame.render(image)

    center = image.pixelColor(20, 20)
    assert (center.red(), center.green(), center.blue()) == (255, 0, 255)
    assert center.alpha() == 255  # background fill, not left transparent


def test_set_background_color_changes_what_gets_painted():
    frame = NineSliceFrame(backgroundColor="#ff00ff", scale=2)
    frame.resize(40, 40)

    frame.setBackgroundColor("#00ff00")

    assert frame._backgroundColor == QColor("#00ff00")


def test_nine_slice_frame_and_edge_share_the_same_underlying_nine_slice():
    # Both go through the module-level sharedNineSlice() cache now, not
    # two disconnected per-class caches.
    frame = NineSliceFrame(backgroundColor="#ffffff")
    edge = NineSliceEdge(backgroundColor="#ffffff", side="right")
    assert frame._nineSlice is edge._nineSlice


# -- NineSlice.paintEdge / NineSliceEdge ------------------------------------

def test_paint_edge_tiles_only_the_named_side_leaving_the_rest_untouched(nineSlice):
    scale = 2
    size = 60
    thickness = nineSlice.borderThickness(scale)
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    nineSlice.paintEdge(painter, QRect(0, 0, size, size), "right", scale=scale)
    painter.end()

    # Right edge painted: the outline column should be opaque ink...
    assert image.pixelColor(size - 1, 5).getRgb() == INK
    # ...but nothing was painted on the opposite (left) side, or any
    # other side - paintEdge draws exactly one edge, no corners.
    assert image.pixelColor(0, 5).alpha() == 0
    assert image.pixelColor(5, 0).alpha() == 0
    assert image.pixelColor(5, size - 1).alpha() == 0
    # Just inside the painted edge, past its thickness, should still be
    # untouched (paintEdge fills only a `thickness`-wide strip).
    assert image.pixelColor(size - thickness - 1, 5).alpha() == 0


def test_paint_edge_rejects_unknown_side(nineSlice):
    image = QImage(10, 10, QImage.Format_ARGB32)
    painter = QPainter(image)
    with pytest.raises(ValueError):
        nineSlice.paintEdge(painter, QRect(0, 0, 10, 10), "diagonal")
    painter.end()


def test_nine_slice_edge_rejects_unknown_side():
    with pytest.raises(ValueError):
        NineSliceEdge(backgroundColor="#ffffff", side="diagonal")


def test_nine_slice_edge_border_thickness_matches_its_scale():
    edge = NineSliceEdge(backgroundColor="#ffffff", side="left", scale=3)
    assert edge.borderThickness() == 2 * 3


def test_nine_slice_edge_paints_background_and_the_one_named_edge():
    edge = NineSliceEdge(backgroundColor="#ff00ff", side="left", scale=2)
    edge.resize(40, 40)
    image = QImage(40, 40, QImage.Format_ARGB32)
    edge.render(image)

    # Away from the painted edge, the background fill shows through.
    center = image.pixelColor(30, 20)
    assert (center.red(), center.green(), center.blue()) == (255, 0, 255)
    # The named (left) edge's outline column is drawn over that fill.
    assert image.pixelColor(0, 20).getRgb() == INK
    # The opposite (right) edge is untouched background, not bordered.
    right = image.pixelColor(39, 20)
    assert (right.red(), right.green(), right.blue()) == (255, 0, 255)
