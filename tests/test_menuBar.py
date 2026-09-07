from utils.ui.menuBar import ThemedMenu
from utils.ui.base import Theme


def test_themed_menu_reserves_border_thickness_as_contents_margins():
    theme = Theme()
    menu = ThemedMenu("File", theme)
    t = menu._nineSlice.borderThickness(2)  # STANDARD_SCALE
    margins = menu.contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (t, t, t, t)


def test_themed_menu_paints_without_raising():
    theme = Theme()
    menu = ThemedMenu("File", theme)
    menu.addAction("New From Image...")
    menu.resize(200, 100)
    menu.repaint()  # should not raise
