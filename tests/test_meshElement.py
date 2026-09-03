import numpy as np

from utils.meshElement import _trianglesToArrays


def test_triangles_to_arrays_computes_the_flat_face_normal():
    # A single triangle in the XZ plane; cross(b-a, c-a) under the
    # right-hand rule this function uses gives -Y here.
    triangle = np.array([(0, 0, 0), (1, 0, 0), (0, 0, 1)], dtype=float)

    positions, normals = _trianglesToArrays(triangle)

    assert np.allclose(positions, triangle)
    expected = np.array([0.0, -1.0, 0.0])
    assert np.allclose(normals[0], expected)
    # flat shading: all three corners of one triangle share the same normal
    assert np.allclose(normals[1], expected)
    assert np.allclose(normals[2], expected)


def test_triangles_to_arrays_handles_a_degenerate_triangle_without_dividing_by_zero():
    # Three coincident points - a zero-area "triangle" with an undefined
    # normal direction - must come back as a zero vector, not NaN/inf.
    triangle = np.array([(1, 1, 1), (1, 1, 1), (1, 1, 1)], dtype=float)

    _, normals = _trianglesToArrays(triangle)

    assert np.all(np.isfinite(normals))
    assert np.allclose(normals, 0.0)


def test_triangles_to_arrays_matches_the_original_per_triangle_loop():
    # Regression: the original implementation called np.cross/np.linalg.norm
    # once per triangle in a Python loop - measured at ~2.2s for an 89k
    # triangle mesh, running on the GUI thread on every mesh update. This
    # checks the vectorized replacement produces identical output.
    def perTriangleLoop(triangles):
        positions = np.asarray(triangles, dtype=np.float32)
        normals = np.zeros_like(positions)
        for i in range(0, len(positions), 3):
            a, b, c = positions[i], positions[i + 1], positions[i + 2]
            n = np.cross(b - a, c - a)
            length = np.linalg.norm(n)
            if length > 1e-8:
                n = n / length
            normals[i:i + 3] = n
        return positions, normals

    rng = np.random.default_rng(0)
    triangles = rng.random((300, 3)) * 10
    triangles[3:6] = [[1, 1, 1], [1, 1, 1], [1, 1, 1]]  # one degenerate triangle mixed in

    expectedPositions, expectedNormals = perTriangleLoop(triangles)
    positions, normals = _trianglesToArrays(triangles)

    assert np.allclose(positions, expectedPositions)
    assert np.allclose(normals, expectedNormals, atol=1e-5)
