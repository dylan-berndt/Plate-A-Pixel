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
    # 50/50 split by pixel count. Regression coverage for two real,
    # previously-shipped bugs that both looked fine by eye: Qt's default
    # SquareCap extends every individual dash half a pen-width past its
    # own two ends (eating into the gap on both sides), which measured
    # as a ~2:1 ink:paper split on this exact shape before Qt.FlatCap
    # was applied to the dashed pass - and is distinct from
    # _maskOutlinePath's own corner-coverage fix, which didn't touch
    # this ratio at all.
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
