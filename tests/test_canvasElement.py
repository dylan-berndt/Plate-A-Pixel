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


def test_mask_outline_path_skips_interior_edges_of_a_solid_block():
    mask = np.ones((3, 3), dtype=bool)
    ys, xs = np.nonzero(mask)

    path = CanvasArtist._maskOutlinePath(mask, ys, xs)

    # A solid 3x3 block's silhouette is just its own perimeter - the
    # four merged runs (top/bottom/left/right), 2 points each.
    assert path.elementCount() == 8


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
    # canvas pixel - the outline alternates ink/paper dashes instead (see
    # _BRUSH_DASH_PATTERN), so at least one of the two always contrasts
    # against whatever's underneath.
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


def test_paint_brush_preview_is_a_no_op_without_a_preview_set(controller):
    artist = CanvasArtist()
    artist.bindProject(controller)
    artist.resize(100, 100)
    canvas = controller.project.canvas

    image = QImage(100, 100, QImage.Format_ARGB32)
    painter = QPainter(image)
    artist._paintBrushPreview(painter, canvas, artist._cellSize(), artist._imageOrigin())  # should not raise
    painter.end()


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
