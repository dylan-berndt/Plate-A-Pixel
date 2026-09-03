from collections import Counter

import pytest

from utils.data.pixelPlan import Face, PixelPlan
from utils.data.pixelComponents import componentTriangles, componentTrianglesFast, BULGE_SIZE, TUBE_MARGIN, WALL_THICKNESS
from utils.data.pixelComponents import _earClip, _signedArea


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


def _lShapePlans(height, fusedSuffix=Face, offsetY=0, offsetX=0):
    """Three pixels forming a concave (reflex) corner: (0,0)-(0,1)-(1,0),
    missing (1,1) - the case that first exposed a real join-rule bug in
    this module's boundary construction (see its history). offsetY/offsetX
    shift the whole shape away from the grid origin without changing its
    geometry - see test_concave_l_shape_tall_hollow_is_watertight_away_from
    _the_grid_origin for why that matters."""
    return [
        PixelPlan(y=offsetY + 0, x=offsetX + 0, color=0, height=height,
                  fused={Face.EAST, Face.SOUTH}, bulged={Face.NORTH, Face.WEST}),
        PixelPlan(y=offsetY + 0, x=offsetX + 1, color=0, height=height,
                  fused={Face.WEST}, bulged={Face.NORTH, Face.EAST, Face.SOUTH}),
        PixelPlan(y=offsetY + 1, x=offsetX + 0, color=0, height=height,
                  fused={Face.NORTH}, bulged={Face.WEST, Face.SOUTH, Face.EAST}),
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


def test_concave_l_shape_tall_hollow_is_watertight_away_from_the_grid_origin():
    # Regression: _buildBoundarySolid's reflex-corner and same-axis-offset
    # branches used the raw boundary loop's *local* grid-relative
    # coordinates directly instead of translating them into the same world
    # coordinates offsetFn already returns - invisible for a group whose
    # bounding box happens to start at (0, 0) (minY == minX == 0 makes the
    # translation a no-op), which is exactly why every other test above
    # missed it. Any group anchored away from the origin - i.e. almost
    # every group in a real multi-color image - got garbled vertices at
    # those points instead, which only ever surfaced downstream as
    # "Not all meshes are volumes!" once a group's cap and tube were
    # unioned (see Mesh._calculateMesh's cap+tube union).
    triangles = componentTriangles(_lShapePlans(height=4, offsetY=10, offsetX=14), hollow=True)

    _assertWatertight(triangles)
    assert _volume(triangles) > 0
    # the shape itself is unchanged, just translated - bounds should land
    # exactly offsetX/offsetY past where the origin-anchored version does.
    (x0, x1), _, (z0, z1) = _bounds(triangles)
    assert x0 < 14.0 < x1
    assert z0 < 10.0 < z1


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


def test_a_hole_touching_the_outer_boundary_at_one_point_is_still_watertight():
    # Regression: a real 13-pixel group pulled from fire1.png (see
    # ARCHITECTURE-adjacent history) whose own outline pinches back on
    # itself with no bulge anywhere to widen the touch (every side here
    # is fused or a plain wall) - the fine-grid pinch fallback correctly
    # traces this into one outer loop plus a 1x1 hole, but that hole
    # touches the outer loop at exactly one vertex. Cutting a hole that
    # touches its outer boundary via CSG pinches the result to a single
    # edge there, which isn't a valid 2-manifold - manifold3d doesn't
    # error on it, it silently hands back a broken mesh instead.
    rows = {
        (91, 111): "ES", (91, 112): "SW", (92, 111): "ENS", (92, 112): "NW",
        (93, 110): "ES", (93, 111): "NW", (94, 110): "NS", (94, 112): "S",
        (95, 110): "ENS", (95, 111): "EW", (95, 112): "NW",
        (96, 109): "E", (96, 110): "NW",
    }
    letterToFace = {"N": Face.NORTH, "S": Face.SOUTH, "E": Face.EAST, "W": Face.WEST}
    plans = [
        PixelPlan(y=y, x=x, color=0, height=1, fused={letterToFace[c] for c in fusedLetters})
        for (y, x), fusedLetters in rows.items()
    ]

    triangles = componentTriangles(plans, hollow=False)

    _assertWatertight(triangles)
    # The pinch makes the traced outer loop's own area 1 unit bigger than
    # the pixel count (14, not 13) - subtracting the 1x1 hole it also
    # traces brings the total back down to exactly the 13 covered cells.
    assert _volume(triangles) == pytest.approx(len(plans), abs=1e-3)


def test_ear_clip_makes_progress_on_a_near_degenerate_remainder():
    # Regression: this exact 82-vertex hole (pulled from a real fire1.png
    # group after a partially-placed selection was raised) shrinks, after
    # 78 legitimate clips, to 4 vertices whose float64 coordinates (many
    # of them .1/.9 fractions accumulated through arithmetic) leave them
    # collinear enough that no candidate ever clears the strict 1e-12
    # convexity cutoff. _earClip used to just burn through its whole
    # guard budget and silently drop those 4 vertices - a real, if tiny,
    # hole in the resulting cap, with no duplicate or missing *edge* to
    # show for it since the undiscovered ears never produced triangles
    # in the first place.
    loop = [
        (79.9, 8.9), (80.9, 8.9), (80.9, 6.1), (78.1, 6.1), (78.1, 7.1), (76.9, 7.1), (76.9, 6.1),
        (75.1, 6.1), (75.1, 7.1), (74.1, 7.1), (74.1, 8.1), (73.1, 8.1), (73.1, 11.1), (72.1, 11.1),
        (72.1, 14.1), (71.1, 14.1), (71.1, 15.9), (73.1, 15.9), (73.1, 17.1), (72.1, 17.1), (72.1, 17.9),
        (73.1, 17.9), (73.1, 20.1), (72.1, 20.1), (72.1, 20.9), (73.1, 20.9), (73.1, 22.1), (71.1, 22.1),
        (71.1, 22.9), (72.1, 22.9), (72.1, 24.1), (70.1, 24.1), (70.1, 24.9), (72.1, 24.9), (72.1, 26.1),
        (71.1, 26.1), (71.1, 27.1), (70.1, 27.1), (70.1, 27.9), (71.1, 27.9), (71.1, 29.1), (70.1, 29.1),
        (70.1, 29.9), (71.1, 29.9), (71.1, 31.1), (70.1, 31.1), (70.1, 32.1), (69.1, 32.1), (69.1, 32.9),
        (70.9, 32.9), (70.9, 31.9), (71.9, 31.9), (71.9, 27.9), (73.9, 27.9), (73.9, 26.9), (77.9, 26.9),
        (77.9, 25.9), (78.9, 25.9), (78.9, 23.9), (80.1, 23.9), (80.1, 24.9), (80.9, 24.9), (80.9, 23.9),
        (81.9, 23.9), (81.9, 22.1), (80.9, 22.1), (80.9, 21.1), (78.9, 21.1), (78.9, 20.1), (76.9, 20.1),
        (76.9, 18.9), (77.9, 18.9), (77.9, 15.1), (76.9, 15.1), (76.9, 13.9), (77.9, 13.9), (77.9, 13.1),
        (75.9, 13.1), (75.9, 11.9), (77.9, 11.9), (77.9, 10.9), (79.9, 10.9),
    ]

    triangles = _earClip(loop)

    assert len(triangles) == len(loop) - 2
    totalArea = sum(
        0.5 * abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1]))
        for a, b, c in triangles
    )
    assert totalArea == pytest.approx(abs(_signedArea(loop)), abs=1e-6)


# componentTrianglesFast (Mesh.fastPreview) trades real watertightness for
# speed - see its own docstring - so these check it encloses the same
# volume as the exact path, not that _assertWatertight passes.

def test_fast_preview_matches_the_exact_volume_of_a_bulged_single_pixel():
    plan = PixelPlan(y=0, x=0, color=0, height=1, bulged={Face.NORTH, Face.SOUTH, Face.EAST, Face.WEST})

    exact = componentTriangles([plan], hollow=False)
    fast = componentTrianglesFast([plan])

    assert _volume(fast) == pytest.approx(_volume(exact), abs=1e-6)


def test_fast_preview_matches_the_exact_volume_of_a_concave_l_shape():
    exact = componentTriangles(_lShapePlans(height=1), hollow=False)
    fast = componentTrianglesFast(_lShapePlans(height=1))

    assert _volume(fast) == pytest.approx(_volume(exact), abs=1e-6)


def test_fast_preview_matches_the_exact_volume_of_a_tall_shape_with_a_tube():
    exact = componentTriangles(_lShapePlans(height=4), hollow=False)
    fast = componentTrianglesFast(_lShapePlans(height=4))

    assert _volume(fast) == pytest.approx(_volume(exact), abs=1e-6)


def test_fast_preview_matches_the_exact_volume_of_a_ring_around_a_hole():
    present = [(y, x) for y in range(3) for x in range(3) if (y, x) != (1, 1)]
    plans = []
    for (y, x) in present:
        fused, bulged = set(), set()
        for face in Face:
            neighbor = face.neighbor(y, x)
            (fused if neighbor in present else bulged).add(face)
        plans.append(PixelPlan(y=y, x=x, color=0, height=1, fused=fused, bulged=bulged))

    exact = componentTriangles(plans, hollow=False)
    fast = componentTrianglesFast(plans)

    assert _volume(fast) == pytest.approx(_volume(exact), abs=1e-5)


def test_fast_preview_merges_a_large_uniform_blocks_walls_into_a_simple_box():
    # Regression: _rawEdges reports one boundary edge per native grid cell
    # by design (see _mergedBoundaryRuns) - a big flat, uniformly-covered
    # block (a solid background, a base plate) has a straight boundary
    # that must collapse into one wall quad per side, not one per pixel
    # of edge length. A 20x20 block that comes out as more than a plain
    # box's 12 triangles means that merge isn't happening.
    n = 20
    plans = []
    for y in range(n):
        for x in range(n):
            fused, bulged = set(), set()
            for face in Face:
                ny, nx = face.neighbor(y, x)
                (fused if 0 <= ny < n and 0 <= nx < n else bulged).add(face)
            plans.append(PixelPlan(y=y, x=x, color=0, height=1, fused=fused, bulged=bulged))

    fast = componentTrianglesFast(plans)

    assert len(fast) // 3 == 12
