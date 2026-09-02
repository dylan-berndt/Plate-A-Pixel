from PySide6.QtWidgets import (
    QLabel, QLineEdit, QSlider, QPushButton, QComboBox, QDialog, QWidget, QGridLayout,
    QHBoxLayout, QVBoxLayout, QButtonGroup, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, QSize, QByteArray, Signal
from PySide6.QtGui import QPixmap, QPainter, QIcon
from PySide6.QtSvg import QSvgRenderer
from .base import *


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
    def __init__(self, options: dict, **kwargs):
        super().__init__(**kwargs)
        for label, value in options.items():
            self.addItem(label, value)


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
    Wand button in the mockup's tool rail."""

    def __init__(self, iconBody: str, onClick=None, checkable: bool = False, size: int = 40,
                 activeColor: str = None, iconColor: str = None, iconColorOn: str = None,
                 theme: Theme = None, **kwargs):
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

        self.setStyleSheet(f"""
            QPushButton {{
                background: {theme.paper};
                border: 1.5px solid {theme.ink};
                border-radius: {theme.borderRadius}px;
            }}
            QPushButton:hover {{ background: {theme.clay200}; }}
            QPushButton:checked {{ background: {activeColor}; }}
            QPushButton:checked:hover {{ background: {activeColor}; }}
        """)
        if onClick is not None:
            self.clicked.connect(onClick)


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

        frame = QFrame()
        # QLabel is itself a QFrame subclass in Qt, so a bare "QFrame {...}"
        # selector would also match any QLabel this frame ever contains
        # (see the identical fix/note in MeshSettingsPanel) - scoping by
        # objectName keeps this rule on just this one frame.
        frame.setObjectName("segmentedControlFrame")
        frame.setStyleSheet(
            f"QFrame#segmentedControlFrame {{ border: 1.5px solid {theme.ink}; border-radius: {theme.borderRadius}px; }}"
        )
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(1, 1, 1, 1)
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


class PillToggle(QPushButton):
    """A checkable pill - Wand's Contiguous/Diagonal toggles."""

    def __init__(self, label: str, checked: bool = False, onToggle=None, theme: Theme = None, **kwargs):
        super().__init__(label, **kwargs)
        theme = theme or Theme()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setStyleSheet(f"""
            QPushButton {{
                background: {theme.clay200}; color: {theme.clay800};
                border: 1.5px solid {theme.ink}; border-radius: 12px;
                padding: 5px 12px; font-size: 10.5px; font-weight: 600;
            }}
            QPushButton:checked {{ background: {theme.glazeDark}; color: {theme.paper}; }}
        """)
        if onToggle is not None:
            self.toggled.connect(onToggle)


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

        buttonStyle = f"""
            QPushButton {{
                background: {theme.paper}; border: 1.5px solid {theme.ink};
                border-radius: 3px; font-size: 12px; padding: 0;
            }}
            QPushButton:hover {{ background: {theme.clay200}; }}
        """
        self._minus = QPushButton("−")
        self._plus = QPushButton("+")
        buttonSize = 40 if vertical else 20
        for button in (self._minus, self._plus):
            button.setFixedSize(buttonSize, 20 if vertical else 20)
            button.setStyleSheet(buttonStyle)

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

    def __init__(self, color, name: str = "", onRename=None, onEditColor=None, theme: Theme = None, **kwargs):
        super().__init__(**kwargs)
        theme = theme or Theme()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(7)

        swatch = QLabel()
        swatch.setFixedSize(18, 18)
        r, g, b = (int(c) for c in color)
        swatch.setStyleSheet(
            f"background: rgb({r},{g},{b}); border: 1.5px solid {theme.ink}; border-radius: 3px;"
        )
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
            editButton = IconButton(Icons.PENCIL, onClick=onEditColor, size=16, theme=theme)
            editButton.setStyleSheet("QPushButton { background: transparent; border: none; }")
            layout.addWidget(editButton)

    def name(self):
        return self._nameEdit.text()

    def setName(self, name: str):
        self._nameEdit.setText(name)


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
            )
            closeButton.setStyleSheet("QPushButton { background: transparent; border: none; }")
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
        )
        self._newTabButton.setStyleSheet("QPushButton { background: transparent; border: none; }")

    def setTabs(self, entries):
        """entries: list of (label, active, dirty)."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # deleteLater(), not setParent(None) - see the identical
                # note in PaletteRail._rebuild.
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
        dropdown = Dropdown(option.options)
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
