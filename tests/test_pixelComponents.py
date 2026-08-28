from utils.data.pixelPlan import Face, PixelPlan
from utils.data.pixelComponents import Cap, Collar, Inlet, Notch, Pixel, Tube, NOTCH_DEPTH, TUBE_MARGIN


def test_cap_with_no_open_or_inlet_faces_is_a_closed_box():
    cap = Cap(x0=0.0, x1=1.0, z0=0.0, z1=1.0, y0=0.0, y1=1.0, openFaces=set(), inlets=[])

    tris = cap.triangles()

    assert len(tris) == 30  # 4 side quads + 1 top quad, 2 triangles each = 10 triangles


def test_cap_omits_a_fused_face():
    closed = Cap(x0=0.0, x1=1.0, z0=0.0, z1=1.0, y0=0.0, y1=1.0, openFaces=set(), inlets=[])
    withFused = Cap(x0=0.0, x1=1.0, z0=0.0, z1=1.0, y0=0.0, y1=1.0, openFaces={Face.EAST}, inlets=[])

    assert len(withFused.triangles()) == len(closed.triangles()) - 6  # one fewer quad


def test_notch_protrudes_past_the_boundary_in_the_top_band():
    notch = Notch(Face.EAST, boundaryValue=1.0, uMid=0.5, uHalf=0.25, neighborHeight=2)

    verts = notch.triangles()

    assert max(v.x for v in verts) == 1.0 + NOTCH_DEPTH
    ys = {round(v.y, 6) for v in verts}
    assert ys == {2.0 - 0.4, 2.0}  # the notch band is exactly [neighborHeight - 0.4, neighborHeight]


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


def test_tube_hollow_adds_an_inner_shell():
    solid = Tube(x0=0.2, x1=0.8, z0=0.2, z1=0.8, y1=3.0, openFaces=set(), hollow=False, notches=[])
    hollow = Tube(x0=0.2, x1=0.8, z0=0.2, z1=0.8, y1=3.0, openFaces=set(), hollow=True, notches=[])

    assert len(hollow.triangles()) > len(solid.triangles())


def test_tube_omits_a_fused_face():
    closed = Tube(x0=0.2, x1=0.8, z0=0.2, z1=0.8, y1=3.0, openFaces=set(), hollow=False, notches=[])
    withFused = Tube(x0=0.2, x1=0.8, z0=0.2, z1=0.8, y1=3.0, openFaces={Face.EAST}, hollow=False, notches=[])

    assert len(withFused.triangles()) < len(closed.triangles())


def test_collar_skips_a_fused_side():
    full = Collar((0.0, 1.0, 0.0, 1.0), (0.2, 0.8, 0.2, 0.8), y=2.0, openFaces=set())
    withFused = Collar((0.0, 1.0, 0.0, 1.0), (0.2, 0.8, 0.2, 0.8), y=2.0, openFaces={Face.WEST})

    assert len(withFused.triangles()) == len(full.triangles()) - 6


def test_pixel_builds_directly_from_a_hand_made_plan_without_a_canvas():
    # PixelPlan and Pixel don't need a Canvas at all - this is the point of
    # separating classification (pixelPlan.py) from geometry (pixelComponents.py).
    plan = PixelPlan(y=0, x=0, color=0, height=3, bulged={Face.NORTH, Face.WEST, Face.EAST, Face.SOUTH})

    pixel = Pixel(plan, hollow=False)

    assert len(pixel.triangles()) > 0
    assert pixel.warnings() == []


def test_pixel_flags_a_thin_connector():
    plan = PixelPlan(y=0, x=0, color=0, height=20, notches={Face.EAST: 2})

    pixel = Pixel(plan, hollow=False)

    assert any("Thin connector" in w for w in pixel.warnings())
