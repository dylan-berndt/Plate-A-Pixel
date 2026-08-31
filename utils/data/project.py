import io
import json
import os
import zipfile
from dataclasses import dataclass, asdict

import numpy as np
from PIL import Image

from .canvas import Canvas
from .palette import Palette
from .mesh import Mesh
from .objExport import exportMeshObjs, MM_PER_UNIT

# Bumped whenever project.json's shape changes in a way Project.load needs
# to branch on. Project.load rejects a file from a newer version outright
# rather than guessing at a shape it's never seen.
FORMAT_VERSION = 1


@dataclass
class ViewSettings:
    """Per-project print/view settings - the "how" of turning a Canvas
    into a mesh and an export, as opposed to the canvas data itself."""

    hollow: bool = False
    # How many grid cells the base plate extends past the canvas's own
    # extent on every side (see Mesh.baseMargin).
    baseMargin: int = 0
    # Millimeters per grid cell in X/Z - a pixel's printed footprint.
    cellWidth: float = MM_PER_UNIT
    # Millimeters per height-layer in Y - one layer's printed thickness.
    cellHeight: float = MM_PER_UNIT

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(d):
        return ViewSettings(
            hollow=d.get("hollow", False),
            baseMargin=d.get("baseMargin", 0),
            cellWidth=d.get("cellWidth", MM_PER_UNIT),
            cellHeight=d.get("cellHeight", MM_PER_UNIT),
        )


class Project:
    """One open document: a Canvas, its Palette (carried on canvas.palette),
    the Mesh derived from them, and the ViewSettings controlling both mesh
    generation and export scale. This is "one tab" - an app hosting several
    open projects just holds a list of these."""

    def __init__(self, canvas: Canvas, viewSettings: ViewSettings = None, name: str = "Untitled"):
        self.name = name
        self.canvas = canvas
        self.viewSettings = viewSettings or ViewSettings()
        self.mesh = Mesh()
        self._syncMeshSettings()

    def _syncMeshSettings(self):
        self.mesh.canvas = self.canvas
        self.mesh.hollow = self.viewSettings.hollow
        self.mesh.baseMargin = self.viewSettings.baseMargin

    def rebuildMesh(self):
        """Recomputes the mesh from the canvas's current state and this
        project's view settings. Cheap to call after every edit - Mesh's
        own cache (_checkForUpdate) no-ops when nothing actually changed."""
        self._syncMeshSettings()
        self.mesh._calculateMesh()
        return self.mesh

    def exportObjs(self, outputDir):
        """Rebuilds the mesh if needed and writes one OBJ per component,
        scaled by this project's cellWidth (X/Z) and cellHeight (Y)."""
        self.rebuildMesh()
        scale = (self.viewSettings.cellWidth, self.viewSettings.cellHeight, self.viewSettings.cellWidth)
        return exportMeshObjs(self.mesh, outputDir, scale=scale)

    @staticmethod
    def newFromImagePath(filePath, name=None):
        canvas = Canvas.fromFilePath(filePath)
        projectName = name or os.path.splitext(os.path.basename(filePath))[0]
        return Project(canvas, name=projectName)

    def save(self, filePath):
        """Writes this project to a single *.pap file: a zip bundle of the
        canvas's (already scale-reduced) image, its height grid, and a
        JSON sidecar with the palette (colors, names) and
        view settings. That's everything Canvas.fromSaved needs to
        reconstruct the exact same canvas - and everything Mesh needs to
        rebuild the exact same mesh - on load."""
        metadata = {
            "formatVersion": FORMAT_VERSION,
            "name": self.name,
            "scale": self.canvas.scale,
            "viewSettings": self.viewSettings.to_dict(),
            "palette": self.canvas.palette.to_dict(),
        }

        with zipfile.ZipFile(filePath, "w", zipfile.ZIP_DEFLATED) as zf:
            imageBuffer = io.BytesIO()
            Image.fromarray(self.canvas.image.astype(np.uint8)).save(imageBuffer, format="PNG")
            zf.writestr("image.png", imageBuffer.getvalue())

            layersBuffer = io.BytesIO()
            np.save(layersBuffer, self.canvas.layers)
            zf.writestr("layers.npy", layersBuffer.getvalue())

            zf.writestr("project.json", json.dumps(metadata, indent=2))

    @staticmethod
    def load(filePath):
        """The inverse of save(): reopens a *.pap file, rebuilding the
        Canvas via fromSaved (so pixels are matched against the palette
        that was actually saved, not re-derived from the image) and a
        fresh Project around it. Selection, active tool, and undo history
        are intentionally not part of the format - a reload always starts
        clean."""
        with zipfile.ZipFile(filePath, "r") as zf:
            metadata = json.loads(zf.read("project.json"))
            if metadata["formatVersion"] > FORMAT_VERSION:
                raise ValueError(
                    f"{filePath} was saved by a newer version of Plate-A-Pixel "
                    f"(format {metadata['formatVersion']}, this build supports up to {FORMAT_VERSION})."
                )

            image = np.array(Image.open(io.BytesIO(zf.read("image.png"))).convert("RGB"))
            layers = np.load(io.BytesIO(zf.read("layers.npy")))

        palette = Palette.from_dict(metadata["palette"])
        canvas = Canvas.fromSaved(image, metadata["scale"], palette, layers)
        viewSettings = ViewSettings.from_dict(metadata["viewSettings"])
        return Project(canvas, viewSettings=viewSettings, name=metadata.get("name", "Untitled"))
