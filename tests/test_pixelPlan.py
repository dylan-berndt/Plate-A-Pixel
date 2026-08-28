import numpy as np

from utils.data.canvas import Canvas
from utils.data.pixelPlan import Face, PixelPlanner


def make_canvas():
    img = np.zeros((4, 8, 3), dtype=np.uint8)
    img[:, :4] = (30, 30, 200)
    img[:, 4:] = (200, 30, 30)
    canvas = Canvas(img)
    canvas.layers[:] = -1
    return canvas


def test_plan_is_none_for_an_empty_cell():
    canvas = make_canvas()
    planner = PixelPlanner(canvas)

    assert planner.plan(0, 1) is None


def test_plan_classifies_fused_side():
    canvas = make_canvas()
    canvas.layers[0, 0] = 3
    canvas.layers[0, 1] = 3  # both logical blue columns, same height

    plan = PixelPlanner(canvas).plan(0, 0)

    assert Face.EAST in plan.fused
    assert not plan.notches
    assert not plan.inlets


def test_plan_classifies_clear_side_as_bulged():
    canvas = make_canvas()
    canvas.layers[0, 0] = 3

    plan = PixelPlanner(canvas).plan(0, 0)

    # off-canvas to the north and west, unplaced neighbor to east and south
    assert plan.bulged == {Face.NORTH, Face.WEST, Face.EAST, Face.SOUTH}


def test_plan_classifies_notch_and_inlet_for_a_height_difference():
    canvas = make_canvas()
    canvas.layers[0, 1] = 4  # blue, taller
    canvas.layers[0, 2] = 2  # red, shorter, directly east of blue

    planner = PixelPlanner(canvas)
    blue = planner.plan(0, 1)
    red = planner.plan(0, 2)

    assert blue.notches[Face.EAST] == 2
    assert Face.EAST not in blue.inlets
    assert Face.EAST not in blue.bulged

    assert red.inlets[Face.WEST] == 4
    assert Face.WEST not in red.notches


def test_plan_same_height_different_color_is_a_plain_wall():
    canvas = make_canvas()
    canvas.layers[0, 1] = 3  # blue
    canvas.layers[0, 2] = 3  # red, same height, different color, adjacent

    planner = PixelPlanner(canvas)
    blue = planner.plan(0, 1)

    assert Face.EAST not in blue.fused
    assert Face.EAST not in blue.notches
    assert Face.EAST not in blue.inlets
    assert Face.EAST in blue.plainWalls


def test_plain_walls_excludes_fused_side():
    canvas = make_canvas()
    canvas.layers[0, 0] = 3
    canvas.layers[0, 1] = 3  # fused, per test_plan_classifies_fused_side

    plan = PixelPlanner(canvas).plan(0, 0)

    assert Face.EAST not in plan.plainWalls


def test_plain_walls_excludes_a_notch_side():
    canvas = make_canvas()
    canvas.layers[0, 1] = 4  # blue, taller
    canvas.layers[0, 2] = 2  # red, shorter - blue owns a notch on its east side

    blue = PixelPlanner(canvas).plan(0, 1)

    assert Face.EAST not in blue.plainWalls


def test_plain_walls_excludes_a_bulged_side():
    canvas = make_canvas()
    canvas.layers[0, 0] = 3  # every side is either off-canvas or unplaced -> all bulged

    plan = PixelPlanner(canvas).plan(0, 0)

    assert plan.plainWalls == set()


def test_diagonal_connection_true_when_both_flanking_cells_are_empty():
    canvas = make_canvas()
    canvas.layers[0, 0] = 3
    canvas.layers[1, 1] = 3  # diagonal, same color/height, flanks left empty

    connections = dict(PixelPlanner(canvas).diagonalConnections(0, 0))

    assert connections[(1, 1)] is True


def test_diagonal_connection_false_when_a_flanking_cell_is_occupied():
    canvas = make_canvas()
    canvas.layers[0, 0] = 3
    canvas.layers[1, 1] = 3
    canvas.layers[0, 1] = 3  # occupies one of the two flanking cells

    connections = dict(PixelPlanner(canvas).diagonalConnections(0, 0))

    assert connections[(1, 1)] is False
