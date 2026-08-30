from collections import Counter, defaultdict

_EPS = 1e-6
_AXES = ('x', 'y', 'z')


def _roundedKey(v):
    return (round(v.x, 6), round(v.y, 6), round(v.z, 6))


def _flatPlane(tri):
    """Which single coordinate is constant across all 3 corners of `tri`
    (its own axis-aligned plane), or None if it's a tilted face - all of
    this codebase's geometry is axis-aligned, but a tilted face would be
    left alone rather than mishandled."""
    for axis in _AXES:
        values = {round(getattr(v, axis), 6) for v in tri}
        if len(values) == 1:
            return axis, getattr(tri[0], axis)
    return None


def _edgePlanes(A, B):
    """Every axis along which edge A-B is itself axis-aligned (both
    endpoints share that coordinate) - independent of whether the
    triangle this edge belongs to is flat overall. A vertical quad (like
    bulgeSeamPatch's) still has a perfectly flat top and bottom edge; a
    candidate vertex living on one of those needs to be found by a flat
    neighbor even though the vertical quad itself never passes
    _flatPlane."""
    planes = []
    for axis in _AXES:
        va, vb = round(getattr(A, axis), 6), round(getattr(B, axis), 6)
        if va == vb:
            planes.append((axis, va))
    return planes


def _project(v, axis):
    return tuple(getattr(v, a) for a in _AXES if a != axis)


def _pointOnSegment(pa, pb, pv):
    """t in (0, 1) if pv lies strictly between pa and pb on the same
    line, else None."""
    dx, dy = pb[0] - pa[0], pb[1] - pa[1]
    length2 = dx * dx + dy * dy
    if length2 < _EPS:
        return None
    cross = dx * (pv[1] - pa[1]) - dy * (pv[0] - pa[0])
    if abs(cross) > _EPS * max(1.0, length2 ** 0.5):
        return None
    t = ((pv[0] - pa[0]) * dx + (pv[1] - pa[1]) * dy) / length2
    return t if _EPS < t < 1 - _EPS else None


def repairTJunctions(triangles, maxPasses=4):
    """Split any triangle edge that another triangle's *dangling* vertex
    sits in the middle of, so two independently-built pieces of flat
    geometry that fully cover the same area but were triangulated
    differently end up sharing a real edge instead of leaving what a
    strict manifold check flags as open (see Pixel/Cap: two fused
    neighbors with different bulge extents along their shared seam are
    the main source of this - the area is always fully covered, just not
    edge-for-edge, since neither side is aware of the other's own
    triangulation).

    Candidate T-vertices are restricted to endpoints of *other edges that
    are themselves currently open* (shared by exactly one triangle) -
    never vertices from already-closed geometry. Grid-aligned geometry
    like this repeats the same handful of offsets (a bulge amount, a
    tube margin) constantly, so an unrestricted "any vertex in the same
    plane" search matches far-away, unrelated, already-correct edges
    purely by coordinate coincidence and duplicates them - this scoping
    is what keeps the repair local to genuine gaps.

    Only considers faces that lie flat in one of the 3 axis-aligned
    planes (the vast majority of the geometry here); a tilted face is
    left untouched. Runs to a fixed point or `maxPasses`, whichever comes
    first - a split can itself introduce a new short edge that needs
    matching against a third, even shorter piece."""
    triList = [triangles[i:i + 3] for i in range(0, len(triangles), 3)]

    for _ in range(maxPasses):
        edgeCount = Counter()
        for tri in triList:
            for a, b in ((0, 1), (1, 2), (2, 0)):
                edgeCount[frozenset((_roundedKey(tri[a]), _roundedKey(tri[b])))] += 1
        openEdges = {key for key, count in edgeCount.items() if count == 1}
        if not openEdges:
            break

        # Candidates come from the *edges* themselves, not from whichever
        # triangle happens to own them - a vertical quad (bulgeSeamPatch's,
        # say) is never flat overall, but its top and bottom edges are
        # each flat on their own, and a flat neighbor (a Collar or Cap
        # wall quad) needs to see those endpoints as candidates too.
        openVertKeysByPlane = defaultdict(set)
        openVertObjs = {}
        for tri in triList:
            for a, b in ((0, 1), (1, 2), (2, 0)):
                A, B = tri[a], tri[b]
                if frozenset((_roundedKey(A), _roundedKey(B))) not in openEdges:
                    continue
                for axis, value in _edgePlanes(A, B):
                    planeKey = (axis, round(value, 6))
                    for v in (A, B):
                        key = _roundedKey(v)
                        openVertKeysByPlane[planeKey].add(key)
                        openVertObjs[key] = v

        replacements = {}
        for idx, tri in enumerate(triList):
            plane = _flatPlane(tri)
            if plane is None:
                continue
            planeKey = (plane[0], round(plane[1], 6))
            axis = plane[0]
            candidateKeys = openVertKeysByPlane.get(planeKey, ())
            for a, b, c in ((0, 1, 2), (1, 2, 0), (2, 0, 1)):
                A, B, C = tri[a], tri[b], tri[c]
                if frozenset((_roundedKey(A), _roundedKey(B))) not in openEdges:
                    continue
                pa, pb = _project(A, axis), _project(B, axis)
                onEdge = []
                for key in candidateKeys:
                    if key == _roundedKey(A) or key == _roundedKey(B):
                        continue
                    t = _pointOnSegment(pa, pb, _project(openVertObjs[key], axis))
                    if t is not None:
                        onEdge.append((t, openVertObjs[key]))
                if onEdge:
                    onEdge.sort(key=lambda tv: tv[0])
                    chain = [A] + [v for _, v in onEdge] + [B]
                    replacements[idx] = [[chain[i], chain[i + 1], C] for i in range(len(chain) - 1)]
                    break

        if not replacements:
            break

        newTriList = []
        for idx, tri in enumerate(triList):
            newTriList.extend(replacements.get(idx, [tri]))
        triList = newTriList

    flat = []
    for tri in triList:
        flat.extend(tri)
    return flat
