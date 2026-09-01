from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame

from .elements import SectionLabel, SegmentedControl, Stepper, Theme


class MeshSettingsPanel(QWidget):
    """The right rail's Mesh card: Solid/Hollow, base margin (cells), and
    the export-only cellWidth/cellHeight (mm) - see CanvasController's
    table in ARCHITECTURE.md for why cellWidth/cellHeight don't touch the
    mesh itself. Each Stepper owns a plain local value synced from
    ViewSettings on bindProject/viewSettingsChanged, since
    CanvasController's setters (setMargin, setCellWidth, setCellHeight)
    all take an absolute value, not a delta."""

    MARGIN_STEP = 1
    CELL_STEP = 1.0

    def __init__(self, theme: Theme = None, **kwargs):
        super().__init__(**kwargs)
        self._theme = theme or Theme()
        self._boundProjectController = None
        self._margin = 0
        self._cellWidth = 0.0
        self._cellHeight = 0.0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 0, 14, 16)
        outer.setSpacing(10)

        outer.addWidget(SectionLabel("Mesh", theme=self._theme))

        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background: {self._theme.paper}; border: 1.5px solid {self._theme.ink}; border-radius: 6px; }}"
        )
        cardLayout = QVBoxLayout(card)
        cardLayout.setContentsMargins(12, 12, 12, 12)
        cardLayout.setSpacing(12)

        self._hollowControl = SegmentedControl(
            {"Solid": False, "Hollow": True}, selected=False, onChange=self._setHollow, theme=self._theme,
        )
        cardLayout.addWidget(self._hollowControl)

        self._marginStepper = self._addRow(cardLayout, "Base margin", self._incrementMargin, self._decrementMargin)
        self._widthStepper = self._addRow(cardLayout, "Width", self._incrementWidth, self._decrementWidth)
        self._heightStepper = self._addRow(cardLayout, "Height", self._incrementHeight, self._decrementHeight)

        outer.addWidget(card)
        outer.addStretch(1)

    def _addRow(self, layout, label, onIncrement, onDecrement):
        row = QHBoxLayout()
        row.addWidget(SectionLabel(label, theme=self._theme), 1)
        stepper = Stepper("", onIncrement=onIncrement, onDecrement=onDecrement, theme=self._theme)
        row.addWidget(stepper)
        layout.addLayout(row)
        return stepper

    # -- edits -----------------------------------------------------------

    def _setHollow(self, hollow):
        if self._boundProjectController is not None:
            self._boundProjectController.canvasController.setHollow(hollow)

    def _incrementMargin(self):
        self._setMargin(self._margin + self.MARGIN_STEP)

    def _decrementMargin(self):
        self._setMargin(max(0, self._margin - self.MARGIN_STEP))

    def _setMargin(self, value):
        if self._boundProjectController is not None:
            self._boundProjectController.canvasController.setMargin(value)

    def _incrementWidth(self):
        self._setCellWidth(self._cellWidth + self.CELL_STEP)

    def _decrementWidth(self):
        self._setCellWidth(max(self.CELL_STEP, self._cellWidth - self.CELL_STEP))

    def _setCellWidth(self, value):
        if self._boundProjectController is not None:
            self._boundProjectController.canvasController.setCellWidth(value)

    def _incrementHeight(self):
        self._setCellHeight(self._cellHeight + self.CELL_STEP)

    def _decrementHeight(self):
        self._setCellHeight(max(self.CELL_STEP, self._cellHeight - self.CELL_STEP))

    def _setCellHeight(self, value):
        if self._boundProjectController is not None:
            self._boundProjectController.canvasController.setCellHeight(value)

    # -- binding to whichever project is currently active ----------------

    def bindProject(self, projectController):
        # viewSettingsChanged covers cellWidth/cellHeight (editing(signal=...)
        # in CanvasController); hollow/baseMargin go through editing(affectsMesh=True)
        # instead, which never emits viewSettingsChanged - only meshInvalidated
        # now and meshReady once the background recompute finishes - so both
        # need to be watched for this panel to stay in sync.
        if self._boundProjectController is not None:
            self._boundProjectController.viewSettingsChanged.disconnect(self._refresh)
            self._boundProjectController.meshReady.disconnect(self._refresh)
        self._boundProjectController = projectController
        if projectController is not None:
            projectController.viewSettingsChanged.connect(self._refresh)
            projectController.meshReady.connect(self._refresh)
        self._refresh()

    def _refresh(self):
        if self._boundProjectController is None:
            self._margin, self._cellWidth, self._cellHeight = 0, 0.0, 0.0
            self._marginStepper.setText("-")
            self._widthStepper.setText("-")
            self._heightStepper.setText("-")
            return

        settings = self._boundProjectController.project.viewSettings
        self._hollowControl.setValue(settings.hollow)
        self._margin = settings.baseMargin
        self._cellWidth = settings.cellWidth
        self._cellHeight = settings.cellHeight
        self._marginStepper.setText(f"{self._margin} cells")
        self._widthStepper.setText(f"{self._cellWidth:g} mm")
        self._heightStepper.setText(f"{self._cellHeight:g} mm")
