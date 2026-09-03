from dataclasses import dataclass


@dataclass
class Theme:
    """The app's visual palette, fonts, and chrome metrics - lifted from
    design/ui-mockup.html's "clay" palette (its CSS custom properties,
    resolved to hex - oklch() isn't something Qt's QSS understands). Every
    composite widget in elements.py pulls its colors from a Theme instance
    instead of hardcoding hex, so retheming is one dataclass, not a grep
    across widgets.

    Font families are requested by name only (no bundled font files) -
    Qt falls back to a system font automatically when a named family isn't
    installed, so these are a best-effort match to the mockup rather than
    a hard dependency."""

    # -- clay palette (darkest to lightest), plus paper/ink/glaze accents --
    clay950: str = "#1f0f09"
    clay800: str = "#4e2b1c"
    clay600: str = "#96553b"
    clay500: str = "#b26b4f"
    clay300: str = "#d7b6a5"
    clay200: str = "#e5cfc3"
    clay100: str = "#f7ece5"
    paper: str = "#f8f4f1"
    ink: str = "#100c0a"
    glaze: str = "#0091a4"
    glazeDark: str = "#006677"

    # -- fonts --
    fontFamily: str = "Familjen Grotesk"
    monoFontFamily: str = "Space Mono"
    displayFontFamily: str = "Fascinate Inline"
    fontSize: int = 12

    # -- chrome metrics --
    borderWidth: int = 2
    borderRadius: int = 4

    # -- legacy aliases some existing call sites still expect --
    @property
    def background(self):
        return self.clay100

    @property
    def surface(self):
        return self.paper

    @property
    def hover(self):
        return self.clay200

    @property
    def pressed(self):
        return self.clay300

    @property
    def disabled(self):
        return self.clay200

    @property
    def text(self):
        return self.ink

    def override(self, **kwargs):
        t = Theme(**{k: v for k, v in self.__dict__.items()})
        for k, v in kwargs.items():
            setattr(t, k, v)
        return t

    # QSS is Qt's per-widget stylesheet language; hover/pressed/disabled are
    # handled by Qt itself via these pseudo-states instead of the manual
    # istate tracking the old pygame Element tree needed.
    def stylesheet(self):
        return f"""
        QWidget {{
            background-color: {self.clay100};
            color: {self.ink};
            font-family: "{self.fontFamily}";
            font-size: {self.fontSize}px;
        }}
        QMainWindow, QDialog {{
            background-color: {self.clay100};
        }}
        QPushButton {{
            background-color: {self.paper};
            border: {self.borderWidth}px solid {self.ink};
            border-radius: {self.borderRadius}px;
            padding: 6px;
        }}
        QPushButton:hover {{
            background-color: {self.clay200};
        }}
        QPushButton:pressed {{
            background-color: {self.clay300};
        }}
        QPushButton:disabled {{
            background-color: {self.clay200};
            color: {self.clay500};
        }}
        QLineEdit, QComboBox {{
            background-color: {self.paper};
            border: {self.borderWidth - 1}px solid {self.ink};
            border-radius: {self.borderRadius}px;
            padding: 3px 6px;
        }}
        QToolTip {{
            background-color: {self.ink};
            color: {self.paper};
            border: none;
            padding: 4px 6px;
        }}
        """
