import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QTest

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
    # rebuildMesh() debounces its actual worker start (see
    # ProjectController.MESH_DEBOUNCE_MS) so a burst of edits doesn't
    # stutter the UI - tests care about "each edit produced a mesh", not
    # that debouncing, so this restores the old fire-on-the-next-event-loop
    # -pass behavior waitForMeshWorker below already expects.
    c._meshDebounceTimer.setInterval(0)
    yield c
    c._meshDebounceTimer.stop()
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


def waitForMeshWorker(controller, timeoutMs=5000, maxRounds=50):
    """Block until `controller`'s in-flight mesh recompute (if any) has
    finished and its meshReady signal has actually been delivered. Needed
    anywhere a test triggers a mesh-affecting edit and then checks
    meshReady/project.mesh - see ProjectController.rebuildMesh.

    rebuildMesh() debounces the actual worker start via a QTimer (zeroed
    out on the `controller` fixture above, but still real on a
    `debounced_controller` - see test_projectController.py). A bare
    processEvents() only dispatches events that are *already* due, so
    while a request is still pending and no worker has started yet, this
    uses qWait() instead to actually let wall-clock time pass until the
    timer fires, rather than spinning maxRounds instantly and giving up
    before it ever does."""
    for _ in range(maxRounds):
        if controller._meshWorker is None and controller._pendingMeshRequest is None:
            return
        if controller._meshWorker is not None:
            controller._meshWorker.wait(timeoutMs)
            QCoreApplication.processEvents()
        else:
            QTest.qWait(10)
    raise TimeoutError("Mesh worker did not finish in time")
