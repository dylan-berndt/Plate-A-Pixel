from utils.data.colorNaming import classifyColor, autoNamesForUnnamed
from utils.data.palette import Palette, PaletteEntry


def test_classify_pure_hues():
    assert classifyColor((255, 0, 0)) == "Red"
    assert classifyColor((255, 165, 0)) == "Orange"
    assert classifyColor((255, 255, 0)) == "Yellow"
    assert classifyColor((0, 255, 0)) == "Green"
    assert classifyColor((0, 255, 255)) == "Cyan"
    assert classifyColor((0, 0, 255)) == "Blue"
    assert classifyColor((128, 0, 255)) == "Purple"
    assert classifyColor((255, 0, 255)) == "Pink"


def test_classify_achromatic_colors():
    assert classifyColor((5, 5, 5)) == "Black"
    assert classifyColor((240, 240, 240)) == "White"
    assert classifyColor((120, 120, 120)) == "Gray"


def test_classify_brown_vs_dark_red():
    # Both are dark, but brown is specifically a dark *orange* hue - a
    # dark, saturated red should stay "Red", not get swept into "Brown".
    assert classifyColor((139, 69, 19)) == "Brown"  # saddlebrown
    assert classifyColor((160, 82, 45)) == "Brown"  # sienna
    assert classifyColor((139, 0, 0)) == "Red"  # darkred
    assert classifyColor((128, 0, 0)) == "Red"  # maroon


def _palette(colors_with_names):
    entries = [PaletteEntry(color=c, name=n) for c, n in colors_with_names]
    return Palette(colors=None, entries=entries)


def test_auto_names_for_unnamed_is_empty_when_everything_is_named():
    palette = _palette([((255, 0, 0), "Fire")])
    assert autoNamesForUnnamed(palette) == {}


def test_auto_names_single_member_family_has_no_number():
    palette = _palette([((255, 0, 0), "")])
    assert autoNamesForUnnamed(palette) == {0: "Red"}


def test_auto_names_multiple_members_numbered_by_brightness_ascending():
    # Three greens at different brightness, deliberately out of order in
    # the palette - numbering must follow brightness, not palette index.
    bright = (150, 255, 150)
    mid = (0, 180, 0)
    dark = (0, 60, 0)
    palette = _palette([(mid, ""), (bright, ""), (dark, "")])

    names = autoNamesForUnnamed(palette)

    assert names[2] == "Green 1"  # dark - darkest
    assert names[0] == "Green 2"  # mid
    assert names[1] == "Green 3"  # bright - brightest


def test_auto_names_only_fills_in_unnamed_entries():
    palette = _palette([((255, 0, 0), "Custom Red"), ((0, 255, 0), "")])

    names = autoNamesForUnnamed(palette)

    assert names == {1: "Green"}


def test_auto_names_groups_separately_by_family():
    palette = _palette([((255, 0, 0), ""), ((0, 255, 0), ""), ((0, 0, 255), "")])

    names = autoNamesForUnnamed(palette)

    assert names == {0: "Red", 1: "Green", 2: "Blue"}
