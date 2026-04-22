import numpy as np
from .canvas import *


class Mesh:
    def __init__(self):
        self.canvas: Canvas = None

    def _checkForUpdate(self):
        if self.canvas is None:
            return False
        
        # TODO: Check for changes in canvas.map, canvas.layers
        return True

    def _calculateMesh(self):
        if not self._checkForUpdate():
            return
        
        transitions = []

        