import sys
import random

from PySide6.QtWidgets import QApplication
from utils import *

MIN_HEIGHT = 1
MAX_HEIGHT = 4
OUTPUT_DIR = "output"

app = QApplication(sys.argv)

canvas = Canvas.loadNewCanvas()
if canvas is None:
    print("No image selected.")
    sys.exit(0)

rows, cols = canvas.map.shape
for y in range(rows):
    for x in range(cols):
        canvas.layers[y, x] = random.randint(MIN_HEIGHT, MAX_HEIGHT)

mesh = Mesh()
mesh.canvas = canvas
mesh.hollow = True
mesh._calculateMesh()

paths = exportMeshObjs(mesh, OUTPUT_DIR)
print(f"Wrote {len(paths)} OBJ file(s) to {OUTPUT_DIR}/:")
for path in paths:
    print(f"  {path}")

for warning in mesh.warnings:
    print(f"warning: {warning}")
