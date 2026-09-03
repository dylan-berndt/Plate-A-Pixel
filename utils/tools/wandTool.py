from .tool import Options, FunctionalTool


class WandTool(FunctionalTool):
    """Click-to-select, built on Canvas.bucketSelect. There is no separate
    "bucket" tool: bucketSelect(contiguous=False) already selects every
    cell matching the clicked position's color exactly like a color-wand
    pick would, so "wand" and "bucket" are the same operation with one
    option (contiguous) toggled, not two separate tools.

    On the layer canvas (useLayers=True - see FunctionalTool.onPress),
    "matching" means matching *height* instead of matching color: the
    same click groups pixels by canvas.layers rather than canvas.map, so
    picking a component out by its assigned height works the same way
    color-picking does on the color canvas."""

    def __init__(self):
        super().__init__(
            name="wand",
            options={
                "mode": Options(
                    "Selection Mode", "dropdown",
                    {"Addition": "add", "Subtraction": "subtract", "Replacement": "replace", "Intersection": "intersect"},
                ),
                "contiguous": Options("Contiguous", "checkbox", {"True": True, "False": False}),
                "diagonal": Options("Use Diagonals", "checkbox", {"True": True, "False": False}),
            },
            selections={"mode": "replace", "contiguous": False, "diagonal": True},
        )

    def onPress(self, controller, pos, useLayers=False):
        canvas = controller.project.canvas
        with controller.projectController.editing(signal=controller.projectController.selectionChanged):
            canvas.bucketSelect(
                pos,
                contiguous=self.selections["contiguous"],
                diagonal=self.selections["diagonal"],
                mode=self.selections["mode"],
                source=canvas.layers if useLayers else canvas.map,
            )
