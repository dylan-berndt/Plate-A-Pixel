import numpy as np
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtGui import QPainter, QImage, QColor, QPen, QPainterPath
from PySide6.QtCore import Qt, QRectF, QPointF, QTimer, Signal

from .ui import *
from .data import *

MIN_ZOOM = 0.1
MAX_ZOOM = 20.0
ZOOM_STEP = 1.15


class CanvasArtist(QWidget):
    """Renders one project's pixel grid and owns the view transform (zoom/
    pan) - CanvasArea (below) only ever turns a mouse event into a widget-
    local point and hands it here for a canvas-position lookup, or asks
    for a repaint.

    Renders straight from canvas.map through canvas.palette.colors rather
    than canvas.image - canvas.image is only the array Canvas was built
    from and never gets touched again (see canvas.py), so drawing from it
    directly would keep showing a color's *original* RGB after a recolor
    (CanvasController.recolorColor only updates the Palette entry)."""

    # Explicit dash pattern (in pen-width units: 3 on, 2 off), not the
    # predefined Qt.DashLine - its exact period isn't part of the public
    # API, and _advanceMarch needs to know the true period to wrap the
    # offset at exactly the right value (wrapping at the wrong value made
    # the animation visibly jump/"bounce" once per cycle instead of
    # looping smoothly).
    _DASH_PATTERN = [3.0, 2.0]

    def __init__(self, theme: Theme = None, **kwargs):
        super().__init__(**kwargs)
        self._theme = theme or Theme()
        self._projectController = None

        # Zoom is expressed as "how much of the viewport's shorter side the
        # image's longer side fills" - 1.0 means the whole image is exactly
        # visible; position is a screen-pixel pan offset on top of that.
        self.zoom = 1.0
        self.position = Vector2(0, 0)

        self.setMouseTracking(True)
        self.setAutoFillBackground(False)

        # Marching-ants animation: advances the dash offset on a timer and
        # only repaints while there's actually a selection to animate, so
        # an idle canvas isn't repainting itself in the background forever.
        self._marchOffset = 0.0
        self._marchTimer = QTimer(self)
        self._marchTimer.setInterval(80)
        self._marchTimer.timeout.connect(self._advanceMarch)
        self._marchTimer.start()

    def _advanceMarch(self):
        if self._projectController is None:
            return
        if not self._projectController.project.canvas.selection.any():
            return
        self._marchOffset = (self._marchOffset + 1.0) % sum(self._DASH_PATTERN)
        self.update()

    def bindProject(self, projectController):
        # Redraw on anything that can change what's on screen: a
        # selection edit, a recolor (palette.setColor doesn't touch
        # canvas.map, but _paintImage reads through the palette every
        # frame - see its docstring - so this still needs to repaint),
        # or a mesh recompute finishing (height edits change nothing
        # visible in 2D today, but cost nothing to also redraw on).
        if self._projectController is not None:
            self._projectController.selectionChanged.disconnect(self.update)
            self._projectController.paletteChanged.disconnect(self.update)
            self._projectController.meshReady.disconnect(self.update)
        self._projectController = projectController
        if projectController is not None:
            projectController.selectionChanged.connect(self.update)
            projectController.paletteChanged.connect(self.update)
            projectController.meshReady.connect(self.update)
        self.resetView()

    def resetView(self):
        self.zoom = 1.0
        self.position = Vector2(0, 0)
        self.update()

    def zoomBy(self, factor, anchor: QPointF = None):
        newZoom = min(MAX_ZOOM, max(MIN_ZOOM, self.zoom * factor))
        if anchor is not None:
            before = self._widgetToImage(anchor)
        self.zoom = newZoom
        if anchor is not None:
            after = self._widgetToImage(anchor)
            cell = self._cellSize()
            if cell > 0:
                self.position = Vector2(
                    self.position.x - (before[0] - after[0]) * cell,
                    self.position.y - (before[1] - after[1]) * cell,
                )
        self.update()

    def panBy(self, dx, dy):
        self.position = Vector2(self.position.x + dx, self.position.y + dy)
        self.update()

    # -- geometry ----------------------------------------------------------

    def _canvasShape(self):
        if self._projectController is None:
            return None
        return self._projectController.project.canvas.map.shape

    def _cellSize(self):
        shape = self._canvasShape()
        if shape is None:
            return 0
        rows, cols = shape
        longSide = max(rows, cols)
        if longSide == 0:
            return 0
        viewport = min(self.width(), self.height())
        return (self.zoom * viewport) / longSide

    def _imageOrigin(self):
        shape = self._canvasShape()
        cell = self._cellSize()
        if shape is None or cell <= 0:
            return QPointF(0, 0)
        rows, cols = shape
        imgW, imgH = cell * cols, cell * rows
        cx = self.width() / 2 + self.position.x
        cy = self.height() / 2 + self.position.y
        return QPointF(cx - imgW / 2, cy - imgH / 2)

    def _widgetToImage(self, point: QPointF):
        """Widget-local point -> fractional (col, row), unclamped - used
        internally to keep the point under the cursor fixed while
        zooming."""
        cell = self._cellSize()
        origin = self._imageOrigin()
        if cell <= 0:
            return (0, 0)
        return ((point.x() - origin.x()) / cell, (point.y() - origin.y()) / cell)

    def mouseToCanvas(self, point: QPointF):
        """Widget-local point -> (row, col), or None outside the canvas."""
        shape = self._canvasShape()
        if shape is None:
            return None
        rows, cols = shape
        col, row = self._widgetToImage(point)
        row, col = int(row), int(col)
        if 0 <= row < rows and 0 <= col < cols:
            return (row, col)
        return None

    def clampToCanvas(self, point: QPointF):
        """Same as mouseToCanvas but clamps into bounds instead of
        returning None - lets a drag continue past the canvas edge like a
        normal paint app, instead of a gesture going dead the moment the
        cursor leaves the image."""
        shape = self._canvasShape()
        if shape is None:
            return None
        rows, cols = shape
        col, row = self._widgetToImage(point)
        row = min(rows - 1, max(0, int(row)))
        col = min(cols - 1, max(0, int(col)))
        return (row, col)

    # -- painting ------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        self._paintChecker(painter)

        pc = self._projectController
        if pc is not None:
            canvas = pc.project.canvas
            cell = self._cellSize()
            origin = self._imageOrigin()
            if cell > 0:
                self._paintImage(painter, canvas, cell, origin)
                self._paintSelectionOverlay(painter, canvas, cell, origin)
                self._paintOverlay(painter, canvas, cell, origin)
        else:
            self._paintEmptyState(painter)
        painter.end()

    def _paintOverlay(self, painter: QPainter, canvas, cell, origin):
        """Hook for a subclass to draw extra per-cell content above the
        selection overlay - a no-op here; see LayerCanvasArtist's height
        labels below for the one thing that currently uses it."""
        pass

    def _paintEmptyState(self, painter: QPainter):
        theme = self._theme
        text = "Open an image to get started"

        font = painter.font()
        font.setPointSizeF(max(9.0, font.pointSizeF()))
        painter.setFont(font)

        metrics = painter.fontMetrics()
        textRect = metrics.boundingRect(text)
        paddingX, paddingY = 24, 16
        boxWidth = textRect.width() + paddingX * 2
        boxHeight = textRect.height() + paddingY * 2
        box = QRectF(
            (self.width() - boxWidth) / 2, (self.height() - boxHeight) / 2, boxWidth, boxHeight,
        )

        painter.setPen(QPen(QColor(theme.ink), 1.5))
        painter.setBrush(QColor(theme.paper))
        painter.drawRoundedRect(box, 8, 8)

        painter.setPen(QColor(theme.clay500))
        painter.drawText(box, Qt.AlignCenter, text)

    def _paintChecker(self, painter: QPainter):
        theme = self._theme
        size = 11
        painter.fillRect(self.rect(), QColor(theme.paper))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(theme.clay200))
        row = 0
        y = 0
        while y < self.height():
            x = size if row % 2 else 0
            while x < self.width():
                painter.drawRect(x, y, size, size)
                x += size * 2
            y += size
            row += 1

    def _paintImage(self, painter: QPainter, canvas, cell, origin):
        rows, cols = canvas.map.shape
        # canvas.map indexes into the palette; palette.colors[map] broadcasts
        # that into an (rows, cols, 3) RGB grid reflecting any live recolor.
        rgb = np.ascontiguousarray(canvas.palette.colors[canvas.map], dtype=np.uint8)
        self._imageBuffer = rgb  # keep alive - QImage doesn't copy the buffer it wraps
        image = QImage(rgb.data, cols, rows, rgb.strides[0], QImage.Format_RGB888)
        target = QRectF(origin.x(), origin.y(), cell * cols, cell * rows)
        painter.drawImage(target, image)

    def _paintSelectionOverlay(self, painter: QPainter, canvas, cell, origin):
        selection = canvas.selection
        if not selection.any():
            return

        fill = QColor(self._theme.glaze)
        fill.setAlphaF(0.38)
        painter.setPen(Qt.NoPen)
        painter.setBrush(fill)
        ys, xs = np.nonzero(selection)
        for y, x in zip(ys.tolist(), xs.tolist()):
            painter.drawRect(QRectF(origin.x() + x * cell, origin.y() + y * cell, cell, cell))

        # Pen width (and, since Qt expresses dash lengths in pen-width
        # units, the dashes with it) scales with the current zoom level:
        # a fixed screen-pixel pen looks chunky relative to tiny
        # zoomed-out cells and thin relative to huge zoomed-in ones.
        penWidth = min(3.0, max(1.0, cell * 0.12))
        pen = QPen(QColor(self._theme.glaze))
        pen.setWidthF(penWidth)
        pen.setDashPattern(self._DASH_PATTERN)
        pen.setDashOffset(self._marchOffset)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(self._selectionOutlinePath(selection, ys, xs, cell, origin))

    def _selectionOutlinePath(self, selection, ys, xs, cell, origin):
        """The selection's actual silhouette, not its bounding box: each
        selected cell contributes only the sides that border an
        unselected cell (or the canvas edge), so the ants hug the real
        shape - a plain filled block's interior edges are skipped, but an
        L-shape or a diagonal pair still outlines correctly.

        Adjacent same-line edges are merged into one continuous run
        before being added to the path (one moveTo/lineTo per run, not
        per cell) so the dash pattern flows continuously along a whole
        straight stretch instead of restarting at every single cell -
        every restart shares the same animated phase, so a run shorter
        than one dash+gap period would flip between fully drawn and fully
        blank in lockstep with its neighbors as the phase animated,
        which is what read as flickering once cells got small enough
        (zoomed out) that a single edge no longer spanned a full dash
        cycle."""
        rows, cols = selection.shape
        horizontal, vertical = {}, {}
        for y, x in zip(ys.tolist(), xs.tolist()):
            if y == 0 or not selection[y - 1, x]:
                horizontal.setdefault(y, []).append(x)
            if y == rows - 1 or not selection[y + 1, x]:
                horizontal.setdefault(y + 1, []).append(x)
            if x == 0 or not selection[y, x - 1]:
                vertical.setdefault(x, []).append(y)
            if x == cols - 1 or not selection[y, x + 1]:
                vertical.setdefault(x + 1, []).append(y)

        path = QPainterPath()
        for lineY, xPositions in horizontal.items():
            for start, end in self._mergeRuns(xPositions):
                path.moveTo(origin.x() + start * cell, origin.y() + lineY * cell)
                path.lineTo(origin.x() + end * cell, origin.y() + lineY * cell)
        for lineX, yPositions in vertical.items():
            for start, end in self._mergeRuns(yPositions):
                path.moveTo(origin.x() + lineX * cell, origin.y() + start * cell)
                path.lineTo(origin.x() + lineX * cell, origin.y() + end * cell)
        return path

    @staticmethod
    def _mergeRuns(positions):
        """Sorted, deduped run-length merge: [0, 1, 2, 4, 5] ->
        [(0, 3), (4, 6)] - consecutive integers collapse into one
        (start, end) span."""
        runs = []
        for p in sorted(set(positions)):
            if runs and runs[-1][1] == p:
                runs[-1] = (runs[-1][0], p + 1)
            else:
                runs.append((p, p + 1))
        return runs


class LayerCanvasArtist(CanvasArtist):
    """Renders canvas.layers instead of canvas.map/palette: a grayscale
    read of which height each pixel is assigned to (darker = lower,
    lighter = higher). A pixel with no height assigned yet (layers < 1 -
    the same "empty" test pixelPlan.py's own PixelPlan.empty uses) gets a
    flat, out-of-range tone instead of being read as a real low height.
    Height numbers are drawn on top when showLabels is on (see the View
    menu's "Show Layer Numbers" toggle in appWindow.py), skipped below a
    cell size where text would just be unreadable clutter.

    Only what a pixel is filled with differs from CanvasArtist - the
    selection overlay/marching ants and all mouse routing (CanvasArea,
    below) are inherited unchanged, so the same Wand/Brush tools that
    select on the color canvas select identically here."""

    LOW_GRAY = 60
    HIGH_GRAY = 255
    UNASSIGNED_GRAY = 235
    # The layer canvas shares its pane with the color canvas (see
    # AppWindow's 2D page), so its cells are routinely half the width
    # they'd be as a full-pane view - a threshold tuned for a full pane
    # (originally 14) left labels never appearing for anything but a
    # tiny canvas. 6 is close to the floor where a single digit is still
    # legible at all.
    MIN_LABEL_CELL = 6

    def __init__(self, theme: Theme = None, **kwargs):
        super().__init__(theme=theme, **kwargs)
        self.showLabels = False
        self._layerRange = None

    def setShowLabels(self, show: bool):
        self.showLabels = bool(show)
        self.update()

    @staticmethod
    def _hexToRgb(hexColor):
        return tuple(int(hexColor[i:i + 2], 16) for i in (1, 3, 5))

    def _heightGray(self, value, lo, hi):
        if hi == lo:
            return self.UNASSIGNED_GRAY
        return int(self.LOW_GRAY + (value - lo) * (self.HIGH_GRAY - self.LOW_GRAY) / (hi - lo))

    def _paintImage(self, painter: QPainter, canvas, cell, origin):
        rows, cols = canvas.layers.shape
        layers = canvas.layers
        assigned = layers >= 1

        rgb = np.empty((rows, cols, 3), dtype=np.uint8)
        rgb[..., 0], rgb[..., 1], rgb[..., 2] = self._hexToRgb(self._theme.clay300)

        self._layerRange = None
        if assigned.any():
            vals = layers[assigned]
            lo, hi = int(vals.min()), int(vals.max())
            self._layerRange = (lo, hi)
            span = hi - lo
            gray = (
                np.full_like(vals, self.UNASSIGNED_GRAY, dtype=np.uint8) if span == 0 else
                (self.LOW_GRAY + (vals - lo) * ((self.HIGH_GRAY - self.LOW_GRAY) / span)).astype(np.uint8)
            )
            for channel in range(3):
                rgb[..., channel][assigned] = gray

        self._imageBuffer = rgb  # keep alive - QImage doesn't copy the buffer it wraps
        image = QImage(rgb.data, cols, rows, rgb.strides[0], QImage.Format_RGB888)
        target = QRectF(origin.x(), origin.y(), cell * cols, cell * rows)
        painter.drawImage(target, image)

    def _paintOverlay(self, painter: QPainter, canvas, cell, origin):
        if not self.showLabels or cell < self.MIN_LABEL_CELL or self._layerRange is None:
            return
        lo, hi = self._layerRange
        layers = canvas.layers
        ys, xs = np.nonzero(layers >= 1)

        font = painter.font()
        font.setPointSizeF(max(4.0, min(11.0, cell * 0.45)))
        painter.setFont(font)

        for y, x in zip(ys.tolist(), xs.tolist()):
            value = int(layers[y, x])
            gray = self._heightGray(value, lo, hi)
            painter.setPen(QColor("#101010" if gray > 140 else "#f5f0ea"))
            rect = QRectF(origin.x() + x * cell, origin.y() + y * cell, cell, cell)
            painter.drawText(rect, Qt.AlignCenter, str(value))


class CanvasArea(QWidget):
    """The interactive 2D canvas panel. Turns mouse events into canvas
    positions and routes them to ToolController.press/drag/release - tool
    state itself lives on AppController.toolController (see
    utils/controllers/toolController.py), not here. Middle-mouse drag
    pans and the wheel zooms; both are handled directly against the
    artist rather than going through a tool, since they're view
    navigation, not an edit.

    `artistClass` swaps in LayerCanvasArtist (above) for the layer view
    slotted into AppWindow.setLayerCanvasArea - everything else here
    (mouse routing, pan/zoom, the fit button) is identical between the
    color and layer panes, so this is the one seam rather than a second
    near-duplicate widget class."""

    zoomChanged = Signal(float)

    def __init__(self, appController, theme: Theme = None, artistClass=CanvasArtist, **kwargs):
        super().__init__(**kwargs)
        self._appController = appController
        self._theme = theme or Theme()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.artist = artistClass(theme=self._theme)
        layout.addWidget(self.artist)

        self._fitButton = IconButton(Icons.EXPAND, onClick=self.resetView, size=26, theme=self._theme, parent=self)
        self._fitButton.move(self.width() - 38, 12)

        self._toolGestureActive = False
        self._panning = False
        self._panOrigin = None
        self._positionOrigin = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fitButton.move(self.width() - 38, 12)

    def bindProject(self, projectController):
        self.artist.bindProject(projectController)
        self.zoomChanged.emit(self.artist.zoom * 100)

    def resetView(self):
        self.artist.resetView()
        self.zoomChanged.emit(self.artist.zoom * 100)

    # -- mouse routing ----------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._panning = True
            self._panOrigin = event.position()
            self._positionOrigin = self.artist.position
            return

        if event.button() == Qt.LeftButton:
            pos = self.artist.mouseToCanvas(event.position())
            if pos is not None:
                self._toolGestureActive = True
                self._appController.toolController.press(pos)

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.position() - self._panOrigin
            self.artist.position = Vector2(
                self._positionOrigin.x + delta.x(), self._positionOrigin.y + delta.y(),
            )
            self.artist.update()
            return

        if self._toolGestureActive:
            pos = self.artist.clampToCanvas(event.position())
            if pos is not None:
                self._appController.toolController.drag(pos)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton and self._panning:
            self._panning = False
            return

        if event.button() == Qt.LeftButton and self._toolGestureActive:
            pos = self.artist.clampToCanvas(event.position())
            if pos is not None:
                self._appController.toolController.release(pos)
            self._toolGestureActive = False

    def wheelEvent(self, event):
        factor = ZOOM_STEP if event.angleDelta().y() > 0 else 1 / ZOOM_STEP
        self.artist.zoomBy(factor, anchor=event.position())
        self.zoomChanged.emit(self.artist.zoom * 100)
