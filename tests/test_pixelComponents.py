from collections import Counter

from utils.data.pixelPlan import Face, PixelPlan
from utils.data.pixelComponents import (
    Cap, Collar, Pixel, Tube,
    elbowWallExtensions, bulgeSeamPatch,
    BULGE_SIZE, TUBE_MARGIN, WALL_THICKNESS,
)


def _edgeDirectionCounts(triangles):
    """For every undirected edge in `triangles`, how many triangles use it
    and in which direction - the same edge used twice in the *same*
    direction means two faces meeting there are wound inconsistently, not
    just duplicated (a real 2-manifold edge is used by exactly one
    triangle each way)."""
    def key(v):
        return (round(v.x, 6), round(v.y, 6), round(v.z, 6))

    directed = Counter()
    for i in range(0, len(triangles), 3):
        tri = triangles[i:i + 3]
        for a, b in ((0, 1), (1, 2), (2, 0)):
            directed[(key(tri[a]), key(tri[b]))] += 1
    return directed


def test_cap_with_no_open_faces_is_a_closed_box():
    cap = Cap(x0=0.0, x1=1.0, z0=0.0, z1=1.0, y0=0.0, y1=1.0, openFaces=set())

    tris = cap.triangles()

    assert len(tris) == 36  # 4 side quads + top + bottom, 2 triangles each = 12 triangles


def test_cap_bottom_face_mirrors_the_top_so_the_cap_is_watertight_alone():
    cap = Cap(x0=0.0, x1=1.0, z0=0.0, z1=1.0, y0=0.0, y1=1.0, openFaces=set())

    tris = cap.triangles()
    triangles = [tris[i:i + 3] for i in range(0, len(tris), 3)]
    bottomTriangles = [tri for tri in triangles if all(v.y == 0.0 for v in tri)]

    assert len(bottomTriangles) == 2  # a full bottom quad, split into 2 triangles


def test_cap_omits_a_fused_face():
    closed = Cap(x0=0.0, x1=1.0, z0=0.0, z1=1.0, y0=0.0, y1=1.0, openFaces=set())
    withFused = Cap(x0=0.0, x1=1.0, z0=0.0, z1=1.0, y0=0.0, y1=1.0, openFaces={Face.EAST})

    assert len(withFused.triangles()) == len(closed.triangles()) - 6  # one fewer quad


def test_tube_hollow_adds_more_geometry_than_a_solid_tube():
    solid = Tube(x0=0.2, x1=0.8, z0=0.2, z1=0.8, y1=3.0, openFaces=set(), hollow=False)
    hollow = Tube(x0=0.2, x1=0.8, z0=0.2, z1=0.8, y1=3.0, openFaces=set(), hollow=True)

    assert len(hollow.triangles()) > len(solid.triangles())


def test_tube_hollow_wall_never_crosses_past_the_tubes_own_boundary():
    # A NORTH wall's box must stay within the tube's own footprint -
    # thickened inward (toward larger z) only, never sticking out past
    # z0 into whatever sits beyond the tube.
    tube = Tube(x0=0.2, x1=0.8, z0=0.2, z1=0.8, y1=3.0, openFaces=set(), hollow=True)

    northWall = tube._wallBox(Face.NORTH)

    assert min(v.z for v in northWall) == tube.z0            # outer face sits exactly at the wall
    assert max(v.z for v in northWall) == tube.z0 + WALL_THICKNESS  # thickened inward (southward), not outward
    assert {v.x for v in northWall} == {tube.x0, tube.x1}    # spans the tube's own width, no more


def test_tube_hollow_walls_of_two_adjacent_sides_meet_with_no_gap_at_the_corner():
    # Distinct per-wall boxes (not a shared cavity) - NORTH and WEST should
    # still overlap/meet cleanly at their shared corner instead of leaving
    # a gap there.
    tube = Tube(x0=0.2, x1=0.8, z0=0.2, z1=0.8, y1=3.0, openFaces=set(), hollow=True)

    north = tube._wallBox(Face.NORTH)
    west = tube._wallBox(Face.WEST)

    assert min(v.x for v in north) <= tube.x0  # north wall reaches at least to the west wall's outer face
    assert min(v.z for v in west) <= tube.z0   # west wall reaches at least to the north wall's outer face


def test_tube_hollow_wall_has_a_floor_at_the_print_bed():
    # Nothing sits below y=0 - without a floor of its own, this box is an
    # open tube with a bare, zero-thickness rim right where it meets the
    # print bed.
    tube = Tube(x0=0.2, x1=0.8, z0=0.2, z1=0.8, y1=3.0, openFaces=set(), hollow=True)

    northWall = tube._wallBox(Face.NORTH)
    triangles = [northWall[i:i + 3] for i in range(0, len(northWall), 3)]
    floorTriangles = [tri for tri in triangles if all(v.y == 0.0 for v in tri)]

    assert len(floorTriangles) == 2  # a full floor quad, split into 2 triangles


def test_tube_solid_has_a_floor_at_the_print_bed():
    # Same bug as the hollow wall above, but for the solid box itself: it
    # used to skip both its top (fair, the cap's own underside covers it)
    # and its bottom - leaving every solid tube open on its underside with
    # no floor at all.
    tube = Tube(x0=0.2, x1=0.8, z0=0.2, z1=0.8, y1=3.0, openFaces=set(), hollow=False)

    triangles = [tube.triangles()[i:i + 3] for i in range(0, len(tube.triangles()), 3)]
    floorTriangles = [tri for tri in triangles if all(v.y == 0.0 for v in tri)]

    assert len(floorTriangles) == 2  # a full floor quad, split into 2 triangles


def test_tube_hollow_wall_is_a_fully_closed_box_on_its_own():
    # Self-contained regardless of what the cap above it does - not just a
    # floor, a matching ceiling too, so this box doesn't depend on lining
    # up edge-for-edge with the cap's own (separately triangulated) bottom
    # face to actually be watertight.
    tube = Tube(x0=0.2, x1=0.8, z0=0.2, z1=0.8, y1=3.0, openFaces=set(), hollow=True)

    northWall = tube._wallBox(Face.NORTH)
    triangles = [northWall[i:i + 3] for i in range(0, len(northWall), 3)]
    ceilingTriangles = [tri for tri in triangles if all(v.y == tube.y1 for v in tri)]

    assert len(ceilingTriangles) == 2
    assert len(northWall) == 6 * 6  # a plain closed box: 6 quads, 2 triangles each


def test_tube_omits_a_fused_face():
    closed = Tube(x0=0.2, x1=0.8, z0=0.2, z1=0.8, y1=3.0, openFaces=set(), hollow=False)
    withFused = Tube(x0=0.2, x1=0.8, z0=0.2, z1=0.8, y1=3.0, openFaces={Face.EAST}, hollow=False)

    assert len(withFused.triangles()) < len(closed.triangles())


def test_collar_skips_a_fused_side():
    full = Collar((0.0, 1.0, 0.0, 1.0), (0.2, 0.8, 0.2, 0.8), y=2.0, skipFaces=set())
    withFused = Collar((0.0, 1.0, 0.0, 1.0), (0.2, 0.8, 0.2, 0.8), y=2.0, skipFaces={Face.WEST})

    assert len(withFused.triangles()) == len(full.triangles()) - 6


def test_pixel_builds_directly_from_a_hand_made_plan_without_a_canvas():
    # PixelPlan and Pixel don't need a Canvas at all - this is the point of
    # separating classification (pixelPlan.py) from geometry (pixelComponents.py).
    plan = PixelPlan(y=0, x=0, color=0, height=3, bulged={Face.NORTH, Face.WEST, Face.EAST, Face.SOUTH})

    pixel = Pixel(plan, hollow=False)

    assert len(pixel.triangles()) > 0
    assert pixel.warnings() == []


def test_pixel_tube_sits_flush_on_a_fused_side():
    # This was the actual bug: fused sides omit the *wall*, but the tube's
    # own cross-section still needs to reach the boundary or the two
    # tubes' solids never touch even though no wall stands between them.
    plan = PixelPlan(y=0, x=0, color=0, height=3, fused={Face.EAST}, bulged={Face.NORTH, Face.WEST, Face.SOUTH})

    pixel = Pixel(plan, hollow=False)

    assert pixel.tube.x1 == 1.0


def test_pixel_tube_sits_flush_on_a_plain_wall_side():
    # EAST has no entry in fused/bulged, so PixelPlan.plainWalls picks it
    # up automatically - the tube should extend to the true grid
    # boundary there (x=1) instead of being inset, so two adjacent same-
    # height/different-color pieces' tubes meet directly with no gap.
    plan = PixelPlan(y=0, x=0, color=0, height=3, bulged={Face.NORTH, Face.WEST, Face.SOUTH})

    pixel = Pixel(plan, hollow=False)

    assert pixel.tube.x1 == 1.0
    assert pixel.tube.x0 == 0.0 + TUBE_MARGIN  # WEST is bulged, not a plain wall - stays inset


def test_pixel_collar_omits_the_plain_wall_side_too():
    plan = PixelPlan(y=0, x=0, color=0, height=3, bulged={Face.NORTH, Face.WEST, Face.SOUTH})

    pixel = Pixel(plan, hollow=False)

    assert Face.EAST in pixel.collar.skipFaces


def test_elbow_wall_extensions_meet_inside_the_elbow_pixel():
    # P=(0,1) is fused SOUTH (to the elbow at (1,1)) and draws its own
    # EAST wall. Q=(1,2) is fused WEST (to the same elbow) and draws its
    # own NORTH wall. P and Q are not fused to each other at all - they
    # only relate diagonally, through the elbow. Each wall should extend,
    # staying in its own plane, out to exactly where the other one sits.
    planP = PixelPlan(y=0, x=1, color=0, height=3, fused={Face.SOUTH}, bulged={Face.NORTH, Face.WEST, Face.EAST})
    planQ = PixelPlan(y=1, x=2, color=0, height=3, fused={Face.WEST}, bulged={Face.NORTH, Face.EAST, Face.SOUTH})
    P = Pixel(planP, hollow=False)
    Q = Pixel(planQ, hollow=False)

    fill = elbowWallExtensions(P, Q, Face.NORTH, Face.EAST)

    assert len(fill) == 12  # two quads (P's extension, Q's extension), 2 triangles each

    pExtension, qExtension = fill[:6], fill[6:]

    assert {v.x for v in pExtension} == {P.tube.x1}  # stays in P's own east-wall plane
    assert {v.z for v in pExtension} == {P.tube.z1, Q.tube.z0}  # extends exactly to Q's north wall

    assert {v.z for v in qExtension} == {Q.tube.z0}  # stays in Q's own north-wall plane
    assert {v.x for v in qExtension} == {Q.tube.x0, P.tube.x1}  # extends exactly to P's east wall


def test_elbow_wall_extensions_are_reinforced_boxes_when_hollow():
    # Same corner as above, but with hollow tubes: the extension should
    # go through the same per-wall box construction as the rest of the
    # wall (floor, ceiling, WALL_THICKNESS) instead of being a bare flat
    # quad with none of that reinforcement.
    planP = PixelPlan(y=0, x=1, color=0, height=3, fused={Face.SOUTH}, bulged={Face.NORTH, Face.WEST, Face.EAST})
    planQ = PixelPlan(y=1, x=2, color=0, height=3, fused={Face.WEST}, bulged={Face.NORTH, Face.EAST, Face.SOUTH})
    P = Pixel(planP, hollow=True)
    Q = Pixel(planQ, hollow=True)

    fill = elbowWallExtensions(P, Q, Face.NORTH, Face.EAST)

    pExtension, qExtension = fill[:36], fill[36:]
    assert len(fill) == 72  # two full closed boxes (6 quads each), 2 triangles each

    pXs = {v.x for v in pExtension}
    assert pXs == {P.tube.x1, P.tube.x1 - WALL_THICKNESS}  # thickened inward, same as a normal wall
    assert {v.z for v in pExtension} == {P.tube.z1, Q.tube.z0}  # still extends exactly to Q's north wall
    assert any(v.y == 0.0 for v in pExtension) and any(v.y == P.tube.y1 for v in pExtension)  # floor and ceiling present


def test_elbow_wall_extensions_empty_when_sides_are_already_flush():
    # If P's own east side (and Q's own north side) are already flush
    # rather than bulged, there's no wall to extend.
    planP = PixelPlan(y=0, x=1, color=0, height=3, fused={Face.SOUTH, Face.EAST}, bulged={Face.NORTH, Face.WEST})
    planQ = PixelPlan(y=1, x=2, color=0, height=3, fused={Face.WEST, Face.NORTH}, bulged={Face.EAST, Face.SOUTH})
    P = Pixel(planP, hollow=False)
    Q = Pixel(planQ, hollow=False)

    assert elbowWallExtensions(P, Q, Face.NORTH, Face.EAST) == []


def test_bulge_seam_patch_closes_the_step_between_a_bulged_and_flush_cap():
    # Q=(0,0) and P=(0,1) are fused along the shared EAST/WEST seam. P also
    # bulges NORTH (nothing north of it); Q does not (something's there).
    # Their north edges no longer line up, so the sliver of P's west face
    # north of Q's own cap edge - up to P's own bulged edge - needs a wall.
    planQ = PixelPlan(y=0, x=0, color=0, height=3, fused={Face.EAST}, bulged={Face.WEST, Face.SOUTH})
    planP = PixelPlan(y=0, x=1, color=0, height=3, fused={Face.WEST}, bulged={Face.NORTH, Face.EAST, Face.SOUTH})
    Q = Pixel(planQ, hollow=False)
    P = Pixel(planP, hollow=False)

    patch = bulgeSeamPatch(P, Q, Face.WEST)

    assert len(patch) == 6  # one quad, 2 triangles
    assert {v.x for v in patch} == {P.cap.x0}          # stays in P's own west-face plane
    assert {v.z for v in patch} == {P.cap.z0, Q.cap.z0}  # spans exactly the bulge overhang
    assert P.cap.z0 == 0.0 - BULGE_SIZE
    assert Q.cap.z0 == 0.0


def test_bulge_seam_patch_empty_when_both_sides_bulge_the_same_way():
    planQ = PixelPlan(y=0, x=0, color=0, height=3, fused={Face.EAST}, bulged={Face.WEST, Face.NORTH, Face.SOUTH})
    planP = PixelPlan(y=0, x=1, color=0, height=3, fused={Face.WEST}, bulged={Face.NORTH, Face.EAST, Face.SOUTH})
    Q = Pixel(planQ, hollow=False)
    P = Pixel(planP, hollow=False)

    assert bulgeSeamPatch(P, Q, Face.WEST) == []


def test_solid_pixel_with_clear_sides_has_no_duplicate_or_inconsistently_wound_edges():
    # A solid pixel bulged on every side (no neighbors at all) should be a
    # single, cleanly closed shell: every edge shared by exactly one
    # triangle in each direction. This was the actual bug behind a lot of
    # the "non-manifold edge" reports - _faceQuad wound NORTH/SOUTH quads
    # opposite to EAST/WEST and to _box() (see _faceQuad), and the Cap's
    # own underside redundantly re-covered the same ring the Collar
    # already closes (see Cap.__init__) - both fixed at the source rather
    # than patched after the fact.
    plan = PixelPlan(y=0, x=0, color=0, height=3, bulged={Face.NORTH, Face.SOUTH, Face.EAST, Face.WEST})
    pixel = Pixel(plan, hollow=False)

    directed = _edgeDirectionCounts(pixel.triangles())

    assert all(count == 1 for count in directed.values())


def test_solid_fused_pair_has_no_duplicate_or_inconsistently_wound_edges():
    # Same check as above, across a real seam between two fused pixels
    # (not just one pixel's own internal geometry).
    planA = PixelPlan(y=0, x=0, color=0, height=3, fused={Face.EAST}, bulged={Face.NORTH, Face.WEST, Face.SOUTH})
    planB = PixelPlan(y=0, x=1, color=0, height=3, fused={Face.WEST}, bulged={Face.NORTH, Face.EAST, Face.SOUTH})
    A = Pixel(planA, hollow=False)
    B = Pixel(planB, hollow=False)

    directed = _edgeDirectionCounts(A.triangles() + B.triangles())

    assert all(count == 1 for count in directed.values())
