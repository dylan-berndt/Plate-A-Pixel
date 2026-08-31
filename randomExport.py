import sys
import random

from PySide6.QtWidgets import QApplication
from utils import *

MIN_HEIGHT = 1
MAX_HEIGHT = 4
BASE_MARGIN = 2
OUTPUT_DIR = "output"

app = QApplication(sys.argv)

canvas = Canvas.loadNewCanvas()
if canvas is None:
    print("No image selected.")
    sys.exit(0)

print(canvas.scale)

for c, color in enumerate(canvas.palette.colors):
    canvas.wandSelect(color)
    # layers starts at -1 (empty) and transformSelection adds to it, so
    # +c alone leaves color 0 at -1 and color 1 at 0 - both still "empty"
    # (height < 1) and silently absorbed into the base plate. +2 makes
    # color c land at height c+1, the first real height.
    canvas.transformSelection(c + 2)

mesh = Mesh()
mesh.canvas = canvas
mesh.hollow = True
mesh.baseMargin = BASE_MARGIN
mesh._calculateMesh()

paths = exportMeshObjs(mesh, OUTPUT_DIR)
print(f"Wrote {len(paths)} OBJ file(s) to {OUTPUT_DIR}/:")
for path in paths:
    print(f"  {path}")

for warning in mesh.warnings:
    print(f"warning: {warning}")
