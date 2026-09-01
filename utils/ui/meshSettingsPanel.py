from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame

from .elements import SectionLabel, SegmentedControl, Stepper, Theme


class MeshSettingsPanel(QWidget):
    """The right rail's Mesh card: Solid/Hollow, base margin (cells), the
    export-only cellWidth/cellHeight (mm), and the structural geometry
    (tubeMargin/wallThickness/bulgeSize - fractions of a cell, see
    Mesh/pixelComponents.py) - see CanvasController's table in
    ARCHITECTURE.md for why cellWidth/cellHeight don't touch the mesh
    itself, unlike everything else here. Each Stepper owns a plain local
    value synced from ViewSettings on bindProject/viewSettingsChanged,
    since every CanvasController setter here takes an absolute value,
    not a delta."""

    MARGIN_STEP = 1
    CELL_STEP = 1.0
    # tubeMargin/wallThickness/bulgeSize are fractions of one grid cell
    # (world units, not mm - see Mesh.tubeMargin and friends), so they
    # need a much finer step than the millimeter-scale cell size fields.
    GEOMETRY_STEP = 0.01

    def __init__(self, theme: Theme = None, **kwargs):
        super().__init__(**kwargs)
        self._theme = theme or Theme()
        self._boundProjectController = None
        self._margin = 0
        self._cellWidth = 0.0
        self._cellHeight = 0.0
        self._tubeMargin = 0.0
        self._wallThickness = 0.0
        self._bulgeSize = 0.0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 0, 14, 16)
        outer.setSpacing(10)

        outer.addWidget(SectionLabel("Mesh", theme=self._theme))

        card = QFrame()
        # QLabel is itself a QFrame subclass in Qt, so a bare "QFrame {...}"
        # selector here would also match every SectionLabel (a QLabel) added
        # below - each one would pick up this card's own border/background,
        # rendering as a little pill around its text. objectName scopes the
        # rule to just this one frame.
        card.setObjectName("meshCard")
        card.setStyleSheet(
            f"QFrame#meshCard {{ background: {self._theme.paper}; border: 1.5px solid {self._theme.ink}; border-radius: 6px; }}"
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
        self._tubeMarginStepper = self._addFloatRow(
            cardLayout, "Tube margin", "_tubeMargin", self._setTubeMargin
        )
        self._wallThicknessStepper = self._addFloatRow(
            cardLayout, "Wall thickness", "_wallThickness", self._setWallThickness
        )
        self._bulgeSizeStepper = self._addFloatRow(
            cardLayout, "Bulge size", "_bulgeSize", self._setBulgeSize
        )

        outer.addWidget(card)
        outer.addStretch(1)

    def _addRow(self, layout, label, onIncrement, onDecrement):
        # Label above the stepper, not beside it: the card's fixed width
        # (matching the mockup's right rail) is too narrow for a label
        # like "Wall thickness" to share a row with a stepper without
        # squeezing the stepper below its own minimum size, clipping its
        # value text against the + button. Stacking gives each the full
        # card width instead of competing for it.
        column = QVBoxLayout()
        column.setSpacing(4)
        column.addWidget(SectionLabel(label, theme=self._theme))

        stepper = Stepper("", onIncrement=onIncrement, onDecrement=onDecrement, theme=self._theme)
        stepperRow = QHBoxLayout()
        stepperRow.addWidget(stepper)
        stepperRow.addStretch(1)
        column.addLayout(stepperRow)

        layout.addLayout(column)
        return stepper

    def _addFloatRow(self, layout, label, attrName, setter):
        """A row for one of the GEOMETRY_STEP-sized fractional-cell
        settings (tubeMargin/wallThickness/bulgeSize) - same shape as
        _addRow's margin/width/height rows, just generic over which
        local attribute it steps and which CanvasController setter it
        calls, since all three only differ in name."""
        def increment():
            setter(getattr(self, attrName) + self.GEOMETRY_STEP)

        def decrement():
            setter(max(0.0, getattr(self, attrName) - self.GEOMETRY_STEP))

        return self._addRow(layout, label, increment, decrement)

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

    def _setTubeMargin(self, value):
        if self._boundProjectController is not None:
            self._boundProjectController.canvasController.setTubeMargin(value)

    def _setWallThickness(self, value):
        if self._boundProjectController is not None:
            self._boundProjectController.canvasController.setWallThickness(value)

    def _setBulgeSize(self, value):
        if self._boundProjectController is not None:
            self._boundProjectController.canvasController.setBulgeSize(value)

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
            self._tubeMargin, self._wallThickness, self._bulgeSize = 0.0, 0.0, 0.0
            for stepper in (
                self._marginStepper, self._widthStepper, self._heightStepper,
                self._tubeMarginStepper, self._wallThicknessStepper, self._bulgeSizeStepper,
            ):
                stepper.setText("-")
            return

        settings = self._boundProjectController.project.viewSettings
        self._hollowControl.setValue(settings.hollow)
        self._margin = settings.baseMargin
        self._cellWidth = settings.cellWidth
        self._cellHeight = settings.cellHeight
        self._tubeMargin = settings.tubeMargin
        self._wallThickness = settings.wallThickness
        self._bulgeSize = settings.bulgeSize
        self._marginStepper.setText(f"{self._margin}")
        self._widthStepper.setText(f"{self._cellWidth:g} mm")
        self._heightStepper.setText(f"{self._cellHeight:g} mm")
        self._tubeMarginStepper.setText(f"{self._tubeMargin:.2f}")
        self._wallThicknessStepper.setText(f"{self._wallThickness:.2f}")
        self._bulgeSizeStepper.setText(f"{self._bulgeSize:.2f}")
