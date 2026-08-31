from .tool import Options, FunctionalTool


class BrushSelectTool(FunctionalTool):
    """Drag-to-select: stamps every cell within a radius of the pointer
    into the selection on press, then keeps stamping as it drags."""

    def __init__(self):
        super().__init__(
            name="brushSelect",
            options={
                "size": Options("Brush Size", "slider", {"Minimum": 1, "Maximum": 35}),
                "mode": Options(
                    "Selection Mode", "dropdown",
                    {"Addition": "add", "Subtraction": "subtract", "Replacement": "replace", "Intersection": "intersect"},
                ),
            },
            selections={"size": 4, "mode": "add"},
        )
        self._dragMode = None

    def onPress(self, controller, pos):
        self._dragMode = self.selections["mode"]
        controller.brushSelect(pos, self.selections["size"], mode=self._dragMode)

    def onDrag(self, controller, pos):
        # A drag continuing a "replace" stroke must not keep replacing -
        # each sample would wipe out every cell painted earlier in the
        # same stroke, leaving only the brush's current stamp selected.
        mode = "add" if self._dragMode == "replace" else self._dragMode
        controller.brushSelect(pos, self.selections["size"], mode=mode)
