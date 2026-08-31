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
