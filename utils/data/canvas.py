import numpy as np
from PIL import Image
import tkinter as tk
from tkinter.filedialog import askopenfilename


class Canvas:
    def __init__(self, image: np.array):
        self.image = image

        self.colors = np.unique(np.reshape(self.image, [-1, self.image.shape[-1]]), axis=0)

        layerShape = self.image.shape[:-1]
        self.map = np.zeros(layerShape, dtype=np.int32)
        for c, color in enumerate(self.colors):
            mask = np.all(self.image == color, axis=-1)
            self.map[mask] = c

        self.baseColor = None
        self.layers = np.zeros(layerShape, dtype=np.int32)

        self.selection = np.zeros(layerShape, dtype=np.bool)

    @staticmethod
    def loadNewCanvas():
        root = tk.Tk()
        root.withdraw()

        filePath = askopenfilename(filetypes=[("PNG Files", "*.png")])
        return Canvas.fromFilePath(filePath)

    @staticmethod
    def fromFilePath(filePath: str):
        image = np.array(Image.open(filePath))
        return Canvas(image)

    # TODO: Mouse to grid
    def transform(self, position):
        pass

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
            self.selection = np.logical_xor(self.selection, selection)
        elif mode == "add":
            self.selection = np.logical_or(self.selection, selection)
        elif mode == "intersect":
            self.selection = np.logical_and(self.selection, selection)
        else:
            raise NotImplementedError("You Goober")

    def bucketSelect(self, position, mode, contiguous, diagonal):
        position = self.transform(position)

        value = self.map[position]

        if not contiguous:
            newSelection = self.map == value
            self.alterSelection(newSelection, mode)
            return

        newSelection = np.zeros_like(self.map, dtype=np.bool)
        newSelection[position] = 1
        queue = [position]

        while queue:
            check = self.validNeighbors(queue[0], diagonal)

            for pos in check:
                if self.map[pos] == value:
                    if not self.selection[pos] and not newSelection[pos]:
                        newSelection[pos] = 1
                        queue.append(pos)

            queue = queue[1:]

        self.alterSelection(newSelection, mode)



if __name__ == "__main__":
    canvas = Canvas.loadNewCanvas()
        
