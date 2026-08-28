import numpy as np
from .canvas import *
from .pixelPlan import Face, PixelPlanner
from .pixelComponents import Pixel


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

        self.mapCache: np.array = None
        self.layerCache: np.array = None
        self.hollowCache = self.hollow

        # meshes[colorIndex] is a list of components - pixels of the same
        # color don't always end up physically connected (see the
        # "disconnected parts" warnings below); each component is a flat
        # list of Vector3, 3 per triangle.
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
        return mapChanged or layersChanged or hollowChanged

    def _calculateMesh(self):
        if not self._checkForUpdate():
            return

        self.mapCache = self.canvas.map.copy()
        self.layerCache = self.canvas.layers.copy()
        self.hollowCache = self.hollow
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
                pixels[(y, x)] = Pixel(plan, self.hollow)
                parent[(y, x)] = (y, x)

        for (y, x), pixel in pixels.items():
            for face in Face:
                if face in pixel.plan.fused:
                    union((y, x), face.neighbor(y, x))
            for neighbor, connected in planner.diagonalConnections(y, x):
                if connected:
                    union((y, x), neighbor)

        components = {}
        componentPixelCount = {}
        for pos, pixel in pixels.items():
            key = (pixel.plan.color, find(pos))
            components.setdefault(key, []).extend(pixel.triangles())
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
