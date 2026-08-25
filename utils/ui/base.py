from dataclasses import dataclass, field


@dataclass
class Theme:
    background: tuple = (30, 30, 30)
    surface: tuple = (45, 45, 45)
    hover: tuple = (60, 60, 60)
    pressed: tuple = (25, 25, 25)
    disabled: tuple = (38, 38, 38)

    text: tuple = (220, 220, 220)

    fontFamily: str = "Arial"
    fontSize: int = 16

    def override(self, **kwargs):
        t = Theme(**self.__dict__)
        for k, v in kwargs.items():
            setattr(t, k, v)
        return t

    # QSS is Qt's per-widget stylesheet language; hover/pressed/disabled are
    # handled by Qt itself via these pseudo-states instead of the manual
    # istate tracking the old pygame Element tree needed.
    def stylesheet(self):
        def rgb(c):
            return f"rgb({c[0]}, {c[1]}, {c[2]})"

        return f"""
        QWidget {{
            background-color: {rgb(self.background)};
            color: {rgb(self.text)};
            font-family: "{self.fontFamily}";
            font-size: {self.fontSize}px;
        }}
        QPushButton {{
            background-color: {rgb(self.surface)};
            border: none;
            padding: 6px;
        }}
        QPushButton:hover {{
            background-color: {rgb(self.hover)};
        }}
        QPushButton:pressed {{
            background-color: {rgb(self.pressed)};
        }}
        QPushButton:disabled {{
            background-color: {rgb(self.disabled)};
        }}
        """
