import numpy as np
from .canvas import *
from .pixelPlan import Face, PixelPlanner
from .pixelComponents import Pixel, elbowWallExtensions, bulgeSeamPatch
from .meshRepair import repairTJunctions

# The four ways a pixel can be fused to two perpendicular neighbors at
# once - each pairing identifies one "elbow": the pixel itself, plus the
# neighbor toward f1 and the neighbor toward f2, which aren't fused to
# each other at all.
_ELBOW_PAIRS = [
    (Face.NORTH, Face.EAST), (Face.NORTH, Face.WEST),
    (Face.SOUTH, Face.EAST), (Face.SOUTH, Face.WEST),
]

BASE_HEIGHT = 1


class _GridView:
    """The bare minimum PixelPlanner needs (.map, .layers, .positionValid)
    to run over a plain array instead of an actual Canvas - lets the base
    plate reuse PixelPlanner/Pixel completely unchanged (see
    Mesh._calculateMesh) instead of needing its own classification path."""

    def __init__(self, map_, layers):
        self.map = map_
        self.layers = layers

    def positionValid(self, position):
        y, x = position
        rows, cols = self.map.shape
        return 0 <= y < rows and 0 <= x < cols


class Mesh:
    """Turns a Canvas's height field into one printable solid per color.
    Reading this top-to-bottom: PixelPlanner classifies the grid (pixelPlan.py),
    Pixel assembles a plan into Cap/Tube/Notch/Inlet/Collar geometry
    (pixelComponents.py), and everything below just wires those together -
    grouping pixels into physically connected pieces per color, and
    collecting warnings from each pixel along the way."""

    def __init__(self):
        self.canvas: Canvas = None

        self.hollow = False
        # How many grid cells the base plate extends past the canvas's own
        # row/column extent on every side - 0 still fills every hole
        # inside the canvas, just without a border past its edge.
        self.baseMargin = 0

        self.mapCache: np.array = None
        self.layerCache: np.array = None
        self.hollowCache = self.hollow
        self.baseMarginCache = self.baseMargin

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
        return mapChanged or layersChanged or hollowChanged or baseMarginChanged

    def _calculateMesh(self):
        if not self._checkForUpdate():
            return

        self.mapCache = self.canvas.map.copy()
        self.layerCache = self.canvas.layers.copy()
        self.hollowCache = self.hollow
        self.baseMarginCache = self.baseMargin
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
        # PixelPlanner/Pixel pipeline as everything else. A real pixel
        # taller than it gets a completely ordinary notch into it, and the
        # base cells fuse with each other exactly like any same-color
        # same-height neighbors always do.
        emptyMask = gridLayers < 1
        gridMap[emptyMask] = baseColor
        gridLayers[emptyMask] = BASE_HEIGHT

        planner = PixelPlanner(_GridView(gridMap, gridLayers))

        pixels = {}
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
                pixels[(y, x)] = Pixel(plan, self.hollow)
                parent[(y, x)] = (y, x)

        extraTriangles = {}
        for (y, x), pixel in pixels.items():
            for face in Face:
                if face in pixel.plan.fused:
                    union((y, x), face.neighbor(y, x))
            for neighbor, connected in planner.diagonalConnections(y, x):
                if connected:
                    union((y, x), neighbor)

            for face in Face:
                if face not in pixel.plan.fused:
                    continue
                neighborPixel = pixels.get(face.neighbor(y, x))
                if neighborPixel is None:
                    continue
                patch = bulgeSeamPatch(pixel, neighborPixel, face)
                if patch:
                    extraTriangles.setdefault((y, x), []).extend(patch)

            if not pixel.tube:
                continue
            for f1, f2 in _ELBOW_PAIRS:
                if f1 not in pixel.plan.fused or f2 not in pixel.plan.fused:
                    continue
                P = pixels.get(f1.neighbor(y, x))
                Q = pixels.get(f2.neighbor(y, x))
                if P is None or Q is None or not P.tube or not Q.tube:
                    continue
                fill = elbowWallExtensions(P, Q, f1, f2)
                if fill:
                    extraTriangles.setdefault((y, x), []).extend(fill)

        components = {}
        componentPixelCount = {}
        for pos, pixel in pixels.items():
            key = (pixel.plan.color, find(pos))
            components.setdefault(key, []).extend(pixel.triangles())
            components[key].extend(extraTriangles.get(pos, []))
            componentPixelCount[key] = componentPixelCount.get(key, 0) + 1
            self.warnings.extend(pixel.warnings())

        colorCount = len(self.canvas.palette) + 1  # +1 for the base color
        meshes = [[] for _ in range(colorCount)]
        perColorRoots = {}
        for (color, root), tris in components.items():
            # Independently-built neighboring pieces (a fused pair with
            # different bulge extents along their seam, say) can fully
            # cover the same area without triangulating it the same way -
            # closing those seams edge-for-edge here is what a strict
            # manifold check (and most slicers) actually require, not
            # just visual coverage.
            meshes[color].append(repairTJunctions(tris))
            perColorRoots.setdefault(color, []).append(root)

        for color, roots in perColorRoots.items():
            if len(roots) > 1:
                self.warnings.append(f"Color {color} produced {len(roots)} disconnected parts.")

        for (color, root), count in componentPixelCount.items():
            if count == 1:
                self.warnings.append(f"Isolated single-pixel part for color {color}.")

        self.meshes = meshes
