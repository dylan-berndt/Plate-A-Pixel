from utils.data.pixelPlan import Face, PixelPlan
from utils.data.pixelComponents import (
    Cap, Collar, Inlet, Notch, Pixel, Tube,
    elbowWallExtensions,
    NOTCH_DEPTH, NOTCH_HEIGHT_RATIO, NOTCH_TOP_MARGIN, TUBE_MARGIN,
)


def test_cap_with_no_open_or_inlet_faces_is_a_closed_box():
    cap = Cap(x0=0.0, x1=1.0, z0=0.0, z1=1.0, y0=0.0, y1=1.0, openFaces=set(), inlets=[])

    tris = cap.triangles()

    assert len(tris) == 30  # 4 side quads + 1 top quad, 2 triangles each = 10 triangles


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


def test_tube_hollow_adds_an_inner_shell():
    solid = Tube(x0=0.2, x1=0.8, z0=0.2, z1=0.8, y1=3.0, openFaces=set(), hollow=False, notches=[])
    hollow = Tube(x0=0.2, x1=0.8, z0=0.2, z1=0.8, y1=3.0, openFaces=set(), hollow=True, notches=[])

    assert len(hollow.triangles()) > len(solid.triangles())


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


def test_elbow_wall_extensions_empty_when_sides_are_already_flush():
    # If P's own east side (and Q's own north side) are already flush
    # rather than bulged, there's no wall to extend.
    planP = PixelPlan(y=0, x=1, color=0, height=3, fused={Face.SOUTH, Face.EAST}, bulged={Face.NORTH, Face.WEST})
    planQ = PixelPlan(y=1, x=2, color=0, height=3, fused={Face.WEST, Face.NORTH}, bulged={Face.EAST, Face.SOUTH})
    P = Pixel(planP, hollow=False)
    Q = Pixel(planQ, hollow=False)

    assert elbowWallExtensions(P, Q, Face.NORTH, Face.EAST) == []


def test_pixel_flags_a_thin_connector():
    plan = PixelPlan(y=0, x=0, color=0, height=20, notches={Face.EAST: 2})

    pixel = Pixel(plan, hollow=False)

    assert any("Thin connector" in w for w in pixel.warnings())
