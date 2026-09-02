import numpy as np
from .canvas import *
from .pixelPlan import Face, PixelPlanner
from .pixelComponents import componentTriangles, TUBE_MARGIN, WALL_THICKNESS, BULGE_SIZE

BASE_HEIGHT = 1


class _GridView:
    """The bare minimum PixelPlanner needs (.map, .layers, .positionValid)
    to run over a plain array instead of an actual Canvas - lets the base
    plate reuse PixelPlanner completely unchanged (see Mesh._calculateMesh)
    instead of needing its own classification path."""

    def __init__(self, map_, layers):
        self.map = map_
        self.layers = layers

    def positionValid(self, position):
        y, x = position
        rows, cols = self.map.shape
        return 0 <= y < rows and 0 <= x < cols


class Mesh:
    """Turns a Canvas's height field into one printable solid per color.
    Reading this top-to-bottom: PixelPlanner classifies the grid
    (pixelPlan.py) into fused/bulged/plainWalls per side, componentTriangles
    turns one connected group's plans directly into a hull (pixelComponents.py),
    and everything below just wires those together - grouping pixels into
    physically connected pieces per color and collecting warnings along
    the way."""

    def __init__(self):
        self.canvas: Canvas = None

        self.hollow = False
        # How many grid cells the base plate extends past the canvas's own
        # row/column extent on every side - 0 still fills every hole
        # inside the canvas, just without a border past its edge.
        self.baseMargin = 0
        # Structural geometry parameters passed straight through to
        # componentTriangles (see pixelComponents.py) - world-unit
        # fractions of one grid cell, not millimeters (cellWidth/cellHeight
        # only scale on export, see objExport.py). Defaults match
        # pixelComponents.py's own constants, so leaving these alone
        # reproduces the old fixed behavior exactly.
        self.tubeMargin = TUBE_MARGIN
        self.wallThickness = WALL_THICKNESS
        self.bulgeSize = BULGE_SIZE

        self.mapCache: np.array = None
        self.layerCache: np.array = None
        self.hollowCache = self.hollow
        self.baseMarginCache = self.baseMargin
        self.tubeMarginCache = self.tubeMargin
        self.wallThicknessCache = self.wallThickness
        self.bulgeSizeCache = self.bulgeSize

        # meshes[colorIndex] is a list of components - pixels of the same
        # color don't always end up physically connected (see the
        # "disconnected parts" warnings below); each component is a flat
        # list of Vector3, 3 per triangle. The base plate isn't a color in
        # canvas.palette - it's appended as one extra entry past the real
        # colors (see _calculateMesh), so it comes back as just another
        # mesh, same as any color's.
        self.meshes = []
        self.warnings = []

    def _checkForUpdate(self):
        if self.canvas is None:
            return False

        mapChanged = (
            self.mapCache is None
            or self.mapCache.shape != self.canvas.map.shape
            or not np.array_equal(self.mapCache, self.canvas.map)
        )
        layersChanged = (
            self.layerCache is None
            or self.layerCache.shape != self.canvas.layers.shape
            or not np.array_equal(self.layerCache, self.canvas.layers)
        )
        hollowChanged = self.hollow != self.hollowCache
        baseMarginChanged = self.baseMargin != self.baseMarginCache
        geometryChanged = (
            self.tubeMargin != self.tubeMarginCache
            or self.wallThickness != self.wallThicknessCache
            or self.bulgeSize != self.bulgeSizeCache
        )
        return mapChanged or layersChanged or hollowChanged or baseMarginChanged or geometryChanged

    def _calculateMesh(self):
        if not self._checkForUpdate():
            return

        self.mapCache = self.canvas.map.copy()
        self.layerCache = self.canvas.layers.copy()
        self.hollowCache = self.hollow
        self.baseMarginCache = self.baseMargin
        self.tubeMarginCache = self.tubeMargin
        self.wallThicknessCache = self.wallThickness
        self.bulgeSizeCache = self.bulgeSize
        self.warnings = []

        canvasRows, canvasCols = self.canvas.map.shape
        margin = self.baseMargin
        rows, cols = canvasRows + 2 * margin, canvasCols + 2 * margin

        # The base color: one past every real palette color, so it never
        # collides with an actual color index.
        baseColor = len(self.canvas.palette)
        gridMap = np.full((rows, cols), baseColor, dtype=self.canvas.map.dtype)
        gridLayers = np.full((rows, cols), -1, dtype=self.canvas.layers.dtype)
        gridMap[margin:margin + canvasRows, margin:margin + canvasCols] = self.canvas.map
        gridLayers[margin:margin + canvasRows, margin:margin + canvasCols] = self.canvas.layers

        # Every cell still empty at this point - a hole inside the canvas,
        # or anywhere in the margin border - becomes base material:
        # literally another color, at height 1, run through the exact same
        # PixelPlanner pipeline as everything else. A real pixel taller
        # than it gets a completely ordinary bulged wall against it, and
        # the base cells fuse with each other exactly like any same-color
        # same-height neighbors always do.
        emptyMask = gridLayers < 1
        gridMap[emptyMask] = baseColor
        gridLayers[emptyMask] = BASE_HEIGHT

        planner = PixelPlanner(_GridView(gridMap, gridLayers))

        plans = {}
        parent = {}

        def find(p):
            while parent[p] != p:
                parent[p] = parent[parent[p]]
                p = parent[p]
            return p

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for y in range(rows):
            for x in range(cols):
                plan = planner.plan(y, x)
                if plan is None:
                    continue
                plans[(y, x)] = plan
                parent[(y, x)] = (y, x)

        for (y, x), plan in plans.items():
            for face in Face:
                if face in plan.fused:
                    union((y, x), face.neighbor(y, x))
            for neighbor, connected in planner.diagonalConnections(y, x):
                if connected:
                    union((y, x), neighbor)

        groups = {}
        for pos, plan in plans.items():
            key = (plan.color, find(pos))
            groups.setdefault(key, []).append(plan)

        colorCount = len(self.canvas.palette) + 1  # +1 for the base color
        meshes = [[] for _ in range(colorCount)]
        perColorRoots = {}
        for (color, root), groupPlans in groups.items():
            meshes[color].append(componentTriangles(
                groupPlans, self.hollow,
                tubeMargin=self.tubeMargin, wallThickness=self.wallThickness, bulgeSize=self.bulgeSize,
            ))
            perColorRoots.setdefault(color, []).append(root)

        for color, roots in perColorRoots.items():
            if len(roots) > 1:
                self.warnings.append(f"Color {color} produced {len(roots)} disconnected parts.")

        for (color, root), groupPlans in groups.items():
            if len(groupPlans) == 1:
                self.warnings.append(f"Isolated single-pixel part for color {color}.")

        self.meshes = meshes
