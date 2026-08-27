import numpy as np
from .canvas import *
from .vector import *


# Axes: X = pixel column, Z = pixel row, Y = height (the vertical/print
# axis - Y-up, matching a typical game-engine convention rather than
# Z-up). Every layer of height is exactly 1 world unit.
TUBE_MARGIN = 0.2            # how far the tube is inset from the pixel's unit-square edge
WALL_THICKNESS = 0.1         # shell thickness when Mesh.hollow is True
NOTCH_DEPTH = 0.12           # how far a notch pokes past the shared pixel boundary
NOTCH_WIDTH_RATIO = 0.5      # fraction of a face's width a notch/inlet spans, centered
BULGE_SIZE = 0.18            # how far a cap flares out past the grid edge on a clear side

DIRECTIONS = [
    # name, d(row), d(col), box-face key
    ('E', 0, 1, '+x'),
    ('W', 0, -1, '-x'),
    ('S', 1, 0, '+z'),
    ('N', -1, 0, '-z'),
]


def _quad(a, b, c, d):
    """Two triangles from four corners taken in order around the quad."""
    return [a, b, c, a, c, d]


def _box(minCorner, maxCorner, skip=frozenset()):
    """Triangles for an axis-aligned box; `skip` omits face keys (open/fused sides)."""
    x0, y0, z0 = minCorner
    x1, y1, z1 = maxCorner
    tris = []
    if '-x' not in skip:
        tris += _quad(Vector3(x0, y0, z0), Vector3(x0, y1, z0), Vector3(x0, y1, z1), Vector3(x0, y0, z1))
    if '+x' not in skip:
        tris += _quad(Vector3(x1, y0, z0), Vector3(x1, y0, z1), Vector3(x1, y1, z1), Vector3(x1, y1, z0))
    if '-z' not in skip:
        tris += _quad(Vector3(x0, y0, z0), Vector3(x1, y0, z0), Vector3(x1, y1, z0), Vector3(x0, y1, z0))
    if '+z' not in skip:
        tris += _quad(Vector3(x0, y0, z1), Vector3(x0, y1, z1), Vector3(x1, y1, z1), Vector3(x1, y0, z1))
    if '-y' not in skip:
        tris += _quad(Vector3(x0, y0, z0), Vector3(x0, y0, z1), Vector3(x1, y0, z1), Vector3(x1, y0, z0))
    if '+y' not in skip:
        tris += _quad(Vector3(x0, y1, z0), Vector3(x1, y1, z0), Vector3(x1, y1, z1), Vector3(x0, y1, z1))
    return tris


def _faceGeometry(faceKey, x0, z0, x1, z1):
    """(fixed value, u-range) for a vertical side face; u runs along Z for
    x-faces and along X for z-faces."""
    if faceKey == '+x':
        return x1, z0, z1
    if faceKey == '-x':
        return x0, z0, z1
    if faceKey == '+z':
        return z1, x0, x1
    return z0, x0, x1  # '-z'


def _facePoint(faceKey, fixedValue, u, y):
    if faceKey in ('+x', '-x'):
        return Vector3(fixedValue, y, u)
    return Vector3(u, y, fixedValue)


def _faceQuad(faceKey, fixedValue, u0, u1, y0, y1):
    p00 = _facePoint(faceKey, fixedValue, u0, y0)
    p10 = _facePoint(faceKey, fixedValue, u1, y0)
    p11 = _facePoint(faceKey, fixedValue, u1, y1)
    p01 = _facePoint(faceKey, fixedValue, u0, y1)
    if faceKey in ('+x', '+z'):
        return _quad(p00, p10, p11, p01)
    return _quad(p10, p00, p01, p11)


NOTCH_HEIGHT_RATIO = 0.4     # notch/inlet height as a fraction of the cap's own height


def _notchWedge(faceKey, boundaryValue, uMid, uHalf, notchTopY):
    """A wedge tab on the tube's inset wall, in the top NOTCH_HEIGHT_RATIO
    of the shorter neighbor's cap band: flush (no protrusion) at the
    bottom of that band, ramping up to full protrusion past the shared
    boundary at the top, with a flat top shelf. Pressed straight down,
    the ramp cams the tab past the matching inlet; the flat shelf is what
    then holds it seated - a plain box wouldn't allow that motion at all."""
    notchBottomY = notchTopY - NOTCH_HEIGHT_RATIO
    uA, uB = uMid - uHalf, uMid + uHalf
    if faceKey in ('+x', '+z'):
        flush = boundaryValue - TUBE_MARGIN
        tip = boundaryValue + NOTCH_DEPTH
    else:
        flush = boundaryValue + TUBE_MARGIN
        tip = boundaryValue - NOTCH_DEPTH

    flushA_bot = _facePoint(faceKey, flush, uA, notchBottomY)
    flushB_bot = _facePoint(faceKey, flush, uB, notchBottomY)
    flushA_top = _facePoint(faceKey, flush, uA, notchTopY)
    flushB_top = _facePoint(faceKey, flush, uB, notchTopY)
    tipA_top = _facePoint(faceKey, tip, uA, notchTopY)
    tipB_top = _facePoint(faceKey, tip, uB, notchTopY)

    tris = []
    tris += _quad(flushA_bot, flushB_bot, tipB_top, tipA_top)   # the ramp
    tris += _quad(flushA_top, tipA_top, tipB_top, flushB_top)   # the flat top shelf
    tris += [flushA_bot, tipA_top, flushA_top]                   # end cap at uA
    tris += [flushB_bot, flushB_top, tipB_top]                   # end cap at uB
    return tris


def _inletRecess(faceKey, fixedValue, uA, uB, y0, y1):
    """The matching cavity on the cap's own face, carved in mirror of
    _notchWedge - flush at the bottom of the band, receding inward to full
    depth at the top, closed off by the cap's own top face above it."""
    # Opposite sign from _notchWedge's "tip": the recess goes inward into
    # this pixel's own solid, not outward past the shared boundary.
    recessed = fixedValue - NOTCH_DEPTH if faceKey in ('+x', '+z') else fixedValue + NOTCH_DEPTH

    flushA_bot = _facePoint(faceKey, fixedValue, uA, y0)
    flushB_bot = _facePoint(faceKey, fixedValue, uB, y0)
    flushA_top = _facePoint(faceKey, fixedValue, uA, y1)
    flushB_top = _facePoint(faceKey, fixedValue, uB, y1)
    recA_top = _facePoint(faceKey, recessed, uA, y1)
    recB_top = _facePoint(faceKey, recessed, uB, y1)

    tris = []
    tris += _quad(flushA_bot, flushB_bot, recB_top, recA_top)   # the ramp (recess floor)
    tris += [flushA_bot, flushA_top, recA_top]                   # end wall at uA
    tris += [flushB_bot, recB_top, flushB_top]                   # end wall at uB
    return tris


def _inletFace(faceKey, fixedValue, u0, u1, capY0, capY1):
    """A cap side face with a wedge-shaped recess in its top
    NOTCH_HEIGHT_RATIO, sized to receive a taller neighbor's notch."""
    uMid = (u0 + u1) / 2.0
    uHalf = (u1 - u0) * NOTCH_WIDTH_RATIO / 2.0
    uA, uB = uMid - uHalf, uMid + uHalf
    notchBottomY = capY1 - NOTCH_HEIGHT_RATIO

    tris = []
    tris += _faceQuad(faceKey, fixedValue, u0, uA, capY0, capY1)              # left flank
    tris += _faceQuad(faceKey, fixedValue, uB, u1, capY0, capY1)              # right flank
    tris += _faceQuad(faceKey, fixedValue, uA, uB, capY0, notchBottomY)       # center strip, below the recess
    tris += _inletRecess(faceKey, fixedValue, uA, uB, notchBottomY, capY1)    # the recess itself
    return tris


def _collarRing(capX0, capX1, capZ0, capZ1, tubeX0, tubeX1, tubeZ0, tubeZ1, y, skipSides):
    """The flat frame connecting the cap's (possibly bulged) outer edge to
    the tube's narrower outer edge directly below it, at their shared
    seam - without this, a narrower tube meeting a wider cap leaves a gap."""
    outer = {
        'nw': (capX0, capZ0), 'ne': (capX1, capZ0),
        'sw': (capX0, capZ1), 'se': (capX1, capZ1),
    }
    inner = {
        'nw': (tubeX0, tubeZ0), 'ne': (tubeX1, tubeZ0),
        'sw': (tubeX0, tubeZ1), 'se': (tubeX1, tubeZ1),
    }

    def v(pt):
        return Vector3(pt[0], y, pt[1])

    tris = []
    if '-x' not in skipSides:
        tris += _quad(v(outer['nw']), v(outer['sw']), v(inner['sw']), v(inner['nw']))
    if '+x' not in skipSides:
        tris += _quad(v(outer['ne']), v(inner['ne']), v(inner['se']), v(outer['se']))
    if '-z' not in skipSides:
        tris += _quad(v(outer['nw']), v(inner['nw']), v(inner['ne']), v(outer['ne']))
    if '+z' not in skipSides:
        tris += _quad(v(outer['sw']), v(outer['se']), v(inner['se']), v(inner['sw']))
    return tris


class Mesh:
    def __init__(self):
        self.canvas: Canvas = None

        self.hollow = False

        self.mapCache: np.array = None
        self.layerCache: np.array = None
        self.hollowCache = self.hollow

        # meshes[colorIndex] is a list of components - pixels of the same
        # color don't always end up physically connected (see the
        # "disconnected parts" warnings below); each component is a flat
        # list of Vector3, 3 per triangle.
        self.meshes = []
        self.warnings = []

    def _checkForUpdate(self):
        if self.canvas is None:
            return False

        mapChanged = (
            self.mapCache is None
            or self.mapCache.shape != self.canvas.map.shape
            or not np.array_equal(self.mapCache, self.canvas.map)
        )
        layersChanged = (
            self.layerCache is None
            or self.layerCache.shape != self.canvas.layers.shape
            or not np.array_equal(self.layerCache, self.canvas.layers)
        )
        hollowChanged = self.hollow != self.hollowCache
        return mapChanged or layersChanged or hollowChanged

    def _isEmpty(self, pos):
        return not self.canvas.positionValid(pos) or self.canvas.layers[pos] < 1

    def _neighborInfo(self, y, x, dy, dx):
        pos = (y + dy, x + dx)
        if self._isEmpty(pos):
            return None
        return self.canvas.map[pos], self.canvas.layers[pos]

    def _sameColorHeight(self, p1, p2):
        if self._isEmpty(p1) or self._isEmpty(p2):
            return False
        return self.canvas.map[p1] == self.canvas.map[p2] and self.canvas.layers[p1] == self.canvas.layers[p2]

    def _buildPixel(self, y, x):
        height = self.canvas.layers[y, x]
        if height < 1:
            return []

        x0, z0, x1, z1 = float(x), float(y), float(x) + 1.0, float(y) + 1.0
        capY0, capY1 = height - 1.0, float(height)
        color = self.canvas.map[y, x]

        fuseFaces = set()
        inletFaces = {}    # faceKey -> neighborHeight (this pixel is shorter)
        tubeDrops = {}      # faceKey -> neighborHeight (this pixel is taller, owns a tube+notch)
        bulgeFaces = set()  # faceKey -> this side has nothing next to it at all

        for _, dy, dx, faceKey in DIRECTIONS:
            info = self._neighborInfo(y, x, dy, dx)
            if info is None:
                bulgeFaces.add(faceKey)
                continue
            nColor, nHeight = info
            if nColor == color and nHeight == height:
                fuseFaces.add(faceKey)
            elif nHeight < height:
                tubeDrops[faceKey] = nHeight
            elif nHeight > height:
                inletFaces[faceKey] = nHeight
            # nHeight == height, different color: a plain wall, nothing special.

        # A clear side's cap flares outward instead of sitting flush at the
        # grid edge - this alone is what lets two pixels that only touch
        # diagonally end up as one physically connected piece; nothing
        # about it depends on color.
        capX0 = x0 - (BULGE_SIZE if '-x' in bulgeFaces else 0.0)
        capX1 = x1 + (BULGE_SIZE if '+x' in bulgeFaces else 0.0)
        capZ0 = z0 - (BULGE_SIZE if '-z' in bulgeFaces else 0.0)
        capZ1 = z1 + (BULGE_SIZE if '+z' in bulgeFaces else 0.0)

        tris = []

        # Cap: the pixel's own top layer, flared on clear sides, with
        # inlets carved into whichever sides face a taller neighbor.
        for _, _, _, faceKey in DIRECTIONS:
            if faceKey in fuseFaces:
                continue
            fixedValue, u0, u1 = _faceGeometry(faceKey, capX0, capZ0, capX1, capZ1)
            if faceKey in inletFaces:
                tris += _inletFace(faceKey, fixedValue, u0, u1, capY0, capY1)
            else:
                tris += _faceQuad(faceKey, fixedValue, u0, u1, capY0, capY1)

        tris += _quad(
            Vector3(capX0, capY1, capZ0), Vector3(capX1, capY1, capZ0),
            Vector3(capX1, capY1, capZ1), Vector3(capX0, capY1, capZ1),
        )

        # Tube: always narrower than the cap (that inset is what makes room
        # for the bulge and the notch/inlet mechanism), running from the
        # print bed up to the underside of the cap.
        tubeY1 = capY0
        m = TUBE_MARGIN
        tubeX0, tubeX1, tubeZ0, tubeZ1 = x0 + m, x1 - m, z0 + m, z1 - m

        if tubeY1 > 0:
            tris += _box((tubeX0, 0.0, tubeZ0), (tubeX1, tubeY1, tubeZ1), skip=fuseFaces | {'+y', '-y'})

            if self.hollow:
                w = WALL_THICKNESS
                ix0, iz0, ix1, iz1 = tubeX0 + w, tubeZ0 + w, tubeX1 - w, tubeZ1 - w
                if ix1 > ix0 and iz1 > iz0:
                    tris += _box((ix0, 0.0, iz0), (ix1, tubeY1, iz1), skip=fuseFaces | {'+y', '-y'})

            # Close the step where the wider (possibly bulged) cap meets
            # the narrower tube directly beneath it.
            tris += _collarRing(capX0, capX1, capZ0, capZ1, tubeX0, tubeX1, tubeZ0, tubeZ1, tubeY1, fuseFaces)

            for faceKey, nHeight in tubeDrops.items():
                fixedValue, u0, u1 = _faceGeometry(faceKey, x0, z0, x1, z1)
                uMid = (u0 + u1) / 2.0
                uHalf = (u1 - u0) * NOTCH_WIDTH_RATIO / 2.0
                tris += _notchWedge(faceKey, fixedValue, uMid, uHalf, float(nHeight))

                drop = height - nHeight
                tubeWidth = 1.0 - 2 * TUBE_MARGIN
                if tubeWidth > 0 and drop / tubeWidth > 5:
                    self.warnings.append(
                        f"Thin connector at ({y}, {x}) side {faceKey}: "
                        f"drop of {drop} layers over a {tubeWidth:.2f}-unit-wide tube."
                    )

        return tris

    def _diagonalPairs(self, y, x):
        """The two unique diagonal neighbor pairs owned by (y, x), each with
        the two orthogonal cells that would have to be clear for a bulge
        alone to connect them."""
        yield (y + 1, x + 1), (y, x + 1), (y + 1, x)   # SE
        yield (y - 1, x + 1), (y, x + 1), (y - 1, x)   # NE

    def _calculateMesh(self):
        if not self._checkForUpdate():
            return

        self.mapCache = self.canvas.map.copy()
        self.layerCache = self.canvas.layers.copy()
        self.hollowCache = self.hollow
        self.warnings = []

        rows, cols = self.canvas.map.shape

        pixelTris = {}
        parent = {}

        def find(p):
            while parent[p] != p:
                parent[p] = parent[parent[p]]
                p = parent[p]
            return p

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for y in range(rows):
            for x in range(cols):
                if self.canvas.layers[y, x] >= 1:
                    parent[(y, x)] = (y, x)

        for y in range(rows):
            for x in range(cols):
                if self.canvas.layers[y, x] < 1:
                    continue
                pixelTris[(y, x)] = self._buildPixel(y, x)

                for _, dy, dx, faceKey in DIRECTIONS:
                    if not self._isEmpty((y + dy, x + dx)):
                        nColor, nHeight = self.canvas.map[y + dy, x + dx], self.canvas.layers[y + dy, x + dx]
                        if nColor == self.canvas.map[y, x] and nHeight == self.canvas.layers[y, x]:
                            union((y, x), (y + dy, x + dx))

                for neighbor, flank1, flank2 in self._diagonalPairs(y, x):
                    if not self.canvas.positionValid(neighbor):
                        continue
                    if self._sameColorHeight((y, x), neighbor) and self._isEmpty(flank1) and self._isEmpty(flank2):
                        union((y, x), neighbor)

        components = {}
        componentPixelCount = {}
        for pos, tris in pixelTris.items():
            color = int(self.canvas.map[pos])
            key = (color, find(pos))
            components.setdefault(key, []).extend(tris)
            componentPixelCount[key] = componentPixelCount.get(key, 0) + 1

        colorCount = len(self.canvas.palette)
        meshes = [[] for _ in range(colorCount)]
        perColorRoots = {}
        for (color, root), tris in components.items():
            meshes[color].append(tris)
            perColorRoots.setdefault(color, []).append(root)

        for color, roots in perColorRoots.items():
            if len(roots) > 1:
                self.warnings.append(f"Color {color} produced {len(roots)} disconnected parts.")

        for (color, root), count in componentPixelCount.items():
            if count == 1:
                self.warnings.append(f"Isolated single-pixel part for color {color}.")

        self.meshes = meshes
