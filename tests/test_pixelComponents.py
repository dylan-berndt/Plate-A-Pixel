from utils.data.pixelPlan import Face, PixelPlan
from utils.data.pixelComponents import (
    Cap, Collar, Inlet, Notch, Pixel, Tube,
    cornerFillTriangles,
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


def test_corner_fill_is_a_single_quad_in_the_omitted_shared_walls_plane():
    # A is fused EAST (to B) and NORTH (to some third pixel, flush there);
    # B is only fused WEST, so its own north side is bulged/inset. A's
    # east wall and B's west wall are both omitted (they're fused), but
    # B's own material only starts at z=1.2, leaving A's boundary open
    # and unbacked for z in [1.0, 1.2]. The fix is exactly that one flat
    # quad, sitting in the same plane as the omitted A/B wall (constant
    # x = the shared seam) - not a box, not a diagonal bridge.
    planA = PixelPlan(y=1, x=1, color=0, height=3, fused={Face.EAST, Face.NORTH}, bulged={Face.WEST, Face.SOUTH})
    planB = PixelPlan(y=1, x=2, color=0, height=3, fused={Face.WEST}, bulged={Face.NORTH, Face.EAST, Face.SOUTH})
    pixelA = Pixel(planA, hollow=False)
    pixelB = Pixel(planB, hollow=False)

    fill = cornerFillTriangles(pixelA, pixelB, Face.EAST, Face.NORTH)

    assert len(fill) == 6  # one quad, 2 triangles
    xs = {v.x for v in fill}
    assert xs == {pixelA.tube.x1}  # entirely in the seam plane - both pixels' shared x, nothing wider
    zs = {v.z for v in fill}
    assert zs == {pixelA.tube.z0, pixelB.tube.z0}  # spans exactly the mismatched gap, nothing more


def test_corner_fill_is_empty_when_sides_already_agree():
    planA = PixelPlan(y=1, x=1, color=0, height=3, fused={Face.EAST, Face.NORTH}, bulged={Face.WEST, Face.SOUTH})
    planB = PixelPlan(y=1, x=2, color=0, height=3, fused={Face.WEST, Face.NORTH}, bulged={Face.EAST, Face.SOUTH})
    pixelA = Pixel(planA, hollow=False)
    pixelB = Pixel(planB, hollow=False)

    assert cornerFillTriangles(pixelA, pixelB, Face.EAST, Face.NORTH) == []


def test_pixel_flags_a_thin_connector():
    plan = PixelPlan(y=0, x=0, color=0, height=20, notches={Face.EAST: 2})

    pixel = Pixel(plan, hollow=False)

    assert any("Thin connector" in w for w in pixel.warnings())
