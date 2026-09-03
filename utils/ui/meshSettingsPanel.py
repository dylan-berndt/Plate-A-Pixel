from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame
from PySide6.QtCore import QTimer

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
    not a delta.

    Every numeric field's controller call is debounced (_debounce below):
    the stepper's own text updates immediately off the local value for
    responsive feedback, but the actual CanvasController.setXxx() call -
    which pushes an undo snapshot and (for the mesh-geometry fields)
    kicks off ProjectController's own mesh-rebuild pipeline - only fires
    once DEBOUNCE_MS has passed with no further click on that same field.
    That's a separate debounce from ProjectController.MESH_DEBOUNCE_MS
    (which only delays when a queued rebuild actually *starts*
    computing): without this one, mashing a stepper's +/- still pushed
    one undo snapshot and queued one rebuild request per click, so undo
    would need as many steps to unwind a quick burst as clicks it took to
    make it."""

    MARGIN_STEP = 1
    CELL_STEP = 1.0
    # tubeMargin/wallThickness/bulgeSize are fractions of one grid cell
    # (world units, not mm - see Mesh.tubeMargin and friends), so they
    # need a much finer step than the millimeter-scale cell size fields.
    GEOMETRY_STEP = 0.01
    # The card's own available width for a row's label+stepper - measured
    # empirically from card.layout().contentsRect() rather than derived
    # from the rail width, card margins, and card padding alone: the
    # card's QSS border (see its QFrame#meshCard stylesheet) also eats
    # into the content rect on top of setContentsMargins, by an amount
    # Qt's box-model computes internally rather than exposing simply.
    CARD_CONTENT_WIDTH = 194

    DEBOUNCE_MS = 200

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
        self._debounceTimers = {}
        self._debouncePending = {}

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

    # The stepper's own natural width (2 buttons + value field + spacing -
    # see Stepper) - the label is capped to whatever's left of the card's
    # content width so it wraps instead of squeezing the stepper's
    # internal spacing (QHBoxLayout doesn't shrink a word-wrapped QLabel's
    # allocation on its own - it needs an explicit cap to actually wrap
    # rather than staying single-line and starving its neighbor).
    STEPPER_WIDTH = 108

    ROW_SPACING = 8

    def _addRow(self, layout, label, onIncrement, onDecrement):
        row = QHBoxLayout()
        row.setSpacing(self.ROW_SPACING)
        # A fixed width, not just a cap: with only a maximum, Qt's box
        # layouts still let this word-wrapped label's minimum-size
        # negotiation interact with (and sometimes compress) the Stepper
        # sitting next to it, since QHBoxLayout doesn't handle a
        # heightForWidth widget's sizing cleanly. Pinning both this and
        # the Stepper (see its own Fixed size policy) to exact widths that
        # sum to CARD_CONTENT_WIDTH removes any ambiguity for Qt to
        # resolve by shrinking one of them unpredictably.
        labelWidget = SectionLabel(label, theme=self._theme)
        labelWidget.setWordWrap(True)
        labelWidget.setFixedWidth(self.CARD_CONTENT_WIDTH - self.STEPPER_WIDTH - self.ROW_SPACING)
        row.addWidget(labelWidget)
        stepper = Stepper("", onIncrement=onIncrement, onDecrement=onDecrement, theme=self._theme)
        row.addWidget(stepper)
        layout.addLayout(row)
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

    def _debounce(self, key, commit):
        """Delays `commit` until DEBOUNCE_MS has passed with no further
        call under this same `key` - see the class docstring. `commit`
        replaces whatever was pending under `key` (so only the *latest*
        requested value for that field ever actually fires) rather than
        queuing, and a pending commit is flushed - not dropped - if the
        bound project changes before its timer elapses (see bindProject/
        _flushDebounce): it was a real edit the user made, just not
        committed yet."""
        self._debouncePending[key] = commit
        timer = self._debounceTimers.get(key)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(self.DEBOUNCE_MS)
            timer.timeout.connect(lambda k=key: self._fireDebounce(k))
            self._debounceTimers[key] = timer
        timer.start()

    def _fireDebounce(self, key):
        commit = self._debouncePending.pop(key, None)
        if commit is not None:
            commit()

    def _flushDebounce(self):
        for key, timer in self._debounceTimers.items():
            if timer.isActive():
                timer.stop()
                self._fireDebounce(key)

    def _setHollow(self, hollow):
        # Not debounced: a deliberate single click on a Solid/Hollow
        # toggle, not something ever mashed like a stepper's +/-.
        if self._boundProjectController is not None:
            self._boundProjectController.canvasController.setHollow(hollow)

    def _incrementMargin(self):
        self._setMargin(self._margin + self.MARGIN_STEP)

    def _decrementMargin(self):
        self._setMargin(max(0, self._margin - self.MARGIN_STEP))

    def _setMargin(self, value):
        self._margin = value
        self._marginStepper.setText(f"{value}")
        if self._boundProjectController is not None:
            controller = self._boundProjectController
            self._debounce("margin", lambda: controller.canvasController.setMargin(value))

    def _incrementWidth(self):
        self._setCellWidth(self._cellWidth + self.CELL_STEP)

    def _decrementWidth(self):
        self._setCellWidth(max(self.CELL_STEP, self._cellWidth - self.CELL_STEP))

    def _setCellWidth(self, value):
        self._cellWidth = value
        self._widthStepper.setText(f"{value:g} mm")
        if self._boundProjectController is not None:
            controller = self._boundProjectController
            self._debounce("cellWidth", lambda: controller.canvasController.setCellWidth(value))

    def _incrementHeight(self):
        self._setCellHeight(self._cellHeight + self.CELL_STEP)

    def _decrementHeight(self):
        self._setCellHeight(max(self.CELL_STEP, self._cellHeight - self.CELL_STEP))

    def _setCellHeight(self, value):
        self._cellHeight = value
        self._heightStepper.setText(f"{value:g} mm")
        if self._boundProjectController is not None:
            controller = self._boundProjectController
            self._debounce("cellHeight", lambda: controller.canvasController.setCellHeight(value))

    def _setTubeMargin(self, value):
        self._tubeMargin = value
        self._tubeMarginStepper.setText(f"{value:.2f}")
        if self._boundProjectController is not None:
            controller = self._boundProjectController
            self._debounce("tubeMargin", lambda: controller.canvasController.setTubeMargin(value))

    def _setWallThickness(self, value):
        self._wallThickness = value
        self._wallThicknessStepper.setText(f"{value:.2f}")
        if self._boundProjectController is not None:
            controller = self._boundProjectController
            self._debounce("wallThickness", lambda: controller.canvasController.setWallThickness(value))

    def _setBulgeSize(self, value):
        self._bulgeSize = value
        self._bulgeSizeStepper.setText(f"{value:.2f}")
        if self._boundProjectController is not None:
            controller = self._boundProjectController
            self._debounce("bulgeSize", lambda: controller.canvasController.setBulgeSize(value))

    # -- binding to whichever project is currently active ----------------

    def bindProject(self, projectController):
        # viewSettingsChanged covers cellWidth/cellHeight (editing(signal=...)
        # in CanvasController); hollow/baseMargin go through editing(affectsMesh=True)
        # instead, which never emits viewSettingsChanged - only meshInvalidated
        # now and meshReady once the background recompute finishes - so both
        # need to be watched for this panel to stay in sync.
        # Flush, not drop: a pending edit was a real click the user made
        # on the project we're about to leave - it should still land
        # there rather than vanish because a tab switch beat the debounce
        # window closing.
        self._flushDebounce()
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
