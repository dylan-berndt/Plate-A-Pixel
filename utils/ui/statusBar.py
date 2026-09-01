from PySide6.QtWidgets import QWidget, QHBoxLayout
from PySide6.QtCore import Qt

from .elements import MonoText, Theme


class StatusBar(QWidget):
    """The thin strip at the bottom: selection size and canvas dimensions
    on the left, zoom on the right. Only shows what's actually derivable
    from Canvas/CanvasController - there's no domain concept of a
    Photoshop-style "layer stack", so this doesn't invent one just
    because design/ui-mockup.html's draft text implied it (see
    design/README.md: the mockup is a draft to diverge from, not a spec)."""

    def __init__(self, theme: Theme = None, **kwargs):
        super().__init__(**kwargs)
        theme = theme or Theme()
        self._theme = theme

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 2, 14, 2)

        self._leftLabel = MonoText("", theme=theme)
        layout.addWidget(self._leftLabel)
        layout.addStretch(1)
        self._rightLabel = MonoText("", theme=theme)
        layout.addWidget(self._rightLabel)

        # A bare QWidget doesn't paint a stylesheet's background-color on
        # its own - only QFrame/QLabel-style widgets do by default - so
        # this needs to opt in explicitly or the whole bar stays transparent
        # over whatever's behind it.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background: {theme.clay950}; color: {theme.clay200};")
        for label in (self._leftLabel, self._rightLabel):
            label.setStyleSheet(f"font-family: '{theme.monoFontFamily}'; font-size: 9.5px; color: {theme.clay200};")

    def refresh(self, projectController, zoomPercent=100):
        if projectController is None:
            self._leftLabel.setText("")
            self._rightLabel.setText("")
            return

        canvas = projectController.project.canvas
        rows, cols = canvas.map.shape
        selected = int(canvas.selection.sum())
        name = projectController.project.name
        self._leftLabel.setText(f"{selected} px selected · {name}")
        self._rightLabel.setText(f"canvas {cols}×{rows} · zoom {zoomPercent:.0f}%")
