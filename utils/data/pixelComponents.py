import numpy as np
import trimesh

from .pixelPlan import Face


# Axes: X = pixel column, Z = pixel row, Y = height (the vertical/print
# axis - Y-up). Every layer of height is exactly 1 world unit.
TUBE_MARGIN = 0.12           # how far the tube is inset from the pixel's unit-square edge
WALL_THICKNESS = 0.1         # shell thickness when a Tube is hollow
BULGE_SIZE = 0.10            # how far a cap flares out past the grid edge on a clear side

# A triangle soup, this codebase's usual convention: an (N, 3) float array
# of vertices, 3 rows per triangle, no shared indices.
_EMPTY_TRIANGLES = np.empty((0, 3), dtype=float)


def _box(x0, x1, y0, y1, z0, z1):
    """An axis-aligned box mesh spanning the given bounds."""
    box = trimesh.creation.box(extents=(x1 - x0, y1 - y0, z1 - z0))
    box.apply_translation(((x0 + x1) / 2.0, (y0 + y1) / 2.0, (z0 + z1) / 2.0))
    return box


def _toTrimesh(triangles):
    faces = np.arange(len(triangles)).reshape(-1, 3)
    return trimesh.Trimesh(vertices=triangles, faces=faces, process=True)


def _fromTrimesh(mesh):
    # One fancy-index gather instead of a nested Python loop re-fetching
    # mesh.vertices (a cached property, but still a per-access call) once
    # per (face, corner) pair - same triangle-soup result, far fewer calls
    # on a mesh with thousands of faces.
    return mesh.vertices[mesh.faces.reshape(-1)]


# ---------------------------------------------------------------------------
# Boundary construction: PixelPlanner's fused/bulged/plainWalls classification
# *is* the boundary (fused = interior). A connected group's cap or tube hull
# is built directly from it: trace the boundary at native grid resolution,
# offset each edge (cap: bulgeSize outward if bulged; tube: tubeMargin inward
# unless flush), dog-ear triangulate, extrude - one triangulation per group,
# not per pixel, so there's no seam between independently-built pieces to get
# wrong. CSG is only ever used to combine a handful of already-simplified
# pieces (a hole cut from a cap, cavities cut from a tube, the cap+tube
# union), never per-pixel.
# ---------------------------------------------------------------------------

_FACE = {'N': Face.NORTH, 'S': Face.SOUTH, 'E': Face.EAST, 'W': Face.WEST}
_DIR = {'N': (1, 0), 'S': (-1, 0), 'E': (0, 1), 'W': (0, -1)}


def _rawEdges(covered):
    """Boundary edges of `covered` (a 2D bool array) at native resolution,
    found via array-shift transitions rather than visiting every cell -
    cost is proportional to perimeter, not area."""
    rows, cols = covered.shape
    # One padded array (zero-initialized, covered copied into the middle)
    # per axis, sliced into the two shifted views a plain np.pad call
    # would otherwise build (and validate) separately, twice - np.pad's
    # generic machinery has real per-call overhead at this scale (one
    # call per group, thousands of groups).
    paddedH = np.zeros((rows + 2, cols), dtype=np.int8)
    paddedH[1:-1] = covered
    diffH = paddedH[1:] - paddedH[:-1]
    nH, nC = np.nonzero(diffH == 1)
    sH, sC = np.nonzero(diffH == -1)

    paddedV = np.zeros((rows, cols + 2), dtype=np.int8)
    paddedV[:, 1:-1] = covered
    diffV = paddedV[:, 1:] - paddedV[:, :-1]
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
    (x, z), any winding - normalized to CCW here); every loop this module
    builds is a plain orthogonal polygon.

    A clipped vertex can only change whether its own two former neighbors
    are ears, so a pointer that steps back to recheck just those two
    (instead of rescanning the whole polygon after every clip) keeps this
    roughly O(n) instead of O(n^3) on a large boundary. The per-candidate
    "is any other vertex inside this ear" check goes vectorized (numpy)
    only once there are enough other points (_VECTORIZE_THRESHOLD) to be
    worth numpy's per-call overhead - most calls are one small quad per
    pixel group, where a plain Python loop is faster.

    A valid ear always exists on a simple polygon with more than 3
    vertices in theory - but a real boundary can shrink to a near-zero-
    area remainder (vertices conceptually collinear but not exactly so
    once float64 has rounded coordinates like 0.1/0.9 through enough
    arithmetic), where no candidate clears the strict 1e-12 convexity
    cutoff. Confirmed directly: that can starve the rotating pointer
    through its whole guard budget, silently dropping the leftover
    vertices - a real hole in the cap. So a full pass finding no ear at
    all falls back to clipping whichever vertex is most convex,
    containment check waived - progress matters more than a perfect
    classification once it's down to numerical noise."""
    poly = list(loop)
    if _signedArea(loop) < 0:
        poly = poly[::-1]
    idx = list(range(len(poly)))
    tris = []
    i = 0
    guard = 0
    maxGuard = len(idx) * len(idx) + 16
    noProgress = 0
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
                if len(others) >= _VECTORIZE_THRESHOLD:
                    p = np.array([poly[j] for j in others])
                    d1 = (p[:, 0] - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (p[:, 1] - b[1])
                    d2 = (p[:, 0] - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (p[:, 1] - c[1])
                    d3 = (p[:, 0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (p[:, 1] - a[1])
                    hasNeg = (d1 < 0) | (d2 < 0) | (d3 < 0)
                    hasPos = (d1 > 0) | (d2 > 0) | (d3 > 0)
                    isEar = not bool(np.any(~(hasNeg & hasPos)))
                else:
                    for j in others:
                        px, pz = poly[j]
                        d1 = (px - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (pz - b[1])
                        d2 = (px - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (pz - c[1])
                        d3 = (px - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (pz - a[1])
                        hasNeg = d1 < 0 or d2 < 0 or d3 < 0
                        hasPos = d1 > 0 or d2 > 0 or d3 > 0
                        if not (hasNeg and hasPos):
                            isEar = False
                            break
        if isEar:
            tris.append((a, b, c))
            del idx[k]
            i = k - 1
            noProgress = 0
            continue
        noProgress += 1
        if noProgress < m:
            i = k + 1
            continue
        # Stuck: a whole pass found nothing. Clip the most-convex
        # remaining candidate regardless of containment.
        def convexity(kk):
            pa, pb, pc_ = poly[idx[kk - 1]], poly[idx[kk]], poly[idx[(kk + 1) % m]]
            return (pb[0] - pa[0]) * (pc_[1] - pa[1]) - (pb[1] - pa[1]) * (pc_[0] - pa[0])
        best = max(range(m), key=convexity)
        ia, ib, ic = idx[best - 1], idx[best], idx[(best + 1) % m]
        tris.append((poly[ia], poly[ib], poly[ic]))
        del idx[best]
        i = best - 1
        noProgress = 0
    if len(idx) == 3:
        tris.append((poly[idx[0]], poly[idx[1]], poly[idx[2]]))
    return tris


_VECTORIZE_THRESHOLD = 16


def _extrudeSolid(loop, yBottom, yTop):
    """One simple polygon (list of (x, z), any winding - see _earClip)
    extruded into a closed solid's triangles."""
    if _signedArea(loop) < 0:
        loop = list(reversed(loop))
    triangles = []
    for (a, b, c) in _earClip(loop):
        triangles += [(a[0], yTop, a[1]), (c[0], yTop, c[1]), (b[0], yTop, b[1])]
        triangles += [(a[0], yBottom, a[1]), (b[0], yBottom, b[1]), (c[0], yBottom, c[1])]
    n = len(loop)
    for i in range(n):
        xa, za = loop[i]
        xb, zb = loop[(i + 1) % n]
        triangles += [(xa, yBottom, za), (xb, yTop, zb), (xb, yBottom, zb)]
        triangles += [(xa, yBottom, za), (xa, yTop, za), (xb, yTop, zb)]
    return np.array(triangles, dtype=float) if triangles else _EMPTY_TRIANGLES


def _assembleOuterMinusHoles(outer, holes, yBottom, yTop):
    """Extrude `outer` and `holes` (already-classified simple polygons)
    and combine them into one trimesh.Trimesh (None if `outer` is empty).
    Multiple outer loops (or holes) can touch or overlap, so they're
    unioned/differenced via CSG rather than concatenated - concatenating
    independently-valid volumes doesn't generally produce a valid one.

    Returns a Trimesh, not a triangle-soup list, so componentTriangles can
    feed it straight into the cap+tube union without a round trip through
    soup: re-converting an already-valid Trimesh to soup and back has been
    observed to silently break its watertightness (see the regression
    test this fix came with)."""
    if not outer:
        return None
    outerPieces = [_toTrimesh(_extrudeSolid(loop, yBottom, yTop)) for loop in outer]
    outerMesh = trimesh.boolean.union(outerPieces) if len(outerPieces) > 1 else outerPieces[0]
    if not holes:
        return outerMesh
    holePieces = [_toTrimesh(_extrudeSolid(loop, yBottom, yTop)) for loop in holes]
    # meshes[0] - meshes[1:] in one call, rather than unioning the holes
    # first and then differencing.
    return trimesh.boolean.difference([outerMesh, *holePieces])


def _hasPinchPoint(planByPos):
    """True if two parts of this group touch at a single grid corner with
    no shared edge (e.g. diagonal pixels whose bulges overlap but nothing
    fuses them) - a real topological ambiguity for boundary tracing
    (which of the two crossing edges continues the loop?), not a rare
    case to guess at. Checks the classic marching-squares saddle pattern
    (two diagonally-opposite cells covered, the other two empty) directly
    via shifted-array comparisons rather than tracing every edge to count
    vertex degree - cheap, since this runs once per group including every
    group that isn't pinched at all."""
    ys = [p.y for p in planByPos.values()]
    xs = [p.x for p in planByPos.values()]
    minY, minX = min(ys), min(xs)
    rows, cols = max(ys) - minY + 1, max(xs) - minX + 1
    covered = np.zeros((rows, cols), dtype=bool)
    for (y, x) in planByPos:
        covered[y - minY, x - minX] = True
    padded = np.pad(covered, 1, constant_values=False)
    nw, ne = padded[:-1, :-1], padded[:-1, 1:]
    sw, se = padded[1:, :-1], padded[1:, 1:]
    saddle = (nw & se & ~ne & ~sw) | (ne & sw & ~nw & ~se)
    return bool(np.any(saddle))


def _buildBoundarySolid(planByPos, offsetFn, margin, yBottom, yTop, outward):
    """The shared engine behind both _capSolid and _tubeSolid: trace the
    boundary at native grid resolution from `planByPos`, offset each raw
    edge via `offsetFn`, join consecutive edges, ear-clip, extrude. Callers
    must have already ruled out a pinch point (see _hasPinchPoint)."""
    if len(planByPos) == 1:
        # An isolated single pixel has exactly 4 convex corners - skip
        # straight to that rectangle instead of the general trace below.
        # Over half of a real dithered image's groups are lone pixels
        # (see Mesh._calculateMesh's "Isolated single-pixel part"
        # warnings), so this is a real win, not a micro-optimization.
        (y, x), = planByPos.keys()
        x0 = offsetFn('W', 0, 0, planByPos, y, x, margin)
        x1 = offsetFn('E', 0, 0, planByPos, y, x, margin)
        z0 = offsetFn('N', 0, 0, planByPos, y, x, margin)
        z1 = offsetFn('S', 0, 0, planByPos, y, x, margin)
        loop = [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]
        return _toTrimesh(_extrudeSolid(loop, yBottom, yTop))

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
            # rawLoop is in local grid-relative coordinates (see
            # _rawEndpoints); offsetFn converts to world coordinates
            # internally, so a raw coordinate used alongside an offset
            # value needs the same conversion, or a group whose bounding
            # box doesn't start at the grid origin gets garbled vertices.
            localX, localZ = rawLoop[i]
            rawX, rawZ = localX + minX, localZ + minY
            offPrev = offsetFn(prevKind, pr, pc, planByPos, minY, minX, margin)
            offCur = offsetFn(curKind, cr, cc, planByPos, minY, minX, margin)
            axPrev, axCur = _axis(prevKind), _axis(curKind)
            if axPrev != axCur:
                prevDir, curDir = _DIR[prevKind], _DIR[curKind]
                cross = prevDir[0] * curDir[1] - prevDir[1] * curDir[0]
                if outward or cross > 0:
                    # Convex corner, or a reflex corner with outward
                    # (cap) offsets: the offset lines cross past the raw
                    # corner, so their intersection is the boundary point.
                    x = offCur if axCur == 'V' else offPrev
                    z = offPrev if axPrev == 'H' else offCur
                    outVerts.append((x, z))
                else:
                    # Reflex corner with inward (tube) offsets: the edges
                    # pull away from the corner and never meet, so route
                    # through the original raw grid corner instead.
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
    """A pinch point is ambiguous only because a single grid vertex can't
    represent both "covered" and "not" at once. Fatten the grid via
    coordinate compression: subdivide each cell's cap footprint into a
    core plus one outward margin strip per bulged side, so neighboring
    pixels' margins never collide. A genuine diagonal overlap then shows
    up as real covered area a boundary trace can walk through cleanly,
    instead of one ambiguous point.

    The fallback group (whichever one has a pinch) can be huge - the base
    plate is one group covering nearly the whole canvas - so coordinate
    lookups are batched np.searchsorted calls over every pixel at once
    rather than one bisect call per pixel per edge; the coverage-array
    writes stay a per-pixel loop since each pixel's footprint is a
    differently-sized rectangle, not something one vectorized scatter can
    express."""
    xs = sorted({v for p in planByPos.values() for v in (p.x - bulgeSize, p.x, p.x + 1, p.x + 1 + bulgeSize)})
    zs = sorted({v for p in planByPos.values() for v in (p.y - bulgeSize, p.y, p.y + 1, p.y + 1 + bulgeSize)})
    xArr, zArr = np.array(xs), np.array(zs)
    covered = np.zeros((len(zs) - 1, len(xs) - 1), dtype=bool)

    positions = list(planByPos.keys())
    ysArr = np.array([p[0] for p in positions], dtype=float)
    xsArr = np.array([p[1] for p in positions], dtype=float)
    cx0 = np.searchsorted(xArr, xsArr).tolist()
    cx1 = np.searchsorted(xArr, xsArr + 1).tolist()
    cz0 = np.searchsorted(zArr, ysArr).tolist()
    cz1 = np.searchsorted(zArr, ysArr + 1).tolist()
    wx0 = np.searchsorted(xArr, xsArr - bulgeSize).tolist()
    ex1 = np.searchsorted(xArr, xsArr + 1 + bulgeSize).tolist()
    nz0 = np.searchsorted(zArr, ysArr - bulgeSize).tolist()
    sz1 = np.searchsorted(zArr, ysArr + 1 + bulgeSize).tolist()

    for i, (y, x) in enumerate(positions):
        plan = planByPos[(y, x)]
        cx0i, cx1i, cz0i, cz1i = cx0[i], cx1[i], cz0[i], cz1[i]
        covered[cz0i:cz1i, cx0i:cx1i] = True

        west, east = Face.WEST in plan.bulged, Face.EAST in plan.bulged
        north, south = Face.NORTH in plan.bulged, Face.SOUTH in plan.bulged
        wx0i, wx1i = wx0[i], cx0i
        ex0i, ex1i = cx1i, ex1[i]
        nz0i, nz1i = nz0[i], cz0i
        sz0i, sz1i = cz1i, sz1[i]
        if west: covered[cz0i:cz1i, wx0i:wx1i] = True
        if east: covered[cz0i:cz1i, ex0i:ex1i] = True
        if north: covered[nz0i:nz1i, cx0i:cx1i] = True
        if south: covered[sz0i:sz1i, cx0i:cx1i] = True

        wp, ep = planByPos.get((y, x - 1)), planByPos.get((y, x + 1))
        np_, sp = planByPos.get((y - 1, x)), planByPos.get((y + 1, x))
        nw = (west and north) or (wp and Face.NORTH in wp.bulged) or (np_ and Face.WEST in np_.bulged)
        ne = (east and north) or (ep and Face.NORTH in ep.bulged) or (np_ and Face.EAST in np_.bulged)
        sw = (west and south) or (wp and Face.SOUTH in wp.bulged) or (sp and Face.WEST in sp.bulged)
        se = (east and south) or (ep and Face.SOUTH in ep.bulged) or (sp and Face.EAST in sp.bulged)
        if nw: covered[nz0i:nz1i, wx0i:wx1i] = True
        if ne: covered[nz0i:nz1i, ex0i:ex1i] = True
        if sw: covered[sz0i:sz1i, wx0i:wx1i] = True
        if se: covered[sz0i:sz1i, ex0i:ex1i] = True

    return covered, xArr, zArr


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
    than one outgoing edge (fattening the grid resolves *most* pinches,
    but dense dithering can still leave one). At a vertex two loops cross
    at, prefer continuing with the *same cell* the arriving edge belongs
    to - two edges of one cell's own boundary always belong together -
    falling back to any remaining edge only if that's already taken."""
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
    """A loop from _traceEdgeDisjointLoops can still revisit a vertex
    (three or more cells meeting at one point) - split it at each repeat
    into simple sub-loops before ear-clipping. Exact, not approximate:
    the sub-loops' areas sum to the original."""
    seen = {}
    for idx, v in enumerate(loop):
        if v in seen:
            i = seen[v]
            return _splitSelfTouchingLoop(loop[i:idx]) + _splitSelfTouchingLoop(loop[:i] + loop[idx:])
        seen[v] = idx
    return [loop]


_TOUCH_EPSILON = 1e-4


def _nudgeTouchingVertex(loop, x, z):
    """Replace `loop`'s (x, z) vertex with a tiny two-segment chamfer,
    cutting the corner instead of moving one point diagonally. Every loop
    this module builds is strictly orthogonal - moving the vertex
    diagonally (an earlier version of this) broke that assumption and
    could make _earClip's ear search genuinely get stuck on a large
    enough polygon (see its own docstring). A chamfer keeps every edge
    axis-aligned: pull back epsilon along the incoming edge's own line,
    step epsilon along the outgoing edge's own line, join with one tiny
    perpendicular segment."""
    n = len(loop)
    i = loop.index((x, z))
    px, pz = loop[i - 1]
    nx, nz = loop[(i + 1) % n]
    d1x, d1z = x - px, z - pz
    d2x, d2z = nx - x, nz - z
    len1 = (d1x * d1x + d1z * d1z) ** 0.5
    len2 = (d2x * d2x + d2z * d2z) ** 0.5
    if len1 == 0 or len2 == 0:
        return loop
    d1x, d1z = d1x / len1 * _TOUCH_EPSILON, d1z / len1 * _TOUCH_EPSILON
    d2x, d2z = d2x / len2 * _TOUCH_EPSILON, d2z / len2 * _TOUCH_EPSILON
    p1 = (x - d1x, z - d1z)
    p3 = (x + d2x, z + d2z)
    p2 = (p1[0] + d2x, p1[1] + d2z)
    return loop[:i] + [p1, p2, p3] + loop[i + 1:]


def _separateTouchingLoops(loops):
    """Two loops - outer/outer, outer/hole, or hole/hole - sharing an
    exact vertex can't go through CSG: the surface would pinch to a
    single edge there, not a valid 2-manifold (manifold3d doesn't error
    on it, it silently hands back a broken mesh). Only possible when
    there's no bulge margin at that corner to fatten the touch into real
    area. Nudging one side of each pair a hair inward (see
    _nudgeTouchingVertex) breaks the coincidence - by less than any
    printer could resolve."""
    seen = {}
    result = list(loops)
    for li, loop in enumerate(result):
        for v in loop:
            if v in seen and seen[v] != li:
                x, z = v
                result[li] = _nudgeTouchingVertex(result[li], x, z)
            else:
                seen[v] = li
    return result


def _buildFromFineCoverage(covered, xEdges, zEdges, yBottom, yTop):
    """Trace `covered`'s boundary loops, dog-ear each independently,
    extrude. A hole gets one cheap CSG difference against the outer
    piece(s) - never per pixel.

    (A greedy rectangle decomposition of `covered` looks like a tempting
    shortcut here, but a rectangle's edge can partially border more than
    one neighbor - two greedily-merged rectangles' faces then don't share
    a vertex where that neighbor's coverage changes, leaving a T-junction
    gap. Dog-ear triangulation of the traced polygon avoids that: it's
    one triangulation of one consistent vertex set.)"""
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

    if len(outer) + len(holes) > 1:
        separated = _separateTouchingLoops(outer + holes)
        outer, holes = separated[:len(outer)], separated[len(outer):]

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
    return _toTrimesh(_extrudeSolid(loop, -0.01, plan.height - 1.0))


def componentTriangles(plans, hollow, tubeMargin=TUBE_MARGIN, wallThickness=WALL_THICKNESS, bulgeSize=BULGE_SIZE):
    """The merged solid for one physically-connected group of same-color,
    same-height PixelPlans (see Mesh._calculateMesh), as an (N, 3) float
    array - 3 rows per triangle, no shared indices (this codebase's usual
    triangle-soup convention).

    Built directly from each pixel's fused/bulged/flush classification
    rather than boolean-unioning one box per pixel: the cap is one hull
    extrusion, the tube (if any pixel is taller than one layer) another,
    cavities simple per-pixel boxes - CSG only ever combines those
    already-simplified pieces (a hole cut from a hull, cavities cut from
    a tube, the final cap+tube union), never per-pixel.

    A pinch point (two cells sharing a corner but no edge, both flanks
    empty) is a genuine ambiguity for a boundary trace at native grid
    resolution - which of the two crossing edges continues the loop? When
    present, the whole group falls back to a finer (3x-per-axis) grid
    where a genuine diagonal overlap shows up as real covered area
    instead of one ambiguous point."""
    height = next(iter(plans)).height
    planByPos = {(p.y, p.x): p for p in plans}
    pinched = _hasPinchPoint(planByPos)

    # Everything below stays a Trimesh (not a re-converted triangle-soup)
    # until the final return - see _assembleOuterMinusHoles for why.
    capMesh = _capSolid(planByPos, bulgeSize, height - 1.0, float(height), pinched)
    if height <= 1:
        return _fromTrimesh(capMesh) if capMesh is not None else _EMPTY_TRIANGLES

    tubeMesh = _tubeSolid(planByPos, tubeMargin, height - 1.0, pinched)
    if hollow and tubeMesh is not None:
        cavityMeshes = [m for m in (_cavitySolid(plan, tubeMargin, wallThickness) for plan in plans) if m is not None]
        if cavityMeshes:
            tubeMesh = trimesh.boolean.difference([tubeMesh, *cavityMeshes])

    if tubeMesh is None:
        return _fromTrimesh(capMesh) if capMesh is not None else _EMPTY_TRIANGLES
    if capMesh is None:
        return _fromTrimesh(tubeMesh)
    merged = trimesh.boolean.union([capMesh, tubeMesh])
    return _fromTrimesh(merged)


# ---------------------------------------------------------------------------
# Fast path for interactive preview only (Mesh.fastPreview) - never used for
# export. Trades away the guarantee componentTriangles above gives (every
# edge shared by exactly two triangles, i.e. a real printable solid) for
# speed: flat faces are tiled directly (no ear-clip) and walls are one quad
# per merged boundary run (no CSG anywhere). Merging same-covered cells into
# bigger tiles can leave two adjacent tiles sharing only part of an edge (a
# T-junction) - invisible to a renderer, since both sides still meet at the
# same coordinates, but not a valid manifold, which is exactly why this
# never feeds export or a slicer.
#
# _fastCapCoverage/_fastTubeCoverage are leaner cousins of
# _capCoverageFine/_tubeCoverageFine (profiling found those the single
# biggest cost here): those unconditionally add a bulge/margin cut line for
# *every* pixel, and the cap version does neighbor lookups for corner
# filling, since they exist for production's rare pinch-point fallback,
# where correctness matters more than speed. Bulge/inset only ever affects
# a small fraction of pixels in typical content, so only adding a cut line
# where a pixel's own side actually needs one keeps the coverage grid close
# to native resolution instead of uniformly finer everywhere. The trade:
# a pixel whose *neighbor's* bulge would otherwise fill in its corner (not
# its own bulge) doesn't get that fill here - a further, already-accepted-
# in-kind small gap, on top of the T-junctions this path already allows.
# ---------------------------------------------------------------------------

def _nativeCoverage(planByPos):
    """Plain native-resolution coverage grid, no coordinate compression -
    for the common case (most groups, since bulge/inset only ever affects
    pixels touching a real boundary) where nothing needs finer-than-a-
    pixel resolution at all."""
    ys = [p.y for p in planByPos.values()]
    xs = [p.x for p in planByPos.values()]
    minY, minX = min(ys), min(xs)
    rows, cols = max(ys) - minY + 1, max(xs) - minX + 1
    covered = np.zeros((rows, cols), dtype=bool)
    for (y, x) in planByPos:
        covered[y - minY, x - minX] = True
    xArr = np.arange(minX, minX + cols + 1, dtype=float)
    zArr = np.arange(minY, minY + rows + 1, dtype=float)
    return covered, xArr, zArr


def _fastCapCoverage(planByPos, bulgeSize):
    if not any(p.bulged for p in planByPos.values()):
        return _nativeCoverage(planByPos)

    xsSet, zsSet = set(), set()
    for (y, x) in planByPos:
        xsSet.add(x); xsSet.add(x + 1)
        zsSet.add(y); zsSet.add(y + 1)
    for (y, x), plan in planByPos.items():
        bulged = plan.bulged
        if Face.WEST in bulged: xsSet.add(x - bulgeSize)
        if Face.EAST in bulged: xsSet.add(x + 1 + bulgeSize)
        if Face.NORTH in bulged: zsSet.add(y - bulgeSize)
        if Face.SOUTH in bulged: zsSet.add(y + 1 + bulgeSize)

    xArr, zArr = np.array(sorted(xsSet)), np.array(sorted(zsSet))
    covered = np.zeros((len(zArr) - 1, len(xArr) - 1), dtype=bool)

    positions = list(planByPos.keys())
    ysArr = np.array([p[0] for p in positions], dtype=float)
    xsArr = np.array([p[1] for p in positions], dtype=float)
    cx0 = np.searchsorted(xArr, xsArr).tolist()
    cx1 = np.searchsorted(xArr, xsArr + 1).tolist()
    cz0 = np.searchsorted(zArr, ysArr).tolist()
    cz1 = np.searchsorted(zArr, ysArr + 1).tolist()

    for i, (y, x) in enumerate(positions):
        covered[cz0[i]:cz1[i], cx0[i]:cx1[i]] = True

    for i, (y, x) in enumerate(positions):
        plan = planByPos[(y, x)]
        if not plan.bulged:
            continue
        cx0i, cx1i, cz0i, cz1i = cx0[i], cx1[i], cz0[i], cz1[i]
        bulged = plan.bulged
        west, east = Face.WEST in bulged, Face.EAST in bulged
        north, south = Face.NORTH in bulged, Face.SOUTH in bulged
        wx0i = int(np.searchsorted(xArr, x - bulgeSize)) if west else None
        ex1i = int(np.searchsorted(xArr, x + 1 + bulgeSize)) if east else None
        nz0i = int(np.searchsorted(zArr, y - bulgeSize)) if north else None
        sz1i = int(np.searchsorted(zArr, y + 1 + bulgeSize)) if south else None
        if west: covered[cz0i:cz1i, wx0i:cx0i] = True
        if east: covered[cz0i:cz1i, cx1i:ex1i] = True
        if north: covered[nz0i:cz0i, cx0i:cx1i] = True
        if south: covered[cz1i:sz1i, cx0i:cx1i] = True
        # This pixel's own two-adjacent-bulged-sides corner - the common
        # case that needs one - filled directly since west/east/north/
        # south are already known here; a corner triggered only by a
        # neighbor's bulge is the accepted gap described above.
        if west and north: covered[nz0i:cz0i, wx0i:cx0i] = True
        if east and north: covered[nz0i:cz0i, cx1i:ex1i] = True
        if west and south: covered[cz1i:sz1i, wx0i:cx0i] = True
        if east and south: covered[cz1i:sz1i, cx1i:ex1i] = True

    return covered, xArr, zArr


def _fastTubeCoverage(planByPos, tubeMargin):
    if all(len(p.flushTubeSides) == 4 for p in planByPos.values()):
        return _nativeCoverage(planByPos)

    xsSet, zsSet = set(), set()
    for (y, x) in planByPos:
        xsSet.add(x); xsSet.add(x + 1)
        zsSet.add(y); zsSet.add(y + 1)
    for (y, x), plan in planByPos.items():
        flush = plan.flushTubeSides
        if Face.WEST not in flush: xsSet.add(x + tubeMargin)
        if Face.EAST not in flush: xsSet.add(x + 1 - tubeMargin)
        if Face.NORTH not in flush: zsSet.add(y + tubeMargin)
        if Face.SOUTH not in flush: zsSet.add(y + 1 - tubeMargin)

    xArr, zArr = np.array(sorted(xsSet)), np.array(sorted(zsSet))
    covered = np.zeros((len(zArr) - 1, len(xArr) - 1), dtype=bool)

    positions = list(planByPos.keys())
    ysArr = np.array([p[0] for p in positions], dtype=float)
    xsArr = np.array([p[1] for p in positions], dtype=float)
    cx0 = np.searchsorted(xArr, xsArr).tolist()
    cx1 = np.searchsorted(xArr, xsArr + 1).tolist()
    cz0 = np.searchsorted(zArr, ysArr).tolist()
    cz1 = np.searchsorted(zArr, ysArr + 1).tolist()

    for i, (y, x) in enumerate(positions):
        plan = planByPos[(y, x)]
        flush = plan.flushTubeSides
        cx0i, cx1i, cz0i, cz1i = cx0[i], cx1[i], cz0[i], cz1[i]
        west, east = Face.WEST in flush, Face.EAST in flush
        north, south = Face.NORTH in flush, Face.SOUTH in flush

        cxIn0i = cx0i if west else int(np.searchsorted(xArr, x + tubeMargin))
        cxIn1i = cx1i if east else int(np.searchsorted(xArr, x + 1 - tubeMargin))
        czIn0i = cz0i if north else int(np.searchsorted(zArr, y + tubeMargin))
        czIn1i = cz1i if south else int(np.searchsorted(zArr, y + 1 - tubeMargin))

        covered[czIn0i:czIn1i, cxIn0i:cxIn1i] = True
        if west: covered[czIn0i:czIn1i, cx0i:cxIn0i] = True
        if east: covered[czIn0i:czIn1i, cxIn1i:cx1i] = True
        if north: covered[cz0i:czIn0i, cxIn0i:cxIn1i] = True
        if south: covered[czIn1i:cz1i, cxIn0i:cxIn1i] = True
        if west and north: covered[cz0i:czIn0i, cx0i:cxIn0i] = True
        if east and north: covered[cz0i:czIn0i, cxIn1i:cx1i] = True
        if west and south: covered[czIn1i:cz1i, cx0i:cxIn0i] = True
        if east and south: covered[czIn1i:cz1i, cxIn1i:cx1i] = True

    return covered, xArr, zArr


def _singlePassTiles(mask):
    """One-pass, non-minimal tiling: expand each True run right, then as
    far down as it stays the same width. Cheap (no repeated re-scanning)
    and, unlike a true largest-rectangle search, doesn't need one - a
    renderer doesn't care how few tiles there are, only that they exist."""
    rows, cols = mask.shape
    remaining = mask.copy()
    rects = []
    for r in range(rows):
        c = 0
        while c < cols:
            if not remaining[r, c]:
                c += 1
                continue
            c1 = c + 1
            while c1 < cols and remaining[r, c1]:
                c1 += 1
            r1 = r + 1
            while r1 < rows and remaining[r1, c:c1].all():
                r1 += 1
            rects.append((r, c, r1, c1))
            remaining[r:r1, c:c1] = False
            c = c1
    return rects


def _mergedBoundaryRuns(covered):
    """Consecutive raw boundary edges along one straight run, merged into
    one span each. _rawEdges reports edges at native grid-cell
    granularity by design (the boundary-trace path merges them via
    _mergeCollinear before extruding) - a long straight run split into
    hundreds of unmerged wall quads is real, wasted triangle count for a
    renderer, not just a cosmetic difference.

    Each direction's raw edges chain in a specific order (see
    _rawEndpoints): N and E chain with increasing c/r, S and W with
    decreasing - getting that backwards would silently reverse those
    walls' winding."""
    byRow, byCol = {}, {}
    for kind, r, c in _rawEdges(covered):
        (byRow if kind in ('N', 'S') else byCol).setdefault((kind, r if kind in ('N', 'S') else c), []).append(
            c if kind in ('N', 'S') else r
        )

    def ranges(values):
        values = sorted(values)
        start = prev = values[0]
        for v in values[1:]:
            if v == prev + 1:
                prev = v
                continue
            yield start, prev + 1
            start = prev = v
        yield start, prev + 1

    spans = []
    for (kind, r), cs in byRow.items():
        for c0, c1 in ranges(cs):
            spans.append(((c0, r), (c1, r)) if kind == 'N' else ((c1, r + 1), (c0, r + 1)))
    for (kind, c), rs in byCol.items():
        for r0, r1 in ranges(rs):
            spans.append(((c + 1, r0), (c + 1, r1)) if kind == 'E' else ((c, r1), (c, r0)))
    return spans


def _fastSolidFromCoverage(covered, xEdges, zEdges, yBottom, yTop):
    """Top + bottom (tiled, not ear-clipped) + walls (one quad per merged
    boundary run) for one coverage grid."""
    # .tolist() once: repeatedly indexing the numpy arrays boxes/unboxes a
    # numpy scalar (then float()) on every single vertex access, plain
    # Python list indexing doesn't.
    xEdges, zEdges = xEdges.tolist(), zEdges.tolist()
    triangles = []

    for (r0, c0, r1, c1) in _singlePassTiles(covered):
        x0, x1 = xEdges[c0], xEdges[c1]
        z0, z1 = zEdges[r0], zEdges[r1]
        triangles.extend((
            (x0, yTop, z0), (x1, yTop, z1), (x1, yTop, z0),
            (x0, yTop, z0), (x0, yTop, z1), (x1, yTop, z1),
            (x0, yBottom, z0), (x1, yBottom, z0), (x1, yBottom, z1),
            (x0, yBottom, z0), (x1, yBottom, z1), (x0, yBottom, z1),
        ))

    for (ax, az), (bx, bz) in _mergedBoundaryRuns(covered):
        xa, za = xEdges[ax], zEdges[az]
        xb, zb = xEdges[bx], zEdges[bz]
        triangles.extend((
            (xa, yBottom, za), (xb, yTop, zb), (xb, yBottom, zb),
            (xa, yBottom, za), (xa, yTop, za), (xb, yTop, zb),
        ))

    return np.array(triangles, dtype=float) if triangles else _EMPTY_TRIANGLES


def componentTrianglesFast(plans, tubeMargin=TUBE_MARGIN, bulgeSize=BULGE_SIZE):
    """Preview-only alternative to componentTriangles - see the section
    banner above for what it trades away. Solid only (no hollow/cavity
    support): Mesh._calculateMesh doesn't offer that combination."""
    height = next(iter(plans)).height
    planByPos = {(p.y, p.x): p for p in plans}

    covered, xEdges, zEdges = _fastCapCoverage(planByPos, bulgeSize)
    capTris = _fastSolidFromCoverage(covered, xEdges, zEdges, height - 1.0, float(height))
    if height <= 1:
        return capTris

    tCovered, txEdges, tzEdges = _fastTubeCoverage(planByPos, tubeMargin)
    tubeTris = _fastSolidFromCoverage(tCovered, txEdges, tzEdges, 0.0, height - 1.0)
    return np.concatenate([capTris, tubeTris])
