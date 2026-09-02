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


def _earClip(loop):
    """Ear-clipping (dog-ear) triangulation of a simple polygon (list of
    (x, z), any winding - normalized to CCW here). Every loop this module
    builds is a plain orthogonal polygon (only axis-aligned edges), so this
    never has to handle anything more exotic than that.

    The "does any other vertex sit inside this candidate ear" check is
    O(n) per candidate ear - unavoidable without a fancier data structure
    - but a big, intricate boundary (the fine-grid pinch fallback's own
    worst case) can have hundreds of vertices, and that check dominated
    this function's cost badly enough to show up as the single largest
    cost in a real 160x160 image's mesh rebuild. Batching it into one
    vectorized point-in-triangle test over all remaining vertices (same
    exact math, just done for every point in one array op instead of one
    Python-level call each) doesn't change the algorithm, just how fast
    each step of it runs.

    Separately: restarting the search for the *next* ear from scratch
    after every single clip (rescanning every remaining vertex in order)
    turns this into roughly O(n) full rescans - each one itself O(n) per
    candidate - i.e. close to O(n^3) overall on a large polygon, on top of
    the per-candidate cost above. Clipping a vertex can only change
    whether its own two former neighbors are ears (nothing else's
    eligibility depends on a vertex that's no longer there), so a single
    pointer that only steps back to recheck those two after a clip, and
    otherwise advances, visits each vertex a bounded number of times
    instead of rescanning everything on every clip."""
    poly = np.array(loop, dtype=float)
    if _signedArea(loop) < 0:
        poly = poly[::-1]
    idx = list(range(len(poly)))
    tris = []
    i = 0
    guard = 0
    maxGuard = len(idx) * len(idx) + 16
    while len(idx) > 3 and guard < maxGuard:
        guard += 1
        m = len(idx)
        k = i % m
        ia, ib, ic = idx[k - 1], idx[k], idx[(k + 1) % m]
        a, b, c = poly[ia], poly[ib], poly[ic]
        isEar = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) > 1e-12
        if isEar:
            others = [j for j in idx if j != ia and j != ib and j != ic]
            if others:
                p = poly[others]
                d1 = (p[:, 0] - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (p[:, 1] - b[1])
                d2 = (p[:, 0] - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (p[:, 1] - c[1])
                d3 = (p[:, 0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (p[:, 1] - a[1])
                hasNeg = (d1 < 0) | (d2 < 0) | (d3 < 0)
                hasPos = (d1 > 0) | (d2 > 0) | (d3 > 0)
                isEar = not bool(np.any(~(hasNeg & hasPos)))
        if isEar:
            tris.append((tuple(a), tuple(b), tuple(c)))
            del idx[k]
            i = k - 1
        else:
            i = k + 1
    if len(idx) == 3:
        tris.append((tuple(poly[idx[0]]), tuple(poly[idx[1]]), tuple(poly[idx[2]])))
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


def _assembleOuterMinusHoles(outer, holes, yBottom, yTop):
    """Extrude `outer` and `holes` (lists of simple polygons, already
    classified by winding) and combine them into one solid. Multiple
    outer loops (or multiple holes) can themselves touch or overlap - the
    fine grid's whole job is turning an ambiguous single-point touch into
    real shared area - so concatenating their triangles into one mesh is
    *not* the same as their union (each piece alone is a valid volume,
    but the naive concatenation generally isn't, and handing a non-volume
    to trimesh.boolean.difference raises "Not all meshes are volumes!").
    So union each side first whenever there's more than one piece, and
    only then take the one final difference. The overwhelmingly common
    case - one outer loop, no holes - needs none of that: round-tripping
    through a full trimesh.Trimesh just to weld vertices nothing else
    touches is pure overhead when there's nothing to union or subtract."""
    if not outer:
        return []
    if len(outer) == 1 and not holes:
        return _extrudeSolid(outer[0], yBottom, yTop)
    outerPieces = [_toTrimesh(_extrudeSolid(loop, yBottom, yTop)) for loop in outer]
    outerMesh = trimesh.boolean.union(outerPieces) if len(outerPieces) > 1 else outerPieces[0]
    if not holes:
        return _fromTrimesh(outerMesh)
    holePieces = [_toTrimesh(_extrudeSolid(loop, yBottom, yTop)) for loop in holes]
    holeMesh = trimesh.boolean.union(holePieces) if len(holePieces) > 1 else holePieces[0]
    return _fromTrimesh(trimesh.boolean.difference([outerMesh, holeMesh]))


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

    return _assembleOuterMinusHoles(outer, holes, yBottom, yTop)


def _axisIndex(coords):
    import bisect
    return lambda v: bisect.bisect_left(coords, v)


def _capCoverageFine(planByPos, bulgeSize):
    """A pinch point (two cells touching at one corner, no shared edge) is
    only ambiguous because a single grid vertex can't represent both a
    'yes' and a 'no' at once. Fatten the grid: subdivide each cell's cap
    footprint into core + one outward margin strip per side (only used
    when that side is actually bulged), via coordinate compression (not a
    fixed-size block - see the comment on this same trick in the git
    history of this module) so neighboring pixels' margins never collide.
    A genuine diagonal overlap (both cells bulging toward the same empty
    corner) then shows up as real, non-zero *area* covered by both -
    which a boundary trace can walk through cleanly, unlike a single
    ambiguous point. This is the fallback for exactly the group where
    _hasPinchPoint is true - a handful of pixels, not the whole canvas -
    so paying a 3x-per-axis grid here costs nothing in practice."""
    xs = sorted({v for p in planByPos.values() for v in (p.x - bulgeSize, p.x, p.x + 1, p.x + 1 + bulgeSize)})
    zs = sorted({v for p in planByPos.values() for v in (p.y - bulgeSize, p.y, p.y + 1, p.y + 1 + bulgeSize)})
    xi, zi = _axisIndex(xs), _axisIndex(zs)
    covered = np.zeros((len(zs) - 1, len(xs) - 1), dtype=bool)

    for (y, x), plan in planByPos.items():
        cx0, cx1 = xi(x), xi(x + 1)
        cz0, cz1 = zi(y), zi(y + 1)
        covered[cz0:cz1, cx0:cx1] = True

        west, east = Face.WEST in plan.bulged, Face.EAST in plan.bulged
        north, south = Face.NORTH in plan.bulged, Face.SOUTH in plan.bulged
        wx0, wx1 = xi(x - bulgeSize), cx0
        ex0, ex1 = cx1, xi(x + 1 + bulgeSize)
        nz0, nz1 = zi(y - bulgeSize), cz0
        sz0, sz1 = cz1, zi(y + 1 + bulgeSize)
        if west: covered[cz0:cz1, wx0:wx1] = True
        if east: covered[cz0:cz1, ex0:ex1] = True
        if north: covered[nz0:nz1, cx0:cx1] = True
        if south: covered[sz0:sz1, cx0:cx1] = True

        wp, ep = planByPos.get((y, x - 1)), planByPos.get((y, x + 1))
        np_, sp = planByPos.get((y - 1, x)), planByPos.get((y + 1, x))
        nw = (west and north) or (wp and Face.NORTH in wp.bulged) or (np_ and Face.WEST in np_.bulged)
        ne = (east and north) or (ep and Face.NORTH in ep.bulged) or (np_ and Face.EAST in np_.bulged)
        sw = (west and south) or (wp and Face.SOUTH in wp.bulged) or (sp and Face.WEST in sp.bulged)
        se = (east and south) or (ep and Face.SOUTH in ep.bulged) or (sp and Face.EAST in sp.bulged)
        if nw: covered[nz0:nz1, wx0:wx1] = True
        if ne: covered[nz0:nz1, ex0:ex1] = True
        if sw: covered[sz0:sz1, wx0:wx1] = True
        if se: covered[sz0:sz1, ex0:ex1] = True

    return covered, np.array(xs), np.array(zs)


def _tubeCoverageFine(planByPos, tubeMargin):
    """Tube counterpart to _capCoverageFine. Insets never reach into a
    neighbor's own territory (unlike a bulge), so unlike the cap this
    needs no neighbor lookups for its corners - self-contained AND."""
    xs = sorted({v for p in planByPos.values() for v in (p.x, p.x + tubeMargin, p.x + 1 - tubeMargin, p.x + 1)})
    zs = sorted({v for p in planByPos.values() for v in (p.y, p.y + tubeMargin, p.y + 1 - tubeMargin, p.y + 1)})
    xi, zi = _axisIndex(xs), _axisIndex(zs)
    covered = np.zeros((len(zs) - 1, len(xs) - 1), dtype=bool)

    for (y, x), plan in planByPos.items():
        cx0, cxIn0, cxIn1, cx1 = xi(x), xi(x + tubeMargin), xi(x + 1 - tubeMargin), xi(x + 1)
        cz0, czIn0, czIn1, cz1 = zi(y), zi(y + tubeMargin), zi(y + 1 - tubeMargin), zi(y + 1)
        covered[czIn0:czIn1, cxIn0:cxIn1] = True

        flush = plan.flushTubeSides
        west, east = Face.WEST in flush, Face.EAST in flush
        north, south = Face.NORTH in flush, Face.SOUTH in flush
        if west: covered[czIn0:czIn1, cx0:cxIn0] = True
        if east: covered[czIn0:czIn1, cxIn1:cx1] = True
        if north: covered[cz0:czIn0, cxIn0:cxIn1] = True
        if south: covered[czIn1:cz1, cxIn0:cxIn1] = True
        if west and north: covered[cz0:czIn0, cx0:cxIn0] = True
        if east and north: covered[cz0:czIn0, cxIn1:cx1] = True
        if west and south: covered[czIn1:cz1, cx0:cxIn0] = True
        if east and south: covered[czIn1:cz1, cxIn1:cx1] = True

    return covered, np.array(xs), np.array(zs)


def _traceEdgeDisjointLoops(rawEdges):
    """Decompose a boundary's directed edges into closed walks, one edge
    at a time, so this always terminates even if some vertex has more
    than one outgoing edge - fattening the grid (see _capCoverageFine)
    resolves *most* pinches into real area, but sufficiently dense
    dithering can still leave one a fine-grid cell wide, so this has to
    be robust regardless. At in-degree==out-degree>1 (a vertex two loops
    still cross at), prefer continuing with the *same cell* the arriving
    edge belongs to - two edges of one cell's own boundary always belong
    together - falling back to any remaining edge only if that cell's own
    continuation was already consumed by an earlier walk through here."""
    outgoing = {}
    for kind, r, c in rawEdges:
        a, b = _rawEndpoints(kind, r, c)
        outgoing.setdefault(a, []).append((b, kind, r, c))

    loops = []
    for start in list(outgoing.keys()):
        while outgoing.get(start):
            loop = [start]
            cur = start
            fromCell = None
            while True:
                candidates = outgoing.get(cur)
                if not candidates:
                    raise RuntimeError("boundary graph is not balanced - a vertex ran out of outgoing edges")
                idx = 0
                if fromCell is not None:
                    for i, (_, _, r, c) in enumerate(candidates):
                        if (r, c) == fromCell:
                            idx = i
                            break
                nxt, kind, r, c = candidates.pop(idx)
                if not candidates:
                    del outgoing[cur]
                fromCell = (r, c)
                if nxt == start:
                    break
                loop.append(nxt)
                cur = nxt
            loops.append(loop)
    return loops


def _splitSelfTouchingLoop(loop):
    """A loop from _traceEdgeDisjointLoops can revisit the same vertex
    more than once (three or more cells meeting at a single point, not
    just the two _traceEdgeDisjointLoops' same-cell preference cleanly
    separates) - split it at each repeat into genuinely simple sub-loops
    before ear-clipping, which doesn't know what to do with a repeated
    vertex. Splitting at a shared point is exact, not approximate: the
    original loop's area is exactly the sum of the sub-loops'."""
    seen = {}
    for idx, v in enumerate(loop):
        if v in seen:
            i = seen[v]
            return _splitSelfTouchingLoop(loop[i:idx]) + _splitSelfTouchingLoop(loop[:i] + loop[idx:])
        seen[v] = idx
    return [loop]


def _buildFromFineCoverage(covered, xEdges, zEdges, yBottom, yTop):
    """Trace `covered`'s boundary loops, dog-ear each independently,
    extrude. A hole gets one cheap CSG difference against the outer
    piece(s) - never per pixel.

    (A tempting-looking shortcut here is to skip polygon tracing
    entirely: take the top/bottom faces straight from a greedy rectangle
    decomposition of `covered`, and the walls straight from its raw
    boundary edges with no loop-chaining. That's exactly the kind of
    independently-triangulated-pieces approach this module's own history
    (see git log) already tried and reverted once - a rectangle's edge
    can *partially* border more than one neighbor, and two greedily-
    merged rectangles' faces then don't share a vertex at the point where
    that neighbor's coverage changes, leaving a T-junction gap. Dog-ear
    triangulation of the traced polygon doesn't have that problem because
    it's one triangulation of one consistent vertex set, not independently
    built pieces stitched after the fact.)"""
    def toWorld(v):
        c, r = v
        return (float(xEdges[c]), float(zEdges[r]))

    outer, holes = [], []
    for rawLoop in _traceEdgeDisjointLoops(_rawEdges(covered)):
        loop = [toWorld(v) for v in rawLoop]
        for simpleLoop in _splitSelfTouchingLoop(loop):
            area = _signedArea(simpleLoop)
            merged = _mergeCollinear(simpleLoop)
            if len(merged) < 3:
                continue
            (outer if area > 0 else holes).append(merged)

    return _assembleOuterMinusHoles(outer, holes, yBottom, yTop)


def _fineGridCapSolid(planByPos, bulgeSize, yBottom, yTop):
    covered, xEdges, zEdges = _capCoverageFine(planByPos, bulgeSize)
    return _buildFromFineCoverage(covered, xEdges, zEdges, yBottom, yTop)


def _fineGridTubeSolid(planByPos, tubeMargin, yTop):
    covered, xEdges, zEdges = _tubeCoverageFine(planByPos, tubeMargin)
    return _buildFromFineCoverage(covered, xEdges, zEdges, 0.0, yTop)


def _capSolid(planByPos, bulgeSize, yBottom, yTop, usePinchFallback):
    if usePinchFallback:
        return _fineGridCapSolid(planByPos, bulgeSize, yBottom, yTop)
    return _buildBoundarySolid(planByPos, _capOffset, bulgeSize, yBottom, yTop, outward=True)


def _tubeSolid(planByPos, tubeMargin, yTop, usePinchFallback):
    if usePinchFallback:
        return _fineGridTubeSolid(planByPos, tubeMargin, yTop)
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
    or the final cap+tube union), never on a per-pixel basis.

    A pinch point - two cells sharing a corner but no edge, both flanks
    empty - is a genuine ambiguity for a single boundary trace at native
    grid resolution (which of the two crossing edges continues the loop?),
    not a rare case to guess at: this is the exact "pieces don't quite
    share an edge" failure mode that pushed this codebase to CSG
    originally. When present, the whole group falls back to a finer
    (3x-per-axis) grid where a genuine diagonal overlap shows up as real
    covered area instead of one ambiguous point - so it costs a bigger
    grid for that one group, not CSG proportional to its pixel count.
    (An earlier version of this fallback split the group into orthogonally
    -connected islands and CSG-unioned them back together - cheap when it
    worked, but boolean-unioning an arbitrary *subset* of what was meant
    to be one union turned out to not always be numerically reliable, even
    though unioning the whole original set was. The fine grid sidesteps
    that by never needing the union in the first place.)"""
    height = next(iter(plans)).height
    planByPos = {(p.y, p.x): p for p in plans}
    pinched = _hasPinchPoint(planByPos)

    capTris = _capSolid(planByPos, bulgeSize, height - 1.0, float(height), pinched)
    if height <= 1:
        return capTris

    tubeTris = _tubeSolid(planByPos, tubeMargin, height - 1.0, pinched)
    if hollow:
        cavityTris = []
        for plan in plans:
            cavity = _cavitySolid(plan, tubeMargin, wallThickness)
            if cavity:
                cavityTris += cavity
        if cavityTris and tubeTris:
            tubeTris = _fromTrimesh(trimesh.boolean.difference([_toTrimesh(tubeTris), _toTrimesh(cavityTris)]))

    if not tubeTris:
        return capTris
    merged = trimesh.boolean.union([_toTrimesh(capTris), _toTrimesh(tubeTris)])
    return _fromTrimesh(merged)
