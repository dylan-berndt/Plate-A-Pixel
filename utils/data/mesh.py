import numpy as np
from .canvas import *
from .pixelPlan import Face, PixelPlanner, planBaseGrid
from .pixelComponents import Pixel, elbowWallExtensions, bulgeSeamPatch, BaseSocket, BASE_PEG_WIDTH_RATIO

# The four ways a pixel can be fused to two perpendicular neighbors at
# once - each pairing identifies one "elbow": the pixel itself, plus the
# neighbor toward f1 and the neighbor toward f2, which aren't fused to
# each other at all.
_ELBOW_PAIRS = [
    (Face.NORTH, Face.EAST), (Face.NORTH, Face.WEST),
    (Face.SOUTH, Face.EAST), (Face.SOUTH, Face.WEST),
]


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
        # row/column extent on every side - 0 fits it exactly to the
        # canvas, still filling every gap between pieces.
        self.baseMargin = 0

        self.mapCache: np.array = None
        self.layerCache: np.array = None
        self.hollowCache = self.hollow
        self.baseMarginCache = self.baseMargin

        # meshes[colorIndex] is a list of components - pixels of the same
        # color don't always end up physically connected (see the
        # "disconnected parts" warnings below); each component is a flat
        # list of Vector3, 3 per triangle.
        self.meshes = []
        # The base plate is its own separate printed piece - always exactly
        # one connected component (the grid it fills is a solid rectangle
        # by construction), kept as a one-item list for the same shape as
        # meshes[colorIndex] so exportMeshObjs can treat it the same way.
        self.baseMesh = []
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

        planner = PixelPlanner(self.canvas)
        rows, cols = self.canvas.map.shape

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
                # Every occupied pixel gets a base peg, regardless of its
                # own horizontal notches - the base plate's whole purpose
                # is holding every piece together from below.
                pixels[(y, x)] = Pixel(plan, self.hollow, basePeg=True)
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

        colorCount = len(self.canvas.palette)
        meshes = [[] for _ in range(colorCount)]
        perColorRoots = {}
        for (color, root), tris in components.items():
            meshes[color].append(tris)
            perColorRoots.setdefault(color, []).append(root)

        for color, roots in perColorRoots.items():
            if len(roots) > 1:
                self.warnings.append(f"Color {color} produced {len(roots)} disconnected parts.")

        for (color, root), count in componentPixelCount.items():
            if count == 1:
                self.warnings.append(f"Isolated single-pixel part for color {color}.")

        self.meshes = meshes
        self.baseMesh = [self._calculateBase(rows, cols)]

    def _calculateBase(self, rows, cols):
        """The base plate: a solid rectangle covering the canvas's own
        footprint plus baseMargin cells on every side, always exactly one
        fused piece (every base cell is fused to every neighbor within
        that rectangle by construction - see planBaseGrid), carrying a
        BaseSocket wherever a real occupied pixel sits above it."""
        basePlans = planBaseGrid(rows, cols, self.baseMargin)
        halfWidth = BASE_PEG_WIDTH_RATIO / 2.0

        tris = []
        for (y, x), plan in basePlans.items():
            topSocket = None
            if 0 <= y < rows and 0 <= x < cols and self.canvas.layers[y, x] >= 1:
                topSocket = BaseSocket(x + 0.5, y + 0.5, halfWidth)
            tris += Pixel(plan, self.hollow, topSocket=topSocket).triangles()
        return tris
