from enum import Enum
from dataclasses import dataclass, field

import numpy as np

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

    @property
    def opposite(self):
        return _OPPOSITE_FACE[self]


_OPPOSITE_FACE = {
    Face.EAST: Face.WEST, Face.WEST: Face.EAST,
    Face.SOUTH: Face.NORTH, Face.NORTH: Face.SOUTH,
}


@dataclass
class PixelPlan:
    """What a single occupied grid cell needs, in grid/height terms only -
    no coordinates or geometry. This is the direct, testable output of
    looking at the canvas: which sides fuse into a neighbor, and which are
    clear (a different height counts as clear too - pieces interlock by
    hand, not by geometry, so a height mismatch gets its own independent
    wall rather than any special treatment)."""

    y: int
    x: int
    color: int
    height: int
    fused: set = field(default_factory=set)
    bulged: set = field(default_factory=set)

    @property
    def position(self):
        return self.y, self.x

    @property
    def plainWalls(self):
        """Sides with a same-height, differently-colored neighbor: no fuse,
        no bulge - just a flat wall, with nothing needing clearance from
        its neighbor's identical flat wall."""
        return set(Face) - self.fused - self.bulged

    @property
    def flushTubeSides(self):
        """Sides where this pixel's tube should sit flush against the grid
        boundary instead of inset: fused sides (so the two tubes' solids
        actually meet and merge, not just have their shared wall omitted
        with a gap still standing between them) and plain-wall sides (so
        two separate pieces' tubes touch instead of standing apart)."""
        return self.fused | self.plainWalls


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
            elif nHeight != result.height:
                result.bulged.add(face)
            # Same height, different color: a plain wall - stays flush
            # against the matching neighbor, no bulge.

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


_ALL_FACES = list(Face)
_FACE_BITS = {face: 1 << i for i, face in enumerate(_ALL_FACES)}


def _shifted(arr, dy, dx, pad):
    """`arr` as seen from grid offset (dy, dx): cells that would fall off
    the edge read as `pad` - the same "out of bounds counts as empty"
    convention as PixelPlanner.isEmpty, but computed for the whole grid at
    once instead of one positionValid() call per cell."""
    rows, cols = arr.shape
    padded = np.pad(arr, 1, mode='constant', constant_values=pad)
    return padded[1 + dy:1 + dy + rows, 1 + dx:1 + dx + cols]


def _codeToFaceSets():
    """One frozenset per possible 4-bit fused/bulged combination, shared
    across every cell with that combination (nothing mutates a PixelPlan's
    fused/bulged after planGrid builds it) - 16 set objects total, not
    one per cell."""
    return [
        frozenset(face for face in _ALL_FACES if code & _FACE_BITS[face])
        for code in range(1 << len(_ALL_FACES))
    ]


_FUSED_SETS = _codeToFaceSets()
_BULGED_SETS = _codeToFaceSets()


def planGrid(map_, layers):
    """Vectorized equivalent of calling PixelPlanner.plan(y, x) for every
    cell in the grid - same classification, computed with whole-grid numpy
    ops instead of one Python call (and Face-enum iteration) per cell.
    PixelPlanner.plan stays the reference implementation the unit tests
    exercise directly; Mesh._calculateMesh uses this one since the
    per-cell path's overhead dominates runtime on real images. Returns
    {(y, x): PixelPlan} for every occupied cell."""
    layers = np.asarray(layers)
    map_ = np.asarray(map_)
    occupied = layers >= 1

    fusedCode = np.zeros(layers.shape, dtype=np.uint8)
    bulgedCode = np.zeros(layers.shape, dtype=np.uint8)
    for face in _ALL_FACES:
        nHeight = _shifted(layers, face.dy, face.dx, -1)
        nColor = _shifted(map_, face.dy, face.dx, 0)
        nEmpty = nHeight < 1
        fusedFace = (~nEmpty) & (nColor == map_) & (nHeight == layers)
        bulgedFace = nEmpty | ((~nEmpty) & (nHeight != layers))
        bit = _FACE_BITS[face]
        fusedCode |= np.where(fusedFace, bit, 0).astype(np.uint8)
        bulgedCode |= np.where(bulgedFace, bit, 0).astype(np.uint8)

    ys, xs = np.nonzero(occupied)
    heights = layers[ys, xs]
    colors = map_[ys, xs]
    fCodes = fusedCode[ys, xs]
    bCodes = bulgedCode[ys, xs]

    plans = {}
    for y, x, color, height, fCode, bCode in zip(
        ys.tolist(), xs.tolist(), colors.tolist(), heights.tolist(), fCodes.tolist(), bCodes.tolist()
    ):
        plans[(y, x)] = PixelPlan(
            y=y, x=x, color=int(color), height=int(height),
            fused=_FUSED_SETS[fCode], bulged=_BULGED_SETS[bCode],
        )
    return plans


def fusedPairs(map_, layers):
    """Vectorized: every fused adjacency edge in the grid, each visited
    once - EAST and SOUTH alone are enough since fused is symmetric (a
    cell's EAST-fused neighbor has that same edge as its own WEST-fused
    side). Feeds Mesh._calculateMesh's union-find directly."""
    layers = np.asarray(layers)
    map_ = np.asarray(map_)
    occupied = layers >= 1
    pairs = []
    for face in (Face.EAST, Face.SOUTH):
        nHeight = _shifted(layers, face.dy, face.dx, -1)
        nColor = _shifted(map_, face.dy, face.dx, 0)
        nEmpty = nHeight < 1
        fused = occupied & (~nEmpty) & (nColor == map_) & (nHeight == layers)
        ys, xs = np.nonzero(fused)
        for y, x in zip(ys.tolist(), xs.tolist()):
            pairs.append(((y, x), (y + face.dy, x + face.dx)))
    return pairs


def diagonalPairs(map_, layers):
    """Vectorized equivalent of PixelPlanner.diagonalConnections for every
    occupied cell, keeping only the connected (SE, NE) pairs. Returns a
    flat list of ((y, x), (ny, nx)) pairs to union."""
    layers = np.asarray(layers)
    map_ = np.asarray(map_)
    occupied = layers >= 1
    pairs = []
    for dy, flankDy in ((1, 1), (-1, -1)):
        nHeight = _shifted(layers, dy, 1, -1)
        nColor = _shifted(map_, dy, 1, 0)
        nOccupied = nHeight >= 1
        sameColorHeight = nOccupied & (nColor == map_) & (nHeight == layers)
        eastEmpty = _shifted(layers, 0, 1, -1) < 1
        flankEmpty = _shifted(layers, flankDy, 0, -1) < 1
        connected = occupied & sameColorHeight & eastEmpty & flankEmpty
        ys, xs = np.nonzero(connected)
        for y, x in zip(ys.tolist(), xs.tolist()):
            pairs.append(((y, x), (y + dy, x + 1)))
    return pairs
