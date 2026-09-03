import numpy as np
from PIL import Image
from PySide6.QtWidgets import QFileDialog

from .palette import Palette


class Canvas:
    def __init__(self, image: np.array, scale: int = None, palette: Palette = None, layers: np.array = None):
        """Builds a Canvas from a raw image by default (auto-detecting scale
        and the palette from the image's own unique colors). `scale`,
        `palette` and `layers` let a caller (Project.load) supply all three
        explicitly instead, reconstructing the exact canvas a save captured
        - matching pixels against the saved palette's own color order
        rather than re-deriving it, so a later recolor can't desync a
        reload from what was actually saved."""
        if scale is None:
            self.image, self.scale = Canvas.detectScale(image)
        else:
            self.image, self.scale = image, scale

        if palette is None:
            uniqueColors = np.unique(np.reshape(self.image, [-1, self.image.shape[-1]]), axis=0)
            palette = Palette(uniqueColors)
        self.palette = palette

        layerShape = self.image.shape[:-1]
        self.map = np.zeros(layerShape, dtype=np.int32)
        for c, color in enumerate(self.palette.colors):
            mask = np.all(self.image == color, axis=-1)
            self.map[mask] = c

        self.baseColor = None
        # -1 means "no pixel placed here yet" (empty space); valid printed
        # pixels have a height of 1 or more, set later via the height brush.
        self.layers = layers if layers is not None else np.full_like(self.map, -1, dtype=np.int32)

        self.selection = np.zeros_like(self.map, dtype=np.bool)

    @staticmethod
    def detectScale(image: np.array):
        h, w = image.shape[:2]
        g = np.gcd(h, w)
        for i in sorted((d for d in range(1, g + 1) if g % d == 0), reverse=True):
            if i == 1:
                return image, 1
            blocks = image.reshape(h // i, i, w // i, i, -1)
            sampled = blocks[:, i // 2, :, i // 2, :]
            blurred = blocks.mean(axis=(1, 3))
            if np.allclose(sampled, blurred):
                return sampled, i
        return image, 1


    # Raw image import - one entry point alongside Project.load for opening
    # a saved *.pap project (see project.py), which passes Canvas its
    # saved scale/palette/layers directly instead of re-detecting them.
    @staticmethod
    def loadNewCanvas(parent=None):
        filePath, _ = QFileDialog.getOpenFileName(parent, "Import Image", "", "PNG Files (*.png)")
        if not filePath:
            return None
        return Canvas.fromFilePath(filePath)

    @staticmethod
    def fromFilePath(filePath: str):
        # Force RGB regardless of the source PNG's actual mode (grayscale,
        # palette-indexed, RGBA, ...) - detectScale and the rest of Canvas
        # assume a 3-channel (H, W, 3) array throughout.
        image = np.array(Image.open(filePath).convert("RGB"))
        return Canvas(image)

    def positionValid(self, position):
        x = position[1]
        y = position[0]

        xValid = x > -1 and x < self.image.shape[1]
        yValid = y > -1 and y < self.image.shape[0]
        return xValid and yValid

    def validNeighbors(self, position, diagonal=True):
        x = position[1]
        y = position[0]

        neighbors = []
        if diagonal:
            for d in range(9):
                dy = (d // 3) - 1
                dx = (d % 3) - 1
                
                positionValid = self.positionValid((y + dy, x + dx))
                notCenter = dx != 0 or dy != 0
                if positionValid and notCenter:
                    neighbors.append((y + dy, x + dx))
        else:
            dx = 1
            dy = 0
            for i in range(4):
                positionValid = self.positionValid((y + dy, x + dx))
                notCenter = dx != 0 or dy != 0
                if positionValid and notCenter:
                    neighbors.append((y + dy, x + dx))

                if i == 1:
                    dx, dy = -dy, -dx
                else:
                    dx, dy = dy, dx

        return neighbors

    def alterSelection(self, selection, mode):
        if mode == "replace":
            self.selection = selection
        elif mode == "subtract":
            # AND-NOT, not XOR: XOR toggles, so a cell in `selection` that
            # wasn't already selected would flip on instead of staying
            # unselected - subtraction should only ever turn cells off.
            self.selection = np.logical_and(self.selection, np.logical_not(selection))
        elif mode == "add":
            self.selection = np.logical_or(self.selection, selection)
        elif mode == "intersect":
            self.selection = np.logical_and(self.selection, selection)
        else:
            raise NotImplementedError("You Goober")

    def bucketSelect(self, position, contiguous=True, diagonal=False, mode="replace", source=None):
        """`source` is the per-pixel array read for the "does this match"
        test - `self.map` (color) by default, but the layer canvas passes
        `self.layers` instead so a click there groups by assigned height
        rather than color (see WandTool.onPress). Same shape as `self.map`
        either way, so everything below is unchanged by which one it is."""
        source = self.map if source is None else source
        value = source[position]

        if not contiguous:
            newSelection = source == value
            self.alterSelection(newSelection, mode)
            return

        newSelection = np.zeros_like(self.map, dtype=np.bool)
        newSelection[position] = 1
        queue = [position]

        while queue:
            check = self.validNeighbors(queue[0], diagonal)

            for pos in check:
                if source[pos] == value and not newSelection[pos]:
                    newSelection[pos] = 1
                    queue.append(pos)

            queue = queue[1:]

        self.alterSelection(newSelection, mode)

    def brushSelect(self, position, radius, mode="replace"):
        """Every cell within `radius` of `position` (Euclidean, in grid
        cells) - color-blind, unlike bucketSelect, since a brush stamps an
        area rather than picking out one color."""
        y, x = position
        yGrid, xGrid = np.ogrid[:self.map.shape[0], :self.map.shape[1]]
        newSelection = (yGrid - y) ** 2 + (xGrid - x) ** 2 <= radius ** 2
        self.alterSelection(newSelection, mode)

    def transformSelection(self, direction=1):
        self.layers[self.selection] += direction
