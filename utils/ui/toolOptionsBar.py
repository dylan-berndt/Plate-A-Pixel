from PySide6.QtWidgets import QWidget, QHBoxLayout, QFrame

from .elements import SectionLabel, IconButton, Icons, Theme, buildOptionWidget


class ToolOptionsBar(QWidget):
    """The bar directly under the tab strip: the active tool's own
    options (built generically off Tool.options - see
    utils/tools/tool.py's Options schema - so a new tool never needs
    hand-written UI here), plus Undo/Redo for whichever project is
    active. Options write straight back to tool.selections - a
    FunctionalTool's onPress/onDrag reads that dict directly at gesture
    time, so there's no controller call for a selection change."""

    def __init__(self, appController, toolController, theme: Theme = None, **kwargs):
        super().__init__(**kwargs)
        theme = theme or Theme()
        self._theme = theme
        self._appController = appController
        self._toolController = toolController

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(14, 6, 14, 6)
        self._layout.setSpacing(12)

        self._nameLabel = SectionLabel("", theme=theme)
        self._layout.addWidget(self._nameLabel)

        self._optionsContainer = QWidget()
        self._optionsLayout = QHBoxLayout(self._optionsContainer)
        self._optionsLayout.setContentsMargins(0, 0, 0, 0)
        self._optionsLayout.setSpacing(12)
        self._layout.addWidget(self._optionsContainer, 1)

        divider = QFrame()
        divider.setFixedWidth(1.5)
        divider.setStyleSheet(f"background: {theme.ink};")
        self._layout.addWidget(divider)

        self._undoButton = IconButton(Icons.UNDO, onClick=self._undo, size=26, theme=theme)
        self._redoButton = IconButton(Icons.REDO, onClick=self._redo, size=26, theme=theme)
        self._layout.addWidget(self._undoButton)
        self._layout.addWidget(self._redoButton)

        self._toolController.activeToolChanged.connect(self._rebuild)
        self._rebuild(self._toolController.registry.activeTool)

    def _rebuild(self, tool):
        while self._optionsLayout.count():
            item = self._optionsLayout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

        if tool is None:
            self._nameLabel.setText("")
            return

        self._nameLabel.setText(tool.name)
        for key, option in tool.options.items():
            widget = buildOptionWidget(
                option, tool.selections[key],
                onChange=(lambda value, k=key: tool.selections.__setitem__(k, value)),
                theme=self._theme,
            )
            self._optionsLayout.addWidget(widget, 0)
        # Without this, leftover horizontal space in the bar gets
        # distributed across the option widgets themselves instead of
        # staying empty - every option would stretch to fill the bar.
        self._optionsLayout.addStretch(1)

    def _undo(self):
        controller = self._appController.activeController
        if controller is not None:
            controller.undo()
        self.refreshUndoRedo()

    def _redo(self):
        controller = self._appController.activeController
        if controller is not None:
            controller.redo()
        self.refreshUndoRedo()

    def refreshUndoRedo(self):
        controller = self._appController.activeController
        self._undoButton.setEnabled(controller is not None and controller.canUndo)
        self._redoButton.setEnabled(controller is not None and controller.canRedo)
