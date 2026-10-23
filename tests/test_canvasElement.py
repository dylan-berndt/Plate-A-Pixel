import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import QCoreApplication, QEvent, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter

from utils.canvasElement import CanvasArea, CanvasArtist
from utils.controllers.appController import AppController
from .fixtures import RED_BLOCK, RED_ISLAND, make_pixel_art


# -- CanvasArtist._maskOutlinePath -------------------------------------------

def test_mask_outline_path_is_built_in_local_unscaled_grid_coordinates():
    # An L-shape, not a solid rectangle - covers the "inner corner" case,
    # not just a plain bounding box.
    mask = np.zeros((4, 4), dtype=bool)
    mask[0:3, 0] = True
    mask[2, 0:3] = True
    ys, xs = np.nonzero(mask)

    path = CanvasArtist._maskOutlinePath(mask, ys, xs)

    assert path.elementCount() > 0
    # Every point should land exactly on the local integer grid - the
    # path is unscaled cell-space, not pre-multiplied by any screen cell
    # size or origin (the caller applies that as a transform instead).
    for i in range(path.elementCount()):
        element = path.elementAt(i)
        assert element.x == int(element.x)
        assert element.y == int(element.y)


def test_mask_outline_path_chains_an_l_shape_into_one_closed_loop_too():
    mask = np.zeros((4, 4), dtype=bool)
    mask[0:3, 0] = True
    mask[2, 0:3] = True
    ys, xs = np.nonzero(mask)

    path = CanvasArtist._maskOutlinePath(mask, ys, xs)

    points = [(path.elementAt(i).x, path.elementAt(i).y) for i in range(path.elementCount())]
    assert points[0] == points[-1]
    # One single loop, not several disconnected subpaths - every corner
    # of the L's 6-sided silhouette, visited once, then the closing
    # return to the start.
    assert len(set(points)) == 6
    assert path.elementCount() == 7


def test_mask_outline_path_does_not_raise_on_a_diagonal_only_pinch_point():
    # Two cells touching only at one shared corner (what WandTool's
    # `diagonal` option lets through - see GREEN_DIAGONAL_PAIR) put four
    # boundary edges at that single point instead of the usual two -
    # _maskOutlinePath's own docstring says this doesn't try to resolve
    # which pair "really" belongs to which cell, just that it has to
    # produce something gapless and not crash.
    mask = np.zeros((4, 4), dtype=bool)
    mask[1, 1] = True
    mask[2, 2] = True
    ys, xs = np.nonzero(mask)

    path = CanvasArtist._maskOutlinePath(mask, ys, xs)  # should not raise

    # Every edge still gets traced - 6 merged runs here (the "waist"
    # edges where the two cells meet merge into one each, horizontally
    # and vertically, since _mergeRuns only looks at numeric adjacency
    # on a shared grid line and can't tell the two cells apart - still a
    # valid, fully-covering closed loop, just one that crosses itself at
    # the pinch point rather than treating it as two separate squares).
    assert path.elementCount() == 7
    points = [(path.elementAt(i).x, path.elementAt(i).y) for i in range(path.elementCount())]
    assert points[0] == points[-1]


def test_mask_outline_path_skips_interior_edges_of_a_solid_block():
    mask = np.ones((3, 3), dtype=bool)
    ys, xs = np.nonzero(mask)

    path = CanvasArtist._maskOutlinePath(mask, ys, xs)

    # A solid 3x3 block's silhouette is just its own perimeter, chained
    # into one closed loop (not four disconnected runs - see
    # _maskOutlinePath's own note on why dashing needs it continuous):
    # a moveTo, three corners, then closeSubpath's own implicit lineTo
    # back to the start.
    assert path.elementCount() == 5


def test_mask_outline_path_chains_runs_into_one_closed_loop():
    mask = np.ones((3, 3), dtype=bool)
    ys, xs = np.nonzero(mask)

    path = CanvasArtist._maskOutlinePath(mask, ys, xs)

    points = [(path.elementAt(i).x, path.elementAt(i).y) for i in range(path.elementCount())]
    assert points[0] == points[-1]  # closed back to its own start
    assert len(set(points)) == 4  # exactly the block's 4 corners, each visited once


# -- CanvasArtist selection overlay caching -----------------------------------

def test_selection_overlay_cache_rebuilds_only_when_the_selection_object_changes(controller):
    artist = CanvasArtist()
    artist.bindProject(controller)
    artist.resize(100, 100)
    canvas = controller.project.canvas
    canvas.bucketSelect(RED_BLOCK[0], contiguous=True, mode="replace")

    image = QImage(100, 100, QImage.Format_ARGB32)
    painter = QPainter(image)
    artist._paintSelectionOverlay(painter, canvas, 10, artist._imageOrigin())
    painter.end()

    firstPath = artist._marchLocalPath
    firstFill = artist._fillImage
    assert artist._selectionCacheRef is canvas.selection

    # Repainting against the exact same selection object (e.g. a pure
    # marching-ants animation tick) must not rebuild either cache.
    painter = QPainter(image)
    artist._paintSelectionOverlay(painter, canvas, 10, artist._imageOrigin())
    painter.end()
    assert artist._marchLocalPath is firstPath
    assert artist._fillImage is firstFill

    # A real edit reassigns canvas.selection to a new array (see
    # Canvas.alterSelection) - the cache must pick that up.
    canvas.bucketSelect(RED_ISLAND, contiguous=True, mode="add")
    painter = QPainter(image)
    artist._paintSelectionOverlay(painter, canvas, 10, artist._imageOrigin())
    painter.end()
    assert artist._selectionCacheRef is canvas.selection
    assert artist._marchLocalPath is not firstPath
    assert artist._fillImage is not firstFill


def test_selection_overlay_paints_nothing_when_selection_is_empty(controller):
    artist = CanvasArtist()
    artist.bindProject(controller)
    artist.resize(100, 100)
    canvas = controller.project.canvas
    assert not canvas.selection.any()

    image = QImage(100, 100, QImage.Format_ARGB32)
    painter = QPainter(image)
    artist._paintSelectionOverlay(painter, canvas, 10, artist._imageOrigin())  # should not raise
    painter.end()
    assert artist._selectionCacheRef is None


# -- CanvasArtist brush preview -----------------------------------------------

def test_set_and_clear_brush_preview_updates_state():
    artist = CanvasArtist()
    assert artist._brushPreview is None

    artist.setBrushPreview(2, 3, 4)
    assert artist._brushPreview == (2, 3, 4)

    artist.clearBrushPreview()
    assert artist._brushPreview is None


def test_paint_brush_preview_matches_canvas_brush_outline_mask_without_raising(controller):
    artist = CanvasArtist()
    artist.bindProject(controller)
    artist.resize(100, 100)
    canvas = controller.project.canvas
    artist.setBrushPreview(2, 2, 1)

    image = QImage(100, 100, QImage.Format_ARGB32)
    painter = QPainter(image)
    artist._paintBrushPreview(painter, canvas, artist._cellSize(), artist._imageOrigin())  # should not raise
    painter.end()


def test_paint_brush_preview_uses_both_ink_and_paper_so_it_stays_visible_on_any_pixel(controller):
    # A single ink-colored line disappeared entirely over a near-black
    # canvas pixel - the dashed ink ants now march over a solid paper
    # base (see _paintBrushPreview) instead, so at least one of the two
    # always contrasts against whatever's underneath.
    artist = CanvasArtist()
    artist.bindProject(controller)
    artist.resize(240, 240)
    canvas = controller.project.canvas
    artist.setBrushPreview(3, 3, 3)

    image = QImage(240, 240, QImage.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    cell = artist._cellSize()
    origin = artist._imageOrigin()
    artist._paintBrushPreview(painter, canvas, cell, origin)
    painter.end()

    ink = QColor(artist._theme.ink).getRgb()[:3]
    paper = QColor(artist._theme.paper).getRgb()[:3]
    pixels = {image.pixelColor(x, y).getRgb()[:3] for y in range(240) for x in range(240)}
    assert ink in pixels
    assert paper in pixels


def test_paint_brush_preview_ink_and_paper_pixel_counts_are_roughly_equal(controller):
    # Not just "both colors appear" (see above) - genuinely close to a
    # 50/50 split by pixel count. Regression coverage for a real,
    # previously-shipped bug that looked fine by eye: Qt's SquareCap
    # extends every individual dash half a pen-width past its own two
    # ends (eating into the gap on both sides), which measured as a
    # ~2:1 ink:paper split on this exact shape - fixed by using
    # Qt.FlatCap (no overshoot bias) for the dashed pass instead, with
    # corner coverage handled separately by _paintCornerPatches (see its
    # own tests below) rather than by cap-style overshoot.
    artist = CanvasArtist()
    artist.bindProject(controller)
    artist.resize(240, 240)
    canvas = controller.project.canvas
    artist.setBrushPreview(3, 3, 3)

    image = QImage(240, 240, QImage.Format_ARGB32)
    image.fill(QColor(255, 0, 255))  # a sentinel distinct from both ants colors
    painter = QPainter(image)
    cell = artist._cellSize()
    origin = artist._imageOrigin()
    artist._paintBrushPreview(painter, canvas, cell, origin)
    painter.end()

    rgb = image.convertToFormat(QImage.Format_RGB888)
    ink = QColor(artist._theme.ink).getRgb()[:3]
    paper = QColor(artist._theme.paper).getRgb()[:3]
    inkCount = paperCount = 0
    for y in range(240):
        for x in range(240):
            c = rgb.pixelColor(x, y).getRgb()[:3]
            if c == ink:
                inkCount += 1
            elif c == paper:
                paperCount += 1
    assert inkCount > 0 and paperCount > 0
    assert 0.85 <= inkCount / paperCount <= 1.15


def test_paint_brush_preview_is_a_no_op_without_a_preview_set(controller):
    artist = CanvasArtist()
    artist.bindProject(controller)
    artist.resize(100, 100)
    canvas = controller.project.canvas

    image = QImage(100, 100, QImage.Format_ARGB32)
    painter = QPainter(image)
    artist._paintBrushPreview(painter, canvas, artist._cellSize(), artist._imageOrigin())  # should not raise
    painter.end()


def test_brush_preview_cache_rebuilds_only_when_row_col_radius_changes(controller):
    artist = CanvasArtist()
    artist.bindProject(controller)
    artist.resize(100, 100)
    canvas = controller.project.canvas
    cell, origin = artist._cellSize(), artist._imageOrigin()

    artist.setBrushPreview(2, 2, 1)
    image = QImage(100, 100, QImage.Format_ARGB32)
    painter = QPainter(image)
    artist._paintBrushPreview(painter, canvas, cell, origin)
    painter.end()
    firstPath = artist._brushPreviewPath
    assert artist._brushPreviewCacheKey == (2, 2, 1)

    # Same (row, col, radius) - a pure marching-ants tick, no actual
    # movement - must not retrace the boundary.
    painter = QPainter(image)
    artist._paintBrushPreview(painter, canvas, cell, origin)
    painter.end()
    assert artist._brushPreviewPath is firstPath

    # A real move to a different cell must rebuild it.
    artist.setBrushPreview(3, 3, 1)
    painter = QPainter(image)
    artist._paintBrushPreview(painter, canvas, cell, origin)
    painter.end()
    assert artist._brushPreviewCacheKey == (3, 3, 1)
    assert artist._brushPreviewPath is not firstPath


# -- CanvasArtist._paintCornerPatches -----------------------------------------

def test_path_subpath_vertices_reports_cumulative_length_around_a_closed_square():
    mask = np.ones((2, 2), dtype=bool)
    ys, xs = np.nonzero(mask)
    path = CanvasArtist._maskOutlinePath(mask, ys, xs)

    subpaths = CanvasArtist._pathSubpathVertices(path)
    assert len(subpaths) == 1
    vertices = subpaths[0]

    # A 2x2 block's outline is a 2x2 square, perimeter 8, closed back to
    # its own start - the first and last vertex share a point, but the
    # last one's cumulative length should be the full perimeter, not 0.
    assert vertices[0][1] == 0.0
    assert vertices[-1][0] == vertices[0][0]
    assert vertices[-1][1] == 8.0


def test_paint_corner_patches_force_every_vertex_square_to_one_uniform_color(controller):
    # The defect this exists to fix (reported directly, pixel-counted by
    # the user, not eyeballed): a dash's on/off color transition landing
    # right at a path corner used to leave that corner's pen-width-sized
    # footprint half one color, half the other - a visibly split 2x2-ish
    # block - because Qt.SquareCap's overshoot only ever extends a dash
    # in its own direction of travel, so the incoming and outgoing dashes
    # at a corner can each only cover part of it. This checks the actual
    # guarantee _paintCornerPatches makes instead: every pixel strictly
    # inside the exact square it paints at a vertex matches that one
    # computed color, for every vertex, across a full animation cycle -
    # not just "the overall ink:paper ratio looks right" (see the
    # ink/paper ratio test above), which an aggregate count can satisfy
    # while still hiding a localized split like this one.
    artist = CanvasArtist()
    artist.bindProject(controller)
    artist.resize(240, 240)
    canvas = controller.project.canvas
    artist.setBrushPreview(3, 3, 3)

    cell = artist._cellSize()
    origin = artist._imageOrigin()
    ink = QColor(artist._theme.ink).getRgb()[:3]
    paper = QColor(artist._theme.paper).getRgb()[:3]

    for offset in (0.0, 1.0, 2.0, 3.0, 4.0, 5.0):
        artist._marchOffset = offset
        image = QImage(240, 240, QImage.Format_ARGB32)
        painter = QPainter(image)
        artist._paintBrushPreview(painter, canvas, cell, origin)
        painter.end()
        rgb = image.convertToFormat(QImage.Format_RGB888)

        path = artist._brushPreviewPath
        penWidth = artist._antsPenWidth(cell)
        onLength = artist._BRUSH_DASH_PATTERN[0] * penWidth
        period = sum(artist._BRUSH_DASH_PATTERN) * penWidth
        offsetLength = offset * penWidth
        half = penWidth / 2.0

        for vertices in CanvasArtist._pathSubpathVertices(path):
            seen = set()
            for point, length in vertices:
                # Mirrors _paintCornerPatches' own dedup: a closed loop's
                # last vertex is the same point as its first (the seam),
                # which can legitimately compute a different phase on its
                # second, full-perimeter-length visit if the pattern's
                # period doesn't evenly divide the loop's total length -
                # only the first (moveTo) visit is the one actually
                # painted, so that's the one this test has to check too.
                key = (round(point.x(), 6), round(point.y(), 6))
                if key in seen:
                    continue
                seen.add(key)
                effective = (length + offsetLength) % period
                expected = ink if effective < onLength else paper
                leftLocal = point.x() + artist._brushPreviewLeft
                topLocal = point.y() + artist._brushPreviewTop
                x0 = int((leftLocal - half) * cell + origin.x()) + 1
                y0 = int((topLocal - half) * cell + origin.y()) + 1
                x1 = int((leftLocal + half) * cell + origin.x())
                y1 = int((topLocal + half) * cell + origin.y())
                for py in range(max(0, y0), min(240, y1)):
                    for px in range(max(0, x0), min(240, x1)):
                        assert rgb.pixelColor(px, py).getRgb()[:3] == expected


def test_paint_brush_preview_has_no_sandwiched_background_gaps_at_a_corner(controller):
    # A sentinel pixel strictly between two painted (ink or paper) pixels
    # along a scan line is real evidence of a coverage hole - not just
    # "near the edge of the painted silhouette", which a naive box check
    # around a corner vertex would false-positive on for a thin stroke.
    artist = CanvasArtist()
    artist.bindProject(controller)
    artist.resize(240, 240)
    canvas = controller.project.canvas
    artist.setBrushPreview(3, 3, 3)

    cell = artist._cellSize()
    origin = artist._imageOrigin()
    sentinel = (255, 0, 255)

    for offset in (0.0, 1.0, 2.0, 3.0, 4.0, 5.0):
        artist._marchOffset = offset
        image = QImage(240, 240, QImage.Format_ARGB32)
        image.fill(QColor(*sentinel))
        painter = QPainter(image)
        artist._paintBrushPreview(painter, canvas, cell, origin)
        painter.end()
        rgb = image.convertToFormat(QImage.Format_RGB888)

        grid = [[rgb.pixelColor(x, y).getRgb()[:3] == sentinel for x in range(240)] for y in range(240)]
        for y in range(240):
            for x in range(1, 239):
                if grid[y][x] and not grid[y][x - 1] and not grid[y][x + 1]:
                    pytest.fail(f"sandwiched gap at ({x}, {y}), offset={offset}")
        for x in range(240):
            for y in range(1, 239):
                if grid[y][x] and not grid[y - 1][x] and not grid[y + 1][x]:
                    pytest.fail(f"sandwiched gap at ({x}, {y}), offset={offset}")


# -- CanvasArtist marching-ants timer gating ----------------------------------

def test_advance_march_is_a_no_op_with_neither_selection_nor_brush_preview(controller):
    artist = CanvasArtist()
    artist.bindProject(controller)
    assert not controller.project.canvas.selection.any()
    assert artist._brushPreview is None

    artist._advanceMarch()

    assert artist._marchOffset == 0.0


def test_advance_march_animates_for_an_active_brush_preview_even_without_a_selection(controller):
    artist = CanvasArtist()
    artist.bindProject(controller)
    assert not controller.project.canvas.selection.any()
    artist.setBrushPreview(2, 2, 1)

    artist._advanceMarch()

    assert artist._marchOffset == 1.0


def test_advance_march_still_animates_for_a_selection_without_a_brush_preview(controller):
    artist = CanvasArtist()
    artist.bindProject(controller)
    controller.project.canvas.bucketSelect(RED_BLOCK[0], contiguous=True, mode="replace")
    assert artist._brushPreview is None

    artist._advanceMarch()

    assert artist._marchOffset == 1.0


# -- CanvasArea brush preview wiring ------------------------------------------

@pytest.fixture
def appController(tmp_path):
    path = tmp_path / "sprite.png"
    Image.fromarray(make_pixel_art()).save(path)
    app = AppController()
    app.newProjectFromImage(str(path))
    return app


@pytest.fixture
def canvasArea(appController):
    area = CanvasArea(appController)
    area.resize(120, 120)
    area.bindProject(appController.activeController)
    return area


def _moveTo(widget, x, y):
    pos = QPointF(x, y)
    event = QMouseEvent(QEvent.MouseMove, pos, pos, Qt.NoButton, Qt.NoButton, Qt.NoModifier)
    QCoreApplication.sendEvent(widget, event)


def test_hovering_with_brush_tool_active_sets_the_preview(appController, canvasArea):
    appController.toolController.setActiveTool("brushSelect")

    _moveTo(canvasArea, 60, 60)

    assert canvasArea.artist._brushPreview is not None


def test_hovering_with_wand_tool_active_does_not_set_a_preview(appController, canvasArea):
    appController.toolController.setActiveTool("wand")

    _moveTo(canvasArea, 60, 60)

    assert canvasArea.artist._brushPreview is None


def test_switching_away_from_brush_clears_an_existing_preview(appController, canvasArea):
    appController.toolController.setActiveTool("brushSelect")
    _moveTo(canvasArea, 60, 60)
    assert canvasArea.artist._brushPreview is not None

    appController.toolController.setActiveTool("wand")

    assert canvasArea.artist._brushPreview is None


def test_hovering_outside_the_canvas_clears_the_preview(appController, canvasArea):
    appController.toolController.setActiveTool("brushSelect")
    _moveTo(canvasArea, 60, 60)
    assert canvasArea.artist._brushPreview is not None

    _moveTo(canvasArea, -999, -999)  # nowhere near a real canvas position

    assert canvasArea.artist._brushPreview is None


def test_leaving_the_widget_clears_the_preview(appController, canvasArea):
    appController.toolController.setActiveTool("brushSelect")
    _moveTo(canvasArea, 60, 60)
    assert canvasArea.artist._brushPreview is not None

    QCoreApplication.sendEvent(canvasArea, QEvent(QEvent.Leave))

    assert canvasArea.artist._brushPreview is None
