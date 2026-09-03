from PySide6.QtWidgets import QWidget, QVBoxLayout, QFrame, QColorDialog, QScrollArea
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt, Signal

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
        # Explicit, not just "no stylesheet means transparent": once any
        # widget anywhere gets a local stylesheet (rightContainer, in the
        # real app - see AppWindow), Qt seems to re-evaluate cascaded
        # matches more eagerly and can auto-enable WA_StyledBackground on
        # a plain descendant QWidget that matches the app-wide QWidget{
        # background-color:...} rule (see Theme.stylesheet()) - even
        # though it never had that attribute set directly - painting a
        # solid box behind every palette row instead of staying
        # transparent over rightContainer's own background.
        self._rowsContainer.setStyleSheet("background: transparent;")
        self._rowsLayout = QVBoxLayout(self._rowsContainer)
        self._rowsLayout.setContentsMargins(0, 0, 0, 0)
        self._rowsLayout.setSpacing(2)
        self._rowsLayout.addStretch(1)

        # A plain container just grows to fit every row, pushing
        # MeshSettingsPanel further down (and eventually off the bottom of
        # the window) as colors are added - scrolling instead keeps this
        # section's height bounded to whatever space it's actually given,
        # with the row list scrolling internally past that. NoFrame since
        # the app already draws its own outlines (see AppWindow); no
        # horizontal scrollbar since rows never exceed the rail's width.
        scrollArea = QScrollArea()
        scrollArea.setWidget(self._rowsContainer)
        scrollArea.setWidgetResizable(True)
        scrollArea.setFrameShape(QScrollArea.NoFrame)
        scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scrollArea.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scrollArea.setStyleSheet("background: transparent;")
        # A floor of ~2 rows so the list never collapses to nothing when
        # the right pane is short on space - PaletteRail still yields the
        # rest of its growth to MeshSettingsPanel below it (see AppWindow's
        # rightLayout stretch factors).
        scrollArea.setMinimumHeight(2 * PaletteRow.ROW_HEIGHT)
        outer.addWidget(scrollArea, 1)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background: {self._theme.ink};")
        outer.addWidget(divider)

        backgroundRow = QWidget()
        # See the identical note on _rowsContainer above.
        backgroundRow.setStyleSheet("background: transparent;")
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
                # deleteLater(), not setParent(None): takeAt() already
                # detaches the widget from the layout, so setParent(None)
                # here would just turn it into an orphaned, independent
                # top-level window (never shown, but never freed either -
                # every recolor/rename leaked one more) instead of
                # actually destroying it. deleteLater() destroys it on the
                # next event-loop tick while it's still parented, so it
                # never becomes a window at all.
                widget.deleteLater()

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
