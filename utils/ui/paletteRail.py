from PySide6.QtWidgets import QWidget, QVBoxLayout, QFrame, QColorDialog
from PySide6.QtGui import QColor
from PySide6.QtCore import Signal

from .elements import SectionLabel, PaletteRow, IconButton, Icons, Theme


class PaletteRail(QWidget):
    """The right rail's palette list: one PaletteRow per Palette entry,
    rebuilt from scratch on paletteChanged (a rename/recolor could touch
    any entry, and entries don't have stable identity across an undo/
    redo restore - see ProjectController._restore - so a full rebuild is
    simpler than trying to patch individual rows in place)."""

    backgroundVisibilityChanged = Signal(bool)

    def __init__(self, theme: Theme = None, **kwargs):
        super().__init__(**kwargs)
        self._theme = theme or Theme()
        self._boundProjectController = None
        self._backgroundVisible = True

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 16, 14, 16)
        outer.setSpacing(10)

        outer.addWidget(SectionLabel("Palette", theme=self._theme))

        self._rowsContainer = QWidget()
        self._rowsLayout = QVBoxLayout(self._rowsContainer)
        self._rowsLayout.setContentsMargins(0, 0, 0, 0)
        self._rowsLayout.setSpacing(2)
        outer.addWidget(self._rowsContainer)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background: {self._theme.ink};")
        outer.addWidget(divider)

        backgroundRow = QWidget()
        from PySide6.QtWidgets import QHBoxLayout, QLabel
        bgLayout = QHBoxLayout(backgroundRow)
        bgLayout.setContentsMargins(2, 2, 2, 2)
        swatch = QLabel()
        swatch.setFixedSize(18, 18)
        swatch.setStyleSheet(f"background: #ffffff; border: 1.5px solid {self._theme.ink}; border-radius: 3px;")
        bgLayout.addWidget(swatch)
        bgLayout.addWidget(SectionLabel("Background", theme=self._theme), 1)
        self._backgroundToggle = IconButton(
            Icons.EYE_OFF, checkable=True, size=16, theme=self._theme, onClick=self._toggleBackground,
        )
        self._backgroundToggle.setStyleSheet("QPushButton { background: transparent; border: none; }")
        bgLayout.addWidget(self._backgroundToggle)
        outer.addWidget(backgroundRow)

        outer.addStretch(1)

    def _toggleBackground(self, checked):
        self._backgroundVisible = not checked
        self.backgroundVisibilityChanged.emit(self._backgroundVisible)

    # -- binding to whichever project is currently active --------------

    def bindProject(self, projectController):
        if self._boundProjectController is not None:
            self._boundProjectController.paletteChanged.disconnect(self._rebuild)
        self._boundProjectController = projectController
        if projectController is not None:
            projectController.paletteChanged.connect(self._rebuild)
        self._rebuild()

    def _rebuild(self):
        while self._rowsLayout.count():
            item = self._rowsLayout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

        if self._boundProjectController is None:
            return

        palette = self._boundProjectController.project.canvas.palette
        for index, entry in enumerate(palette):
            row = PaletteRow(
                entry.color, entry.name,
                onRename=(lambda name, i=index: self._rename(i, name)),
                # onEditColor reaches IconButton.clicked (see PaletteRow),
                # which always passes its checked:bool positionally to any
                # connected callable that declares a parameter - even a
                # defaulted one - so a bare "lambda i=index" silently gets
                # i=False (index 0!) instead of its default. The leading
                # `checked` absorbs that bool so `i` actually falls through
                # to its default.
                onEditColor=(lambda checked=False, i=index: self._editColor(i)),
                theme=self._theme,
            )
            self._rowsLayout.addWidget(row)

    def _rename(self, index, name):
        if self._boundProjectController is None:
            return
        self._boundProjectController.canvasController.renameColor(index, name)

    def _editColor(self, index):
        if self._boundProjectController is None:
            return
        palette = self._boundProjectController.project.canvas.palette
        current = QColor(*[int(c) for c in palette[index].color])
        color = QColorDialog.getColor(current, self, "Choose Color")
        if color.isValid():
            self._boundProjectController.canvasController.recolorColor(
                index, (color.red(), color.green(), color.blue())
            )
