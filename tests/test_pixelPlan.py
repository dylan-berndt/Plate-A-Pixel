import numpy as np

from utils.data.canvas import Canvas
from utils.data.pixelPlan import Face, PixelPlanner


def make_canvas():
    img = np.zeros((4, 8, 3), dtype=np.uint8)
    img[:, :4] = (30, 30, 200)
    img[:, 4:] = (200, 30, 30)
    canvas = Canvas(img, scale=1)
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
    assert Face.EAST not in plan.bulged  # fused sides merge into one continuous surface, no wall to bulge


def test_plan_classifies_clear_side_as_bulged():
    canvas = make_canvas()
    canvas.layers[0, 0] = 3

    plan = PixelPlanner(canvas).plan(0, 0)

    # off-canvas to the north and west, unplaced neighbor to east and south
    assert plan.bulged == {Face.NORTH, Face.WEST, Face.EAST, Face.SOUTH}


def test_plan_classifies_a_height_difference_as_bulged():
    canvas = make_canvas()
    canvas.layers[0, 1] = 4  # blue, taller
    canvas.layers[0, 2] = 2  # red, shorter, directly east of blue

    planner = PixelPlanner(canvas)
    blue = planner.plan(0, 1)
    red = planner.plan(0, 2)

    # No interlock mechanism - a height mismatch is just a clear side, so
    # each pixel draws its own independent wall, same as an empty neighbor.
    assert Face.EAST in blue.bulged
    assert Face.EAST not in blue.fused
    assert Face.WEST in red.bulged
    assert Face.WEST not in red.fused


def test_plan_same_height_different_color_is_a_plain_wall():
    canvas = make_canvas()
    canvas.layers[0, 3] = 3  # blue
    canvas.layers[0, 4] = 3  # red, same height, different color, adjacent

    planner = PixelPlanner(canvas)
    blue = planner.plan(0, 3)

    assert Face.EAST not in blue.fused
    assert Face.EAST in blue.plainWalls
    assert Face.EAST not in blue.bulged  # must stay flush against the matching neighbor


def test_plain_walls_excludes_fused_side():
    canvas = make_canvas()
    canvas.layers[0, 0] = 3
    canvas.layers[0, 1] = 3  # fused, per test_plan_classifies_fused_side

    plan = PixelPlanner(canvas).plan(0, 0)

    assert Face.EAST not in plan.plainWalls


def test_plain_walls_excludes_a_height_mismatch_side():
    canvas = make_canvas()
    canvas.layers[0, 1] = 4  # blue, taller
    canvas.layers[0, 2] = 2  # red, shorter

    blue = PixelPlanner(canvas).plan(0, 1)

    assert Face.EAST not in blue.plainWalls


def test_plain_walls_excludes_a_bulged_side():
    canvas = make_canvas()
    canvas.layers[0, 0] = 3  # every side is either off-canvas or unplaced -> all bulged

    plan = PixelPlanner(canvas).plan(0, 0)

    assert plan.plainWalls == set()


def test_bulge_fires_on_every_side_without_a_same_height_neighbor():
    # The general rule: a side bulges unless a same-height neighbor sits
    # right against it there - a same-color same-height neighbor fuses
    # (no separate wall to bulge), a different-color same-height neighbor
    # is a plain wall (must stay flush against it); every other case -
    # empty, or a height mismatch - bulges.
    canvas = make_canvas()
    canvas.layers[0, 0] = 3               # this pixel
    canvas.layers[0, 1] = 3               # east: same color, same height -> fused
    canvas.layers[1, 0] = 3               # south: same height...
    canvas.map[1, 0] = canvas.map[0, 4]   # ...but a different color -> plain wall

    plan = PixelPlanner(canvas).plan(0, 0)

    assert Face.EAST in plan.fused
    assert Face.EAST not in plan.bulged                 # fused: no bulge
    assert Face.SOUTH in plan.plainWalls
    assert Face.SOUTH not in plan.bulged                # plain wall: no bulge
    assert Face.WEST in plan.bulged                      # off-canvas: bulge
    assert Face.NORTH in plan.bulged                     # off-canvas: bulge


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
