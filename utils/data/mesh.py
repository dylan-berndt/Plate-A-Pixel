import numpy as np
from .canvas import *
from .vector import *


class Mesh:
    def __init__(self):
        self.canvas: Canvas = None

        self.hollow = False

        self.mapCache: np.array = None
        self.layerCache: np.array = None
        self.hollowCache = self.hollow

        self.meshes = []

    def _checkForUpdate(self):
        if self.canvas is None:
            return False
        
        mapChanged = not np.allclose(self.mapCache, self.canvas.map)
        layersChanged = not np.allclose(self.layerCache, self.canvas.layers)
        hollowChanged = not self.hollow == self.hollowCache
        return mapChanged or layersChanged or hollowChanged
    
    # Used to rotate a mesh from above. Should be used before translation (typically on notches)
    # Always in 90 degree increments, so clockwise 1 = 90 degrees, clockwise 2 = 180 degrees
    def _rotateMeshXY(self, mesh: list[Vector3], clockwise):
        for i in range(clockwise):
            for t in range(len(mesh)):
                mesh[t] = Vector3(mesh[t].y, -mesh[t].x, mesh[t].z)

        return mesh
    
    def _translateMesh(self, mesh: list[Vector3], position: Vector3):
        for t in range(len(mesh)):
            mesh[t] = mesh[t] + position
        
        return mesh
    
    # Returns mesh data for a notch, both positive and negative
    # Positive notches are at the bottom of the attachment sections
    # and allow the pieces of the model to come together.
    # Negative notches are the inlets where positive notches attach to lower pixels
    # Notches only ever go sideways out/in from a wall
    def _notch(self, position: Vector3, angle: int = 0, positive=True):
        pass

    # Inlet place on a pixel cap for a higher pixel to attach to
    def _inlet(self, position: Vector3, angle: int = 0):
        notchMesh = self._notch(Vector3(0, 0, 0), positive=False)

        # TODO: Generate 4 rectangles around notch, one wall of pixel cap
        wallMesh = []

        mesh = notchMesh.extend(wallMesh)

        return self._translateMesh(self._rotateMeshXY(mesh, angle), position)

    # Returns mesh data for a flat rectangle/square
    def _rectangle(self, position: Vector3, direction: Vector3):
        pass
    
    # Returns mesh data (list of Vector3 vertices) for a particular cap of a pixel
    # Sides with pixels of similar color should connect contiguously, dissimilar colors should yield a wall between the two.
    # Sides with nothing next to them should have a bulge, this allows dithered pixels to connect and form a single mesh
    def _pixelCap(self, position: Vector3, sidesClear=[True, True, True, True]):
        # TODO: Top of cap, simple rectangle
        # TODO: Rounded corners (top to sides, side to side)
        # TODO: Notched sides
        # TODO: Bulge
        pass

    def _tube(self, position: Vector3):
        # TODO: Determine sides requiring walls
        # TODO: Determine location of notches in walls
        pass

    def _calculateMesh(self):
        if not self._checkForUpdate():
            return
        
        self.mapCache = self.canvas.map
        self.layerCache = self.canvas.layers

        meshes = [[] for i in range(self.canvas.palette)]
        
        # Transitions, essentially how much taller am I than the pixel to my X (left, right, top, bottom)
        left = self.canvas.layers[:, 1:] - self.canvas.layers[:, :-1]
        right = self.canvas.layers[:, :-1] - self.canvas.layers[:, 1:]
        up = self.canvas.layers[:, 1:] - self.canvas.layers[:, :-1]
        down = self.canvas.layers[:, :-1] - self.canvas.layers[:, 1:]

        # TODO: Build mesh for each color in the pixel art
        for color in self.canvas.palette:
            mesh = []
            numbers = self.canvas.map
            layers = self.canvas.layers
            for y in range(numbers.shape[0]):
                for x in range(numbers.shape[1]):
                    pass

        self.meshes = meshes



        