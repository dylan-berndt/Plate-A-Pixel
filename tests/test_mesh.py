import numpy as np
import pytest

from utils.data.canvas import Canvas
from utils.data.mesh import Mesh


def make_two_color_canvas():
    """A 2-logical-column canvas: blue on the left, red on the right,
    heights left at -1 (empty) so each test sets exactly what it needs."""
    img = np.zeros((4, 8, 3), dtype=np.uint8)
    img[:, :4] = (30, 30, 200)
    img[:, 4:] = (200, 30, 30)
    canvas = Canvas(img)
    canvas.layers[:] = -1
    return canvas


@pytest.fixture
def two_color_canvas():
    return make_two_color_canvas()


def total_triangles(mesh):
    return sum(len(component) for components in mesh.meshes for component in components) // 3


def test_empty_canvas_produces_no_geometry(two_color_canvas):
    mesh = Mesh()
    mesh.canvas = two_color_canvas
    mesh._calculateMesh()

    assert total_triangles(mesh) == 0
    assert mesh.warnings == []


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
    # blue (taller, height 4) directly left of red (shorter, height 2) -
    # the notch/inlet case. They must interlock geometrically but still
    # come out as two separate solids, one per color.
    two_color_canvas.layers[0, 1] = 4  # blue
    two_color_canvas.layers[0, 2] = 2  # red

    mesh = Mesh()
    mesh.canvas = two_color_canvas
    mesh._calculateMesh()

    blueIndex = two_color_canvas.map[0, 1]
    redIndex = two_color_canvas.map[0, 2]
    assert len(mesh.meshes[blueIndex]) == 1
    assert len(mesh.meshes[redIndex]) == 1
    assert total_triangles(mesh) > 0

    # blue's notch should poke past the shared boundary (x=2) into red's cell
    blueVerts = mesh.meshes[blueIndex][0]
    assert max(v.x for v in blueVerts) > 2.0
    # red stays within its own cell; the inlet is a recess, not a hole through it
    redVerts = mesh.meshes[redIndex][0]
    assert min(v.x for v in redVerts) >= 2.0


def test_diagonal_same_height_pixels_bulge_into_one_component(two_color_canvas):
    two_color_canvas.layers[0, 0] = 3
    two_color_canvas.layers[1, 1] = 3  # diagonal from (0, 0), same color/height

    mesh = Mesh()
    mesh.canvas = two_color_canvas
    mesh._calculateMesh()

    blueIndex = two_color_canvas.map[0, 0]
    assert len(mesh.meshes[blueIndex]) == 1


def test_fully_packed_checkerboard_has_no_bulge_connectivity():
    # A 2x2 checkerboard where every side of every pixel has *some* pixel
    # next to it (just possibly a different color) - bulging only ever
    # happens on a genuinely clear side, so nothing bulges here and neither
    # diagonal pair connects. (A dedicated notch-based connector for this
    # case, keyed off palette order per the corrected spec, isn't
    # implemented yet - see the write-up.)
    img = np.zeros((2, 2, 3), dtype=np.uint8)
    img[0, 0] = (30, 30, 200)
    img[1, 1] = (30, 30, 200)
    img[0, 1] = (200, 30, 30)
    img[1, 0] = (200, 30, 30)
    canvas = Canvas(img)
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


def test_base_plate_fills_the_canvas_footprint_with_zero_margin(two_color_canvas):
    two_color_canvas.layers[0, 0] = 3

    mesh = Mesh()
    mesh.canvas = two_color_canvas
    mesh.baseMargin = 0
    mesh._calculateMesh()

    assert len(mesh.baseMesh) == 1
    verts = mesh.baseMesh[0]
    assert len(verts) > 0
    rows, cols = two_color_canvas.map.shape
    assert min(v.x for v in verts) >= -0.2  # a small bulge past 0 at the outer edge, nothing further
    assert max(v.x for v in verts) <= cols + 0.2
    assert min(v.z for v in verts) >= -0.2
    assert max(v.z for v in verts) <= rows + 0.2


def test_base_plate_margin_extends_the_footprint(two_color_canvas):
    two_color_canvas.layers[0, 0] = 3

    mesh = Mesh()
    mesh.canvas = two_color_canvas
    mesh.baseMargin = 2
    mesh._calculateMesh()

    verts = mesh.baseMesh[0]
    rows, cols = two_color_canvas.map.shape
    assert min(v.x for v in verts) < -1.0   # reaches out past the canvas edge by the margin
    assert max(v.x for v in verts) > cols + 1.0


def test_base_plate_carries_a_socket_under_every_occupied_pixel():
    from utils.data.pixelComponents import BASE_PEG_DEPTH

    canvas = make_two_color_canvas()
    canvas.layers[0, 0] = 3
    canvas.layers[0, 1] = 3

    mesh = Mesh()
    mesh.canvas = canvas
    mesh._calculateMesh()

    verts = mesh.baseMesh[0]
    # the socket recess floor sits at this specific shallow negative y -
    # the base cell's own (much lower) cap bottom doesn't reach that high
    assert any(v.y == -BASE_PEG_DEPTH for v in verts)


def test_base_plate_has_no_socket_when_canvas_is_entirely_empty(two_color_canvas):
    from utils.data.pixelComponents import BASE_PEG_DEPTH

    mesh = Mesh()
    mesh.canvas = two_color_canvas
    mesh._calculateMesh()

    verts = mesh.baseMesh[0]
    assert len(verts) > 0                                 # the plate itself still exists
    assert not any(v.y == -BASE_PEG_DEPTH for v in verts)  # but nothing carved a socket into it


def test_real_pixels_get_a_base_peg_reaching_below_y0(two_color_canvas):
    two_color_canvas.layers[0, 0] = 3

    mesh = Mesh()
    mesh.canvas = two_color_canvas
    mesh._calculateMesh()

    blueIndex = two_color_canvas.map[0, 0]
    verts = mesh.meshes[blueIndex][0]
    assert any(v.y < 0.0 for v in verts)


def test_thin_connector_is_flagged(two_color_canvas):
    # A large height gap between two adjacent, differently colored pixels
    # produces a tall, narrow connector - worth a soft warning, not a hard
    # error, since it's a printability concern rather than an invalid shape.
    two_color_canvas.layers[0, 1] = 20
    two_color_canvas.layers[0, 2] = 1

    mesh = Mesh()
    mesh.canvas = two_color_canvas
    mesh._calculateMesh()

    assert any("Thin connector" in w for w in mesh.warnings)
