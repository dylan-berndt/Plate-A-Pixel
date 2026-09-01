import pytest
from PySide6.QtCore import QCoreApplication

from utils.data.canvas import Canvas
from utils.data.project import Project, ViewSettings
from utils.controllers.projectController import ProjectController
from .fixtures import make_pixel_art


@pytest.fixture
def pixel_art_image():
    return make_pixel_art()


@pytest.fixture
def canvas(pixel_art_image):
    return Canvas(pixel_art_image)


@pytest.fixture
def controller():
    """A ProjectController (and its canvasController) around a fresh
    pixel-art Canvas, shared by test_projectController.py and
    test_canvasController.py."""
    canvas = Canvas(make_pixel_art())
    project = Project(canvas, viewSettings=ViewSettings(hollow=False, baseMargin=0))
    c = ProjectController(project)
    yield c
    if c._meshWorker is not None:
        c._meshWorker.wait()  # don't leave a running QThread dangling past the test


def spy(signal):
    """Collects every emission of `signal` as a list of arg-tuples."""
    calls = []
    signal.connect(lambda *args: calls.append(args))
    return calls


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    """ProjectController's mesh recompute runs on a background QThread and
    hands its result back via a queued signal - that delivery only happens
    while a Qt event loop is being pumped, which requires an application
    instance to exist. Qt allows only one per process, so this is session-
    scoped and shared by every test."""
    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


def waitForMeshWorker(controller, timeoutMs=5000, maxRounds=5):
    """Block until `controller`'s in-flight mesh recompute (if any) has
    finished and its meshReady signal has actually been delivered. Needed
    anywhere a test triggers a mesh-affecting edit and then checks
    meshReady/project.mesh - see ProjectController._rebuildMesh."""
    for _ in range(maxRounds):
        worker = controller._meshWorker
        if worker is None:
            return
        worker.wait(timeoutMs)
        QCoreApplication.processEvents()
    raise TimeoutError("Mesh worker did not finish in time")
