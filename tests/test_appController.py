import pytest
from PIL import Image

from utils.controllers.appController import AppController
from utils.controllers.projectController import ProjectController
from .fixtures import make_pixel_art


@pytest.fixture
def imagePath(tmp_path):
    path = tmp_path / "sprite.png"
    Image.fromarray(make_pixel_art()).save(path)
    return str(path)


@pytest.fixture
def app():
    return AppController()


def _spy(signal):
    calls = []
    signal.connect(lambda *args: calls.append(args))
    return calls


def test_new_project_from_image_becomes_the_active_controller(app, imagePath):
    opened = _spy(app.projectOpened)
    activeChanged = _spy(app.activeProjectChanged)

    controller = app.newProjectFromImage(imagePath)

    assert isinstance(controller, ProjectController)
    assert app.activeController is controller
    assert app.projectControllers == [controller]
    assert opened == [(controller,)]
    assert activeChanged == [(controller,)]


def test_open_project_round_trips_a_saved_file(app, imagePath, tmp_path):
    original = app.newProjectFromImage(imagePath, name="Original")
    savePath = tmp_path / "test.pap"
    original.project.save(str(savePath))

    reopened = app.openProject(str(savePath))

    assert app.activeController is reopened
    assert reopened.project.name == "Original"
    assert len(app.projectControllers) == 2


def test_set_active_project_switches_the_active_controller(app, imagePath):
    first = app.newProjectFromImage(imagePath, name="First")
    second = app.newProjectFromImage(imagePath, name="Second")
    assert app.activeController is second

    app.setActiveProject(0)

    assert app.activeController is first


def test_set_active_project_rejects_an_out_of_range_index(app, imagePath):
    app.newProjectFromImage(imagePath)

    with pytest.raises(IndexError):
        app.setActiveProject(5)


def test_closing_the_active_project_falls_back_to_the_previous_one(app, imagePath):
    first = app.newProjectFromImage(imagePath, name="First")
    second = app.newProjectFromImage(imagePath, name="Second")
    closed = _spy(app.projectClosed)

    app.closeProject(1)

    assert app.activeController is first
    assert closed == [(second,)]
    assert app.projectControllers == [first]


def test_closing_the_last_project_leaves_no_active_project(app, imagePath):
    app.newProjectFromImage(imagePath)

    app.closeProject(0)

    assert app.activeController is None
    assert app.projectControllers == []


def test_closing_an_inactive_project_keeps_the_active_one_and_reindexes(app, imagePath):
    first = app.newProjectFromImage(imagePath, name="First")
    second = app.newProjectFromImage(imagePath, name="Second")
    app.setActiveProject(0)  # first is active, second sits at index 1

    app.closeProject(1)

    assert app.activeController is first
    assert app.projectControllers == [first]


def test_save_active_project_with_no_projects_raises(app, tmp_path):
    with pytest.raises(RuntimeError):
        app.saveActiveProject(str(tmp_path / "out.pap"))


def test_save_active_project_writes_the_active_project(app, imagePath, tmp_path):
    app.newProjectFromImage(imagePath)
    savePath = tmp_path / "out.pap"

    app.saveActiveProject(str(savePath))

    assert savePath.exists()


def test_save_active_project_with_no_path_reuses_the_last_saved_path(app, imagePath, tmp_path):
    app.newProjectFromImage(imagePath)
    savePath = tmp_path / "out.pap"
    app.saveActiveProject(str(savePath))

    app.activeController.canvasController.recolorColor(0, (1, 2, 3))
    app.saveActiveProject()  # plain "Save" - no path given

    assert app.activeController.isDirty is False


def test_save_active_project_with_no_path_and_never_saved_raises(app, imagePath):
    app.newProjectFromImage(imagePath)

    with pytest.raises(ValueError):
        app.saveActiveProject()
