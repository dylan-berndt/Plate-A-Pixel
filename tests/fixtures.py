import numpy as np

# A small, hand-laid-out logical pixel-art grid shared across the test
# suite. Chosen to exercise three bucket-select behaviors at once:
#   - RED_BLOCK: a solid, orthogonally contiguous region
#   - RED_ISLAND: the same color again, disconnected from RED_BLOCK
#   - GREEN_DIAGONAL_PAIR: two pixels of the same color that only touch
#     corner-to-corner (the dithering case the `diagonal` flag exists for)
BACKGROUND = (35, 35, 40)
RED = (220, 40, 40)
GREEN = (40, 180, 90)

# Indexed [y][x] to match Canvas's (y, x) position convention.
GRID = [
    [RED,        RED,        RED,        BACKGROUND, BACKGROUND, BACKGROUND],
    [RED,        RED,        RED,        BACKGROUND, GREEN,      BACKGROUND],
    [BACKGROUND, BACKGROUND, BACKGROUND, BACKGROUND, BACKGROUND, GREEN],
    [BACKGROUND, BACKGROUND, BACKGROUND, BACKGROUND, BACKGROUND, BACKGROUND],
    [BACKGROUND, BACKGROUND, BACKGROUND, BACKGROUND, BACKGROUND, BACKGROUND],
    [BACKGROUND, BACKGROUND, BACKGROUND, BACKGROUND, BACKGROUND, RED],
]

RED_BLOCK = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)]
RED_ISLAND = (5, 5)
GREEN_DIAGONAL_PAIR = [(1, 4), (2, 5)]


def make_pixel_art(block_size=4):
    """Render GRID as an upscaled raster image (block_size raster px per logical px),
    the same shape Canvas.detectScale expects to reduce back down."""
    rows = len(GRID)
    cols = len(GRID[0])
    image = np.zeros((rows * block_size, cols * block_size, 3), dtype=np.uint8)

    for y, row in enumerate(GRID):
        for x, color in enumerate(row):
            image[y * block_size:(y + 1) * block_size, x * block_size:(x + 1) * block_size] = color

    return image
