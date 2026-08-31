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
    """A Tool that can act on a canvas position, given the ProjectController
    to act through. Handlers take that controller as an explicit argument
    rather than the tool storing one itself - a tool stays selected across
    a tab switch, but which project it should be editing changes, so
    ToolController resolves the current one on every call instead of a
    tool caching a stale reference.

    onPress is the only handler a tool must implement - onDrag/onRelease
    default to no-ops for tools (like Wand) that only care about a single
    click."""

    def onPress(self, controller, pos):
        raise NotImplementedError

    def onDrag(self, controller, pos):
        pass

    def onRelease(self, controller, pos):
        pass
