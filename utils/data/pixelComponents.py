import numpy as np
import trimesh

from .pixelPlan import Face
from .vector import Vector3


# Axes: X = pixel column, Z = pixel row, Y = height (the vertical/print
# axis - Y-up). Every layer of height is exactly 1 world unit.
TUBE_MARGIN = 0.12           # how far the tube is inset from the pixel's unit-square edge
WALL_THICKNESS = 0.1         # shell thickness when a Tube is hollow
BULGE_SIZE = 0.10            # how far a cap flares out past the grid edge on a clear side


def _box(x0, x1, y0, y1, z0, z1):
    """An axis-aligned box mesh spanning the given bounds."""
    box = trimesh.creation.box(extents=(x1 - x0, y1 - y0, z1 - z0))
    box.apply_translation(((x0 + x1) / 2.0, (y0 + y1) / 2.0, (z0 + z1) / 2.0))
    return box


def _toTrimesh(triangles):
    verts = [(v.x, v.y, v.z) for v in triangles]
    faces = [[i, i + 1, i + 2] for i in range(0, len(triangles), 3)]
    return trimesh.Trimesh(vertices=verts, faces=faces, process=True)


def _fromTrimesh(mesh):
    triangles = []
    for face in mesh.faces:
        for vertexIndex in face:
            x, y, z = mesh.vertices[vertexIndex]
            triangles.append(Vector3(float(x), float(y), float(z)))
    return triangles


# ---------------------------------------------------------------------------
# Boundary construction: PixelPlanner already classifies every side of every
# pixel as fused/bulged/plainWalls - that *is* the boundary (fused = interior,
# nothing else exposes a wall there). So a whole connected group's cap or
# tube hull is built directly from that classification: trace the boundary
# at native grid resolution, offset each edge by whatever its own pixel+face
# already dictates (cap: bulgeSize outward if bulged; tube: tubeMargin
# inward unless flush), dog-ear triangulate, extrude. No boolean CSG for any
# of that - only a handful of already-simplified pieces (a hole cut from a
# cap, cavities cut from a tube, or the final cap+tube union) ever go through
# a boolean op, and each of those is O(1) in canvas size, not O(pixels).
#
# See ARCHITECTURE.md-adjacent history: an earlier hand-fitted Cap/Tube/
# Collar system (pre-dating the plain-box-plus-boolean-union rewrite) was
# abandoned because independently-triangulated pieces kept not-quite-sharing
# edges. The difference here is there's exactly one triangulation per whole
# connected group (not one per pixel) built off a single boundary trace, so
# there's no seam between independently-built pieces to get wrong.
# ---------------------------------------------------------------------------

_FACE = {'N': Face.NORTH, 'S': Face.SOUTH, 'E': Face.EAST, 'W': Face.WEST}
_DIR = {'N': (1, 0), 'S': (-1, 0), 'E': (0, 1), 'W': (0, -1)}


def _rawEdges(covered):
    """Boundary edges of `covered` (a 2D bool array) at native resolution,
    found via array-shift transitions rather than visiting every cell -
    cost is proportional to perimeter, not area."""
    rows, cols = covered.shape
    above = np.vstack([np.zeros((1, cols), dtype=bool), covered])
    below = np.vstack([covered, np.zeros((1, cols), dtype=bool)])
    diffH = below.astype(np.int8) - above.astype(np.int8)
    nH, nC = np.nonzero(diffH == 1)
    sH, sC = np.nonzero(diffH == -1)

    left = np.hstack([np.zeros((rows, 1), dtype=bool), covered])
    right = np.hstack([covered, np.zeros((rows, 1), dtype=bool)])
    diffV = right.astype(np.int8) - left.astype(np.int8)
    wR, wV = np.nonzero(diffV == 1)
    eR, eV = np.nonzero(diffV == -1)

    edges = []
    edges += [('N', r, c) for r, c in zip(nH.tolist(), nC.tolist())]
    edges += [('S', r, c) for r, c in zip((sH - 1).tolist(), sC.tolist())]
    edges += [('W', r, c) for r, c in zip(wR.tolist(), wV.tolist())]
    edges += [('E', r, c) for r, c in zip(eR.tolist(), (eV - 1).tolist())]
    return edges


def _rawEndpoints(kind, r, c):
    """Local-grid integer endpoints of one raw edge, in a fixed CCW-around-
    the-cell order - the convention that makes two adjacent covered cells'
    shared edge cancel out (opposite direction) when both are present."""
    if kind == 'N':
        return (c, r), (c + 1, r)
    if kind == 'E':
        return (c + 1, r), (c + 1, r + 1)
    if kind == 'S':
        return (c + 1, r + 1), (c, r + 1)
    if kind == 'W':
        return (c, r + 1), (c, r)


def _axis(kind):
    return 'H' if kind in ('N', 'S') else 'V'


def _capOffset(kind, r, c, plans, minY, minX, bulgeSize):
    """This raw cap edge's own fixed perpendicular coordinate: shifted
    outward by bulgeSize if that pixel's own face is bulged, otherwise
    flush (a plainWall side stays exactly on the grid line)."""
    gy, gx = r + minY, c + minX
    bulged = _FACE[kind] in plans[(gy, gx)].bulged
    if kind == 'N':
        return gy - bulgeSize if bulged else gy
    if kind == 'S':
        return gy + 1 + bulgeSize if bulged else gy + 1
    if kind == 'W':
        return gx - bulgeSize if bulged else gx
    if kind == 'E':
        return gx + 1 + bulgeSize if bulged else gx + 1


def _tubeOffset(kind, r, c, plans, minY, minX, tubeMargin):
    """Same idea as _capOffset, but inset (not outset) unless flush."""
    gy, gx = r + minY, c + minX
    flush = _FACE[kind] in plans[(gy, gx)].flushTubeSides
    if kind == 'N':
        return gy if flush else gy + tubeMargin
    if kind == 'S':
        return gy + 1 if flush else gy + 1 - tubeMargin
    if kind == 'W':
        return gx if flush else gx + tubeMargin
    if kind == 'E':
        return gx + 1 if flush else gx + 1 - tubeMargin


def _signedArea(loop):
    area = 0.0
    n = len(loop)
    for i in range(n):
        x0, z0 = loop[i]
        x1, z1 = loop[(i + 1) % n]
        area += x0 * z1 - x1 * z0
    return area / 2.0


def _mergeCollinear(loop):
    n = len(loop)
    out = []
    for i in range(n):
        px, pz = loop[i - 1]
        x, z = loop[i]
        nx, nz = loop[(i + 1) % n]
        if (px == x == nx) or (pz == z == nz):
            continue
        out.append((x, z))
    return out


def _isConvex(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) > 1e-12


def _pointInTri(p, a, b, c):
    def sign(p1, p2, p3):
        return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])
    d1, d2, d3 = sign(p, a, b), sign(p, b, c), sign(p, c, a)
    hasNeg, hasPos = (d1 < 0 or d2 < 0 or d3 < 0), (d1 > 0 or d2 > 0 or d3 > 0)
    return not (hasNeg and hasPos)


def _earClip(loop):
    """Ear-clipping (dog-ear) triangulation of a simple polygon (list of
    (x, z), any winding - normalized to CCW here). Every loop this module
    builds is a plain orthogonal polygon (only axis-aligned edges), so this
    never has to handle anything more exotic than that."""
    poly = list(loop)
    if _signedArea(poly) < 0:
        poly.reverse()
    tris = []
    guard = 0
    while len(poly) > 3 and guard < 10000:
        guard += 1
        n = len(poly)
        clipped = False
        for i in range(n):
            a, b, c = poly[i - 1], poly[i], poly[(i + 1) % n]
            if not _isConvex(a, b, c):
                continue
            if any(p not in (a, b, c) and _pointInTri(p, a, b, c) for p in poly):
                continue
            tris.append((a, b, c))
            del poly[i]
            clipped = True
            break
        if not clipped:
            break
    if len(poly) == 3:
        tris.append((poly[0], poly[1], poly[2]))
    return tris


def _extrudeSolid(loop, yBottom, yTop):
    """One simple polygon (list of (x, z), any winding - see _earClip)
    extruded into a closed solid's triangles."""
    if _signedArea(loop) < 0:
        loop = list(reversed(loop))
    triangles = []
    for (a, b, c) in _earClip(loop):
        triangles += [Vector3(a[0], yTop, a[1]), Vector3(c[0], yTop, c[1]), Vector3(b[0], yTop, b[1])]
        triangles += [Vector3(a[0], yBottom, a[1]), Vector3(b[0], yBottom, b[1]), Vector3(c[0], yBottom, c[1])]
    n = len(loop)
    for i in range(n):
        xa, za = loop[i]
        xb, zb = loop[(i + 1) % n]
        triangles += [Vector3(xa, yBottom, za), Vector3(xb, yTop, zb), Vector3(xb, yBottom, zb)]
        triangles += [Vector3(xa, yBottom, za), Vector3(xa, yTop, za), Vector3(xb, yTop, zb)]
    return triangles


def _hasPinchPoint(planByPos):
    """True if two parts of this group touch at a single grid corner with
    no shared edge (e.g. diagonal pixels whose bulges overlap but nothing
    fuses them) - a real topological ambiguity (which of the two crossing
    boundary edges continues the loop?), not a rare theoretical case to
    silently guess at. Cheap to check, and independent of cap vs tube
    (it's purely about which grid cells are present)."""
    ys = [p.y for p in planByPos.values()]
    xs = [p.x for p in planByPos.values()]
    minY, minX = min(ys), min(xs)
    rows, cols = max(ys) - minY + 1, max(xs) - minX + 1
    covered = np.zeros((rows, cols), dtype=bool)
    for (y, x) in planByPos:
        covered[y - minY, x - minX] = True
    outgoing = {}
    for kind, r, c in _rawEdges(covered):
        a, _ = _rawEndpoints(kind, r, c)
        outgoing[a] = outgoing.get(a, 0) + 1
    return any(n > 1 for n in outgoing.values())


def _buildBoundarySolid(planByPos, offsetFn, margin, yBottom, yTop, outward):
    """The shared engine behind both _capSolid and _tubeSolid: trace the
    boundary at native grid resolution from `planByPos`, offset each raw
    edge via `offsetFn`, join consecutive edges, ear-clip, extrude. Callers
    must have already ruled out a pinch point (see _hasPinchPoint)."""
    ys = [p.y for p in planByPos.values()]
    xs = [p.x for p in planByPos.values()]
    minY, minX = min(ys), min(xs)
    rows, cols = max(ys) - minY + 1, max(xs) - minX + 1
    covered = np.zeros((rows, cols), dtype=bool)
    for (y, x) in planByPos:
        covered[y - minY, x - minX] = True

    nxt, info = {}, {}
    for kind, r, c in _rawEdges(covered):
        a, b = _rawEndpoints(kind, r, c)
        nxt[a] = b
        info[(a, b)] = (kind, r, c)

    visited = set()
    rawLoops = []
    for start in list(nxt.keys()):
        if start in visited:
            continue
        loop = [start]
        visited.add(start)
        cur = nxt[start]
        while cur != start:
            loop.append(cur)
            visited.add(cur)
            cur = nxt[cur]
        rawLoops.append(loop)

    outer, holes = [], []
    for rawLoop in rawLoops:
        n = len(rawLoop)
        edgeKinds = [info[(rawLoop[i], rawLoop[(i + 1) % n])] for i in range(n)]

        outVerts = []
        for i in range(n):
            prevKind, pr, pc = edgeKinds[i - 1]
            curKind, cr, cc = edgeKinds[i]
            rawX, rawZ = rawLoop[i]
            offPrev = offsetFn(prevKind, pr, pc, planByPos, minY, minX, margin)
            offCur = offsetFn(curKind, cr, cc, planByPos, minY, minX, margin)
            axPrev, axCur = _axis(prevKind), _axis(curKind)
            if axPrev != axCur:
                prevDir, curDir = _DIR[prevKind], _DIR[curKind]
                cross = prevDir[0] * curDir[1] - prevDir[1] * curDir[0]
                if outward or cross > 0:
                    # Convex corner (either offset direction), or a reflex
                    # corner with outward (cap-style) offsets: the two
                    # offset lines actually cross past the raw corner - two
                    # pixels bulging toward a shared empty corner physically
                    # overlap there, so their intersection is the real
                    # boundary point.
                    x = offCur if axCur == 'V' else offPrev
                    z = offPrev if axPrev == 'H' else offCur
                    outVerts.append((x, z))
                else:
                    # Reflex corner with inward (tube-style) offsets: both
                    # edges pull *away* from the corner, so they never
                    # reach each other - the boundary has to route through
                    # the original raw grid corner instead.
                    outVerts.append((rawX, offPrev) if axPrev == 'H' else (offPrev, rawZ))
                    outVerts.append((rawX, rawZ))
                    outVerts.append((rawX, offCur) if axCur == 'H' else (offCur, rawZ))
            elif axCur == 'H':
                outVerts.append((rawX, offPrev))
                if offPrev != offCur:
                    outVerts.append((rawX, offCur))
            else:
                outVerts.append((offPrev, rawZ))
                if offPrev != offCur:
                    outVerts.append((offCur, rawZ))

        area = _signedArea(outVerts)
        merged = _mergeCollinear(outVerts)
        if len(merged) < 3:
            continue
        (outer if area > 0 else holes).append(merged)

    outerTris = []
    for loop in outer:
        outerTris += _extrudeSolid(loop, yBottom, yTop)
    if not outerTris:
        return []
    if not holes:
        return outerTris
    outerMesh = _toTrimesh(outerTris)
    holeMeshes = [_toTrimesh(_extrudeSolid(h, yBottom, yTop)) for h in holes]
    return _fromTrimesh(trimesh.boolean.difference([outerMesh] + holeMeshes))


def _legacyCapSolid(plans, bulgeSize):
    """Fallback for the rare pinch-point case: build each pixel's own cap
    box (exactly the old per-pixel construction) and boolean-union them.
    Only ever reached when _hasPinchPoint is true, so this being O(pixels)
    CSG doesn't matter - real mesh.py usage essentially never hits it (the
    auto base-fill in Mesh._calculateMesh occupies both flanking cells of
    any diagonal pair, which already suppresses this exact connectivity)."""
    boxes = []
    for plan in plans:
        x0, z0 = float(plan.x), float(plan.y)
        x1, z1 = x0 + 1.0, z0 + 1.0
        capX0 = x0 - (bulgeSize if Face.WEST in plan.bulged else 0.0)
        capX1 = x1 + (bulgeSize if Face.EAST in plan.bulged else 0.0)
        capZ0 = z0 - (bulgeSize if Face.NORTH in plan.bulged else 0.0)
        capZ1 = z1 + (bulgeSize if Face.SOUTH in plan.bulged else 0.0)
        boxes.append(_box(capX0, capX1, plan.height - 1.0, float(plan.height), capZ0, capZ1))
    merged = trimesh.boolean.union(boxes) if len(boxes) > 1 else boxes[0]
    return _fromTrimesh(merged)


def _legacyTubeSolid(plans, tubeMargin):
    """Tube-side counterpart to _legacyCapSolid - same rare fallback."""
    boxes = []
    for plan in plans:
        if plan.height <= 1:
            continue
        x0, z0 = float(plan.x), float(plan.y)
        x1, z1 = x0 + 1.0, z0 + 1.0
        flush = plan.flushTubeSides
        m = tubeMargin
        tubeX0 = x0 if Face.WEST in flush else x0 + m
        tubeX1 = x1 if Face.EAST in flush else x1 - m
        tubeZ0 = z0 if Face.NORTH in flush else z0 + m
        tubeZ1 = z1 if Face.SOUTH in flush else z1 - m
        boxes.append(_box(tubeX0, tubeX1, 0.0, plan.height - 1.0, tubeZ0, tubeZ1))
    if not boxes:
        return []
    merged = trimesh.boolean.union(boxes) if len(boxes) > 1 else boxes[0]
    return _fromTrimesh(merged)


def _capSolid(planByPos, bulgeSize, yBottom, yTop, usePinchFallback):
    if usePinchFallback:
        return _legacyCapSolid(list(planByPos.values()), bulgeSize)
    return _buildBoundarySolid(planByPos, _capOffset, bulgeSize, yBottom, yTop, outward=True)


def _tubeSolid(planByPos, tubeMargin, yTop, usePinchFallback):
    if usePinchFallback:
        return _legacyTubeSolid(list(planByPos.values()), tubeMargin)
    return _buildBoundarySolid(planByPos, _tubeOffset, tubeMargin, 0.0, yTop, outward=False)


def _cavitySolid(plan, tubeMargin, wallThickness):
    """A hollow tube's cavity: an unconditional further inset of the tube
    rectangle by wallThickness, punched a hair past the print bed (y just
    below 0) so it comes out fully open there instead of leaving a
    paper-thin floor sliver. Cavities never merge across pixels - even at
    a flush tube-tube junction they stay separated by 2x wall thickness -
    so each is just its own small box, no dog-ear needed."""
    flush = plan.flushTubeSides
    x0, z0 = float(plan.x), float(plan.y)
    x1, z1 = x0 + 1.0, z0 + 1.0
    m = tubeMargin
    tubeX0 = x0 if Face.WEST in flush else x0 + m
    tubeX1 = x1 if Face.EAST in flush else x1 - m
    tubeZ0 = z0 if Face.NORTH in flush else z0 + m
    tubeZ1 = z1 if Face.SOUTH in flush else z1 - m
    t = wallThickness
    cavX0, cavX1 = tubeX0 + t, tubeX1 - t
    cavZ0, cavZ1 = tubeZ0 + t, tubeZ1 - t
    if cavX1 <= cavX0 or cavZ1 <= cavZ0:
        return None
    loop = [(cavX0, cavZ0), (cavX1, cavZ0), (cavX1, cavZ1), (cavX0, cavZ1)]
    return _extrudeSolid(loop, -0.01, plan.height - 1.0)


def componentTriangles(plans, hollow, tubeMargin=TUBE_MARGIN, wallThickness=WALL_THICKNESS, bulgeSize=BULGE_SIZE):
    """The merged solid for one physically-connected group of same-color,
    same-height PixelPlans (see Mesh._calculateMesh), as a flat list of
    Vector3 - 3 per triangle, no shared indices, matching this codebase's
    usual triangle-soup convention.

    Built directly from each pixel's already-known fused/bulged/flush
    classification (see the boundary-construction block above) rather than
    boolean-unioning one box per pixel: the cap is one hull extrusion, the
    tube (if any pixel is taller than one layer) is another, and cavities
    are simple per-pixel boxes - CSG is used only to combine those already-
    simplified pieces (a hole cut from a hull, cavities cut from the tube,
    or the final cap+tube union), never on a per-pixel basis."""
    planByPos = {(p.y, p.x): p for p in plans}
    height = next(iter(planByPos.values())).height
    usePinchFallback = _hasPinchPoint(planByPos)

    capTris = _capSolid(planByPos, bulgeSize, height - 1.0, float(height), usePinchFallback)
    if height <= 1:
        return capTris

    tubeTris = _tubeSolid(planByPos, tubeMargin, height - 1.0, usePinchFallback)
    if hollow:
        cavityTris = []
        for plan in planByPos.values():
            cavity = _cavitySolid(plan, tubeMargin, wallThickness)
            if cavity:
                cavityTris += cavity
        if cavityTris and tubeTris:
            tubeTris = _fromTrimesh(trimesh.boolean.difference([_toTrimesh(tubeTris), _toTrimesh(cavityTris)]))

    if not tubeTris:
        return capTris
    merged = trimesh.boolean.union([_toTrimesh(capTris), _toTrimesh(tubeTris)])
    return _fromTrimesh(merged)
