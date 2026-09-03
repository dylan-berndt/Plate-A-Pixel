import colorsys

# Hue bucket boundaries in degrees (0-360), each [start, end) - the plain-
# hue fallback once the achromatic (gray/black/white) and brown special
# cases below are ruled out. Deliberately approximate ("just generally
# match in HSV space", not a precise colorimetric model) - these are
# meant to produce a reasonable human label for an unnamed palette entry,
# not to classify color science.
_HUE_FAMILIES = [
    (15, "Red"),
    (45, "Orange"),
    (70, "Yellow"),
    (170, "Green"),
    (200, "Cyan"),
    (255, "Blue"),
    (290, "Purple"),
    (345, "Pink"),
    # wraps back to Red past 345 - see classifyColor.
]


def _hsv(rgb):
    r, g, b = (c / 255.0 for c in rgb)
    return colorsys.rgb_to_hsv(r, g, b)


def brightness(rgb):
    """HSV value (0-1) - what autoNamesForUnnamed ranks same-family
    entries by."""
    return _hsv(rgb)[2]


def classifyColor(rgb):
    """A rough, human-legible color family name for an (r, g, b) triple.
    Achromatic colors (gray/black/white) and brown are carved out before
    falling through to a plain hue bucket, since hue alone can't tell
    them apart from a saturated color at the same angle - a gray has no
    meaningful hue at all, and a brown turns out to be mostly a matter of
    *value*, not saturation the way it might seem: classic "brown"
    swatches (saddlebrown, sienna, chocolate) sit squarely in the orange
    hue range at fairly high saturation - scaling a color's brightness
    down doesn't reduce its saturation ratio much - so what actually
    separates them from a bright orange is a darker value, not a muddier
    one. Restricted to the orange sub-range specifically (not red too):
    a dark, saturated *red* (darkred) reads as a dark red, not a brown."""
    h, s, v = _hsv(rgb)
    hueDeg = (h * 360.0) % 360.0

    if v < 0.12:
        return "Black"
    if s < 0.12:
        return "White" if v > 0.85 else "Gray"
    if 15 <= hueDeg < 45 and v < 0.75:
        return "Brown"

    for boundary, family in _HUE_FAMILIES:
        if hueDeg < boundary:
            return family
    return "Red"  # >= 345 wraps back around to red


def autoNamesForUnnamed(palette):
    """{index: name} for every currently-unnamed entry in `palette` -
    doesn't rename anything itself (callers apply the result through
    Palette.rename - see CanvasController.autoNameUnnamedColors - so
    it's a real, undoable edit, not a hidden save-time transformation).

    Entries sharing a color family are numbered by brightness (HSV
    value, ascending - "Green 1" is the darkest green present, "Green 3"
    the brightest), so a repeated family stays disambiguated; a family
    with only one unnamed member skips the number entirely ("Brown", not
    "Brown 1"). Only unnamed entries participate - an existing name
    (whether auto-generated earlier or typed by the user) is never
    touched or considered when numbering, so this can't accidentally
    rewrite a name the user already chose. That does mean a fresh
    "Green 1" could coincidentally collide with an already-named entry
    the user separately called "Green 1" - a real but minor edge case
    left to the existing duplicate-name warning (objExport.
    duplicateColorNames) rather than solved here."""
    unnamed = [(i, entry) for i, entry in enumerate(palette) if not entry.name.strip()]
    if not unnamed:
        return {}

    byFamily = {}
    for index, entry in unnamed:
        byFamily.setdefault(classifyColor(entry.color), []).append((index, entry))

    names = {}
    for family, members in byFamily.items():
        members.sort(key=lambda pair: brightness(pair[1].color))
        if len(members) == 1:
            names[members[0][0]] = family
        else:
            for rank, (index, entry) in enumerate(members, start=1):
                names[index] = f"{family} {rank}"
    return names
