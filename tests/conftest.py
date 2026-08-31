import pytest

from utils.data.canvas import Canvas
from .fixtures import make_pixel_art


@pytest.fixture
def pixel_art_image():
    return make_pixel_art()


@pytest.fixture
def canvas(pixel_art_image):
    return Canvas(pixel_art_image)
