import pytest

from utils.data.canvas import Canvas
from utils.data.project import Project
from utils.controllers.projectController import ProjectController
from utils.tools.tool import Tool, FunctionalTool, ToolRegistry
from utils.tools.wandTool import WandTool
from .fixtures import make_pixel_art, RED_BLOCK, RED_ISLAND, GREEN_DIAGONAL_PAIR


@pytest.fixture
def controller():
    return ProjectController(Project(Canvas(make_pixel_art())))


def test_functional_tool_onpress_is_unimplemented_by_default():
    tool = FunctionalTool("bare", {}, {})
    with pytest.raises(NotImplementedError):
        tool.onPress(controller=None, pos=(0, 0))


def test_functional_tool_ondrag_and_onrelease_default_to_no_ops():
    tool = FunctionalTool("bare", {}, {})
    assert tool.onDrag(controller=None, pos=(0, 0)) is None
    assert tool.onRelease(controller=None, pos=(0, 0)) is None


def test_wand_tool_is_a_tool_with_its_own_default_selections():
    tool = WandTool()
    assert isinstance(tool, Tool)
    assert tool.name == "wand"
    assert tool.selections == {"mode": "replace", "contiguous": False, "diagonal": True}


def test_wand_tool_press_non_contiguous_selects_every_matching_color(controller):
    tool = WandTool()
    tool.selections["contiguous"] = False

    tool.onPress(controller, (0, 0))

    canvas = controller.project.canvas
    for pos in RED_BLOCK:
        assert canvas.selection[pos]
    assert canvas.selection[RED_ISLAND]  # non-contiguous grabs the disconnected red pixel too


def test_wand_tool_press_contiguous_stops_at_the_color_boundary(controller):
    tool = WandTool()
    tool.selections["contiguous"] = True

    tool.onPress(controller, (0, 0))

    canvas = controller.project.canvas
    for pos in RED_BLOCK:
        assert canvas.selection[pos]
    assert not canvas.selection[RED_ISLAND]


def test_wand_tool_press_respects_diagonal_option(controller):
    tool = WandTool()
    tool.selections["contiguous"] = True
    tool.selections["diagonal"] = False

    tool.onPress(controller, GREEN_DIAGONAL_PAIR[0])

    canvas = controller.project.canvas
    assert canvas.selection[GREEN_DIAGONAL_PAIR[0]]
    assert not canvas.selection[GREEN_DIAGONAL_PAIR[1]]


def test_tool_registry_defaults_to_the_first_tool():
    registry = ToolRegistry([WandTool()])
    assert registry.activeTool.name == "wand"


def test_tool_registry_set_active_tool_switches_by_name():
    wand = WandTool()
    registry = ToolRegistry([wand])

    registry.setActiveTool("wand")

    assert registry.activeTool is wand


def test_tool_registry_set_active_tool_rejects_an_unknown_name():
    registry = ToolRegistry([WandTool()])
    with pytest.raises(ValueError):
        registry.setActiveTool("nonexistent")


def test_empty_tool_registry_has_no_active_tool():
    registry = ToolRegistry([])
    assert registry.activeTool is None
