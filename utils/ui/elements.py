from PySide6.QtWidgets import (
    QLabel, QLineEdit, QSlider, QPushButton, QComboBox, QDialog, QWidget, QGridLayout,
    QHBoxLayout, QVBoxLayout, QButtonGroup, QSizePolicy,
)
from PySide6.QtCore import Qt, QSize, QByteArray, Signal
from PySide6.QtGui import QPixmap, QPainter, QIcon, QColor
from PySide6.QtSvg import QSvgRenderer
from .base import *
from .nineSlice import NineSliceFrame, sharedNineSlice, STANDARD_SCALE


class Text(QLabel):
    def __init__(self, text, **kwargs):
        super().__init__(text, **kwargs)
        self.setAlignment(Qt.AlignCenter)

    def setStyleSheet(self, styleSheet):
        # QLabel is itself a QFrame subclass, and Qt auto-enables
        # WA_StyledBackground the instant any per-instance stylesheet is
        # set on a widget - without an explicit background property, it
        # then paints an opaque fill from the inherited palette instead
        # of staying transparent (this is exactly what made SectionLabel/
        # MonoText render as a filled pill once nested inside a bordered
        # QFrame card - see MeshSettingsPanel). Every Text subclass here
        # only ever styles font/color, so default to transparent unless
        # the caller's own sheet says otherwise.
        if "background" not in styleSheet:
            styleSheet = f"background: transparent; {styleSheet}"
        super().setStyleSheet(styleSheet)


class SectionLabel(Text):
    """A small uppercase, letter-spaced heading - "LAYER"/"PALETTE"/"MESH"
    in the mockup's rails. QSS has no letter-spacing property, so this
    just uppercases the text itself and leans on font size/weight/color
    for the same "quiet heading" effect."""

    def __init__(self, text, theme: Theme = None, **kwargs):
        super().__init__(text.upper(), **kwargs)
        theme = theme or Theme()
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {theme.clay800};")


class MonoText(Text):
    """A monospace readout - RGB triples, coordinates, the layer-height
    number - anywhere the mockup uses Space Mono for a value rather than a
    label."""

    def __init__(self, text, theme: Theme = None, **kwargs):
        super().__init__(text, **kwargs)
        theme = theme or Theme()
        self.setStyleSheet(f"font-family: '{theme.monoFontFamily}'; font-size: 11px;")


class TextInput(QLineEdit):
    def __init__(self, placeholder="", **kwargs):
        super().__init__(**kwargs)
        self.setPlaceholderText(placeholder)


class Slider(QSlider):
    def __init__(self, values: tuple, handleValue, defaultValue=None, **kwargs):
        super().__init__(Qt.Horizontal, **kwargs)
        self.setMinimum(values[0])
        self.setMaximum(values[1])
        self.setValue(values[0] if defaultValue is None else defaultValue)

        self.handleValue = handleValue
        self.valueChanged.connect(self.handleValue)


class Image(QLabel):
    def __init__(self, pixmap: QPixmap, **kwargs):
        super().__init__(**kwargs)
        self.setPixmap(pixmap)


class Button(QPushButton):
    def __init__(self, onClick, **kwargs):
        super().__init__(**kwargs)

        self.onClick = onClick
        self.clicked.connect(self.onClick)

    # Kept to mirror the old Button(...).add(Text(...)) call pattern from
    # main.py; a QPushButton just takes its label as text directly.
    def add(self, element: QLabel):
        self.setText(element.text())
        return self


class Dropdown(QComboBox):
    """A longer options dropdown (buildOptionWidget falls back to this
    past 4 choices - see its own note; nothing built into a real tool
    uses it yet). The closed field's border is the app's nine-slice art
    instead of QSS; the popup list itself stays native like every other
    Qt popup this app doesn't reach into (QMenu's dropdown is the one
    exception - see menuBar.py's ThemedMenu)."""

    def __init__(self, options: dict, theme: Theme = None, **kwargs):
        super().__init__(**kwargs)
        theme = theme or Theme()
        for label, value in options.items():
            self.addItem(label, value)
        self._nineSlice = sharedNineSlice()
        t = self._nineSlice.borderThickness(STANDARD_SCALE)
        self.setStyleSheet(
            f"QComboBox {{ background: transparent; border: none; padding: 2px {t + 18}px 2px {t + 4}px; }}"
        )
        self._backgroundColor = QColor(theme.paper)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        t = self._nineSlice.borderThickness(STANDARD_SCALE)
        painter.fillRect(self.rect().adjusted(t, t, -t, -t), self._backgroundColor)
        self._nineSlice.paint(painter, self.rect(), STANDARD_SCALE)
        painter.end()
        super().paintEvent(event)


class Popup(QDialog):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class Grid(QWidget):
    def __init__(self, margins=(0, 0, 0, 0), **kwargs):
        super().__init__(**kwargs)

        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(*margins)

    def add(self, element: QWidget, position, size):
        self._layout.addWidget(element, position[1], position[0], size[1], size[0])
        return self


# -- icons -----------------------------------------------------------------
# Icons are inline SVG path/line/etc markup (the same viewBox="0 0 24 24",
# stroke-based style design/ui-mockup.html uses) rather than bundled image
# files, so a color swap is just a re-render, not a second asset per state.

def renderSvgIcon(bodyMarkup: str, color: str, size: int = 24) -> QPixmap:
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="none" stroke="{color}" stroke-width="1.6" '
        f'stroke-linecap="round" stroke-linejoin="round">{bodyMarkup}</svg>'
    )
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


class Icons:
    """Inner-SVG markup (no outer <svg> tag) for every icon the view layer
    needs, lifted from design/ui-mockup.html so a rail button and its
    mockup counterpart draw the same glyph."""

    WAND = '<line x1="5" y1="19" x2="12.3" y2="11.7"/><path d="M17 4 L17 7 M15.5 5.5 L18.5 5.5"/><path d="M20 9.5 L20 11.5 M19 10.5 L21 10.5"/><circle cx="14" cy="9" r="0.9" fill="currentColor" stroke="none"/>'
    BRUSH = '<path d="M6 9 C6 7.2 18 7.2 18 9 L16 17 C16 18.4 8 18.4 8 17 Z"/><circle cx="12" cy="20.3" r="1.3" fill="currentColor" stroke="none"/>'
    CHECK = '<path d="M4 12 L9 17 L20 5"/>'
    UNDO = '<path d="M7 7 L4 10 L7 13"/><path d="M4 10 H14 C17 10 19 12 19 15 C19 18 17 20 14 20 H10"/>'
    REDO = '<path d="M17 7 L20 10 L17 13"/><path d="M20 10 H10 C7 10 5 12 5 15 C5 18 7 20 10 20 H14"/>'
    PLUS = '<path d="M12 5 V19 M5 12 H19"/>'
    CLOSE = '<path d="M6 6 L18 18 M18 6 L6 18"/>'
    EXPAND = '<path d="M4 9 V4 H9 M15 4 H20 V9 M20 15 V20 H15 M9 20 H4 V15"/>'
    PENCIL = '<path d="M4 20 L4.5 16.5 L15 6 L18 9 L7.5 19.5 Z"/><line x1="13" y1="8" x2="16" y2="11"/>'
    DOWNLOAD = '<path d="M12 4 V15 M7 11 L12 16 L17 11"/><path d="M5 19 H19"/>'
    EYE_OFF = '<path d="M3 3 L21 21"/><path d="M9.5 5.5 C13.5 4.5 18 7 21 12 C19.8 14.1 18.3 15.7 16.6 16.8 M6.8 7.6 C4.9 8.9 3.4 10.7 3 12 C5.5 16.5 9 19 12 19 C13 19 14 18.8 15 18.4"/><path d="M9.8 10 C9.3 10.5 9 11.2 9 12 C9 13.7 10.3 15 12 15 C12.8 15 13.5 14.7 14 14.2"/>'


class IconButton(QPushButton):
    """A square, icon-only button. Renders the given icon body in ink when
    off and paper when on (checked) so a checkable rail button reads
    correctly against its own highlighted background - see the active
    Wand button in the mockup's tool rail.

    `bordered=True` (the default) paints a pixel-art nine-slice border/
    background instead of QSS's border/border-radius, matching the rest
    of the app's chrome (see NineSliceFrame's own note on why QSS's
    anti-aliased border-radius doesn't work for pixel art). The few
    "ghost" icon buttons that sit inline in other rows/bars (a palette
    row's edit pencil, a tab's close X, the tab bar's own "+") pass
    `bordered=False` to keep their existing plain, borderless look
    instead."""

    def __init__(self, iconBody: str, onClick=None, checkable: bool = False, size: int = 40,
                 activeColor: str = None, iconColor: str = None, iconColorOn: str = None,
                 theme: Theme = None, bordered: bool = True, borderScale: int = STANDARD_SCALE, **kwargs):
        super().__init__(**kwargs)
        theme = theme or Theme()
        activeColor = activeColor or theme.glaze
        iconColor = iconColor or theme.ink
        iconColorOn = iconColorOn or theme.paper

        self.setCheckable(checkable)
        self.setFixedSize(size, size)

        iconSize = max(10, int(size * 0.42))
        icon = QIcon()
        icon.addPixmap(renderSvgIcon(iconBody, iconColor, iconSize), QIcon.Normal, QIcon.Off)
        icon.addPixmap(renderSvgIcon(iconBody, iconColorOn, iconSize), QIcon.Normal, QIcon.On)
        self.setIcon(icon)
        self.setIconSize(QSize(iconSize, iconSize))

        # Either way, QSS itself draws nothing: bordered paints its own
        # background/border in paintEvent below (so QSS must stay out of
        # the way), and ghost buttons were always meant to be fully
        # transparent with no border of their own.
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")

        self._bordered = bordered
        if bordered:
            self._nineSlice = sharedNineSlice()
            self._borderScale = borderScale
            self._paperColor = QColor(theme.paper)
            self._hoverColor = QColor(theme.clay200)
            self._activeColor = QColor(activeColor)

        if onClick is not None:
            self.clicked.connect(onClick)

    def paintEvent(self, event):
        if self._bordered:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing, False)
            if self.isChecked():
                color = self._activeColor
            elif self.underMouse():
                color = self._hoverColor
            else:
                color = self._paperColor
            t = self._nineSlice.borderThickness(self._borderScale)
            painter.fillRect(self.rect().adjusted(t, t, -t, -t), color)
            self._nineSlice.paint(painter, self.rect(), self._borderScale)
            painter.end()
        super().paintEvent(event)

    def enterEvent(self, event):
        super().enterEvent(event)
        if self._bordered:
            self.update()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if self._bordered:
            self.update()


class _NineSliceButtonBase(QPushButton):
    """Shared paint plumbing for every other QPushButton in the app that
    draws its own pixel-art nine-slice border/background rather than
    relying on QSS - PillToggle, the Stepper +/- buttons, NineSliceButton,
    and ViewModeTabs' buttons all subclass this. (IconButton doesn't -
    its bordered=False escape hatch needs paintEvent to do nothing at
    all, which doesn't fit this base's assume-always-bordered paintEvent
    cleanly enough to be worth forcing.) A subclass only has to answer
    _fillColor() (which color to paint behind the border for its current
    state) and set its own QSS to transparent background/no border plus
    whatever text/font rules it needs - paintEvent/enterEvent/leaveEvent
    here are otherwise identical for all of them."""

    def __init__(self, *args, borderScale: int = STANDARD_SCALE, **kwargs):
        super().__init__(*args, **kwargs)
        self._nineSlice = sharedNineSlice()
        self._borderScale = borderScale

    def _fillColor(self) -> QColor:
        raise NotImplementedError

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        t = self._nineSlice.borderThickness(self._borderScale)
        painter.fillRect(self.rect().adjusted(t, t, -t, -t), self._fillColor())
        self._nineSlice.paint(painter, self.rect(), self._borderScale)
        painter.end()
        super().paintEvent(event)

    def enterEvent(self, event):
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.update()


# -- grouped controls --------------------------------------------------------

class SegmentedControl(QWidget):
    """A row of mutually-exclusive text buttons sharing one outer border -
    Wand's Replace/Add/Sub/Int, the Mesh panel's Solid/Hollow. Built off a
    plain {label: value} dict so it can render a "dropdown"-typed Options
    schema entry (see buildOptionWidget below) as well as be used
    directly."""

    def __init__(self, options: dict, selected=None, onChange=None, theme: Theme = None, **kwargs):
        super().__init__(**kwargs)
        theme = theme or Theme()
        self.onChange = onChange

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # A NineSliceFrame (assets/slice.png), not a QFrame with a QSS
        # border/border-radius - see the identical note on
        # MeshSettingsPanel's card for why (hard pixel-art corners, and no
        # stylesheet here for a child QLabel to accidentally inherit).
        # backgroundColor is only ever visible at the four corner notches
        # cut by the rounded border art (the buttons below fill the rest
        # of the frame edge-to-edge) - theme.paper matches every context
        # this control is actually used in.
        frame = NineSliceFrame(theme.paper, scale=2)
        layout = QHBoxLayout(frame)
        frameBorder = frame.borderThickness()
        layout.setContentsMargins(1 + frameBorder, 1 + frameBorder, 1 + frameBorder, 1 + frameBorder)
        layout.setSpacing(0)
        outer.addWidget(frame)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons = {}
        for label, value in options.items():
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(value == selected)
            btn.setFlat(True)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {theme.paper}; color: {theme.clay800}; border: none;
                    padding: 5px 11px; font-size: 10.5px; font-weight: 700;
                }}
                QPushButton:checked {{ background: {theme.glaze}; color: {theme.paper}; }}
            """)
            btn.clicked.connect(lambda checked, v=value: self._select(v))
            layout.addWidget(btn)
            self._group.addButton(btn)
            self._buttons[value] = btn

    def _select(self, value):
        if self.onChange is not None:
            self.onChange(value)

    def setValue(self, value):
        btn = self._buttons.get(value)
        if btn is not None:
            btn.setChecked(True)


class PillToggle(_NineSliceButtonBase):
    """A checkable toggle - Wand's Contiguous/Diagonal toggles. Square,
    not an actual pill, despite the name (kept for the call sites/tests
    that already refer to it) - painted with the same pixel-art
    nine-slice border as every other bordered button in the app now."""

    def __init__(self, label: str, checked: bool = False, onToggle=None, theme: Theme = None, **kwargs):
        super().__init__(label, **kwargs)
        theme = theme or Theme()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none; color: {theme.clay800};
                padding: 5px 12px; font-size: 10.5px; font-weight: 600;
            }}
            QPushButton:checked {{ color: {theme.paper}; }}
        """)
        self._offColor = QColor(theme.clay200)
        self._onColor = QColor(theme.glazeDark)
        if onToggle is not None:
            self.toggled.connect(onToggle)

    def _fillColor(self):
        return self._onColor if self.isChecked() else self._offColor


class NineSliceButton(_NineSliceButtonBase):
    """A plain bordered text button - Settings' Reset/Close, Export's
    Cancel/Export/Choose Location... - painted with the app's nine-slice
    border instead of Theme.stylesheet()'s native QSS fallback, which
    stays in place only for genuinely native dialogs (QMessageBox and
    friends) this class doesn't reach into."""

    def __init__(self, text: str, onClick=None, theme: Theme = None, **kwargs):
        super().__init__(text, **kwargs)
        theme = theme or Theme()
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none; color: {theme.ink};
                padding: 6px 14px;
            }}
        """)
        self._paperColor = QColor(theme.paper)
        self._hoverColor = QColor(theme.clay200)
        self._pressedColor = QColor(theme.clay300)
        if onClick is not None:
            self.clicked.connect(onClick)

    def _fillColor(self):
        if self.isDown():
            return self._pressedColor
        if self.underMouse():
            return self._hoverColor
        return self._paperColor


class NineSliceLineEdit(QLineEdit):
    """A QLineEdit bordered with the app's nine-slice art instead of QSS -
    Export's destination-folder field. PaletteRow's inline rename field
    stays genuinely borderless on purpose (see its own note there), so
    it doesn't use this."""

    def __init__(self, text: str = "", theme: Theme = None, **kwargs):
        super().__init__(text, **kwargs)
        theme = theme or Theme()
        self.setFrame(False)
        self._nineSlice = sharedNineSlice()
        t = self._nineSlice.borderThickness(STANDARD_SCALE)
        self.setStyleSheet("QLineEdit { background: transparent; border: none; padding: 3px; }")
        self.setTextMargins(t + 2, t, t + 2, t)
        self._backgroundColor = QColor(theme.paper)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        t = self._nineSlice.borderThickness(STANDARD_SCALE)
        painter.fillRect(self.rect().adjusted(t, t, -t, -t), self._backgroundColor)
        self._nineSlice.paint(painter, self.rect(), STANDARD_SCALE)
        painter.end()
        super().paintEvent(event)


class _StepperButton(_NineSliceButtonBase):
    """A -/+ button - see _NineSliceButtonBase for the shared paint
    plumbing. Kept private: this button shows text, not an icon, and has
    no checked/active state to track, so it doesn't fit IconButton."""

    def __init__(self, text: str, theme: Theme, **kwargs):
        super().__init__(text, **kwargs)
        self.setStyleSheet("QPushButton { background: transparent; border: none; font-size: 12px; padding: 0; }")
        self._paperColor = QColor(theme.paper)
        self._hoverColor = QColor(theme.clay200)

    def _fillColor(self):
        return self._hoverColor if self.underMouse() else self._paperColor


class Stepper(QWidget):
    """The "− value +" control used throughout the mockup's right rail
    (base margin, cell width/height) and the tool rail (layer height).
    Purely presentational - it doesn't own a numeric value itself, since
    the layer-height stepper's "value" isn't something the view can own
    (CanvasController.transformSelectionLayer only takes a relative delta;
    the displayed number is derived from canvas.layers over the current
    selection by whoever wires this up). Callers needing an owned value
    (base margin, cell width/height) track it themselves and call
    setText() after every change."""

    def __init__(self, text: str = "", onIncrement=None, onDecrement=None, theme: Theme = None,
                 vertical: bool = False, **kwargs):
        super().__init__(**kwargs)
        theme = theme or Theme()

        # Fixed, not the QWidget default Preferred: a -/value/+ control
        # reads as broken if it's ever narrower than its own contents (the
        # value text creeping under the + button) - it should never be
        # the thing that gives when a row runs short on space; a sibling
        # label should shrink/wrap first (see MeshSettingsPanel._addRow).
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        layout = QVBoxLayout(self) if vertical else QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4 if vertical else 6)

        self._minus = _StepperButton("−", theme)
        self._plus = _StepperButton("+", theme)
        buttonSize = 40 if vertical else 20
        for button in (self._minus, self._plus):
            button.setFixedSize(buttonSize, 20 if vertical else 20)

        self._label = MonoText(text, theme=theme)
        # Wide enough for "0.12"/"40 mm"-shaped values even when the
        # intended Space Mono font isn't installed and Qt substitutes a
        # wider fallback (no bundled font files - see Theme's docstring).
        self._label.setMinimumWidth(40 if vertical else 56)

        if onDecrement is not None:
            self._minus.clicked.connect(onDecrement)
        if onIncrement is not None:
            self._plus.clicked.connect(onIncrement)

        # Vertical order matches the mockup's tool rail: + on top, value,
        # then - below - not the horizontal -/value/+ reading order.
        order = (self._plus, self._label, self._minus) if vertical else (self._minus, self._label, self._plus)
        for widget in order:
            layout.addWidget(widget)

    def setText(self, text: str):
        self._label.setText(text)


class PaletteRow(QWidget):
    """One entry in the palette rail: a color swatch, an editable name
    field (renaming is the common case, so it's inline rather than a
    separate rename affordance), and the RGB readout. `color` is an
    (r, g, b) triple."""

    # Locked, not left to sizeHint(): every row's natural height already
    # comes out the same (same swatch size, same two-line text stack), but
    # nothing enforced that - a future change to any child (e.g. name text
    # wrapping) could make one row taller than its neighbors. An explicit
    # fixed height also gives PaletteRail's scroll area a stable per-row
    # size to lay rows out against.
    ROW_HEIGHT = 30

    def __init__(self, color, name: str = "", onRename=None, onEditColor=None, theme: Theme = None, **kwargs):
        super().__init__(**kwargs)
        theme = theme or Theme()
        self.setFixedHeight(self.ROW_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(7)

        r, g, b = (int(c) for c in color)
        swatch = NineSliceFrame(f"#{r:02x}{g:02x}{b:02x}", scale=STANDARD_SCALE)
        swatch.setFixedSize(18, 18)
        layout.addWidget(swatch)

        textColumn = QVBoxLayout()
        textColumn.setContentsMargins(0, 0, 0, 0)
        textColumn.setSpacing(0)

        self._nameEdit = QLineEdit(name)
        self._nameEdit.setPlaceholderText("Unnamed")
        # QLineEdit:focus needs its own explicit rule - the base
        # (unfocused) "background: transparent" above doesn't carry over
        # once focused, so clicking into the field to rename a color
        # revealed a plain white/paper focus background otherwise.
        self._nameEdit.setStyleSheet(f"""
            QLineEdit {{
                border: none; background: transparent;
                font-size: 10.5px; font-weight: 600; padding: 0;
            }}
            QLineEdit:focus {{ border: none; background: transparent; }}
        """)
        if onRename is not None:
            self._nameEdit.editingFinished.connect(lambda: onRename(self._nameEdit.text()))
        textColumn.addWidget(self._nameEdit)

        rgbLabel = MonoText(f"{r}, {g}, {b}", theme=theme)
        rgbLabel.setAlignment(Qt.AlignLeft)
        rgbLabel.setStyleSheet(f"font-family: '{theme.monoFontFamily}'; font-size: 8px; color: {theme.clay800};")
        textColumn.addWidget(rgbLabel)

        textContainer = QWidget()
        textContainer.setLayout(textColumn)
        layout.addWidget(textContainer, 1)

        if onEditColor is not None:
            editButton = IconButton(Icons.PENCIL, onClick=onEditColor, size=16, theme=theme, bordered=False)
            layout.addWidget(editButton)

    def name(self):
        return self._nameEdit.text()

    def setName(self, name: str):
        self._nameEdit.setText(name)


class _ViewModeButton(_NineSliceButtonBase):
    """One Canvas/Layer/Mesh button in ViewModeTabs - see
    _NineSliceButtonBase for the shared paint plumbing. Active/hover/
    default just pick a different fill color, same as every other
    bordered button in the app; text color still needs its own QSS
    since _fillColor() only controls the background."""

    def __init__(self, text: str, theme: Theme, **kwargs):
        super().__init__(text, **kwargs)
        self._theme = theme
        self._active = False
        self.setCursor(Qt.PointingHandCursor)
        self._applyTextStyle()

    def setActive(self, active: bool):
        self._active = active
        self._applyTextStyle()
        self.update()

    def _applyTextStyle(self):
        theme = self._theme
        color = theme.ink if self._active else theme.paper
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none; color: {color};
                font-size: 10.5px; font-weight: 700; padding: 0 14px;
            }}
        """)

    def _fillColor(self):
        theme = self._theme
        if self._active:
            return QColor(theme.paper)
        if self.underMouse():
            return QColor(theme.clay600)
        return QColor(theme.clay800)


class ViewModeTabs(QWidget):
    """The small "2D"/"3D" switcher pinned to the work area's top-left
    corner (see AppWindow), floating on top of the canvas/mesh panes
    rather than laid out beside them - the caller parents this to the
    work area and positions/raises it, this class just renders and
    reports clicks. Its buttons paint the same pixel-art nine-slice
    border as everything else in the app now (see _ViewModeButton) -
    square corners, same width, no QSS border of its own.

    Not built on Tab/TabBar: those are one-per-open-project (dirty dot,
    close button, unbounded count) - this is a fixed two-entry mode
    switch, so reusing them would mean stripping more than it'd share.

    Deliberately has no background/border of its own - only the buttons
    are styled, so nothing shows here but their own bordered shapes
    floating directly over whatever pane is behind them. (No
    WA_StyledBackground, and none should be added: setting that
    attribute makes a plain QWidget start painting a background from the
    app's stylesheet even with no per-instance stylesheet of its own -
    see the identical note on Text.setStyleSheet - which is exactly the
    unwanted opaque rectangle around the tabs this class used to have.)

    Not placed in a parent layout (the caller floats and positions it
    with move()/raise_()), so nothing ever resizes it to fit its buttons
    automatically the way a layout-managed widget would - adjustSize()
    at the end of __init__ does that once, explicitly; without it this
    widget stays at whatever default size a bare QWidget starts with,
    regardless of its buttons' actual content."""

    def __init__(self, modes=("2D", "3D"), active=None, onChange=None, theme: Theme = None, **kwargs):
        super().__init__(**kwargs)
        theme = theme or Theme()
        self._theme = theme
        self._onChange = onChange
        self._active = active if active is not None else modes[0]

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Plain (non-checkable) buttons, not a QButtonGroup of checkables -
        # a checkable button toggles itself off on a second click, which
        # would let the user click the active tab into an unselected
        # state; restyling by hand on every click sidesteps that instead
        # of fighting Qt's default toggle behavior.
        self._buttons = {}
        for mode in modes:
            button = _ViewModeButton(mode, theme)
            # Height fixed for a consistent tab strip; width left to
            # QPushButton's own sizeHint (text plus the QSS padding
            # below) rather than a shared fixed size tuned for "2D"/"3D" -
            # that clipped/cramped longer labels like "Canvas"/"Mesh".
            button.setFixedHeight(28)
            button.clicked.connect(lambda checked=False, m=mode: self._select(m))
            layout.addWidget(button)
            self._buttons[mode] = button

        self._applyStyles()
        # See the class docstring - this widget floats outside any parent
        # layout, so it never gets auto-sized to its content otherwise.
        self.adjustSize()

    def showEvent(self, event):
        super().showEvent(event)
        # Re-adjust on first real show, not just at construction: some
        # styles/platforms don't finish resolving an instance stylesheet's
        # font metrics until the widget is actually polished for display,
        # which can leave the construction-time adjustSize() sized off an
        # only-provisional sizeHint.
        self.adjustSize()

    def _applyStyles(self):
        for mode, button in self._buttons.items():
            button.setActive(mode == self._active)

    def _select(self, mode):
        if mode != self._active:
            self._active = mode
            self._applyStyles()
            if self._onChange is not None:
                self._onChange(mode)

    def setActive(self, mode):
        if mode in self._buttons and mode != self._active:
            self._active = mode
            self._applyStyles()


DIRTY_MARK = "●"  # BLACK CIRCLE - the unsaved-changes dot next to a tab's project name


class Tab(QWidget):
    """One project tab. `dirty` shows the unicode dot mark next to the
    project's name (ProjectController.isDirty); `active` styles it like
    the mockup's foregrounded tab."""

    def __init__(self, label: str, active: bool = False, dirty: bool = False,
                 onSelect=None, onClose=None, theme: Theme = None, **kwargs):
        super().__init__(**kwargs)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._theme = theme or Theme()
        self._active = active
        self._onSelect = onSelect

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(6)

        self._label = Text(label)
        self._label.setStyleSheet("font-size: 11.5px; font-weight: 600;")
        layout.addWidget(self._label)

        self._dirtyMark = Text(DIRTY_MARK if dirty else "")
        self._dirtyMark.setFixedWidth(10)
        layout.addWidget(self._dirtyMark)

        if onClose is not None:
            closeIconColor = self._theme.ink if active else self._theme.paper
            closeButton = IconButton(
                Icons.CLOSE, onClick=onClose, size=16, iconColor=closeIconColor, theme=self._theme,
                bordered=False,
            )
            layout.addWidget(closeButton)

        self._applyStyle()

    def _applyStyle(self):
        theme = self._theme
        if self._active:
            self.setStyleSheet(f"background: {theme.clay100}; color: {theme.ink};")
        else:
            self.setStyleSheet(f"background: {theme.clay800}; color: {theme.paper};")
            self._label.setStyleSheet("font-size: 11.5px; font-weight: 600; color: " + theme.paper + ";")

    def setActive(self, active: bool):
        self._active = active
        self._applyStyle()

    def setDirty(self, dirty: bool):
        self._dirtyMark.setText(DIRTY_MARK if dirty else "")

    def mousePressEvent(self, event):
        if self._onSelect is not None:
            self._onSelect()
        super().mousePressEvent(event)


class TabBar(QWidget):
    """The project-tab strip. `setTabs` takes the full list of
    (label, active, dirty) tuples and rebuilds; call it from
    AppController.projectOpened/projectClosed/activeProjectChanged. A
    dirty-only refresh (no structural change) can go through setDirty
    instead of a full rebuild."""

    def __init__(self, onSelect=None, onClose=None, onNewTab=None, theme: Theme = None, **kwargs):
        super().__init__(**kwargs)
        self._theme = theme or Theme()
        self._onSelect = onSelect
        self._onClose = onClose
        self._tabs = []

        # So the strip reads as one continuous bar (matching an inactive
        # tab's own background) instead of showing the app's default
        # background through any gap - the trailing space before/after
        # the "+" button in particular.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background: {self._theme.clay800};")

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._layout.setAlignment(Qt.AlignLeft)

        # Sits directly on TabBar's own dark background (see above), not a
        # light card, so its icon needs the light/dark swap Tab's own
        # close button gets for the same reason.
        self._newTabButton = IconButton(
            Icons.PLUS, onClick=onNewTab, size=30, iconColor=self._theme.paper, theme=self._theme,
            bordered=False,
        )

    def setTabs(self, entries):
        """entries: list of (label, active, dirty)."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            # deleteLater(), not setParent(None) - see the identical note
            # in PaletteRail._rebuild. Not identical in one way that
            # matters, though: unlike that layout (which only ever holds
            # disposable rows), this one also holds _newTabButton, a
            # single persistent widget re-added at the end of every call
            # rather than recreated - deleteLater()-ing it here too would
            # still let it be re-added lower down in *this* call (the
            # actual deletion is deferred to the next event-loop tick),
            # but the very next setTabs() call would be reusing a Python
            # wrapper around an already-destroyed C++ object, raising
            # "Internal C++ object already deleted" the moment it's
            # touched again (addWidget, or this same deleteLater()).
            if widget is not None and widget is not self._newTabButton:
                widget.deleteLater()

        self._tabs = []
        for index, (label, active, dirty) in enumerate(entries):
            tab = Tab(
                label, active=active, dirty=dirty,
                # Tab calls onSelect directly in mousePressEvent (no Qt
                # signal involved), so no bool ever lands in `i` there.
                # onClose does reach IconButton.clicked though, which
                # passes its checked:bool positionally to any connected
                # callable declaring a parameter - the leading `checked`
                # absorbs that so `i` still falls through to its default
                # (see the identical note in PaletteRail._rebuild).
                onSelect=(lambda i=index: self._onSelect(i)) if self._onSelect else None,
                onClose=(lambda checked=False, i=index: self._onClose(i)) if self._onClose else None,
                theme=self._theme,
            )
            self._layout.addWidget(tab)
            self._tabs.append(tab)
        self._layout.addWidget(self._newTabButton)

    def setDirty(self, index: int, dirty: bool):
        if 0 <= index < len(self._tabs):
            self._tabs[index].setDirty(dirty)


# -- Options-schema-driven controls -----------------------------------------

def buildOptionWidget(option, currentValue, onChange, theme: Theme = None):
    """Builds the right widget for one Tool Options entry (see
    utils/tools/tool.py's Options dataclass) generically off its
    optionType, so a new tool's options bar never needs hand-written UI -
    only a schema. A "dropdown" with a handful of choices (Wand's 4-way
    selection mode) reads better as a SegmentedControl than an actual
    combo box, matching the mockup; a longer dropdown falls back to a
    real one."""
    theme = theme or Theme()

    if option.optionType == "dropdown":
        if len(option.options) <= 4:
            return SegmentedControl(option.options, selected=currentValue, onChange=onChange, theme=theme)
        dropdown = Dropdown(option.options, theme=theme)
        index = dropdown.findData(currentValue)
        if index >= 0:
            dropdown.setCurrentIndex(index)
        dropdown.currentIndexChanged.connect(lambda i: onChange(dropdown.itemData(i)))
        return dropdown

    if option.optionType == "checkbox":
        return PillToggle(option.name, checked=bool(currentValue), onToggle=onChange, theme=theme)

    if option.optionType == "slider":
        # One row - label, slider, value field - not stacked, so this
        # option never changes the tool options bar's height relative to
        # any other option type (a dropdown/checkbox row and a slider row
        # used to be different heights, which made the whole window
        # resize - and the tool rail along with it, since it has no fixed
        # height of its own - just from switching tools).
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(SectionLabel(option.name, theme=theme))

        bounds = (option.options.get("Minimum", 0), option.options.get("Maximum", 100))
        slider = Slider(bounds, onChange, defaultValue=currentValue)
        layout.addWidget(slider)

        valueField = TextInput()
        valueField.setFixedWidth(36)
        valueField.setText(str(currentValue))
        valueField.setStyleSheet(
            f"font-family: '{theme.monoFontFamily}'; font-size: 10.5px; padding: 1px 4px;"
        )
        layout.addWidget(valueField)

        slider.valueChanged.connect(lambda v: valueField.setText(str(v)))

        def _onFieldEdited():
            text = valueField.text().strip()
            if not text.lstrip("-").isdigit():
                valueField.setText(str(slider.value()))
                return
            slider.setValue(min(bounds[1], max(bounds[0], int(text))))

        valueField.editingFinished.connect(_onFieldEdited)

        return container

    raise NotImplementedError(f"No widget for option type '{option.optionType}'")
