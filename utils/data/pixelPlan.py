from enum import Enum
from dataclasses import dataclass, field
from .canvas import *


class Face(Enum):
    """One of a pixel's four orthogonal sides. Carries enough about the grid
    (which neighbor it points at) and the local axis (which world axis is
    fixed for that side, and which direction is "outward") that geometry
    code never has to re-derive it from a string key."""

    EAST = ('E', 0, 1, +1)
    WEST = ('W', 0, -1, -1)
    SOUTH = ('S', 1, 0, +1)
    NORTH = ('N', -1, 0, -1)

    def __init__(self, label, dy, dx, sign):
        self.label = label
        self.dy = dy
        self.dx = dx
        self.sign = sign

    @property
    def axis(self):
        """Which world axis is fixed for this face: 'x' for E/W, 'z' for S/N."""
        return 'x' if self.dx != 0 else 'z'

    @property
    def boxKey(self):
        """This face's key in the '+x'/'-x'/'+z'/'-z' scheme _box() uses."""
        return ('+' if self.sign > 0 else '-') + self.axis

    def neighbor(self, y, x):
        return y + self.dy, x + self.dx

    def offset(self, value, amount):
        """`value` shifted `amount` further outward along this face's
        normal (a negative amount shifts inward instead)."""
        return value + self.sign * amount


@dataclass
class PixelPlan:
    """What a single occupied grid cell needs, in grid/height terms only -
    no coordinates or geometry. This is the direct, testable output of
    looking at the canvas: which sides fuse into a neighbor, which are
    clear (and so flare into a bulge), which face a taller neighbor (and
    need an inlet), and which face a shorter one (and own a notch)."""

    y: int
    x: int
    color: int
    height: int
    fused: set = field(default_factory=set)
    bulged: set = field(default_factory=set)
    notches: dict = field(default_factory=dict)   # Face -> neighbor height (this pixel is taller)
    inlets: dict = field(default_factory=dict)     # Face -> neighbor height (this pixel is shorter)

    @property
    def position(self):
        return self.y, self.x

    @property
    def plainWalls(self):
        """Sides with a same-height, differently-colored neighbor: no fuse,
        no bulge, no notch/inlet - just a flat wall, with nothing needing
        clearance from its neighbor's identical flat wall."""
        return set(Face) - self.fused - self.bulged - set(self.notches) - set(self.inlets)


class PixelPlanner:
    """Reads the canvas and classifies each occupied cell into a
    PixelPlan, plus the diagonal-connectivity checks used to group pixels
    into physically connected pieces. Nothing here touches a coordinate or
    a triangle - it only ever answers "what is next to what, and how"."""

    def __init__(self, canvas: Canvas):
        self.canvas = canvas

    def isEmpty(self, pos):
        return bool(not self.canvas.positionValid(pos) or self.canvas.layers[pos] < 1)

    def sameColorHeight(self, p1, p2):
        if self.isEmpty(p1) or self.isEmpty(p2):
            return False
        return bool(self.canvas.map[p1] == self.canvas.map[p2] and self.canvas.layers[p1] == self.canvas.layers[p2])

    def plan(self, y, x):
        """The PixelPlan for (y, x), or None if nothing is placed there."""
        height = self.canvas.layers[y, x]
        if height < 1:
            return None

        color = int(self.canvas.map[y, x])
        result = PixelPlan(y=y, x=x, color=color, height=int(height))

        for face in Face:
            pos = face.neighbor(y, x)
            if self.isEmpty(pos):
                result.bulged.add(face)
                continue
            nColor, nHeight = int(self.canvas.map[pos]), int(self.canvas.layers[pos])
            if nColor == color and nHeight == result.height:
                result.fused.add(face)
            elif nHeight < result.height:
                result.notches[face] = nHeight
            elif nHeight > result.height:
                result.inlets[face] = nHeight
            # Same height, different color: a plain wall - no entry needed.

        return result

    def diagonalConnections(self, y, x):
        """The two diagonal neighbor pairs (y, x) owns (SE and NE, so every
        pair in the grid is visited from exactly one side), each with
        whether they're connected. A diagonal pair is only connected when
        it's the same color and height *and* both of the orthogonal cells
        between them are empty - that's exactly when both pixels' bulges
        reach into the shared corner and physically overlap."""
        for neighbor, flank1, flank2 in (
            ((y + 1, x + 1), (y, x + 1), (y + 1, x)),
            ((y - 1, x + 1), (y, x + 1), (y - 1, x)),
        ):
            if not self.canvas.positionValid(neighbor):
                continue
            connected = (
                self.sameColorHeight((y, x), neighbor)
                and self.isEmpty(flank1)
                and self.isEmpty(flank2)
            )
            yield neighbor, connected
