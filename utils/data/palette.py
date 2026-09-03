import numpy as np
from dataclasses import dataclass, asdict


@dataclass
class PaletteEntry:
    """One color in a Canvas's palette. `color` is an (r, g, b) triple in
    the same 0-255 range as the source image; `name` is a user-facing
    label with no meaning to the domain layer beyond display."""

    color: tuple
    name: str = ""

    def to_dict(self):
        d = asdict(self)
        d["color"] = [int(c) for c in self.color]
        return d

    @staticmethod
    def from_dict(d):
        return PaletteEntry(color=tuple(int(c) for c in d["color"]), name=d.get("name", ""))


class Palette:
    """An ordered list of PaletteEntry, indexed the same way as
    Canvas.map's color values (entry i is the color that map == i means).
    Wraps what used to be a bare Nx3 numpy array so a color can carry a
    name without every numeric consumer (bucketSelect, Mesh's per-color
    grouping, objExport's folder naming) needing to change how it looks
    colors up."""

    def __init__(self, colors, entries=None):
        """`colors` is an Nx3 array/list of RGB rows, in the exact order
        Canvas.map's indices refer to. `entries` optionally supplies the
        full PaletteEntry list directly (used by from_dict/Canvas.fromSaved
        where names already exist) - when given, `colors` is ignored."""
        if entries is not None:
            self._entries = list(entries)
        else:
            self._entries = [PaletteEntry(color=tuple(int(c) for c in row)) for row in colors]

    def __len__(self):
        return len(self._entries)

    def __getitem__(self, index):
        return self._entries[index]

    def __iter__(self):
        return iter(self._entries)

    @property
    def colors(self):
        """Nx3 numpy array of every entry's color, for the numeric code
        (bucketSelect and friends) that just wants RGB rows."""
        return np.array([entry.color for entry in self._entries], dtype=np.uint8)

    def indexOf(self, color):
        """The index of the entry matching `color`, or None if no entry
        matches."""
        for i, entry in enumerate(self._entries):
            if tuple(entry.color) == tuple(color):
                return i
        return None

    def rename(self, index, name):
        self._entries[index].name = name

    def setColor(self, index, color):
        self._entries[index].color = tuple(int(c) for c in color)

    def to_dict(self):
        return [entry.to_dict() for entry in self._entries]

    @staticmethod
    def from_dict(data):
        return Palette(colors=None, entries=[PaletteEntry.from_dict(d) for d in data])
