from pathlib import Path

from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPixmap, QPainter, QColor
from PySide6.QtCore import QRect, Qt

# assets/ sits at the repo root, two levels above this file
# (utils/ui/nineSlice.py) - see also assets/lospec500.gpl, which Theme's
# colors (base.py) are matched against.
ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"
DEFAULT_SLICE_PATH = ASSETS_DIR / "slice.png"
DEFAULT_CORNER_SIZE = 2

# One NineSlice per (path, cornerSize), shared by every NineSliceFrame/
# NineSliceEdge/IconButton instance and anything else that paints with
# one - slicing the same source image again for every widget would just
# be wasted work, not wrong, so this is a plain optimization living at
# module level so nothing has to reach into one particular class to get it.
_shared = {}


def sharedNineSlice(imagePath=DEFAULT_SLICE_PATH, cornerSize: int = DEFAULT_CORNER_SIZE) -> "NineSlice":
    key = (str(imagePath), cornerSize)
    if key not in _shared:
        _shared[key] = NineSlice(imagePath, cornerSize)
    return _shared[key]


class NineSlice:
    """A nine-slice border texture cut from a small square source image -
    assets/slice.png by default: an 8x8 tile whose outer 2-pixel margin
    (`cornerSize`) is the corner art (used exactly as-is, never scaled or
    tiled - that's what keeps a rounded pixel-art corner looking
    intentional rather than smeared) and whose next band in is the edge
    art, tiled - not stretched - across however long a real edge needs
    to be, so scaling up to fit a widget repeats crisp source pixels
    instead of smoothing/blurring them. What's left in the middle is the
    center tile (fully transparent in slice.png itself, so painting it
    is a no-op there and a caller's own background shows through - see
    NineSliceFrame below); it's read out and painted anyway rather than
    assumed transparent, so a differently-authored source image with an
    opaque center still works.

    Loading and slicing (a handful of QPixmap.copy() calls) happens once
    per source image in __init__ - cheap enough that every NineSliceFrame
    doesn't need to share a single instance, but NineSliceFrame does
    share one per (path, cornerSize) anyway (see its _shared cache) since
    there's no reason not to."""

    def __init__(self, imagePath=DEFAULT_SLICE_PATH, cornerSize: int = DEFAULT_CORNER_SIZE):
        self.cornerSize = cornerSize
        source = QPixmap(str(imagePath))
        if source.isNull():
            raise ValueError(f"Could not load nine-slice source image: {imagePath}")

        edgeWidth = source.width() - 2 * cornerSize
        edgeHeight = source.height() - 2 * cornerSize
        if edgeWidth <= 0 or edgeHeight <= 0:
            raise ValueError(
                f"cornerSize={cornerSize} leaves no room for edges in a "
                f"{source.width()}x{source.height()} source image"
            )

        c = cornerSize
        self.topLeft = source.copy(0, 0, c, c)
        self.topRight = source.copy(c + edgeWidth, 0, c, c)
        self.bottomLeft = source.copy(0, c + edgeHeight, c, c)
        self.bottomRight = source.copy(c + edgeWidth, c + edgeHeight, c, c)
        self.top = source.copy(c, 0, edgeWidth, c)
        self.bottom = source.copy(c, c + edgeHeight, edgeWidth, c)
        self.left = source.copy(0, c, c, edgeHeight)
        self.right = source.copy(c + edgeWidth, c, c, edgeHeight)
        self.center = source.copy(c, c, edgeWidth, edgeHeight)

    def borderThickness(self, scale: int) -> int:
        return self.cornerSize * scale

    @staticmethod
    def _upscale(pixmap: QPixmap, width: int, height: int) -> QPixmap:
        # FastTransformation = nearest-neighbor, not the smooth/bilinear
        # default - the entire point of drawing pixel art through this
        # class instead of QSS's own border-image is keeping hard pixel
        # edges when magnified, not blurring them away.
        return pixmap.scaled(width, height, Qt.IgnoreAspectRatio, Qt.FastTransformation)

    def paint(self, painter: QPainter, rect: QRect, scale: int = 1):
        """Paints corners (as-is, magnified only by `scale`), edges
        (tiled - see the class docstring), and the center (stretched to
        fill, but transparent in slice.png so this is a no-op there) into
        `rect`. Does not touch anything outside `rect` and does not fill
        any background of its own - see NineSliceFrame for pairing this
        with an actual fill behind the (normally transparent) center."""
        c = self.borderThickness(scale)
        midWidth = rect.width() - 2 * c
        midHeight = rect.height() - 2 * c

        painter.drawPixmap(rect.left(), rect.top(), self._upscale(self.topLeft, c, c))
        painter.drawPixmap(rect.right() - c + 1, rect.top(), self._upscale(self.topRight, c, c))
        painter.drawPixmap(rect.left(), rect.bottom() - c + 1, self._upscale(self.bottomLeft, c, c))
        painter.drawPixmap(rect.right() - c + 1, rect.bottom() - c + 1, self._upscale(self.bottomRight, c, c))

        if midWidth > 0:
            painter.drawTiledPixmap(
                QRect(rect.left() + c, rect.top(), midWidth, c),
                self._upscale(self.top, self.top.width() * scale, c),
            )
            painter.drawTiledPixmap(
                QRect(rect.left() + c, rect.bottom() - c + 1, midWidth, c),
                self._upscale(self.bottom, self.bottom.width() * scale, c),
            )
        if midHeight > 0:
            painter.drawTiledPixmap(
                QRect(rect.left(), rect.top() + c, c, midHeight),
                self._upscale(self.left, c, self.left.height() * scale),
            )
            painter.drawTiledPixmap(
                QRect(rect.right() - c + 1, rect.top() + c, c, midHeight),
                self._upscale(self.right, c, self.right.height() * scale),
            )
        if midWidth > 0 and midHeight > 0:
            painter.drawPixmap(
                QRect(rect.left() + c, rect.top() + c, midWidth, midHeight),
                self._upscale(self.center, midWidth, midHeight),
            )

    def paintEdge(self, painter: QPainter, rect: QRect, side: str, scale: int = 1):
        """Tiles just one named edge's art along the corresponding side of
        `rect`, its full length - no corners, unlike paint() above. For a
        panel with only one real visible border - the tool rail's right
        edge or the right pane's left edge, both flush against the
        window's other three edges, where a rounded corner wouldn't sit
        against anything and so wouldn't make sense."""
        c = self.borderThickness(scale)
        if side == "top":
            tile = self._upscale(self.top, self.top.width() * scale, c)
            painter.drawTiledPixmap(QRect(rect.left(), rect.top(), rect.width(), c), tile)
        elif side == "bottom":
            tile = self._upscale(self.bottom, self.bottom.width() * scale, c)
            painter.drawTiledPixmap(QRect(rect.left(), rect.bottom() - c + 1, rect.width(), c), tile)
        elif side == "left":
            tile = self._upscale(self.left, c, self.left.height() * scale)
            painter.drawTiledPixmap(QRect(rect.left(), rect.top(), c, rect.height()), tile)
        elif side == "right":
            tile = self._upscale(self.right, c, self.right.height() * scale)
            painter.drawTiledPixmap(QRect(rect.right() - c + 1, rect.top(), c, rect.height()), tile)
        else:
            raise ValueError(f"Unknown side '{side}' - must be top/bottom/left/right")


class NineSliceFrame(QWidget):
    """A pixel-art alternative to a bordered/rounded QFrame "card" - paints
    its border via a NineSlice instead of QSS's border/border-radius (which
    anti-aliases corners - exactly the smoothing a pixel-art border needs
    to avoid), filling the area inside that border with `backgroundColor`
    first so the source image's normally-transparent center shows that
    fill through rather than punching a hole in the widget.

    A plain QWidget, not a QFrame - unlike the QSS approach this project's
    other cards use (see MeshSettingsPanel's own note on QLabel being a
    QFrame subclass and needing objectName-scoped selectors to avoid
    style bleed onto child QLabels), painting everything itself in
    paintEvent means there's no stylesheet here at all for a descendant
    to accidentally inherit.

    Owns no layout of its own - a caller adds one exactly like it would
    to a plain QFrame, using borderThickness() to pad contentsMargins so
    children never overlap the painted border:

        card = NineSliceFrame(theme.paper, theme=theme)
        layout = QVBoxLayout(card)
        t = card.borderThickness()
        layout.setContentsMargins(12 + t, 12 + t, 12 + t, 12 + t)
    """

    def __init__(
        self, backgroundColor: str, scale: int = 3,
        imagePath=DEFAULT_SLICE_PATH, cornerSize: int = DEFAULT_CORNER_SIZE,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._scale = scale
        self._backgroundColor = QColor(backgroundColor)
        self._nineSlice = sharedNineSlice(imagePath, cornerSize)

    def borderThickness(self) -> int:
        return self._nineSlice.borderThickness(self._scale)

    def setBackgroundColor(self, color: str):
        self._backgroundColor = QColor(color)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        t = self.borderThickness()
        painter.fillRect(self.rect().adjusted(t, t, -t, -t), self._backgroundColor)
        self._nineSlice.paint(painter, self.rect(), self._scale)
        painter.end()


class NineSliceEdge(QWidget):
    """Like NineSliceFrame, but for a panel with only one real visible
    border - the tool rail's right edge, or a side pane's left edge, both
    flush against the window's other three edges. A full four-corner frame
    would draw rounded corners that don't sit against anything and so
    wouldn't make sense; this fills the whole rect with `backgroundColor`
    and tiles just the named edge's art along that one side (see
    NineSlice.paintEdge).

    Owns no layout of its own, same as NineSliceFrame - a caller adds one
    and pads contentsMargins on the bordered side with borderThickness()
    so children never overlap the painted edge:

        rail = NineSliceEdge(theme.clay300, side="right", scale=2)
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(0, 0, rail.borderThickness(), 0)
    """

    def __init__(
        self, backgroundColor: str, side: str, scale: int = 2,
        imagePath=DEFAULT_SLICE_PATH, cornerSize: int = DEFAULT_CORNER_SIZE,
        **kwargs,
    ):
        super().__init__(**kwargs)
        if side not in ("top", "bottom", "left", "right"):
            raise ValueError(f"Unknown side '{side}' - must be top/bottom/left/right")
        self._side = side
        self._scale = scale
        self._backgroundColor = QColor(backgroundColor)
        self._nineSlice = sharedNineSlice(imagePath, cornerSize)

    def borderThickness(self) -> int:
        return self._nineSlice.borderThickness(self._scale)

    def setBackgroundColor(self, color: str):
        self._backgroundColor = QColor(color)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.fillRect(self.rect(), self._backgroundColor)
        self._nineSlice.paintEdge(painter, self.rect(), self._side, self._scale)
        painter.end()
