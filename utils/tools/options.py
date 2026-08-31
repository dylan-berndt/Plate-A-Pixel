from dataclasses import dataclass


@dataclass
class Options:
    """One configurable knob on a Tool, e.g. Wand's "mode" or "contiguous".
    Purely descriptive - `options` maps a human label to the value it
    sets - so a UI can build a dropdown/checkbox/slider from this without
    the Tool itself knowing anything about widgets."""

    name: str
    optionType: str
    options: dict
