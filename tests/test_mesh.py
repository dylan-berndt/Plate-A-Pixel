from pathlib import Path

import numpy as np
import pytest
import trimesh
from PIL import Image

from utils.data.canvas import Canvas
from utils.data.mesh import Mesh

FIRE1_PATH = Path(__file__).resolve().parent.parent / "fire1.png"


def make_two_color_canvas():
    """A 2-logical-column canvas: blue on the left, red on the right,
    heights left at -1 (empty) so each test sets exactly what it needs."""
    img = np.zeros((4, 8, 3), dtype=np.uint8)
    img[:, :4] = (30, 30, 200)
    img[:, 4:] = (200, 30, 30)
    canvas = Canvas(img, scale=1)
    canvas.layers[:] = -1
    return canvas


@pytest.fixture
def two_color_canvas():
    return make_two_color_canvas()


def total_triangles(mesh):
    return sum(len(component) for components in mesh.meshes for component in components) // 3


def total_real_triangles(mesh, canvas):
    # mesh.meshes carries one extra entry past canvas.palette for the base
    # plate (see Mesh._calculateMesh) - this sums only the real colors.
    return sum(
        len(component) for components in mesh.meshes[:len(canvas.palette)] for component in components
    ) // 3


def test_empty_canvas_produces_no_real_pixel_geometry(two_color_canvas):
    # Nothing placed means every cell becomes base material instead - see
    # test_base_plate_fills_an_entirely_empty_canvas below - but no real
    # color should have any geometry of its own.
    mesh = Mesh()
    mesh.canvas = two_color_canvas
    mesh._calculateMesh()

    assert total_real_triangles(mesh, two_color_canvas) == 0


def test_recompute_is_a_no_op_when_nothing_changed(two_color_canvas):
    # Regression: _checkForUpdate used to call np.allclose against the
    # None caches on the very first run and crash.
    two_color_canvas.layers[0, 0] = 3
    mesh = Mesh()
    mesh.canvas = two_color_canvas
    mesh._calculateMesh()
    firstWarnings = list(mesh.warnings)

    mesh._calculateMesh()
    assert mesh.warnings == firstWarnings


def test_same_color_same_height_neighbors_fuse_into_one_component(two_color_canvas):
    two_color_canvas.layers[0, 0] = 3
    two_color_canvas.layers[0, 1] = 3  # both logical blue columns, per make_two_color_canvas

    mesh = Mesh()
    mesh.canvas = two_color_canvas
    mesh._calculateMesh()

    blueIndex = two_color_canvas.map[0, 0]
    assert len(mesh.meshes[blueIndex]) == 1
    assert mesh.warnings == []


def test_different_height_neighbors_never_fuse_even_when_connected(two_color_canvas):
    # blue (taller, height 4) directly left of red (shorter, height 2) - no
    # interlock between them, just two independent solids each bulging its
    # own wall toward the other.
    two_color_canvas.layers[0, 3] = 4  # blue
    two_color_canvas.layers[0, 4] = 2  # red

    mesh = Mesh()
    mesh.canvas = two_color_canvas
    mesh._calculateMesh()

    blueIndex = two_color_canvas.map[0, 3]
    redIndex = two_color_canvas.map[0, 4]
    assert len(mesh.meshes[blueIndex]) == 1
    assert len(mesh.meshes[redIndex]) == 1
    assert total_triangles(mesh) > 0

    from utils.data.pixelComponents import BULGE_SIZE, TUBE_MARGIN

    # each pixel's cap bulges toward the other (no same-height neighbor
    # there), flaring BULGE_SIZE past the shared boundary (x=4) - and
    # BULGE_SIZE stays under TUBE_MARGIN specifically so neither cap's
    # bulge ever reaches the other's own (inset) tube.
    assert BULGE_SIZE < TUBE_MARGIN
    blueVerts = mesh.meshes[blueIndex][0]
    assert max(v.x for v in blueVerts) == pytest.approx(4.0 + BULGE_SIZE, abs=1e-5)
    redVerts = mesh.meshes[redIndex][0]
    assert min(v.x for v in redVerts) == pytest.approx(4.0 - BULGE_SIZE, abs=1e-5)


def test_diagonal_same_height_pixels_no_longer_bulge_once_the_base_fills_their_flanks(two_color_canvas):
    # This used to bulge into one component (the diagonal-connectivity
    # rule requires both flanking cells to be genuinely clear) - now that
    # the base plate always fills empty cells (see Mesh._calculateMesh),
    # those flanks are occupied instead, so the two pixels stay separate
    # and each interlocks with the base on its own.
    two_color_canvas.layers[0, 0] = 3
    two_color_canvas.layers[1, 1] = 3  # diagonal from (0, 0), same color/height

    mesh = Mesh()
    mesh.canvas = two_color_canvas
    mesh._calculateMesh()

    blueIndex = two_color_canvas.map[0, 0]
    assert len(mesh.meshes[blueIndex]) == 2


def test_fully_packed_checkerboard_has_no_bulge_connectivity():
    # A 2x2 checkerboard where every side of every pixel has *some* pixel
    # next to it (just possibly a different color) - bulging only ever
    # happens on a genuinely clear side, so nothing bulges here and neither
    # diagonal pair connects. (A dedicated connector for this case, keyed
    # off palette order per the corrected spec, isn't implemented yet -
    # see the write-up.)
    img = np.zeros((2, 2, 3), dtype=np.uint8)
    img[0, 0] = (30, 30, 200)
    img[1, 1] = (30, 30, 200)
    img[0, 1] = (200, 30, 30)
    img[1, 0] = (200, 30, 30)
    canvas = Canvas(img, scale=1)
    canvas.layers[:] = 3

    mesh = Mesh()
    mesh.canvas = canvas
    mesh._calculateMesh()

    blueIndex = canvas.map[0, 0]
    redIndex = canvas.map[0, 1]
    assert len(mesh.meshes[blueIndex]) == 2
    assert len(mesh.meshes[redIndex]) == 2
    assert sum("disconnected parts" in w for w in mesh.warnings) == 2


def test_isolated_single_pixel_is_flagged(two_color_canvas):
    two_color_canvas.layers[0, 0] = 3

    mesh = Mesh()
    mesh.canvas = two_color_canvas
    mesh._calculateMesh()

    assert any("Isolated single-pixel part" in w for w in mesh.warnings)


def test_hollow_flag_adds_an_inner_shell_wall(two_color_canvas):
    two_color_canvas.layers[0, 0] = 3

    solid = Mesh()
    solid.canvas = two_color_canvas
    solid.hollow = False
    solid._calculateMesh()

    hollow = Mesh()
    hollow.canvas = two_color_canvas
    hollow.hollow = True
    hollow._calculateMesh()

    assert total_triangles(hollow) > total_triangles(solid)


def base_index(canvas):
    return len(canvas.palette)


def test_base_plate_fills_an_entirely_empty_canvas(two_color_canvas):
    mesh = Mesh()
    mesh.canvas = two_color_canvas
    mesh._calculateMesh()

    assert len(mesh.meshes[base_index(two_color_canvas)]) >= 1


def test_base_plate_fills_a_hole_inside_the_canvas(two_color_canvas):
    # Every cell around this single placed pixel is a "hole" - the base
    # should fill all of them, with zero margin needed for that.
    two_color_canvas.layers[0, 0] = 3

    mesh = Mesh()
    mesh.canvas = two_color_canvas
    mesh.baseMargin = 0
    mesh._calculateMesh()

    assert len(mesh.meshes[base_index(two_color_canvas)]) >= 1


def test_base_plate_margin_extends_past_the_canvas_edge():
    img = np.zeros((3, 3, 3), dtype=np.uint8)
    img[:] = (30, 30, 200)
    canvas = Canvas(img, scale=1)
    canvas.layers[:] = -1
    canvas.layers[1, 1] = 3

    withoutMargin = Mesh()
    withoutMargin.canvas = canvas
    withoutMargin.baseMargin = 0
    withoutMargin._calculateMesh()

    withMargin = Mesh()
    withMargin.canvas = canvas
    withMargin.baseMargin = 2
    withMargin._calculateMesh()

    def base_extent(mesh):
        verts = [v for comp in mesh.meshes[base_index(canvas)] for v in comp]
        return max(v.x for v in verts) - min(v.x for v in verts)

    assert base_extent(withMargin) > base_extent(withoutMargin)


def test_a_taller_pixel_bulges_against_the_base():
    # The whole point: no separate mechanism for this - a real pixel taller
    # than the base (height 1) sitting next to it goes through exactly the
    # same height-mismatch classification as two differently-colored
    # pixels of different heights always have - it just bulges.
    img = np.zeros((3, 3, 3), dtype=np.uint8)
    img[:] = (30, 30, 200)
    canvas = Canvas(img, scale=1)
    canvas.layers[:] = -1
    canvas.layers[1, 1] = 3

    mesh = Mesh()
    mesh.canvas = canvas
    mesh.baseMargin = 0
    mesh._calculateMesh()

    from utils.data.pixelComponents import BULGE_SIZE

    blueIndex = canvas.map[1, 1]
    blueVerts = mesh.meshes[blueIndex][0]
    # it's surrounded entirely by (shorter) base cells, with no same-height
    # neighbor anywhere - so the cap bulges on every side.
    assert max(v.x for v in blueVerts) == pytest.approx(2.0 + BULGE_SIZE, abs=1e-5)
    assert min(v.x for v in blueVerts) == pytest.approx(1.0 - BULGE_SIZE, abs=1e-5)
    assert max(v.z for v in blueVerts) == pytest.approx(2.0 + BULGE_SIZE, abs=1e-5)
    assert min(v.z for v in blueVerts) == pytest.approx(1.0 - BULGE_SIZE, abs=1e-5)

    baseVerts = [v for comp in mesh.meshes[base_index(canvas)] for v in comp]
    assert len(baseVerts) > 0


def test_base_cells_fuse_with_each_other_around_a_hole():
    img = np.zeros((3, 3, 3), dtype=np.uint8)
    img[:] = (30, 30, 200)
    canvas = Canvas(img, scale=1)
    canvas.layers[:] = -1
    canvas.layers[1, 1] = 3  # a single occupied pixel surrounded entirely by holes

    mesh = Mesh()
    mesh.canvas = canvas
    mesh.baseMargin = 0
    mesh._calculateMesh()

    # every other cell in the 3x3 grid is base - it should all fuse into
    # one connected ring around the occupied center, not stay as 8 separate
    # single-cell pieces
    assert len(mesh.meshes[base_index(canvas)]) == 1


@pytest.mark.skipif(not FIRE1_PATH.exists(), reason="fire1.png test asset not present")
def test_raising_a_selection_on_a_real_image_stays_watertight():
    # Regression: componentTriangles used to convert its cap/tube to a
    # triangle soup and back to a Trimesh before the final cap+tube union -
    # trimesh's vertex-welding on that *second* conversion has been
    # observed to silently break the watertightness the first conversion's
    # welding had already gotten right, for a big enough/complex enough
    # mesh (a small hand-built canvas won't reproduce this - it only shows
    # up on a large, intricate real group, which is exactly why this uses
    # the real test image rather than a synthetic one). Surfaced as
    # "Not all meshes are volumes!" the moment a raised selection's tube
    # got unioned against its cap.
    img = np.array(Image.open(FIRE1_PATH).convert("RGB"))
    canvas = Canvas(img)
    canvas.layers[:] = 1
    canvas.selection[40:50, 40:50] = True
    canvas.transformSelection(1)

    mesh = Mesh()
    mesh.canvas = canvas
    mesh._calculateMesh()

    for colorMeshes in mesh.meshes:
        for component in colorMeshes:
            verts = [(v.x, v.y, v.z) for v in component]
            faces = [[i, i + 1, i + 2] for i in range(0, len(component), 3)]
            assert trimesh.Trimesh(vertices=verts, faces=faces, process=True).is_watertight


def _totalVolume(mesh, canvas):
    vol = 0.0
    for components in mesh.meshes[:len(canvas.palette)]:
        for triangles in components:
            if not triangles:
                continue
            verts = [(v.x, v.y, v.z) for v in triangles]
            faces = [[i, i + 1, i + 2] for i in range(0, len(triangles), 3)]
            vol += abs(trimesh.Trimesh(vertices=verts, faces=faces, process=True).volume)
    return vol


def test_fast_preview_matches_the_exact_volume(two_color_canvas):
    # fastPreview (componentTrianglesFast) trades away real watertightness
    # for speed - it should still enclose the same volume as the exact path.
    two_color_canvas.layers[:] = 1

    exact = Mesh()
    exact.canvas = two_color_canvas
    exact._calculateMesh()

    fast = Mesh()
    fast.canvas = two_color_canvas
    fast.fastPreview = True
    fast._calculateMesh()

    assert total_real_triangles(fast, two_color_canvas) > 0
    assert _totalVolume(fast, two_color_canvas) == pytest.approx(_totalVolume(exact, two_color_canvas), abs=1e-3)


def test_toggling_fast_preview_forces_a_recompute_even_with_nothing_else_changed(two_color_canvas):
    two_color_canvas.layers[:] = 1
    mesh = Mesh()
    mesh.canvas = two_color_canvas
    mesh._calculateMesh()
    assert mesh.fastPreviewCache is False

    mesh.fastPreview = True
    mesh._calculateMesh()

    # If _checkForUpdate missed the flag flip, _calculateMesh would have
    # no-op'd and left fastPreviewCache at its old value.
    assert mesh.fastPreviewCache is True
