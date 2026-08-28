from .pixelPlan import Face
from .vector import *


# Axes: X = pixel column, Z = pixel row, Y = height (the vertical/print
# axis - Y-up). Every layer of height is exactly 1 world unit.
TUBE_MARGIN = 0.2            # how far the tube is inset from the pixel's unit-square edge
WALL_THICKNESS = 0.1         # shell thickness when a Tube is hollow
NOTCH_DEPTH = 0.12           # how far a notch pokes past the shared pixel boundary
NOTCH_WIDTH_RATIO = 0.5      # fraction of a face's width a notch/inlet spans, centered
NOTCH_HEIGHT_RATIO = 0.4     # notch/inlet height as a fraction of the cap's own height
BULGE_SIZE = 0.18            # how far a cap flares out past the grid edge on a clear side
THIN_CONNECTOR_RATIO = 5     # a notch's height drop past this multiple of the tube's width gets flagged


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


def _faceRange(face: Face, x0, z0, x1, z1):
    """(fixed value, u-range) for a vertical side face; u runs along Z for
    x-faces and along X for z-faces."""
    if face is Face.EAST:
        return x1, z0, z1
    if face is Face.WEST:
        return x0, z0, z1
    if face is Face.SOUTH:
        return z1, x0, x1
    return z0, x0, x1  # Face.NORTH


def _facePoint(face: Face, fixedValue, u, y):
    if face.axis == 'x':
        return Vector3(fixedValue, y, u)
    return Vector3(u, y, fixedValue)


def _faceQuad(face: Face, fixedValue, u0, u1, y0, y1):
    p00 = _facePoint(face, fixedValue, u0, y0)
    p10 = _facePoint(face, fixedValue, u1, y0)
    p11 = _facePoint(face, fixedValue, u1, y1)
    p01 = _facePoint(face, fixedValue, u0, y1)
    if face.sign > 0:
        return _quad(p00, p10, p11, p01)
    return _quad(p10, p00, p01, p11)


class Notch:
    """A wedge tab on a tube's face, in the top NOTCH_HEIGHT_RATIO of the
    shorter neighbor's cap band: flush (no protrusion) at the bottom of
    that band, ramping up to full protrusion past the shared boundary at
    the top, with a flat top shelf. Pressed straight down, the ramp cams
    the tab past the matching Inlet; the flat shelf is what then holds it
    seated - a plain box wouldn't allow that motion at all."""

    def __init__(self, face: Face, boundaryValue: float, uMid: float, uHalf: float, neighborHeight: int):
        self.face = face
        self.boundaryValue = boundaryValue
        self.uMid = uMid
        self.uHalf = uHalf
        self.neighborHeight = neighborHeight

    def isThinRelativeTo(self, ownHeight):
        drop = ownHeight - self.neighborHeight
        tubeWidth = 1.0 - 2 * TUBE_MARGIN
        return tubeWidth > 0 and drop / tubeWidth > THIN_CONNECTOR_RATIO

    def triangles(self):
        face = self.face
        topY = float(self.neighborHeight)
        botY = topY - NOTCH_HEIGHT_RATIO
        uA, uB = self.uMid - self.uHalf, self.uMid + self.uHalf
        flush = face.offset(self.boundaryValue, -TUBE_MARGIN)
        tip = face.offset(self.boundaryValue, NOTCH_DEPTH)

        flushA_bot = _facePoint(face, flush, uA, botY)
        flushB_bot = _facePoint(face, flush, uB, botY)
        flushA_top = _facePoint(face, flush, uA, topY)
        flushB_top = _facePoint(face, flush, uB, topY)
        tipA_top = _facePoint(face, tip, uA, topY)
        tipB_top = _facePoint(face, tip, uB, topY)

        tris = []
        tris += _quad(flushA_bot, flushB_bot, tipB_top, tipA_top)   # the ramp
        tris += _quad(flushA_top, tipA_top, tipB_top, flushB_top)   # the flat top shelf
        tris += [flushA_bot, tipA_top, flushA_top]                   # end cap at uA
        tris += [flushB_bot, flushB_top, tipB_top]                   # end cap at uB
        return tris


class Inlet:
    """The matching cavity on a cap's own face, carved as the mirror of a
    Notch: flush at the bottom of its band, receding inward to full depth
    at the top, closed off above by the cap's own top face."""

    def __init__(self, face: Face, fixedValue: float, u0: float, u1: float, capY0: float, capY1: float):
        self.face = face
        self.fixedValue = fixedValue
        self.u0, self.u1 = u0, u1
        self.capY0, self.capY1 = capY0, capY1

    def triangles(self):
        face = self.face
        uMid = (self.u0 + self.u1) / 2.0
        uHalf = (self.u1 - self.u0) * NOTCH_WIDTH_RATIO / 2.0
        uA, uB = uMid - uHalf, uMid + uHalf
        recessTopY = self.capY1
        recessBotY = recessTopY - NOTCH_HEIGHT_RATIO
        # Opposite sign from Notch's "tip": the recess goes inward into
        # this pixel's own solid, not outward past the shared boundary.
        recessed = face.offset(self.fixedValue, -NOTCH_DEPTH)

        tris = []
        tris += _faceQuad(face, self.fixedValue, self.u0, uA, self.capY0, self.capY1)              # left flank
        tris += _faceQuad(face, self.fixedValue, uB, self.u1, self.capY0, self.capY1)              # right flank
        tris += _faceQuad(face, self.fixedValue, uA, uB, self.capY0, recessBotY)                    # below the recess

        flushA_bot = _facePoint(face, self.fixedValue, uA, recessBotY)
        flushB_bot = _facePoint(face, self.fixedValue, uB, recessBotY)
        recA_top = _facePoint(face, recessed, uA, recessTopY)
        recB_top = _facePoint(face, recessed, uB, recessTopY)
        flushA_top = _facePoint(face, self.fixedValue, uA, recessTopY)
        flushB_top = _facePoint(face, self.fixedValue, uB, recessTopY)

        tris += _quad(flushA_bot, flushB_bot, recB_top, recA_top)   # the recess floor (ramp)
        tris += [flushA_bot, flushA_top, recA_top]                   # end wall at uA
        tris += [flushB_bot, recB_top, flushB_top]                   # end wall at uB
        return tris


class Cap:
    """The pixel's own top layer: a full-width unit-height slab, flared
    outward on any clear (bulged) side, with an Inlet cut into any side
    facing a taller neighbor, and simply omitted on any fused side."""

    def __init__(self, x0, x1, z0, z1, y0, y1, openFaces, inlets):
        self.x0, self.x1, self.z0, self.z1 = x0, x1, z0, z1
        self.y0, self.y1 = y0, y1
        self.openFaces = openFaces
        self.inlets = {inlet.face: inlet for inlet in inlets}

    def triangles(self):
        tris = []
        for face in Face:
            if face in self.openFaces:
                continue
            if face in self.inlets:
                tris += self.inlets[face].triangles()
            else:
                fixedValue, u0, u1 = _faceRange(face, self.x0, self.z0, self.x1, self.z1)
                tris += _faceQuad(face, fixedValue, u0, u1, self.y0, self.y1)

        tris += _quad(
            Vector3(self.x0, self.y1, self.z0), Vector3(self.x1, self.y1, self.z0),
            Vector3(self.x1, self.y1, self.z1), Vector3(self.x0, self.y1, self.z1),
        )
        return tris


class Collar:
    """The flat frame connecting the cap's (possibly bulged) outer edge to
    the narrower tube directly below it, at their shared seam - without
    this, a narrower tube meeting a wider cap leaves a gap."""

    def __init__(self, capBounds, tubeBounds, y, openFaces):
        self.capX0, self.capX1, self.capZ0, self.capZ1 = capBounds
        self.tubeX0, self.tubeX1, self.tubeZ0, self.tubeZ1 = tubeBounds
        self.y = y
        self.openFaces = openFaces

    def triangles(self):
        outer = {
            'nw': (self.capX0, self.capZ0), 'ne': (self.capX1, self.capZ0),
            'sw': (self.capX0, self.capZ1), 'se': (self.capX1, self.capZ1),
        }
        inner = {
            'nw': (self.tubeX0, self.tubeZ0), 'ne': (self.tubeX1, self.tubeZ0),
            'sw': (self.tubeX0, self.tubeZ1), 'se': (self.tubeX1, self.tubeZ1),
        }

        def v(pt):
            return Vector3(pt[0], self.y, pt[1])

        tris = []
        if Face.WEST not in self.openFaces:
            tris += _quad(v(outer['nw']), v(outer['sw']), v(inner['sw']), v(inner['nw']))
        if Face.EAST not in self.openFaces:
            tris += _quad(v(outer['ne']), v(inner['ne']), v(inner['se']), v(outer['se']))
        if Face.NORTH not in self.openFaces:
            tris += _quad(v(outer['nw']), v(inner['nw']), v(inner['ne']), v(outer['ne']))
        if Face.SOUTH not in self.openFaces:
            tris += _quad(v(outer['sw']), v(outer['se']), v(inner['se']), v(inner['sw']))
        return tris


class Tube:
    """Everything below the cap, running from the print bed up to the
    cap's underside - always narrower than the cap (that inset is what
    makes room for the bulge and the notch/inlet mechanism). Carries a
    Notch for every side where this pixel is taller than its neighbor."""

    def __init__(self, x0, x1, z0, z1, y1, openFaces, hollow, notches):
        self.x0, self.x1, self.z0, self.z1 = x0, x1, z0, z1
        self.y1 = y1
        self.openFaces = openFaces
        self.hollow = hollow
        self.notches = notches

    def triangles(self):
        skip = {face.boxKey for face in self.openFaces} | {'+y', '-y'}
        tris = _box((self.x0, 0.0, self.z0), (self.x1, self.y1, self.z1), skip=skip)

        if self.hollow:
            w = WALL_THICKNESS
            ix0, iz0, ix1, iz1 = self.x0 + w, self.z0 + w, self.x1 - w, self.z1 - w
            if ix1 > ix0 and iz1 > iz0:
                tris += _box((ix0, 0.0, iz0), (ix1, self.y1, iz1), skip=skip)

        for notch in self.notches:
            tris += notch.triangles()
        return tris


class Pixel:
    """The full solid for one occupied grid cell, assembled from a
    PixelPlan: a Cap, and - if the pixel is taller than one layer - a
    Tube and the Collar closing the seam between them."""

    def __init__(self, plan, hollow: bool):
        self.plan = plan

        x0, z0 = float(plan.x), float(plan.y)
        x1, z1 = x0 + 1.0, z0 + 1.0
        capX0 = x0 - (BULGE_SIZE if Face.WEST in plan.bulged else 0.0)
        capX1 = x1 + (BULGE_SIZE if Face.EAST in plan.bulged else 0.0)
        capZ0 = z0 - (BULGE_SIZE if Face.NORTH in plan.bulged else 0.0)
        capZ1 = z1 + (BULGE_SIZE if Face.SOUTH in plan.bulged else 0.0)
        capY0, capY1 = plan.height - 1.0, float(plan.height)

        inlets = []
        for face, neighborHeight in plan.inlets.items():
            fixedValue, u0, u1 = _faceRange(face, capX0, capZ0, capX1, capZ1)
            inlets.append(Inlet(face, fixedValue, u0, u1, capY0, capY1))

        self.cap = Cap(capX0, capX1, capZ0, capZ1, capY0, capY1, plan.fused, inlets)

        self.tube = None
        self.collar = None
        if capY0 > 0:
            m = TUBE_MARGIN
            tubeBounds = (x0 + m, x1 - m, z0 + m, z1 - m)

            notches = []
            for face, neighborHeight in plan.notches.items():
                boundaryValue, u0, u1 = _faceRange(face, x0, z0, x1, z1)
                uMid, uHalf = (u0 + u1) / 2.0, (u1 - u0) * NOTCH_WIDTH_RATIO / 2.0
                notches.append(Notch(face, boundaryValue, uMid, uHalf, neighborHeight))

            self.tube = Tube(*tubeBounds, capY0, plan.fused, hollow, notches)
            self.collar = Collar((capX0, capX1, capZ0, capZ1), tubeBounds, capY0, plan.fused)

    def triangles(self):
        tris = list(self.cap.triangles())
        if self.tube:
            tris += self.tube.triangles()
            tris += self.collar.triangles()
        return tris

    def warnings(self):
        if not self.tube:
            return []
        y, x = self.plan.position
        return [
            f"Thin connector at ({y}, {x}) side {notch.face.label}: "
            f"drop of {self.plan.height - notch.neighborHeight} layers "
            f"over a {1.0 - 2 * TUBE_MARGIN:.2f}-unit-wide tube."
            for notch in self.tube.notches
            if notch.isThinRelativeTo(self.plan.height)
        ]
