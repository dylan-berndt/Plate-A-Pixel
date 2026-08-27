import numpy as np
from .canvas import *
from .vector import *


# Every layer of height is exactly 1 world unit; a pixel's cap is always
# exactly one layer thick, so it never needs its own tunable constant.
TUBE_MARGIN = 0.2            # how far a tube's wall is inset from the pixel's unit-square edge
WALL_THICKNESS = 0.1         # shell thickness when Mesh.hollow is True
NOTCH_DEPTH = 0.12           # how far a notch pokes past the shared pixel boundary
NOTCH_WIDTH_RATIO = 0.5      # fraction of a face's width a notch/inlet spans, centered
BULGE_SIZE = 0.18            # half-width of the corner-fill cube used to fuse diagonal pixels

DIRECTIONS = [
    # name, dy, dx, box-face key
    ('E', 0, 1, '+x'),
    ('W', 0, -1, '-x'),
    ('S', 1, 0, '+y'),
    ('N', -1, 0, '-y'),
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
        tris += _quad(Vector3(x0, y0, z0), Vector3(x0, y0, z1), Vector3(x0, y1, z1), Vector3(x0, y1, z0))
    if '+x' not in skip:
        tris += _quad(Vector3(x1, y0, z0), Vector3(x1, y1, z0), Vector3(x1, y1, z1), Vector3(x1, y0, z1))
    if '-y' not in skip:
        tris += _quad(Vector3(x0, y0, z0), Vector3(x1, y0, z0), Vector3(x1, y0, z1), Vector3(x0, y0, z1))
    if '+y' not in skip:
        tris += _quad(Vector3(x0, y1, z0), Vector3(x0, y1, z1), Vector3(x1, y1, z1), Vector3(x1, y1, z0))
    if '-z' not in skip:
        tris += _quad(Vector3(x0, y0, z0), Vector3(x0, y1, z0), Vector3(x1, y1, z0), Vector3(x1, y0, z0))
    if '+z' not in skip:
        tris += _quad(Vector3(x0, y0, z1), Vector3(x1, y0, z1), Vector3(x1, y1, z1), Vector3(x0, y1, z1))
    return tris


def _faceGeometry(faceKey, x0, y0, x1, y1):
    """(fixed axis, fixed value, u-range) for a vertical side face."""
    if faceKey == '+x':
        return 'x', x1, y0, y1
    if faceKey == '-x':
        return 'x', x0, y0, y1
    if faceKey == '+y':
        return 'y', y1, x0, x1
    return 'y', y0, x0, x1


def _facePoint(faceKey, fixedValue, u, z):
    if faceKey in ('+x', '-x'):
        return Vector3(fixedValue, u, z)
    return Vector3(u, fixedValue, z)


def _faceQuad(faceKey, fixedValue, u0, u1, z0, z1):
    p00 = _facePoint(faceKey, fixedValue, u0, z0)
    p10 = _facePoint(faceKey, fixedValue, u1, z0)
    p11 = _facePoint(faceKey, fixedValue, u1, z1)
    p01 = _facePoint(faceKey, fixedValue, u0, z1)
    # +x/+y faces look outward from increasing u->z; -x/-y need the opposite
    # winding to keep the outward-facing normal on the correct side.
    if faceKey in ('+x', '+y'):
        return _quad(p00, p10, p11, p01)
    return _quad(p10, p00, p01, p11)


def _notchBox(faceKey, boundaryValue, uMid, uHalf, z0, z1):
    """A tab protruding from a tube's inset wall out past the shared pixel
    boundary, so it engages the neighbor's inlet pocket on the other side."""
    inward = TUBE_MARGIN
    outward = NOTCH_DEPTH
    if faceKey == '+x':
        return _box((boundaryValue - inward, uMid - uHalf, z0), (boundaryValue + outward, uMid + uHalf, z1))
    if faceKey == '-x':
        return _box((boundaryValue - outward, uMid - uHalf, z0), (boundaryValue + inward, uMid + uHalf, z1))
    if faceKey == '+y':
        return _box((uMid - uHalf, boundaryValue - inward, z0), (uMid + uHalf, boundaryValue + outward, z1))
    return _box((uMid - uHalf, boundaryValue - outward, z0), (uMid + uHalf, boundaryValue + inward, z1))


def _inletFace(faceKey, fixedValue, u0, u1, z0, z1):
    """A cap side face with a full-height pocket recessed into its center,
    sized to receive a taller neighbor's notch."""
    uMid = (u0 + u1) / 2.0
    uHalf = (u1 - u0) * NOTCH_WIDTH_RATIO / 2.0
    uA, uB = uMid - uHalf, uMid + uHalf

    tris = []
    tris += _faceQuad(faceKey, fixedValue, u0, uA, z0, z1)
    tris += _faceQuad(faceKey, fixedValue, uB, u1, z0, z1)

    depth = NOTCH_DEPTH
    if faceKey == '+x':
        tris += _box((fixedValue - depth, uA, z0), (fixedValue, uB, z1), skip={'+x'})
    elif faceKey == '-x':
        tris += _box((fixedValue, uA, z0), (fixedValue + depth, uB, z1), skip={'-x'})
    elif faceKey == '+y':
        tris += _box((uA, fixedValue - depth, z0), (uB, fixedValue, z1), skip={'+y'})
    else:
        tris += _box((uA, fixedValue, z0), (uB, fixedValue + depth, z1), skip={'-y'})
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

    def _neighborInfo(self, y, x, dy, dx):
        pos = (y + dy, x + dx)
        if not self.canvas.positionValid(pos):
            return None
        height = self.canvas.layers[pos]
        if height < 1:
            return None
        return self.canvas.map[pos], height

    def _sameColorHeight(self, p1, p2):
        h1, h2 = self.canvas.layers[p1], self.canvas.layers[p2]
        if h1 < 1 or h2 < 1:
            return False
        return self.canvas.map[p1] == self.canvas.map[p2] and h1 == h2

    # Two diagonal pixel pairs sharing a 2x2 block can both be eligible for
    # a corner bulge at once (a checkerboard "saddle" - see the write-up).
    # Only one can physically occupy that corner: the lower palette index
    # wins, the other pair is left as separate, unconnected pieces.
    def _computeSaddleSuppressions(self):
        suppressed = set()
        rows, cols = self.canvas.map.shape
        for y in range(rows - 1):
            for x in range(cols - 1):
                a1, a2 = (y, x), (y + 1, x + 1)
                b1, b2 = (y, x + 1), (y + 1, x)
                aEligible = self._sameColorHeight(a1, a2)
                bEligible = self._sameColorHeight(b1, b2)
                if aEligible and bEligible:
                    colorA = self.canvas.map[a1]
                    colorB = self.canvas.map[b1]
                    if colorA <= colorB:
                        # pair B is owned by 'NE' from its lower pixel (y+1, x),
                        # which is the one that reaches (y, x+1) going NE.
                        suppressed.add((y + 1, x, 'NE'))
                    else:
                        suppressed.add((y, x, 'SE'))
        return suppressed

    def _cornerBulges(self, y, x, height, suppressed):
        tris = []
        z0, z1 = height - 1.0, float(height)
        for dName, dy, dx, cx, cy in (('SE', 1, 1, x + 1.0, y + 1.0), ('NE', -1, 1, x + 1.0, y)):
            if (y, x, dName) in suppressed:
                continue
            neighbor = (y + dy, x + dx)
            if not self.canvas.positionValid(neighbor):
                continue
            if not self._sameColorHeight((y, x), neighbor):
                continue
            tris += _box(
                (cx - BULGE_SIZE, cy - BULGE_SIZE, z0),
                (cx + BULGE_SIZE, cy + BULGE_SIZE, z1),
            )
        return tris

    def _buildPixel(self, y, x, suppressedBulges):
        height = self.canvas.layers[y, x]
        if height < 1:
            return []

        x0, y0, x1, y1 = float(x), float(y), float(x) + 1.0, float(y) + 1.0
        capZ0, capZ1 = height - 1.0, float(height)

        fuseFaces = set()
        inletFaces = {}   # faceKey -> neighborHeight (this pixel is shorter)
        tubeDrops = {}     # faceKey -> neighborHeight (this pixel is taller, owns a tube+notch)

        for _, dy, dx, faceKey in DIRECTIONS:
            info = self._neighborInfo(y, x, dy, dx)
            if info is None:
                continue
            nColor, nHeight = info
            color = self.canvas.map[y, x]
            if nColor == color and nHeight == height:
                fuseFaces.add(faceKey)
            elif nHeight < height:
                tubeDrops[faceKey] = nHeight
            elif nHeight > height:
                inletFaces[faceKey] = nHeight
            # nHeight == height, different color: a plain wall, nothing special.

        tris = []

        # Cap: the pixel's own top layer, full width, with inlets carved
        # into whichever sides face a taller neighbor.
        for _, _, _, faceKey in DIRECTIONS:
            if faceKey in fuseFaces:
                continue
            _, fixedValue, u0, u1 = _faceGeometry(faceKey, x0, y0, x1, y1)
            if faceKey in inletFaces:
                tris += _inletFace(faceKey, fixedValue, u0, u1, capZ0, capZ1)
            else:
                tris += _faceQuad(faceKey, fixedValue, u0, u1, capZ0, capZ1)

        # Cap top - the only horizontal face any pixel ever draws. The
        # cap/body seam and the body's base are both left open: they're
        # either an internal seam between two solids of the same pixel, or
        # the bottom face resting flush on the print bed.
        tris += _quad(
            Vector3(x0, y0, capZ1), Vector3(x1, y0, capZ1), Vector3(x1, y1, capZ1), Vector3(x0, y1, capZ1),
        )

        # Bulges at diagonal corners, for dithered same-color/same-height
        # pixels that would otherwise only touch at a single edge.
        tris += self._cornerBulges(y, x, height, suppressedBulges)

        # Body: everything below the cap, down to the print bed. Any side
        # needing a tube pulls the *entire* body in to tube width, rather
        # than narrowing only the sides that strictly need it - simpler to
        # generate, at the cost of narrowing some plain walls that didn't
        # strictly need it.
        bodyZ1 = capZ0
        if bodyZ1 > 0:
            tubeMode = bool(tubeDrops)
            if tubeMode:
                m = TUBE_MARGIN
                bx0, by0, bx1, by1 = x0 + m, y0 + m, x1 - m, y1 - m
            else:
                bx0, by0, bx1, by1 = x0, y0, x1, y1

            tris += _box((bx0, by0, 0.0), (bx1, by1, bodyZ1), skip=fuseFaces | {'+z', '-z'})

            if self.hollow:
                w = WALL_THICKNESS
                ix0, iy0, ix1, iy1 = bx0 + w, by0 + w, bx1 - w, by1 - w
                if ix1 > ix0 and iy1 > iy0:
                    tris += _box((ix0, iy0, 0.0), (ix1, iy1, bodyZ1), skip=fuseFaces | {'+z', '-z'})

            for faceKey, nHeight in tubeDrops.items():
                _, fixedValue, u0, u1 = _faceGeometry(faceKey, x0, y0, x1, y1)
                uMid = (u0 + u1) / 2.0
                uHalf = (u1 - u0) * NOTCH_WIDTH_RATIO / 2.0
                notchZ0, notchZ1 = nHeight - 1.0, float(nHeight)
                tris += _notchBox(faceKey, fixedValue, uMid, uHalf, notchZ0, notchZ1)

                drop = height - nHeight
                tubeWidth = 1.0 - 2 * TUBE_MARGIN
                if tubeWidth > 0 and drop / tubeWidth > 5:
                    self.warnings.append(
                        f"Thin connector at ({y}, {x}) side {faceKey}: "
                        f"drop of {drop} layers over a {tubeWidth:.2f}-unit-wide tube."
                    )

        return tris

    def _calculateMesh(self):
        if not self._checkForUpdate():
            return

        self.mapCache = self.canvas.map.copy()
        self.layerCache = self.canvas.layers.copy()
        self.hollowCache = self.hollow
        self.warnings = []

        rows, cols = self.canvas.map.shape
        suppressedBulges = self._computeSaddleSuppressions()

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
                if self.canvas.layers[y, x] < 1:
                    continue
                parent[(y, x)] = (y, x)

        for y in range(rows):
            for x in range(cols):
                if self.canvas.layers[y, x] < 1:
                    continue
                pixelTris[(y, x)] = self._buildPixel(y, x, suppressedBulges)

                for _, dy, dx, faceKey in DIRECTIONS:
                    info = self._neighborInfo(y, x, dy, dx)
                    if info is None:
                        continue
                    nColor, nHeight = info
                    if nColor == self.canvas.map[y, x] and nHeight == self.canvas.layers[y, x]:
                        union((y, x), (y + dy, x + dx))

                for dName, dy, dx in (('SE', 1, 1), ('NE', -1, 1)):
                    if (y, x, dName) in suppressedBulges:
                        continue
                    neighbor = (y + dy, x + dx)
                    if self.canvas.positionValid(neighbor) and self._sameColorHeight((y, x), neighbor):
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
