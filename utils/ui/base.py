from dataclasses import dataclass


@dataclass
class Theme:
    """The app's visual palette, fonts, and chrome metrics. Every composite
    widget in elements.py pulls its colors from a Theme instance instead of
    hardcoding hex, so retheming is one dataclass, not a grep across
    widgets.

    Colors are every one of the original design/ui-mockup.html "clay"
    palette's roles (darkest-to-lightest clay ramp, paper/ink/glaze
    accents), each reassigned to a match in assets/lospec500.gpl (the
    game-art palette the project settled on - see that file for the full
    42-color set these were chosen from) rather than the original
    palette's own hex values - a full-app retheme onto a fixed,
    restricted swatch set, not just a few new accent colors layered on
    top of the old ramp.

    Matched in CIE Lab space, not raw RGB - Euclidean RGB distance
    doesn't track *perceived* color difference well (it under-weights
    hue/chroma relative to how the eye actually judges "closest match"),
    which is exactly what went wrong on the first pass here: clay300/
    clay200 (the tool rail/right pane's own panel background and the
    canvas checkerboard - colors this visible were the whole reason this
    got re-examined) both nearest-matched to saturated pinks in RGB
    space, alien to the original warm-tan clay ramp, and Lab distance
    still agreed pink was numerically closest - there simply isn't a
    close match to a light warm neutral in this palette. Rather than
    force a perceptually-nearest color that breaks the ramp's own
    identity, clay300/clay200/clay100 are hand-picked instead to
    continue the same warm brown-to-cream progression clay800/clay600/
    clay500 already land on (idx9/5/11 in lospec500.gpl), verified
    monotonically increasing in Lab lightness (L: 24.8, 40.2, 50.7, 74.4,
    84.4, 94.9, 100.0 from clay800 through paper) rather than picked by
    eye alone. Every other role here is the real Lab-nearest match. ink
    and clay950 intentionally land on two different near-black swatches
    (not the same one, unlike a raw-nearest pass) so the menu bar
    (clay950) still reads as a shade lighter than actual text/border ink,
    matching the original palette's own relationship between the two.

    Font families are requested by name only (no bundled font files) -
    Qt falls back to a system font automatically when a named family isn't
    installed, so these are a best-effort match to the mockup rather than
    a hard dependency."""

    # -- clay palette (darkest to lightest), plus paper/ink/glaze accents --
    # See the class docstring above for where each of these actually came
    # from (assets/lospec500.gpl, Lab-nearest per role except the
    # hand-picked clay300/clay200/clay100 - see there for why).
    clay950: str = "#2c1e31"
    clay800: str = "#4d3533"
    clay600: str = "#94493a"
    clay500: str = "#a26d3f"
    clay300: str = "#dab163"
    clay200: str = "#e8d282"
    clay100: str = "#f7f3b7"
    paper: str = "#ffffff"
    ink: str = "#10121c"
    glaze: str = "#008b8b"
    glazeDark: str = "#006554"

    # -- fonts --
    fontFamily: str = "Familjen Grotesk"
    monoFontFamily: str = "Space Mono"
    displayFontFamily: str = "Fascinate Inline"
    fontSize: int = 12

    # -- chrome metrics --
    # The one border width used everywhere in the app - QSS borders and
    # nine-slice borders (NineSlice.DEFAULT_CORNER_SIZE * STANDARD_SCALE,
    # see nineSlice.py) alike - so pixel art never sits next to a
    # thinner/thicker or anti-aliased border and reads as inconsistent.
    # No borderRadius any more: every corner in the app is square now,
    # nine-slice's own rounded corner art aside.
    borderWidth: int = 4

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
            border: {self.borderWidth}px solid {self.ink};
            padding: 3px 6px;
        }}
        QToolTip {{
            background-color: {self.ink};
            color: {self.paper};
            border: none;
            padding: 4px 6px;
        }}
        """
