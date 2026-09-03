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


class Tool:
    """A tool's own configuration: its option schema (what can be
    changed) and its current selections (what the user has it set to
    right now) - e.g. Wand's selections might be {"mode": "replace",
    "contiguous": False}. Pure state; a Tool by itself doesn't know how
    to edit anything.

    Concrete tools that actually act on a canvas position subclass
    FunctionalTool, not Tool directly."""

    def __init__(self, name: str, options: dict, selections: dict):
        self.name = name
        self.options = options
        self.selections = selections


class FunctionalTool(Tool):
    """A Tool that can act on a canvas position, given the CanvasController
    to act through (see utils/controllers/canvasController.py). Handlers
    take that controller as an explicit argument rather than the tool
    storing one itself - a tool stays selected across a tab switch, but
    which project it should be editing changes, so ToolController
    resolves the current one on every call instead of a tool caching a
    stale reference.

    onPress is the only handler a tool must implement - onDrag/onRelease
    default to no-ops for tools (like Wand) that only care about a single
    click.

    `useLayers` says which canvas view the gesture started on (see
    CanvasArea/LayerCanvasArtist) - False for the color canvas, True for
    the layer canvas. It's ToolController's job to resolve that from
    which pane sent the event and pass it through uniformly to whichever
    tool is active; only a tool whose selection logic is actually
    color/height-dependent (WandTool) needs to look at it - see its
    onPress for how that plays out. A spatial tool like BrushSelectTool
    ignores it, since a radius-based stamp means the same thing on either
    pane."""

    def onPress(self, controller, pos, useLayers=False):
        raise NotImplementedError

    def onDrag(self, controller, pos, useLayers=False):
        pass

    def onRelease(self, controller, pos, useLayers=False):
        pass


class ToolRegistry:
    """The set of available tools and which one is active - what a tool
    rail and options bar bind to."""

    def __init__(self, tools):
        self.tools = tools
        self._activeIndex = 0 if tools else None

    @property
    def activeTool(self):
        return self.tools[self._activeIndex] if self._activeIndex is not None else None

    def setActiveTool(self, name):
        for i, tool in enumerate(self.tools):
            if tool.name == name:
                self._activeIndex = i
                return
        raise ValueError(f"No tool named '{name}'")
