import numpy as np
from .canvas import *
from .vector import Vector3
from .pixelPlan import planGrid, fusedPairs, diagonalPairs
from .pixelComponents import componentTriangles, componentTrianglesFast, TUBE_MARGIN, WALL_THICKNESS, BULGE_SIZE

BASE_HEIGHT = 1


def computeMeshData(map_, layers, paletteLen, hollow, fastPreview, baseMargin, tubeMargin, wallThickness, bulgeSize):
    """The actual grouping + triangulation work, as a plain function over
    arrays and numbers rather than a Canvas/Mesh - Mesh._calculateMesh
    calls this in-process, and ProjectController's live-preview worker
    submits it to a separate process instead (see its own module), since
    a module-level function is what a process pool needs to pickle as a
    call target. Returns (meshes, warnings), matching Mesh.meshes/
    .warnings."""
    canvasRows, canvasCols = map_.shape
    margin = baseMargin
    rows, cols = canvasRows + 2 * margin, canvasCols + 2 * margin

    # The base color: one past every real palette color, so it never
    # collides with an actual color index.
    baseColor = paletteLen
    gridMap = np.full((rows, cols), baseColor, dtype=map_.dtype)
    gridLayers = np.full((rows, cols), -1, dtype=layers.dtype)
    gridMap[margin:margin + canvasRows, margin:margin + canvasCols] = map_
    gridLayers[margin:margin + canvasRows, margin:margin + canvasCols] = layers

    # Every cell still empty at this point - a hole inside the canvas, or
    # anywhere in the margin border - becomes base material: literally
    # another color, at height 1, run through the exact same
    # classification as everything else. A real pixel taller than it gets
    # a completely ordinary bulged wall against it, and the base cells
    # fuse with each other exactly like any same-color same-height
    # neighbors always do.
    emptyMask = gridLayers < 1
    gridMap[emptyMask] = baseColor
    gridLayers[emptyMask] = BASE_HEIGHT

    plans = planGrid(gridMap, gridLayers)

    parent = {pos: pos for pos in plans}

    def find(p):
        while parent[p] != p:
            parent[p] = parent[parent[p]]
            p = parent[p]
        return p

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for a, b in fusedPairs(gridMap, gridLayers):
        union(a, b)
    for a, b in diagonalPairs(gridMap, gridLayers):
        union(a, b)

    groups = {}
    for pos, plan in plans.items():
        key = (plan.color, find(pos))
        groups.setdefault(key, []).append(plan)

    colorCount = paletteLen + 1  # +1 for the base color
    meshes = [[] for _ in range(colorCount)]
    perColorRoots = {}
    for (color, root), groupPlans in groups.items():
        if fastPreview:
            triangles = componentTrianglesFast(groupPlans, tubeMargin=tubeMargin, bulgeSize=bulgeSize)
        else:
            triangles = componentTriangles(
                groupPlans, hollow, tubeMargin=tubeMargin, wallThickness=wallThickness, bulgeSize=bulgeSize,
            )
        meshes[color].append(triangles)
        perColorRoots.setdefault(color, []).append(root)

    warnings = []
    for color, roots in perColorRoots.items():
        if len(roots) > 1:
            warnings.append(f"Color {color} produced {len(roots)} disconnected parts.")
    for (color, root), groupPlans in groups.items():
        if len(groupPlans) == 1:
            warnings.append(f"Isolated single-pixel part for color {color}.")

    return meshes, warnings


def _packMeshes(meshes):
    """meshes (list[list[list[Vector3]]]) with each component's triangle
    soup packed into one (N, 3) float32 array. Pickling a numpy array is
    close to a memcpy; pickling a list of thousands of individual Vector3
    objects pays that object's full per-instance pickle overhead once per
    vertex, which dominates a process-pool round trip for any mesh with a
    real triangle count (measured: ~1.2s of pickling for ~117k triangles,
    against ~1.4s to actually compute them) - see
    ProjectController._MeshWorker, the only caller that needs this."""
    return [
        [np.array([(v.x, v.y, v.z) for v in triangles], dtype=np.float32) if triangles
         else np.empty((0, 3), dtype=np.float32)
         for triangles in components]
        for components in meshes
    ]


def unpackMeshes(packed):
    """Inverse of _packMeshes - back to list[list[list[Vector3]]], the
    shape Mesh.meshes is documented and used everywhere else as.
    .tolist() once per component, not per vertex: iterating a numpy array
    row-by-row boxes a numpy scalar for every single x/y/z, the same
    overhead _fastSolidFromCoverage avoids the same way."""
    return [
        [[Vector3(x, y, z) for x, y, z in arr.tolist()] for arr in components]
        for components in packed
    ]


def computeMeshDataPacked(*args, **kwargs):
    """computeMeshData, with its meshes packed for a cheap pickle - the
    call target ProjectController's process pool actually submits."""
    meshes, warnings = computeMeshData(*args, **kwargs)
    return _packMeshes(meshes), warnings


class Mesh:
    """Turns a Canvas's height field into one printable solid per color.
    planGrid (pixelPlan.py) classifies every cell into fused/bulged/
    plainWalls per side, componentTriangles (pixelComponents.py) turns one
    connected group's plans into a hull, and everything below wires those
    together - grouping pixels into physically connected pieces per color
    and collecting warnings along the way.

    fastPreview swaps that for componentTrianglesFast - a much cheaper but
    not-actually-watertight mesh, meant only for the live viewport while
    editing. Export always recomputes with fastPreview off (see
    Project.rebuildMesh)."""

    def __init__(self):
        self.canvas: Canvas = None

        self.hollow = False
        # Trades away real watertightness for speed (see componentTrianglesFast)
        # - only ever set for the live-preview worker, never for export.
        self.fastPreview = False
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
        self.fastPreviewCache = self.fastPreview
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
        fastPreviewChanged = self.fastPreview != self.fastPreviewCache
        baseMarginChanged = self.baseMargin != self.baseMarginCache
        geometryChanged = (
            self.tubeMargin != self.tubeMarginCache
            or self.wallThickness != self.wallThicknessCache
            or self.bulgeSize != self.bulgeSizeCache
        )
        return (
            mapChanged or layersChanged or hollowChanged or fastPreviewChanged
            or baseMarginChanged or geometryChanged
        )

    def _refreshCaches(self):
        self.mapCache = self.canvas.map.copy()
        self.layerCache = self.canvas.layers.copy()
        self.hollowCache = self.hollow
        self.fastPreviewCache = self.fastPreview
        self.baseMarginCache = self.baseMargin
        self.tubeMarginCache = self.tubeMargin
        self.wallThicknessCache = self.wallThickness
        self.bulgeSizeCache = self.bulgeSize

    def _calculateMesh(self):
        if not self._checkForUpdate():
            return
        self._refreshCaches()
        self.meshes, self.warnings = computeMeshData(
            self.canvas.map, self.canvas.layers, len(self.canvas.palette),
            self.hollow, self.fastPreview, self.baseMargin, self.tubeMargin, self.wallThickness, self.bulgeSize,
        )
