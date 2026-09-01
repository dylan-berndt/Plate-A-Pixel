from collections import Counter

from utils.data.pixelPlan import Face, PixelPlan
from utils.data.pixelComponents import Pixel, componentTriangles, BULGE_SIZE, TUBE_MARGIN, WALL_THICKNESS


def _bounds(mesh):
    # trimesh box construction round-trips through a translation, which
    # introduces float noise (0.1 -> 0.10000000000000009) - round it away,
    # these tests only care about the geometry, not bit-for-bit floats.
    (x0, y0, z0), (x1, y1, z1) = mesh.bounds
    r = lambda v: round(float(v), 9)
    return (r(x0), r(x1)), (r(y0), r(y1)), (r(z0), r(z1))


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


def test_pixel_with_no_neighbors_bulges_the_cap_on_every_side():
    plan = PixelPlan(y=0, x=0, color=0, height=3, bulged={Face.NORTH, Face.SOUTH, Face.EAST, Face.WEST})

    pixel = Pixel(plan, hollow=False)

    (x0, x1), (y0, y1), (z0, z1) = _bounds(pixel.solids[0])
    assert (x0, x1) == (0.0 - BULGE_SIZE, 1.0 + BULGE_SIZE)
    assert (z0, z1) == (0.0 - BULGE_SIZE, 1.0 + BULGE_SIZE)
    assert (y0, y1) == (2.0, 3.0)  # the cap is always exactly the top unit layer


def test_pixel_honors_an_overridden_bulge_size():
    plan = PixelPlan(y=0, x=0, color=0, height=3, bulged={Face.NORTH, Face.SOUTH, Face.EAST, Face.WEST})

    pixel = Pixel(plan, hollow=False, bulgeSize=0.4)

    (x0, x1), (y0, y1), (z0, z1) = _bounds(pixel.solids[0])
    assert (x0, x1) == (0.0 - 0.4, 1.0 + 0.4)
    assert (z0, z1) == (0.0 - 0.4, 1.0 + 0.4)


def test_pixel_honors_an_overridden_tube_margin():
    plan = PixelPlan(y=0, x=0, color=0, height=3, bulged={Face.NORTH, Face.SOUTH, Face.EAST, Face.WEST})

    default = Pixel(plan, hollow=False)
    wider = Pixel(plan, hollow=False, tubeMargin=0.3)

    (dx0, dx1), _, _ = _bounds(default.solids[1])
    (wx0, wx1), _, _ = _bounds(wider.solids[1])
    assert wx0 > dx0
    assert wx1 < dx1


def test_pixel_honors_an_overridden_wall_thickness():
    plan = PixelPlan(y=0, x=0, color=0, height=3, bulged={Face.NORTH, Face.SOUTH, Face.EAST, Face.WEST})

    thin = Pixel(plan, hollow=True, wallThickness=0.05)
    thick = Pixel(plan, hollow=True, wallThickness=0.3)

    (tx0, tx1), _, _ = _bounds(thin.cavities[0])
    (kx0, kx1), _, _ = _bounds(thick.cavities[0])
    # a thicker wall leaves a smaller cavity
    assert (kx1 - kx0) < (tx1 - tx0)


def test_pixel_cap_stays_flush_on_a_fused_or_plain_wall_side():
    plan = PixelPlan(y=0, x=0, color=0, height=3, fused={Face.EAST}, bulged={Face.NORTH, Face.WEST})
    # SOUTH has no entry in fused/bulged, so PixelPlan.plainWalls picks it up.

    pixel = Pixel(plan, hollow=False)

    (x0, x1), _, (z0, z1) = _bounds(pixel.solids[0])
    assert x1 == 1.0       # EAST fused: no bulge
    assert z1 == 1.0       # SOUTH plain wall: no bulge
    assert x0 == 0.0 - BULGE_SIZE   # WEST bulged: flares out


def test_pixel_single_layer_has_no_tube():
    plan = PixelPlan(y=0, x=0, color=0, height=1, bulged={Face.NORTH, Face.SOUTH, Face.EAST, Face.WEST})

    pixel = Pixel(plan, hollow=False)

    assert len(pixel.solids) == 1  # just the cap, nothing below it
    assert pixel.cavities == []


def test_pixel_tube_box_is_inset_on_bulged_sides_and_flush_on_fused_or_plain_wall_sides():
    plan = PixelPlan(y=0, x=0, color=0, height=3, fused={Face.EAST}, bulged={Face.NORTH, Face.WEST})
    # SOUTH is a plain wall.

    pixel = Pixel(plan, hollow=False)

    assert len(pixel.solids) == 2
    (x0, x1), (y0, y1), (z0, z1) = _bounds(pixel.solids[1])
    assert (y0, y1) == (0.0, 2.0)
    assert x1 == 1.0                   # EAST fused: flush
    assert z1 == 1.0                   # SOUTH plain wall: flush
    assert x0 == 0.0 + TUBE_MARGIN     # WEST bulged: inset
    assert z0 == 0.0 + TUBE_MARGIN     # NORTH bulged: inset


def test_pixel_solid_tube_has_no_cavity():
    plan = PixelPlan(y=0, x=0, color=0, height=3, bulged={Face.NORTH, Face.SOUTH, Face.EAST, Face.WEST})

    pixel = Pixel(plan, hollow=False)

    assert pixel.cavities == []


def test_pixel_hollow_tube_has_a_cavity_inset_by_wall_thickness():
    plan = PixelPlan(y=0, x=0, color=0, height=3, bulged={Face.NORTH, Face.SOUTH, Face.EAST, Face.WEST})

    pixel = Pixel(plan, hollow=True)

    assert len(pixel.cavities) == 1
    (x0, x1), (y0, y1), (z0, z1) = _bounds(pixel.cavities[0])
    tubeX0 = 0.0 + TUBE_MARGIN
    assert x0 == tubeX0 + WALL_THICKNESS
    assert x1 == (1.0 - TUBE_MARGIN) - WALL_THICKNESS
    assert y1 == 2.0                    # stops exactly at the cap's underside
    assert y0 < 0.0                     # punches through the tube's own floor


def test_component_triangles_of_a_single_pixel_is_watertight():
    plan = PixelPlan(y=0, x=0, color=0, height=3, bulged={Face.NORTH, Face.SOUTH, Face.EAST, Face.WEST})
    pixel = Pixel(plan, hollow=False)

    triangles = componentTriangles([pixel])

    assert len(triangles) > 0
    directed = _edgeDirectionCounts(triangles)
    assert all(count == 1 for count in directed.values())


def test_component_triangles_of_a_hollow_single_pixel_is_watertight():
    plan = PixelPlan(y=0, x=0, color=0, height=3, bulged={Face.NORTH, Face.SOUTH, Face.EAST, Face.WEST})
    pixel = Pixel(plan, hollow=True)

    triangles = componentTriangles([pixel])

    assert len(triangles) > 0
    directed = _edgeDirectionCounts(triangles)
    assert all(count == 1 for count in directed.values())


def test_component_triangles_merges_two_fused_pixels_into_one_watertight_solid():
    planA = PixelPlan(y=0, x=0, color=0, height=3, fused={Face.EAST}, bulged={Face.NORTH, Face.WEST, Face.SOUTH})
    planB = PixelPlan(y=0, x=1, color=0, height=3, fused={Face.WEST}, bulged={Face.NORTH, Face.EAST, Face.SOUTH})
    A = Pixel(planA, hollow=False)
    B = Pixel(planB, hollow=False)

    triangles = componentTriangles([A, B])

    assert len(triangles) > 0
    directed = _edgeDirectionCounts(triangles)
    assert all(count == 1 for count in directed.values())
    # a single merged solid spanning both pixels, not two separate boxes
    # just sitting next to each other
    xs = [v.x for v in triangles]
    assert min(xs) < 0.0   # A's own west bulge
    assert max(xs) > 2.0   # B's own east bulge


def test_component_triangles_of_a_diagonal_pair_merges_when_bulges_overlap():
    # Same color/height, diagonal, with both flanking cells clear - their
    # bulges reach into the shared corner and physically touch, so the
    # boolean union should come back as one connected solid.
    planA = PixelPlan(y=0, x=0, color=0, height=3, bulged={Face.NORTH, Face.WEST, Face.EAST, Face.SOUTH})
    planB = PixelPlan(y=1, x=1, color=0, height=3, bulged={Face.NORTH, Face.WEST, Face.EAST, Face.SOUTH})
    A = Pixel(planA, hollow=False)
    B = Pixel(planB, hollow=False)

    triangles = componentTriangles([A, B])

    import trimesh
    verts = [(v.x, v.y, v.z) for v in triangles]
    faces = [[i, i + 1, i + 2] for i in range(0, len(triangles), 3)]
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    assert len(mesh.split(only_watertight=False)) == 1
