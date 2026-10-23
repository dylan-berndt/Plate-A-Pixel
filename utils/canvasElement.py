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

    # BrushSelectTool's preview (see _paintBrushPreview) needs its own,
    # equal-length pattern rather than reusing _DASH_PATTERN as-is: its
    # dashed ink pass marches over a solid *paper* base, not transparency,
    # so an uneven split (like 3:2 above) would show more black than
    # white (or vice versa) instead of the equal amounts the dashes are
    # there to guarantee. _DASH_PATTERN's own 3:2 bias is fine where it's
    # used - the "off" half is just transparency there, not a second
    # color competing for equal billing.
    _BRUSH_DASH_PATTERN = [3.0, 3.0]

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

        # Outline path + fill image cached from the selection array that
        # built them (see _paintSelectionOverlay) - identity, not
        # equality: Canvas.alterSelection always reassigns self.selection
        # to a brand new array rather than mutating one in place, so a
        # plain `is` check is a free, exact "did the selection actually
        # change since last frame" test. Without this, both were being
        # rebuilt from scratch on every single marching-ants timer tick
        # (~12.5/sec) forever while any selection existed, at a cost
        # proportional to selection complexity - the animation itself only
        # ever changes _marchOffset, so that was all wasted work.
        self._selectionCacheRef = None
        self._marchLocalPath = None
        self._fillImage = None
        self._fillBuffer = None  # keep alive - QImage doesn't copy it

        # (row, col, radius) of BrushSelectTool's hover outline - see
        # setBrushPreview/clearBrushPreview, driven by CanvasArea. None
        # when the brush isn't the active tool or the pointer isn't over
        # the canvas.
        self._brushPreview = None

        # Outline path cached from the (row, col, radius) that built it -
        # same reasoning as _selectionCacheRef above, now that the brush
        # preview also redraws on every marching-ants timer tick (not
        # just mouse movement): plain tuple equality is enough here (no
        # GC-id-reuse concern like the selection array has - these are
        # just ints), since the cache only needs to miss when the brush
        # actually moves to a new cell or radius, not every animation
        # frame.
        self._brushPreviewCacheKey = None
        self._brushPreviewPath = None
        self._brushPreviewLeft = 0
        self._brushPreviewTop = 0

    def _advanceMarch(self):
        if self._projectController is None:
            return
        hasSelection = self._projectController.project.canvas.selection.any()
        if not hasSelection and self._brushPreview is None:
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

    def setBrushPreview(self, row, col, radius):
        """Called by CanvasArea as the pointer moves while BrushSelectTool
        is active - (row, col) is the cell under the cursor (clamped, so
        it keeps showing at the edge mid-drag exactly like the stamp
        itself does - see CanvasArea._updateBrushPreview)."""
        self._brushPreview = (row, col, radius)
        self.update()

    def clearBrushPreview(self):
        if self._brushPreview is not None:
            self._brushPreview = None
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
                self._paintBrushPreview(painter, canvas, cell, origin)
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

        # Rebuilt only when the selection itself has actually changed
        # since the last paint - `is`, not equality: Canvas.alterSelection
        # always reassigns self.selection to a new array rather than
        # mutating one in place (see alterSelection), so identity is a
        # free, exact staleness check. Holding the actual old array here
        # (not just id(selection)) matters: it keeps that array alive, so
        # a *different* selection array can never happen to get allocated
        # at the same id() an old, already-garbage-collected one held -
        # `is` can't be fooled that way, a bare id() comparison technically
        # could be. Both the outline path and the fill image are built
        # once in *local* grid-cell units (mask[0,0] at local (0,0), one
        # unit per cell) - view geometry (cell/origin) never invalidates
        # the cache, it's applied as a transform at draw time instead (see
        # below), so panning/zooming/resizing while a selection sits idle
        # costs nothing extra either.
        if selection is not self._selectionCacheRef:
            ys, xs = np.nonzero(selection)
            self._selectionCacheRef = selection
            self._marchLocalPath = self._maskOutlinePath(selection, ys, xs)
            self._fillImage, self._fillBuffer = self._buildFillImage(selection, self._theme.glaze)

        rows, cols = selection.shape
        painter.save()
        painter.translate(origin)
        painter.scale(cell, cell)

        painter.setPen(Qt.NoPen)
        painter.drawImage(QRectF(0, 0, cols, rows), self._fillImage)

        self._paintMarchingAnts(painter, self._marchLocalPath, cell, self._theme.glaze)
        painter.restore()

    def _paintBrushPreview(self, painter: QPainter, canvas, cell, origin):
        """BrushSelectTool's hover outline (see setBrushPreview) - the
        exact cells a click would stamp, grid-aligned, not a circle
        glyph, marching exactly like the real selection's ants above
        (same timer, same _marchOffset, same _paintMarchingAnts) rather
        than a separate static technique: ink dashes over a solid paper
        base instead of glaze dashes over a transparent one, so there
        are two real colors involved instead of one dashed color plus
        whatever's underneath - a solid dark outline alone disappeared
        entirely over a canvas pixel that's already near-black.

        The mask/path are cached by (row, col, radius) exactly like the
        selection caches by its array - see _brushPreviewCacheKey - since
        this now redraws on every animation tick (not just mouse
        movement), there's no reason to retrace the boundary when the
        brush hasn't actually moved since last frame."""
        if self._brushPreview is None:
            return

        if self._brushPreview != self._brushPreviewCacheKey:
            row, col, radius = self._brushPreview
            mask, top, left = canvas.brushOutlineMask((row, col), radius)
            ys, xs = np.nonzero(mask)
            self._brushPreviewCacheKey = self._brushPreview
            self._brushPreviewPath = self._maskOutlinePath(mask, ys, xs) if ys.size else None
            self._brushPreviewLeft = left
            self._brushPreviewTop = top

        path = self._brushPreviewPath
        if path is None:
            return

        painter.save()
        painter.translate(origin)
        painter.scale(cell, cell)
        painter.translate(self._brushPreviewLeft, self._brushPreviewTop)

        # Solid, undashed base first - not a second independently-dashed
        # pass offset to interleave with the black one (what this used to
        # do): two separately-dashed strokes could round to visibly
        # different widths under the canvas's antialiasing-off rendering,
        # since each dash's edges can land at a different sub-pixel
        # position. A plain continuous stroke has no dash edges to round
        # inconsistently, and the black ants on top are the literal same
        # dashed-pen code the real selection uses.
        #
        # This pass itself needs no explicit cap style any more - the
        # path is now continuous closed loops (see _maskOutlinePath), so
        # every real corner is a join, not a cap; Qt's SquareCap default
        # only ever applies to the open ends of a rare unclosed pinch-
        # point remnant, same as it always has for the real selection.
        # The *dashed* pass below still needs Qt.FlatCap though, and for
        # a different reason than corner coverage: cap style governs the
        # two ends of every individual dash segment, not just a
        # subpath's own absolute start/end - closeSubpath() never touched
        # that. SquareCap extends each "on" dash half a pen-width past
        # its own boundary on both sides, which eats into the "off" gap
        # on either side of it - measured on a plain straight test line,
        # SquareCap split ~2.03:1 in black's favor regardless of how many
        # corners the path had, FlatCap ~1.02:1 every time.
        solidPen = QPen(QColor(self._theme.paper))
        solidPen.setWidthF(self._antsPenWidth(cell))
        painter.setPen(solidPen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        self._paintMarchingAnts(
            painter, path, cell, self._theme.ink, dashPattern=self._BRUSH_DASH_PATTERN, capStyle=Qt.FlatCap,
        )
        painter.restore()

    def _antsPenWidth(self, cell):
        """Local-space (not device-pixel) marching-ants pen width, shared
        by the real selection outline and the brush preview's black half
        (see _paintMarchingAnts/_paintBrushPreview) so both are sized
        identically. Clamped in device-pixel terms - a fixed screen-pixel
        pen looks chunky relative to tiny zoomed-out cells and thin
        relative to huge zoomed-in ones - then divided back by `cell`
        since the path it strokes is drawn under a scale(cell, cell)
        transform, same as the path's own coordinates are."""
        return min(3.0, max(1.0, cell * 0.12)) / cell

    def _paintMarchingAnts(self, painter: QPainter, path, cell, color, dashPattern=None, capStyle=None):
        """Strokes `path` (already under the caller's translate/scale -
        see _paintSelectionOverlay/_paintBrushPreview) with `color`,
        dashed and animated via self._marchOffset - the one piece of
        drawing logic behind both the real selection's ants (the default
        _DASH_PATTERN, Qt's default cap style) and BrushSelectTool's
        preview outline's dashed half (its own equal-length
        _BRUSH_DASH_PATTERN and Qt.FlatCap - see _paintBrushPreview's own
        note on why that one needs a non-default cap style and this one
        doesn't: cap style governs every individual dash's own two ends,
        and the real selection's "off" gaps are transparent, with
        nothing there for a slightly-too-long "on" dash to visibly
        encroach on). A different pattern's own period doesn't need to
        match _DASH_PATTERN's - Qt wraps a dash offset by whatever
        pattern it's actually painting with, regardless of what modulus
        _advanceMarch happens to wrap _marchOffset itself by."""
        pen = QPen(QColor(color))
        pen.setWidthF(self._antsPenWidth(cell))
        pen.setDashPattern(dashPattern if dashPattern is not None else self._DASH_PATTERN)
        pen.setDashOffset(self._marchOffset)
        if capStyle is not None:
            pen.setCapStyle(capStyle)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

    def _buildFillImage(self, mask, fillColor, alpha=0.38):
        """A translucent-fill RGBA QImage, one pixel per mask cell,
        transparent outside it - one drawImage call (in
        _paintSelectionOverlay) instead of one drawRect per selected
        cell, which used to run at the marching-ants animation's ~12.5fps
        for as long as any selection existed, at a cost proportional to
        selection size. Returns (image, buffer) - the caller must keep
        `buffer` alive exactly like _paintImage's own _imageBuffer, since
        QImage wraps the numpy array's memory rather than copying it."""
        color = QColor(fillColor)
        r, g, b, _ = color.getRgb()
        rows, cols = mask.shape
        rgba = np.zeros((rows, cols, 4), dtype=np.uint8)
        rgba[mask] = (r, g, b, round(alpha * 255))
        image = QImage(rgba.data, cols, rows, rgba.strides[0], QImage.Format_RGBA8888)
        return image, rgba

    @staticmethod
    def _maskOutlinePath(mask, ys, xs):
        """A boolean mask's actual silhouette, not its bounding box: each
        True cell contributes only the sides that border a False cell (or
        the mask's own edge), so the outline hugs the real shape - a
        plain filled block's interior edges are skipped, but an L-shape
        or a diagonal pair still outlines correctly. Shared by the real
        selection (_paintSelectionOverlay) and BrushSelectTool's hover
        preview (_paintBrushPreview) - both are just "trace this mask's
        boundary," whether the mask is canvas.selection itself or a small
        local brush-radius mask.

        Built in local, unscaled grid-cell units - mask[0,0] at path-space
        (0,0), one unit per cell - not screen pixels; the caller applies
        whatever translate/scale maps that onto the canvas (see both
        paint methods above). `ys`/`xs` are mask's own np.nonzero(mask),
        passed in since every caller already has them.

        Adjacent same-line edges are first merged into single runs (one
        straight span per run, not per cell), then runs sharing an
        endpoint are chained into one continuous subpath per connected
        loop of the boundary, closed back to its own start with
        closeSubpath() - not left as one disconnected moveTo/lineTo pair
        per run, which is what this used to do. That mattered for two
        real, previously-shipped-and-reported bugs: a dashed pen draws
        each subpath independently, restarting its dash phase at 0 and
        capping (not joining) its two ends - every stair-step corner was
        both a fresh dash-phase reset (an "on" segment ending one run and
        a new one starting the next could land on unrelated phases,
        making same-color runs across a corner look randomly too long or
        too short) and a capped gap (Qt caps, unlike joins, can leave the
        outside of a corner uncovered - no cap style tuning fixes that
        for every corner, since which corners are convex versus concave
        isn't fixed, it alternates around the loop). One continuous
        subpath per loop fixes both at once: dashing flows through every
        corner's actual join instead of resetting, and a join - any join
        style - never leaves the gap a cap can.

        Chaining can't always find one clean per-region loop: two cells
        that only touch at a single pixel corner (a diagonal-only pinch,
        like the Wand's own `diagonal` option lets through) have their
        "waist" edges - each cell's edge closest to the other - fall on
        the same grid line at numerically adjacent positions, so
        _mergeRuns (which only sees numbers, not which cell an edge
        belongs to) merges them into one straight run that happens to
        pass *through* the pinch point rather than ending there. The
        chained path still ends up as one single closed loop, it just
        crosses itself at that point - visually a figure-eight/hourglass
        through the two cells, rather than two separate squares. Still
        fully gapless and still every edge drawn exactly once; just not
        the same loop split a human tracing the two squares by eye would
        draw."""
        rows, cols = mask.shape
        horizontal, vertical = {}, {}
        for y, x in zip(ys.tolist(), xs.tolist()):
            if y == 0 or not mask[y - 1, x]:
                horizontal.setdefault(y, []).append(x)
            if y == rows - 1 or not mask[y + 1, x]:
                horizontal.setdefault(y + 1, []).append(x)
            if x == 0 or not mask[y, x - 1]:
                vertical.setdefault(x, []).append(y)
            if x == cols - 1 or not mask[y, x + 1]:
                vertical.setdefault(x + 1, []).append(y)

        edges = []
        for lineY, xPositions in horizontal.items():
            for start, end in CanvasArtist._mergeRuns(xPositions):
                edges.append(((start, lineY), (end, lineY)))
        for lineX, yPositions in vertical.items():
            for start, end in CanvasArtist._mergeRuns(yPositions):
                edges.append(((lineX, start), (lineX, end)))

        adjacency = {}
        for i, (a, b) in enumerate(edges):
            adjacency.setdefault(a, []).append(i)
            adjacency.setdefault(b, []).append(i)

        used = [False] * len(edges)
        path = QPainterPath()
        for startIdx in range(len(edges)):
            if used[startIdx]:
                continue
            start, b = edges[startIdx]
            used[startIdx] = True
            path.moveTo(*start)
            path.lineTo(*b)
            current = b
            while current != start:
                nextIdx = next((i for i in adjacency.get(current, ()) if not used[i]), None)
                if nextIdx is None:
                    break
                used[nextIdx] = True
                p1, p2 = edges[nextIdx]
                current = p2 if p1 == current else p1
                path.lineTo(*current)
            if current == start:
                path.closeSubpath()
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
    slotted into AppWindow.setLayerCanvasArea - mouse routing and pan/
    zoom are identical between the color and layer panes, so this is the
    one seam rather than a second near-duplicate widget class. The one
    thing that does differ is passed through, not branched on here: which
    pane a gesture started on decides `useLayers` (see
    ToolController.press/FunctionalTool.onPress), so a tool whose
    selection logic depends on it - WandTool - can sample canvas.layers
    instead of canvas.map when the click came from the layer canvas."""

    zoomChanged = Signal(float)

    def __init__(self, appController, theme: Theme = None, artistClass=CanvasArtist, **kwargs):
        super().__init__(**kwargs)
        self._appController = appController
        self._theme = theme or Theme()

        # So a plain hover (no button held) still generates move events
        # for BrushSelectTool's preview outline - see _updateBrushPreview.
        self.setMouseTracking(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.artist = artistClass(theme=self._theme)
        layout.addWidget(self.artist)

        # Fixed for this pane's lifetime (the artist class never changes
        # after construction) - tells ToolController whether a gesture
        # starting here should sample canvas.layers instead of canvas.map
        # (see FunctionalTool.onPress/WandTool.onPress).
        self._useLayers = isinstance(self.artist, LayerCanvasArtist)

        self._toolGestureActive = False
        self._panning = False
        self._panOrigin = None
        self._positionOrigin = None

        # A tool switch away from Brush (or to it) doesn't itself generate
        # a mouse move - without this, switching off Brush while the
        # pointer sits still over the canvas would leave its last preview
        # outline stuck on screen forever.
        appController.toolController.activeToolChanged.connect(self.artist.clearBrushPreview)

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
                self._appController.toolController.press(pos, useLayers=self._useLayers)

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
                self._appController.toolController.drag(pos, useLayers=self._useLayers)

        self._updateBrushPreview(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton and self._panning:
            self._panning = False
            return

        if event.button() == Qt.LeftButton and self._toolGestureActive:
            pos = self.artist.clampToCanvas(event.position())
            if pos is not None:
                self._appController.toolController.release(pos, useLayers=self._useLayers)
            self._toolGestureActive = False

    def leaveEvent(self, event):
        self.artist.clearBrushPreview()

    def _updateBrushPreview(self, event):
        """BrushSelectTool's hover outline (see CanvasArtist.
        setBrushPreview) - not itself a canvas edit, so it's decided
        straight from the active tool/pointer position here rather than
        going through ToolController.press/drag. While a gesture is
        active, uses the same clamped position the drag itself uses (see
        mouseMoveEvent above) so the preview keeps tracking at the canvas
        edge instead of vanishing mid-stroke; otherwise a plain hover
        outside the canvas clears it instead of clamping into view."""
        tool = self._appController.toolController.registry.activeTool
        if tool is None or tool.name != "brushSelect":
            self.artist.clearBrushPreview()
            return

        pos = (
            self.artist.clampToCanvas(event.position()) if self._toolGestureActive else
            self.artist.mouseToCanvas(event.position())
        )
        if pos is None:
            self.artist.clearBrushPreview()
            return

        row, col = pos
        self.artist.setBrushPreview(row, col, tool.selections.get("size", 1))

    def wheelEvent(self, event):
        factor = ZOOM_STEP if event.angleDelta().y() > 0 else 1 / ZOOM_STEP
        self.artist.zoomBy(factor, anchor=event.position())
        self.zoomChanged.emit(self.artist.zoom * 100)
