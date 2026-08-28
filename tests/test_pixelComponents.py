from utils.data.pixelPlan import Face, PixelPlan
from utils.data.pixelComponents import (
    Cap, Collar, Inlet, Notch, Pixel, Tube,
    BasePeg, BaseSocket,
    elbowWallExtensions, bulgeSeamPatch,
    BASE_PEG_DEPTH, BASE_PEG_WIDTH_RATIO,
    BULGE_SIZE, NOTCH_DEPTH, NOTCH_HEIGHT_RATIO, NOTCH_TOP_MARGIN, TUBE_MARGIN, WALL_THICKNESS,
)


def test_cap_with_no_open_or_inlet_faces_is_a_closed_box():
    cap = Cap(x0=0.0, x1=1.0, z0=0.0, z1=1.0, y0=0.0, y1=1.0, openFaces=set(), inlets=[])

    tris = cap.triangles()

    assert len(tris) == 36  # 4 side quads + top + bottom, 2 triangles each = 12 triangles


def test_cap_bottom_face_mirrors_the_top_so_the_cap_is_watertight_alone():
    cap = Cap(x0=0.0, x1=1.0, z0=0.0, z1=1.0, y0=0.0, y1=1.0, openFaces=set(), inlets=[])

    tris = cap.triangles()
    triangles = [tris[i:i + 3] for i in range(0, len(tris), 3)]
    bottomTriangles = [tri for tri in triangles if all(v.y == 0.0 for v in tri)]

    assert len(bottomTriangles) == 2  # a full bottom quad, split into 2 triangles


def test_cap_omits_a_fused_face():
    closed = Cap(x0=0.0, x1=1.0, z0=0.0, z1=1.0, y0=0.0, y1=1.0, openFaces=set(), inlets=[])
    withFused = Cap(x0=0.0, x1=1.0, z0=0.0, z1=1.0, y0=0.0, y1=1.0, openFaces={Face.EAST}, inlets=[])

    assert len(withFused.triangles()) == len(closed.triangles()) - 6  # one fewer quad


def test_notch_protrudes_past_the_boundary_below_the_top_margin():
    notch = Notch(Face.EAST, boundaryValue=1.0, uMid=0.5, uHalf=0.25, neighborHeight=2)

    verts = notch.triangles()

    assert max(v.x for v in verts) == 1.0 + NOTCH_DEPTH
    ys = {round(v.y, 6) for v in verts}
    expectedTop = 2.0 - NOTCH_TOP_MARGIN
    assert ys == {expectedTop - NOTCH_HEIGHT_RATIO, expectedTop}


def test_notch_flush_end_stays_at_the_tube_wall():
    notch = Notch(Face.EAST, boundaryValue=1.0, uMid=0.5, uHalf=0.25, neighborHeight=2)

    verts = notch.triangles()

    assert min(v.x for v in verts) == 1.0 - TUBE_MARGIN


def test_notch_is_thin_only_past_the_configured_ratio():
    shallow = Notch(Face.EAST, boundaryValue=1.0, uMid=0.5, uHalf=0.25, neighborHeight=2)
    steep = Notch(Face.EAST, boundaryValue=1.0, uMid=0.5, uHalf=0.25, neighborHeight=2)

    assert shallow.isThinRelativeTo(ownHeight=3) is False
    assert steep.isThinRelativeTo(ownHeight=20) is True


def test_inlet_recess_never_crosses_into_the_neighbors_cell():
    # A WEST-facing inlet belongs to a pixel whose solid occupies x >= 0;
    # the recess must stay on that side (x >= 0), never going negative.
    inlet = Inlet(Face.WEST, fixedValue=0.0, u0=0.0, u1=1.0, capY0=0.0, capY1=1.0)

    verts = inlet.triangles()

    assert min(v.x for v in verts) >= 0.0
    assert max(v.x for v in verts) == NOTCH_DEPTH


def test_inlet_recess_leaves_solid_material_above_it():
    # The recess band no longer sits flush with the cap's own top edge -
    # there should be real material between the recess and capY1, both
    # for strength at the locking point and so it doesn't bite into the
    # visible top corner.
    inlet = Inlet(Face.WEST, fixedValue=0.0, u0=0.0, u1=1.0, capY0=0.0, capY1=1.0)

    verts = inlet.triangles()

    assert max(v.y for v in verts) == 1.0
    assert any(v.y == 1.0 and v.x == 0.0 for v in verts)  # flush material right at the top edge


def test_tube_hollow_adds_more_geometry_than_a_solid_tube():
    solid = Tube(x0=0.2, x1=0.8, z0=0.2, z1=0.8, y1=3.0, openFaces=set(), hollow=False, notches=[])
    hollow = Tube(x0=0.2, x1=0.8, z0=0.2, z1=0.8, y1=3.0, openFaces=set(), hollow=True, notches=[])

    assert len(hollow.triangles()) > len(solid.triangles())


def test_tube_hollow_wall_never_crosses_past_the_tubes_own_boundary():
    # A NORTH wall's box must stay within the tube's own footprint -
    # thickened inward (toward larger z) only, never sticking out past
    # z0 into whatever sits beyond the tube.
    tube = Tube(x0=0.2, x1=0.8, z0=0.2, z1=0.8, y1=3.0, openFaces=set(), hollow=True, notches=[])

    northWall = tube._wallBox(Face.NORTH)

    assert min(v.z for v in northWall) == tube.z0            # outer face sits exactly at the wall
    assert max(v.z for v in northWall) == tube.z0 + WALL_THICKNESS  # thickened inward (southward), not outward
    assert {v.x for v in northWall} == {tube.x0, tube.x1}    # spans the tube's own width, no more


def test_tube_hollow_walls_of_two_adjacent_sides_meet_with_no_gap_at_the_corner():
    # Distinct per-wall boxes (not a shared cavity) - NORTH and WEST should
    # still overlap/meet cleanly at their shared corner instead of leaving
    # a gap there.
    tube = Tube(x0=0.2, x1=0.8, z0=0.2, z1=0.8, y1=3.0, openFaces=set(), hollow=True, notches=[])

    north = tube._wallBox(Face.NORTH)
    west = tube._wallBox(Face.WEST)

    assert min(v.x for v in north) <= tube.x0  # north wall reaches at least to the west wall's outer face
    assert min(v.z for v in west) <= tube.z0   # west wall reaches at least to the north wall's outer face


def test_tube_hollow_wall_has_a_floor_at_the_print_bed():
    # Nothing sits below y=0 - without a floor of its own, this box is an
    # open tube with a bare, zero-thickness rim right where it meets the
    # print bed.
    tube = Tube(x0=0.2, x1=0.8, z0=0.2, z1=0.8, y1=3.0, openFaces=set(), hollow=True, notches=[])

    northWall = tube._wallBox(Face.NORTH)
    triangles = [northWall[i:i + 3] for i in range(0, len(northWall), 3)]
    floorTriangles = [tri for tri in triangles if all(v.y == 0.0 for v in tri)]

    assert len(floorTriangles) == 2  # a full floor quad, split into 2 triangles


def test_tube_hollow_wall_is_a_fully_closed_box_on_its_own():
    # Self-contained regardless of what the cap above it does - not just a
    # floor, a matching ceiling too, so this box doesn't depend on lining
    # up edge-for-edge with the cap's own (separately triangulated) bottom
    # face to actually be watertight.
    tube = Tube(x0=0.2, x1=0.8, z0=0.2, z1=0.8, y1=3.0, openFaces=set(), hollow=True, notches=[])

    northWall = tube._wallBox(Face.NORTH)
    triangles = [northWall[i:i + 3] for i in range(0, len(northWall), 3)]
    ceilingTriangles = [tri for tri in triangles if all(v.y == tube.y1 for v in tri)]

    assert len(ceilingTriangles) == 2
    assert len(northWall) == 6 * 6  # a plain closed box: 6 quads, 2 triangles each


def test_tube_omits_a_fused_face():
    closed = Tube(x0=0.2, x1=0.8, z0=0.2, z1=0.8, y1=3.0, openFaces=set(), hollow=False, notches=[])
    withFused = Tube(x0=0.2, x1=0.8, z0=0.2, z1=0.8, y1=3.0, openFaces={Face.EAST}, hollow=False, notches=[])

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
    # EAST has no entry in fused/bulged/notches/inlets, so PixelPlan.plainWalls
    # picks it up automatically - the tube should extend to the true grid
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


def test_pixel_flags_a_thin_connector():
    plan = PixelPlan(y=0, x=0, color=0, height=20, notches={Face.EAST: 2})

    pixel = Pixel(plan, hollow=False)

    assert any("Thin connector" in w for w in pixel.warnings())


def test_base_peg_protrudes_below_y0_never_above_it():
    peg = BasePeg(cx=0.5, cz=0.5, halfWidth=0.25)

    verts = peg.triangles()

    assert max(v.y for v in verts) == 0.0
    assert min(v.y for v in verts) == -BASE_PEG_DEPTH


def test_base_peg_tapers_narrower_at_the_tip_than_at_y0():
    peg = BasePeg(cx=0.5, cz=0.5, halfWidth=0.25)

    verts = peg.triangles()

    atY0 = [v for v in verts if v.y == 0.0]
    atTip = [v for v in verts if v.y == -BASE_PEG_DEPTH]
    assert max(v.x for v in atY0) - min(v.x for v in atY0) == 0.5       # full width at the flush end
    assert max(v.x for v in atTip) - min(v.x for v in atTip) < 0.5      # narrower at the tip


def test_pixel_with_base_peg_gets_one_attached_at_y0():
    plan = PixelPlan(y=0, x=0, color=0, height=3, bulged={Face.NORTH, Face.WEST, Face.EAST, Face.SOUTH})

    withPeg = Pixel(plan, hollow=False, basePeg=True)
    withoutPeg = Pixel(plan, hollow=False, basePeg=False)

    assert len(withPeg.triangles()) > len(withoutPeg.triangles())
    assert any(v.y < 0.0 for v in withPeg.triangles())
    assert not any(v.y < 0.0 for v in withoutPeg.triangles())


def test_base_socket_opening_matches_a_base_pegs_own_footprint():
    # A peg centered the same way should fit exactly into the socket's
    # opening at y=0 - same halfWidth, same taper depth.
    peg = BasePeg(cx=0.5, cz=0.5, halfWidth=0.25)
    socket = BaseSocket(cx=0.5, cz=0.5, halfWidth=0.25)

    pegVerts = peg.triangles()
    socketVerts = socket.triangles(x0=0.0, x1=1.0, z0=0.0, z1=1.0, y=0.0)

    pegAtY0 = {round(v.x, 6) for v in pegVerts if v.y == 0.0}
    socketAtY0 = {round(v.x, 6) for v in socketVerts if v.y == 0.0}
    assert pegAtY0 <= socketAtY0  # the peg's own x-extent is present among the socket's y=0 vertices


def test_base_socket_never_carves_past_its_own_cap_footprint():
    socket = BaseSocket(cx=0.5, cz=0.5, halfWidth=0.25)

    verts = socket.triangles(x0=0.0, x1=1.0, z0=0.0, z1=1.0, y=0.0)

    assert min(v.x for v in verts) >= 0.0
    assert max(v.x for v in verts) <= 1.0
    assert min(v.y for v in verts) == -BASE_PEG_DEPTH  # leaves solid material below the recess


def test_pixel_with_top_socket_carves_the_cap_top_instead_of_a_flat_quad():
    plan = PixelPlan(y=0, x=0, color=-1, height=0)
    socket = BaseSocket(cx=0.5, cz=0.5, halfWidth=BASE_PEG_WIDTH_RATIO / 2.0)

    withSocket = Pixel(plan, hollow=False, topSocket=socket)
    withoutSocket = Pixel(plan, hollow=False)

    assert len(withSocket.triangles()) > len(withoutSocket.triangles())
    # the recess floor, distinct from the cap's own (much lower) bottom face
    assert any(v.y == -BASE_PEG_DEPTH for v in withSocket.triangles())
    assert not any(v.y == -BASE_PEG_DEPTH for v in withoutSocket.triangles())
