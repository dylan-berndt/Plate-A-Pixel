import numpy as np
import pytest
from PIL import Image

from utils.data.canvas import Canvas
from utils.data.project import Project, ViewSettings
from .fixtures import make_pixel_art


@pytest.fixture
def project():
    canvas = Canvas(make_pixel_art())
    canvas.layers[:] = -1
    canvas.layers[0, 0] = 3
    canvas.layers[0, 1] = 3
    canvas.palette.rename(canvas.palette.indexOf((220, 40, 40)), "Red")
    viewSettings = ViewSettings(hollow=True, baseMargin=2, cellWidth=8.0, cellHeight=2.5)
    return Project(canvas, viewSettings=viewSettings, name="Test Project")


def test_from_image_path_names_the_project_after_the_file(tmp_path):
    path = tmp_path / "my_sprite.png"
    Image.fromarray(make_pixel_art()).save(path)

    project = Project.fromImagePath(str(path))

    assert project.name == "my_sprite"
    assert len(project.canvas.palette) == 3


def test_from_image_path_name_is_overridable(tmp_path):
    path = tmp_path / "my_sprite.png"
    Image.fromarray(make_pixel_art()).save(path)

    project = Project.fromImagePath(str(path), name="Custom Name")

    assert project.name == "Custom Name"


def test_rebuild_mesh_produces_a_mesh_for_every_palette_color_plus_base(project):
    mesh = project.rebuildMesh()

    assert len(mesh.meshes) == len(project.canvas.palette) + 1


def test_rebuild_mesh_forces_the_exact_generator_even_after_a_fast_preview_mesh_was_swapped_in(project):
    # Simulates what ProjectController._onMeshComputed does after a live
    # background worker finishes: project.mesh gets replaced by one built
    # with fastPreview on. Export (rebuildMesh) must never hand that mesh
    # to exportObjs as-is - it has to force a fresh, exact recompute.
    import trimesh

    project.mesh.fastPreview = True
    project.mesh._calculateMesh()
    assert project.mesh.fastPreview is True

    project.rebuildMesh()

    assert project.mesh.fastPreview is False
    for colorMeshes in project.mesh.meshes:
        for component in colorMeshes:
            if len(component) == 0:
                continue
            faces = [[i, i + 1, i + 2] for i in range(0, len(component), 3)]
            assert trimesh.Trimesh(vertices=component, faces=faces, process=True).is_watertight


def test_save_load_round_trip_preserves_image_layers_and_palette(tmp_path, project):
    path = tmp_path / "test.pap"
    project.save(str(path))

    restored = Project.load(str(path))

    # save() renames the project to match the saved filename (see its own
    # docstring) - "Test Project" was this fixture's pre-save name, not
    # what either `project` or `restored` should show afterward.
    assert project.name == "test"
    assert restored.name == "test"
    assert np.array_equal(restored.canvas.image, project.canvas.image)
    assert np.array_equal(restored.canvas.layers, project.canvas.layers)
    assert np.array_equal(restored.canvas.map, project.canvas.map)
    assert len(restored.canvas.palette) == len(project.canvas.palette)
    for original, loaded in zip(project.canvas.palette, restored.canvas.palette):
        assert original.name == loaded.name
        assert original.color == loaded.color


def test_save_load_round_trip_preserves_view_settings(tmp_path, project):
    path = tmp_path / "test.pap"
    project.save(str(path))

    restored = Project.load(str(path))

    assert restored.viewSettings == project.viewSettings


def test_save_load_round_trip_reconstructs_an_equivalent_mesh(tmp_path, project):
    path = tmp_path / "test.pap"
    project.save(str(path))
    originalMesh = project.rebuildMesh()

    restored = Project.load(str(path))
    restoredMesh = restored.rebuildMesh()

    originalTriangleCount = sum(len(c) for components in originalMesh.meshes for c in components)
    restoredTriangleCount = sum(len(c) for components in restoredMesh.meshes for c in components)
    assert restoredTriangleCount == originalTriangleCount


def test_loaded_project_selection_starts_clean_even_if_original_had_one(tmp_path, project):
    project.canvas.bucketSelect((0, 0))
    assert project.canvas.selection.sum() > 0

    path = tmp_path / "test.pap"
    project.save(str(path))
    restored = Project.load(str(path))

    assert restored.canvas.selection.sum() == 0


def test_export_objs_uses_cell_width_and_height_as_independent_axis_scales(tmp_path, project):
    paths = project.exportObjs(str(tmp_path))

    assert len(paths) > 0
    content = open(paths[0]).read()
    assert f"{project.viewSettings.cellWidth}" in content
    assert f"{project.viewSettings.cellHeight}" in content


def test_new_project_has_no_file_path(project):
    assert project.filePath is None


def test_save_records_the_file_path(tmp_path, project):
    path = str(tmp_path / "test.pap")

    project.save(path)

    assert project.filePath == path


def test_load_records_the_file_path(tmp_path, project):
    path = str(tmp_path / "test.pap")
    project.save(path)

    restored = Project.load(path)

    assert restored.filePath == path
