from .tool import Options, FunctionalTool


class BrushSelectTool(FunctionalTool):
    """Drag-to-select: stamps every cell within a radius of the pointer
    into the selection on press, then keeps stamping as it drags.
    Ignores useLayers (see FunctionalTool.onPress) - Canvas.brushSelect
    is a pure radius stamp with no color/height test at all, so it
    already means the same thing on the color and layer canvases."""

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

    def _stamp(self, controller, pos, mode):
        with controller.projectController.editing(signal=controller.projectController.selectionChanged):
            controller.project.canvas.brushSelect(pos, self.selections["size"], mode=mode)

    def onPress(self, controller, pos, useLayers=False):
        self._dragMode = self.selections["mode"]
        self._stamp(controller, pos, self._dragMode)

    def onDrag(self, controller, pos, useLayers=False):
        # A drag continuing a "replace" stroke must not keep replacing -
        # each sample would wipe out every cell painted earlier in the
        # same stroke, leaving only the brush's current stamp selected.
        mode = "add" if self._dragMode == "replace" else self._dragMode
        self._stamp(controller, pos, mode)
