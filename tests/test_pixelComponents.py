from collections import Counter

import pytest

from utils.data.pixelPlan import Face, PixelPlan
from utils.data.pixelComponents import componentTriangles, BULGE_SIZE, TUBE_MARGIN, WALL_THICKNESS


def _bounds(triangles):
    # componentTriangles' final assembly goes through trimesh's boolean
    # union/difference (see its own docstring - only ever combining a
    # couple of already-simplified pieces, never per-pixel), which
    # introduces float noise the same way a bare box construction does
    # elsewhere in this test suite - round it away, these tests only care
    # about the geometry, not bit-for-bit floats.
    r = lambda v: round(float(v), 6)
    return (
        (r(min(v.x for v in triangles)), r(max(v.x for v in triangles))),
        (r(min(v.y for v in triangles)), r(max(v.y for v in triangles))),
        (r(min(v.z for v in triangles)), r(max(v.z for v in triangles))),
    )


def _volume(triangles):
    vol = 0.0
    for i in range(0, len(triangles), 3):
        a, b, c = triangles[i], triangles[i + 1], triangles[i + 2]
        vol += a.x * (b.y * c.z - b.z * c.y) - a.y * (b.x * c.z - b.z * c.x) + a.z * (b.x * c.y - b.y * c.x)
    return vol / 6.0


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


def _assertWatertight(triangles):
    assert len(triangles) > 0
    directed = _edgeDirectionCounts(triangles)
    assert all(count == 1 for count in directed.values())


def test_isolated_pixel_cap_bulges_on_every_side():
    plan = PixelPlan(y=0, x=0, color=0, height=3, bulged={Face.NORTH, Face.SOUTH, Face.EAST, Face.WEST})

    triangles = componentTriangles([plan], hollow=False)

    (x0, x1), _, (z0, z1) = _bounds(triangles)
    assert (x0, x1) == (0.0 - BULGE_SIZE, 1.0 + BULGE_SIZE)
    assert (z0, z1) == (0.0 - BULGE_SIZE, 1.0 + BULGE_SIZE)
    _assertWatertight(triangles)


def test_isolated_pixel_honors_an_overridden_bulge_size():
    plan = PixelPlan(y=0, x=0, color=0, height=3, bulged={Face.NORTH, Face.SOUTH, Face.EAST, Face.WEST})

    triangles = componentTriangles([plan], hollow=False, bulgeSize=0.4)

    (x0, x1), _, (z0, z1) = _bounds(triangles)
    assert (x0, x1) == (0.0 - 0.4, 1.0 + 0.4)
    assert (z0, z1) == (0.0 - 0.4, 1.0 + 0.4)


def test_isolated_pixel_cap_stays_flush_on_a_fused_or_plain_wall_side():
    # A single isolated pixel never actually has a fused neighbor present
    # (fused implies a same-group neighbor - see
    # test_two_fused_pixels_merge_without_a_seam below for that case), but
    # marking a side fused instead of bulged still proves the cap doesn't
    # flare there - only Face.WEST's own bulge should show up.
    plan = PixelPlan(y=0, x=0, color=0, height=3, fused={Face.EAST}, bulged={Face.WEST})
    # SOUTH/NORTH have no entry in fused/bulged, so PixelPlan.plainWalls picks them up.

    triangles = componentTriangles([plan], hollow=False)

    (x0, x1), _, (z0, z1) = _bounds(triangles)
    assert x1 == 1.0                      # EAST fused: no bulge
    assert (z0, z1) == (0.0, 1.0)         # NORTH/SOUTH plain walls: no bulge
    assert x0 == 0.0 - BULGE_SIZE         # WEST bulged: flares out


def test_isolated_pixel_single_layer_has_no_tube():
    plan = PixelPlan(y=0, x=0, color=0, height=1, bulged={Face.NORTH, Face.SOUTH, Face.EAST, Face.WEST})

    solid = componentTriangles([plan], hollow=False)
    hollow = componentTriangles([plan], hollow=True)

    # nothing to hollow out without a tube below the cap
    assert _volume(solid) == _volume(hollow)
    (_, (y0, y1), _) = _bounds(solid)
    assert (y0, y1) == (0.0, 1.0)


def test_isolated_tall_pixel_tube_is_inset_on_bulged_sides_and_flush_on_fused_or_plain_wall_sides():
    plan = PixelPlan(y=0, x=0, color=0, height=3, fused={Face.EAST}, bulged={Face.NORTH, Face.WEST})
    # SOUTH is a plain wall.

    triangles = componentTriangles([plan], hollow=False)

    # The tube's own footprint is exactly the solid's cross-section at
    # y=0 (its floor), separate from the (possibly bulged) cap above it.
    floor = [v for v in triangles if abs(v.y) < 1e-9]
    assert floor
    assert max(v.x for v in floor) == pytest.approx(1.0, abs=1e-5)                     # EAST fused: flush
    assert max(v.z for v in floor) == pytest.approx(1.0, abs=1e-5)                     # SOUTH plain wall: flush
    assert min(v.x for v in floor) == pytest.approx(0.0 + TUBE_MARGIN, abs=1e-5)       # WEST bulged: inset
    assert min(v.z for v in floor) == pytest.approx(0.0 + TUBE_MARGIN, abs=1e-5)       # NORTH bulged: inset
    _assertWatertight(triangles)


def test_isolated_tall_pixel_honors_an_overridden_tube_margin():
    plan = PixelPlan(y=0, x=0, color=0, height=3, bulged={Face.NORTH, Face.SOUTH, Face.EAST, Face.WEST})

    default = componentTriangles([plan], hollow=False)
    wider = componentTriangles([plan], hollow=False, tubeMargin=0.3)

    defaultFloor = [v for v in default if abs(v.y) < 1e-9]
    widerFloor = [v for v in wider if abs(v.y) < 1e-9]
    assert min(v.x for v in widerFloor) > min(v.x for v in defaultFloor)
    assert max(v.x for v in widerFloor) < max(v.x for v in defaultFloor)


def test_isolated_tall_pixel_solid_tube_has_no_cavity():
    plan = PixelPlan(y=0, x=0, color=0, height=3, bulged={Face.NORTH, Face.SOUTH, Face.EAST, Face.WEST})

    solid = componentTriangles([plan], hollow=False)
    hollow = componentTriangles([plan], hollow=True)

    assert _volume(hollow) < _volume(solid)  # the cavity actually removed material


def test_isolated_tall_pixel_honors_an_overridden_wall_thickness():
    plan = PixelPlan(y=0, x=0, color=0, height=3, bulged={Face.NORTH, Face.SOUTH, Face.EAST, Face.WEST})

    thin = componentTriangles([plan], hollow=True, wallThickness=0.05)
    thick = componentTriangles([plan], hollow=True, wallThickness=0.3)

    # a thicker wall leaves a smaller cavity, so more material remains
    assert _volume(thick) > _volume(thin)


def test_component_triangles_of_a_single_pixel_is_watertight():
    plan = PixelPlan(y=0, x=0, color=0, height=3, bulged={Face.NORTH, Face.SOUTH, Face.EAST, Face.WEST})

    _assertWatertight(componentTriangles([plan], hollow=False))


def test_component_triangles_of_a_hollow_single_pixel_is_watertight():
    plan = PixelPlan(y=0, x=0, color=0, height=3, bulged={Face.NORTH, Face.SOUTH, Face.EAST, Face.WEST})

    _assertWatertight(componentTriangles([plan], hollow=True))


def test_component_triangles_merges_two_fused_pixels_into_one_watertight_solid():
    planA = PixelPlan(y=0, x=0, color=0, height=3, fused={Face.EAST}, bulged={Face.NORTH, Face.WEST, Face.SOUTH})
    planB = PixelPlan(y=0, x=1, color=0, height=3, fused={Face.WEST}, bulged={Face.NORTH, Face.EAST, Face.SOUTH})

    triangles = componentTriangles([planA, planB], hollow=False)

    _assertWatertight(triangles)
    # a single merged solid spanning both pixels, not two separate boxes
    # just sitting next to each other
    xs = [v.x for v in triangles]
    assert min(xs) < 0.0   # A's own west bulge
    assert max(xs) > 2.0   # B's own east bulge


def test_component_triangles_of_a_diagonal_pair_merges_when_bulges_overlap():
    # Same color/height, diagonal, with both flanking cells clear - their
    # bulges reach into the shared corner and physically touch, so the
    # result should come back as one connected solid. Diagonal-only
    # connectivity like this is also the one case that hits the pinch-point
    # fallback (see _hasPinchPoint in pixelComponents.py).
    planA = PixelPlan(y=0, x=0, color=0, height=3, bulged={Face.NORTH, Face.WEST, Face.EAST, Face.SOUTH})
    planB = PixelPlan(y=1, x=1, color=0, height=3, bulged={Face.NORTH, Face.WEST, Face.EAST, Face.SOUTH})

    triangles = componentTriangles([planA, planB], hollow=False)

    import trimesh
    verts = [(v.x, v.y, v.z) for v in triangles]
    faces = [[i, i + 1, i + 2] for i in range(0, len(triangles), 3)]
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    assert len(mesh.split(only_watertight=False)) == 1


def _lShapePlans(height, fusedSuffix=Face):
    """Three pixels forming a concave (reflex) corner: (0,0)-(0,1)-(1,0),
    missing (1,1) - the case that first exposed a real join-rule bug in
    this module's boundary construction (see its history)."""
    return [
        PixelPlan(y=0, x=0, color=0, height=height, fused={Face.EAST, Face.SOUTH}, bulged={Face.NORTH, Face.WEST}),
        PixelPlan(y=0, x=1, color=0, height=height, fused={Face.WEST}, bulged={Face.NORTH, Face.EAST, Face.SOUTH}),
        PixelPlan(y=1, x=0, color=0, height=height, fused={Face.NORTH}, bulged={Face.WEST, Face.SOUTH, Face.EAST}),
    ]


def test_concave_l_shape_is_watertight_with_a_filled_notch():
    triangles = componentTriangles(_lShapePlans(height=1), hollow=False)

    _assertWatertight(triangles)
    # the two arms' own bulges reach into the shared missing corner and
    # overlap there, so the notch isn't a sharp reflex cut - it's filled
    # out to bulgeSize past the raw grid corner.
    assert max(v.x for v in triangles) > 2.0
    assert max(v.z for v in triangles) > 2.0


def test_concave_l_shape_tall_hollow_is_watertight():
    # Height > 1 exercises the tube, whose reflex-corner join rule is the
    # opposite of the cap's (insets pull away from the corner instead of
    # overlapping into it - see _buildBoundarySolid's `outward` branch).
    triangles = componentTriangles(_lShapePlans(height=4), hollow=True)

    _assertWatertight(triangles)
    assert _volume(triangles) > 0


def test_ring_around_a_hole_is_watertight_with_area_minus_the_hole():
    # A 3x3 block of one color with the center cell missing (belongs to a
    # different group) - the outer ring's own cap footprint is a polygon
    # with a hole in it, not a simple rectangle.
    present = [(y, x) for y in range(3) for x in range(3) if (y, x) != (1, 1)]
    plans = []
    for (y, x) in present:
        fused, bulged = set(), set()
        for face in Face:
            neighbor = face.neighbor(y, x)
            (fused if neighbor in present else bulged).add(face)
        plans.append(PixelPlan(y=y, x=x, color=0, height=1, fused=fused, bulged=bulged))

    triangles = componentTriangles(plans, hollow=False)

    _assertWatertight(triangles)
    outerArea = (3 + 2 * BULGE_SIZE) ** 2
    holeArea = (1 - 2 * BULGE_SIZE) ** 2
    assert _volume(triangles) == pytest.approx(outerArea - holeArea, abs=1e-5)
