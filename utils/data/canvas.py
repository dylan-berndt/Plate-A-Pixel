import numpy as np
from PIL import Image
import tkinter as tk
from tkinter.filedialog import askopenfilename


class Canvas:
    def __init__(self, image: np.array):
        # TODO: Evaluate using map instead of raw image
        self.image, self.scale = Canvas.detectScale(image)

        self.colors = np.unique(np.reshape(self.image, [-1, self.image.shape[-1]]), axis=0)

        layerShape = self.image.shape[:-1]
        self.map = np.zeros(layerShape, dtype=np.int32)
        for c, color in enumerate(self.colors):
            mask = np.all(self.image == color, axis=-1)
            self.map[mask] = c

        self.baseColor = None
        self.layers = np.zeros_like(self.map, dtype=np.int32)

        self.selection = np.zeros_like(self.map, dtype=np.bool)

    @staticmethod
    def detectScale(image: np.array):
        maxScale = 1
        baseImage = image
        xGrid, yGrid = np.meshgrid(np.arange(baseImage.shape[1]), np.arange(baseImage.shape[0]))
        for i in range(2, 17):
            if i >= image.shape[0] or i >= image.shape[1]:
                break
            
            # Nearest neighbor sampling to get reference color without blurring
            sampleMask = np.logical_and(yGrid % i == i // 2, xGrid % i == i // 2)
            sampled = image[sampleMask]
            
            # Sample a block of the pixels that we assume should be the same color
            blurGrid = np.stack([yGrid // i, xGrid // i], axis=-1)
            # Flat array with the grid index of each pixel
            values, gridIndices = np.unique(blurGrid.reshape(-1, 2), return_inverse=True, axis=0)
            # Blurring produces a different size image than the sampling
            if values.shape[0] != sampled.reshape(-1, image.shape[-1]).shape[0]:
                continue
            
            # Empty array to store the blurred values
            blurred = np.zeros([values.shape[0], image.shape[-1]])
            
            np.add.at(blurred, gridIndices, image.reshape(-1, image.shape[-1]))
            blurred = blurred / (i * i)
            
            # If all pixels in the grid-blurred image are the same as the reference pixel
            # for every reference pixel, no actual blurring of colors has occured and
            # we can assume that our current grid size is valid
            if np.allclose(sampled, blurred):
                baseImage = sampled
                maxScale = i
                
            baseImage = baseImage.reshape(image.shape[0] // maxScale, image.shape[1] // maxScale, image.shape[-1])

        return baseImage, maxScale


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
        
