from .pixelPlan import Face
from .vector import *


# Axes: X = pixel column, Z = pixel row, Y = height (the vertical/print
# axis - Y-up). Every layer of height is exactly 1 world unit.
TUBE_MARGIN = 0.12           # how far the tube is inset from the pixel's unit-square edge
WALL_THICKNESS = 0.1         # shell thickness when a Tube is hollow
NOTCH_DEPTH = 0.04           # how far a notch pokes past the shared pixel boundary
NOTCH_WIDTH_RATIO = 0.3      # fraction of a face's width a notch/inlet spans, centered
NOTCH_HEIGHT_RATIO = 0.2     # notch/inlet height as a fraction of the cap's own height
NOTCH_TOP_MARGIN = 0.2       # gap left above the notch/inlet band, so it isn't flush with the top edge
BULGE_SIZE = 0.10            # how far a cap flares out past the grid edge on a clear side
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
    # _facePoint maps u to z for x-axis faces but to x for z-axis faces -
    # swapping which physical axis u/fixedValue land on is itself
    # orientation-reversing (right-handed x,y,z), so the same sign check
    # that picks the correct winding for EAST/WEST picks the wrong one for
    # NORTH/SOUTH unless it's inverted here. Was a real bug, not just a
    # cosmetic one: it made every NORTH/SOUTH quad from this helper (Cap
    # walls, Inlet flanks, wall extensions, ...) wind opposite to the
    # EAST/WEST ones and to _box()'s own convention, leaving genuinely
    # closed seams between them flagged as non-manifold.
    forward = face.sign > 0
    if face.axis == 'z':
        forward = not forward
    if forward:
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
        topY = float(self.neighborHeight) - NOTCH_TOP_MARGIN
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
        recessTopY = self.capY1 - NOTCH_TOP_MARGIN
        recessBotY = recessTopY - NOTCH_HEIGHT_RATIO
        # Opposite sign from Notch's "tip": the recess goes inward into
        # this pixel's own solid, not outward past the shared boundary.
        recessed = face.offset(self.fixedValue, -NOTCH_DEPTH)

        tris = []
        tris += _faceQuad(face, self.fixedValue, self.u0, uA, self.capY0, self.capY1)              # left flank
        tris += _faceQuad(face, self.fixedValue, uB, self.u1, self.capY0, self.capY1)              # right flank
        tris += _faceQuad(face, self.fixedValue, uA, uB, self.capY0, recessBotY)                    # below the recess
        tris += _faceQuad(face, self.fixedValue, uA, uB, recessTopY, self.capY1)                    # above the recess

        flushA_bot = _facePoint(face, self.fixedValue, uA, recessBotY)
        flushB_bot = _facePoint(face, self.fixedValue, uB, recessBotY)
        recA_top = _facePoint(face, recessed, uA, recessTopY)
        recB_top = _facePoint(face, recessed, uB, recessTopY)
        flushA_top = _facePoint(face, self.fixedValue, uA, recessTopY)
        flushB_top = _facePoint(face, self.fixedValue, uB, recessTopY)

        # Same axis-vs-sign story as _faceQuad (see its own comment): these
        # three pieces meet each other at real edges (the ramp's two ends
        # against the two end walls), so their winding has to flip
        # together as a set whenever this effective sign does, not each
        # independently, and not by raw face.sign alone.
        forward = face.sign > 0
        if face.axis == 'z':
            forward = not forward
        if forward:
            tris += _quad(flushA_bot, flushB_bot, recB_top, recA_top)   # the recess floor (ramp)
            tris += [flushA_bot, recA_top, flushA_top]                   # end wall at uA
            tris += [flushB_bot, flushB_top, recB_top]                   # end wall at uB
        else:
            tris += _quad(recA_top, recB_top, flushB_bot, flushA_bot)   # the recess floor (ramp)
            tris += [flushA_bot, flushA_top, recA_top]                   # end wall at uA
            tris += [flushB_bot, recB_top, flushB_top]                   # end wall at uB
        return tris


class Cap:
    """The pixel's own top layer: a full-width unit-height slab, flared
    outward on any clear (bulged) side, with an Inlet cut into any side
    facing a taller neighbor, and simply omitted on any fused side."""

    def __init__(self, x0, x1, z0, z1, y0, y1, openFaces, inlets, floorBounds=None):
        self.x0, self.x1, self.z0, self.z1 = x0, x1, z0, z1
        self.y0, self.y1 = y0, y1
        self.openFaces = openFaces
        self.inlets = {inlet.face: inlet for inlet in inlets}
        # The underside quad below closes over exactly this rectangle:
        # - None (default, no Tube below): the cap's own full footprint -
        #   nothing else is going to close it, so it's fully self-contained.
        # - False (a solid Tube below): omitted entirely. A solid tube is
        #   real material all the way from the print bed up to here, so
        #   there's no actual boundary between it and the cap above it in
        #   the tube's own footprint - drawing a floor there would be a
        #   redundant internal wall sealed inside solid material, not a
        #   real surface. The ring outside the tube's footprint is still a
        #   real boundary (air below, cap above) - that's the Collar's job.
        # - a (x0, x1, z0, z1) tuple (a hollow Tube below): the tube's own
        #   footprint, to seal its hollow cavity's open top - a real
        #   surface this time, since there's genuinely air below it.
        self.drawFloor = floorBounds is not False
        self.floorX0, self.floorX1, self.floorZ0, self.floorZ1 = (
            (x0, x1, z0, z1) if not floorBounds else floorBounds
        )

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
        if not self.drawFloor:
            return tris
        # The underside, wound the other way round so it faces down instead
        # of up - without it the cap is an open shell on its underside,
        # relying on whatever sits below to close it. Only spans floorBounds
        # (see __init__), not the full footprint, so it doesn't re-cover the
        # ring a Collar already handles.
        tris += _quad(
            Vector3(self.floorX0, self.y0, self.floorZ1), Vector3(self.floorX1, self.y0, self.floorZ1),
            Vector3(self.floorX1, self.y0, self.floorZ0), Vector3(self.floorX0, self.y0, self.floorZ0),
        )
        return tris


class Collar:
    """The flat frame connecting the cap's (possibly bulged) outer edge to
    the narrower tube directly below it, at their shared seam. The cap's
    own underside only closes over the tube's footprint (see Cap), so this
    ring - between that and the cap's actual outer edge - is the only
    thing that closes it; without this, a narrower tube meeting a wider
    cap leaves a gap. Plain-wall sides need no frame at all: their tube
    already sits flush with the cap above it, so there's no step to close
    (see Pixel)."""

    def __init__(self, capBounds, tubeBounds, y, skipFaces):
        self.capX0, self.capX1, self.capZ0, self.capZ1 = capBounds
        self.tubeX0, self.tubeX1, self.tubeZ0, self.tubeZ1 = tubeBounds
        self.y = y
        self.skipFaces = skipFaces

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
        if Face.WEST not in self.skipFaces:
            tris += _quad(v(outer['nw']), v(outer['sw']), v(inner['sw']), v(inner['nw']))
        if Face.EAST not in self.skipFaces:
            tris += _quad(v(outer['ne']), v(inner['ne']), v(inner['se']), v(outer['se']))
        if Face.NORTH not in self.skipFaces:
            tris += _quad(v(outer['nw']), v(inner['nw']), v(inner['ne']), v(outer['ne']))
        if Face.SOUTH not in self.skipFaces:
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
        sideSkip = {face.boxKey for face in self.openFaces}

        if self.hollow:
            tris = []
            for face in Face:
                if face.boxKey in sideSkip:
                    continue
                tris += self._wallBox(face)
        else:
            # Top is covered by the cap's own downward-facing bottom quad
            # (see Cap.triangles) so it's skipped here same as the hollow
            # case above - but unlike a hollow wall's own box (each of
            # which closes itself off at the print bed, see _wallBox), a
            # solid tube's box was never given its own floor, leaving every
            # solid part open on its underside.
            tris = _box((self.x0, 0.0, self.z0), (self.x1, self.y1, self.z1), skip=sideSkip | {'+y'})

        for notch in self.notches:
            tris += notch.triangles()
        return tris

    def _wallBox(self, face, u0=None, u1=None):
        """A solid slab standing in for `face`'s wall: its outer face is
        exactly that wall (so it lines up with whatever's flush against
        it), thickened inward by WALL_THICKNESS - never outward past the
        tube's own boundary. No shared cavity, just one box per wall.

        u0/u1 override the wall's own span along its length - used to
        extend a wall past its own footprint to meet another pixel's wall
        at a shared elbow corner (see _wallExtension), so the extension
        is built by the same box construction as the rest of the wall
        and gets the same thickness, floor and ceiling, rather than being
        a separate flat patch bolted on afterwards."""
        outer = _tubeBoundary(self, face)
        inner = face.offset(outer, -WALL_THICKNESS)
        if u0 is None:
            u0, u1 = (self.z0, self.z1) if face.axis == 'x' else (self.x0, self.x1)
        else:
            u0, u1 = sorted((u0, u1))
        if face.axis == 'x':
            x0, x1 = sorted((outer, inner))
            z0, z1 = u0, u1
        else:
            z0, z1 = sorted((outer, inner))
            x0, x1 = u0, u1
        if x1 <= x0 or z1 <= z0:
            return []
        # Fully closed on its own, top and bottom included: the cap's own
        # bottom face (see Cap.triangles) does cover this box's footprint
        # from above, but as one flat quad spanning the whole cap it doesn't
        # share edges with this box's small rim - a seam a strict manifold
        # check would flag, even though nothing's actually open there. Not
        # depending on that alignment at all is simpler than trying to keep
        # the two in sync.
        return _box((x0, 0.0, z0), (x1, self.y1, z1))


def _tubeBoundary(tube, face):
    if face is Face.NORTH:
        return tube.z0
    if face is Face.SOUTH:
        return tube.z1
    if face is Face.WEST:
        return tube.x0
    return tube.x1  # Face.EAST


def _wallExtension(pixel, wallFace, seamValue, targetValue):
    """A longer version of `pixel`'s own wallFace wall: same plane, same
    orientation, its u-range just widened from its current flush end
    (seamValue) out to targetValue. Not a new face in a different plane -
    literally that wall, extended. When the tube is hollow this goes
    through Tube._wallBox like the rest of the wall, so the extension is
    reinforced (thickness, floor, ceiling) the same way; a solid tube's
    wall is already fully filled material, so a flat quad is enough to
    extend its skin."""
    if seamValue == targetValue:
        return []
    tube = pixel.tube
    if tube.hollow:
        return tube._wallBox(wallFace, seamValue, targetValue)
    fixedValue = _tubeBoundary(tube, wallFace)
    u0, u1 = sorted((seamValue, targetValue))
    return _faceQuad(wallFace, fixedValue, u0, u1, 0.0, tube.y1)


def elbowWallExtensions(P, Q, f1, f2):
    """P and Q are diagonal neighbors of a shared "elbow" pixel, fused to
    it via the perpendicular faces f1 (toward P) and f2 (toward Q) - P and
    Q are not fused to each other at all. Each already draws its own wall
    facing the other's general direction (P's f2 wall, Q's f1 wall), but
    each stops short at its own flush boundary with the elbow. This
    extends each wall's own length, in its own plane, out to wherever the
    other one's wall actually sits, so they cross inside the elbow
    pixel's footprint instead of leaving a gap between them."""
    tris = []
    if f2 not in P.plan.flushTubeSides:
        seamP = _tubeBoundary(P.tube, f1.opposite)
        targetP = _tubeBoundary(Q.tube, f1)
        tris += _wallExtension(P, f2, seamP, targetP)
    if f1 not in Q.plan.flushTubeSides:
        seamQ = _tubeBoundary(Q.tube, f2.opposite)
        targetQ = _tubeBoundary(P.tube, f2)
        tris += _wallExtension(Q, f1, seamQ, targetQ)
    return tris


_PERPENDICULARS = {
    Face.WEST: (Face.NORTH, Face.SOUTH), Face.EAST: (Face.NORTH, Face.SOUTH),
    Face.NORTH: (Face.WEST, Face.EAST), Face.SOUTH: (Face.WEST, Face.EAST),
}


def _capBoundary(pixel, face):
    if face is Face.NORTH:
        return pixel.cap.z0
    if face is Face.SOUTH:
        return pixel.cap.z1
    if face is Face.WEST:
        return pixel.cap.x0
    return pixel.cap.x1  # Face.EAST


def bulgeSeamPatch(pixel, neighbor, fusedFace):
    """`pixel` is fused to `neighbor` across fusedFace, so its own cap wall
    there is skipped entirely - the two caps are assumed to line up and
    merge into one continuous surface. That assumption breaks when
    `pixel` bulges on a side perpendicular to fusedFace and `neighbor`
    doesn't bulge the same way: `pixel`'s cap then reaches further along
    that edge than `neighbor`'s does, and the sliver in between - past
    `neighbor`'s edge, up to `pixel`'s own bulged edge - has no wall at
    all. Patch just that sliver, on `pixel`'s own face, in its own
    plane."""
    tris = []
    fixedValue = _capBoundary(pixel, fusedFace)
    for perpendicular in _PERPENDICULARS[fusedFace]:
        if perpendicular not in pixel.plan.bulged or perpendicular in neighbor.plan.bulged:
            continue
        u0, u1 = sorted((_capBoundary(neighbor, perpendicular), _capBoundary(pixel, perpendicular)))
        tris += _faceQuad(fusedFace, fixedValue, u0, u1, pixel.cap.y0, pixel.cap.y1)
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

        tubeBounds = None
        if capY0 > 0:
            m = TUBE_MARGIN
            # Fused and plain-wall sides need no clearance from their
            # neighbor: the tube sits flush with the grid boundary there
            # instead of inset, so the two tubes' solids actually meet
            # (fused) or touch (plain wall) rather than each standing
            # apart with a gap between them - only notch/inlet sides (need
            # room for the interlock) and bulge sides (need room for the
            # diagonal-fill trick) stay inset.
            flush = plan.flushTubeSides
            tubeX0 = x0 if Face.WEST in flush else x0 + m
            tubeX1 = x1 if Face.EAST in flush else x1 - m
            tubeZ0 = z0 if Face.NORTH in flush else z0 + m
            tubeZ1 = z1 if Face.SOUTH in flush else z1 - m
            tubeBounds = (tubeX0, tubeX1, tubeZ0, tubeZ1)

        # A tube below narrows (hollow) or entirely removes (solid - real,
        # continuous material already, no boundary to draw) what the cap's
        # own underside needs to close (see Cap.__init__) - the ring
        # outside that is the Collar's job either way.
        if tubeBounds is None:
            floorBounds = None
        elif hollow:
            floorBounds = tubeBounds
        else:
            floorBounds = False
        self.cap = Cap(capX0, capX1, capZ0, capZ1, capY0, capY1, plan.fused, inlets, floorBounds=floorBounds)

        self.tube = None
        self.collar = None
        if tubeBounds is not None:
            notches = []
            for face, neighborHeight in plan.notches.items():
                boundaryValue, u0, u1 = _faceRange(face, x0, z0, x1, z1)
                uMid, uHalf = (u0 + u1) / 2.0, (u1 - u0) * NOTCH_WIDTH_RATIO / 2.0
                notches.append(Notch(face, boundaryValue, uMid, uHalf, neighborHeight))

            self.tube = Tube(*tubeBounds, capY0, plan.fused, hollow, notches)
            self.collar = Collar((capX0, capX1, capZ0, capZ1), tubeBounds, capY0, flush)

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
