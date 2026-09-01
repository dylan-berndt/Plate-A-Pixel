import numpy as np
from PySide6.QtWidgets import QWidget, QVBoxLayout, QButtonGroup, QFrame

from .elements import IconButton, Icons, SectionLabel, Stepper, Theme


def selectionHeightText(canvas):
    """What the layer-height stepper should display for the current
    selection: the shared height when every selected cell agrees, "*"
    when they don't (mixed selection - no single value to show), "-"
    when nothing is selected at all."""
    if not canvas.selection.any():
        return "-"
    heights = canvas.layers[canvas.selection]
    if np.all(heights == heights[0]):
        return str(int(heights[0]))
    return "*"


class ToolRail(QWidget):
    """The left rail: tool selection (Wand/Brush - the two real tools;
    see ARCHITECTURE.md's "explicitly not built" list for why there
    isn't a third) and the layer-height stepper, which is the view for
    CanvasController.transformSelectionLayer(delta) - there's no tool for
    height, so this is the only place that edit happens from.

    Needs both appController (to resolve whichever project is active at
    click time, for the height buttons and tool switching) and
    toolController (to switch tools and know which one is active) since
    those live on AppController but aren't the same object."""

    def __init__(self, appController, toolController, theme: Theme = None, **kwargs):
        super().__init__(**kwargs)
        theme = theme or Theme()
        self._appController = appController
        self._toolController = toolController
        self._boundProjectController = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 14, 0, 14)
        layout.setSpacing(8)
        layout.setAlignment(layout.alignment())

        self._toolGroup = QButtonGroup(self)
        self._toolGroup.setExclusive(True)
        self._toolButtons = {}
        for name, iconBody in (("wand", Icons.WAND), ("brushSelect", Icons.BRUSH)):
            button = IconButton(
                iconBody, checkable=True, theme=theme,
                onClick=(lambda checked, n=name: self._toolController.setActiveTool(n)),
            )
            self._toolGroup.addButton(button)
            self._toolButtons[name] = button
            layout.addWidget(button)

        divider = QFrame()
        divider.setFixedHeight(1.5)
        divider.setStyleSheet(f"background: {theme.ink};")
        layout.addWidget(divider)

        layout.addWidget(SectionLabel("Layer", theme=theme))
        self._layerStepper = Stepper(
            "-", onIncrement=self._raiseSelection, onDecrement=self._lowerSelection, theme=theme,
        )
        layout.addWidget(self._layerStepper)

        layout.addStretch(1)

        self._toolController.activeToolChanged.connect(self._onActiveToolChanged)
        self._onActiveToolChanged(self._toolController.registry.activeTool)

    def _onActiveToolChanged(self, tool):
        if tool is None:
            return
        button = self._toolButtons.get(tool.name)
        if button is not None:
            button.setChecked(True)

    def _raiseSelection(self):
        self._transformSelection(1)

    def _lowerSelection(self):
        self._transformSelection(-1)

    def _transformSelection(self, delta):
        controller = self._appController.activeController
        if controller is None:
            return
        controller.canvasController.transformSelectionLayer(delta)

    # -- binding to whichever project is currently active --------------

    def bindProject(self, projectController):
        if self._boundProjectController is not None:
            self._boundProjectController.selectionChanged.disconnect(self._refreshLayerStepper)
            self._boundProjectController.meshReady.disconnect(self._refreshLayerStepper)
        self._boundProjectController = projectController
        if projectController is not None:
            projectController.selectionChanged.connect(self._refreshLayerStepper)
            projectController.meshReady.connect(self._refreshLayerStepper)
        self._refreshLayerStepper()

    def _refreshLayerStepper(self):
        if self._boundProjectController is None:
            self._layerStepper.setText("-")
            return
        canvas = self._boundProjectController.project.canvas
        self._layerStepper.setText(selectionHeightText(canvas))
