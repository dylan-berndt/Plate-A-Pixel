from collections import Counter

from utils.data.vector import Vector3
from utils.data.meshRepair import repairTJunctions


def _quad(a, b, c, d):
    return [a, b, c, a, c, d]


def _edgeCounts(triangles):
    edges = Counter()
    for i in range(0, len(triangles), 3):
        tri = triangles[i:i + 3]
        for a, b in ((0, 1), (1, 2), (2, 0)):
            p = (round(tri[a].x, 6), round(tri[a].y, 6), round(tri[a].z, 6))
            q = (round(tri[b].x, 6), round(tri[b].y, 6), round(tri[b].z, 6))
            edges[frozenset((p, q))] += 1
    return edges


def test_repair_closes_a_mismatched_seam_between_two_adjacent_rectangles():
    # Rectangle A (x:[0,1], z:[0,1]) sits flush against rectangle B
    # (x:[1,2], z:[0,1.5]) - same seam at x=1, but B reaches further in z,
    # so A's east edge and B's west edge don't match vertex-for-vertex,
    # even though the combined area is fully covered.
    A = _quad(Vector3(0, 0, 0), Vector3(1, 0, 0), Vector3(1, 0, 1), Vector3(0, 0, 1))
    B = _quad(Vector3(1, 0, 0), Vector3(2, 0, 0), Vector3(2, 0, 1.5), Vector3(1, 0, 1.5))
    triangles = A + B

    seam = frozenset({(1.0, 0.0, 0.0), (1.0, 0.0, 1.0)})
    assert _edgeCounts(triangles)[seam] == 1  # open before repair

    repaired = repairTJunctions(triangles)

    assert _edgeCounts(repaired)[seam] == 2  # closed after repair


def test_repair_leaves_a_genuinely_matching_mesh_unchanged():
    # Two rectangles that already share a full, matching edge - nothing
    # to repair, and the triangle count shouldn't grow.
    A = _quad(Vector3(0, 0, 0), Vector3(1, 0, 0), Vector3(1, 0, 1), Vector3(0, 0, 1))
    B = _quad(Vector3(1, 0, 0), Vector3(2, 0, 0), Vector3(2, 0, 1), Vector3(1, 0, 1))
    triangles = A + B

    repaired = repairTJunctions(triangles)

    assert len(repaired) == len(triangles)


def test_repair_does_not_touch_a_tilted_face():
    # A single triangle with no constant axis at all (not flat in x, y,
    # or z) - left completely alone, even with a vertex from elsewhere
    # sitting exactly on one of its edges.
    tilted = [Vector3(0, 0, 0), Vector3(1, 1, 0), Vector3(0, 1, 1)]
    strayVertex = Vector3(0.5, 0.5, 0.0)  # lies on the tilted edge (0,0,0)-(1,1,0)
    unrelatedFlatTriangle = _quad(
        Vector3(0, 5, 0), Vector3(1, 5, 0), Vector3(1, 5, 1), Vector3(0, 5, 1),
    )

    repaired = repairTJunctions(tilted + [strayVertex, Vector3(9, 9, 9), Vector3(9, 9, 8)] + unrelatedFlatTriangle)

    # the tilted triangle itself is untouched (still exactly 3 verts for it)
    tiltedOut = repaired[:3]
    assert [(round(v.x, 6), round(v.y, 6), round(v.z, 6)) for v in tiltedOut] == [
        (0.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 1.0),
    ]


def test_repair_does_not_create_bogus_matches_from_coincidental_coordinates():
    # Two adjacent rectangles, far away, that already match perfectly
    # (a genuinely closed seam) - sharing a coordinate value (z=1) with
    # an unrelated *open* edge elsewhere in the same plane must not pull
    # that closed seam into a false "repair": candidates are restricted
    # to endpoints of other open edges only, never already-matched ones.
    closedLeft = _quad(Vector3(10, 0, 0), Vector3(11, 0, 0), Vector3(11, 0, 1), Vector3(10, 0, 1))
    closedRight = _quad(Vector3(11, 0, 0), Vector3(12, 0, 0), Vector3(12, 0, 1), Vector3(11, 0, 1))
    openRectangle = _quad(Vector3(0, 0, 0), Vector3(3, 0, 0), Vector3(3, 0, 1), Vector3(0, 0, 1))
    triangles = closedLeft + closedRight + openRectangle

    before = _edgeCounts(triangles)
    closedSeam = frozenset({(11.0, 0.0, 0.0), (11.0, 0.0, 1.0)})
    assert before[closedSeam] == 2  # genuinely closed already

    repaired = repairTJunctions(triangles)

    after = _edgeCounts(repaired)
    assert after[closedSeam] == 2  # still exactly 2 - not duplicated into an overlap
    assert len(repaired) == len(triangles)  # nothing to repair here at all


def test_repair_handles_multiple_t_vertices_on_the_same_edge():
    # Three small rectangles line up against one large one at x=1, each
    # covering a slice of its z-range - the large rectangle's west edge
    # needs splitting at two interior points, not just one.
    big = _quad(Vector3(1, 0, 0), Vector3(2, 0, 0), Vector3(2, 0, 3), Vector3(1, 0, 3))
    small1 = _quad(Vector3(0, 0, 0), Vector3(1, 0, 0), Vector3(1, 0, 1), Vector3(0, 0, 1))
    small2 = _quad(Vector3(0, 0, 1), Vector3(1, 0, 1), Vector3(1, 0, 2), Vector3(0, 0, 2))
    small3 = _quad(Vector3(0, 0, 2), Vector3(1, 0, 2), Vector3(1, 0, 3), Vector3(0, 0, 3))
    triangles = big + small1 + small2 + small3

    repaired = repairTJunctions(triangles)
    after = _edgeCounts(repaired)

    assert after[frozenset({(1.0, 0.0, 0.0), (1.0, 0.0, 1.0)})] == 2
    assert after[frozenset({(1.0, 0.0, 1.0), (1.0, 0.0, 2.0)})] == 2
    assert after[frozenset({(1.0, 0.0, 2.0), (1.0, 0.0, 3.0)})] == 2
