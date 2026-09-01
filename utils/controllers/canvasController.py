class CanvasController:
    """Geometry-affecting settings for one project's canvas:
    transformSelectionLayer, setHollow, setMargin. Each is a single `with
    self.projectController.editing(affectsMesh=True):` block - that
    context manager (see ProjectController.editing) pushes the undo
    snapshot and rebuilds the mesh on exit, so nothing here repeats that
    bookkeeping by hand.

    Selection (bucketSelect, brushSelect) isn't here - it lives directly
    on WandTool/BrushSelectTool, which call Canvas's own bucketSelect/
    brushSelect and wrap themselves in `with controller.projectController.
    editing():`. Those are real, independently-tested domain methods on
    Canvas; putting a same-signature passthrough here on top of them
    would just be a second copy of the same parameter list for no benefit.

    Wraps the owning ProjectController rather than a bare Project so every
    edit still goes through that ProjectController's undo stack and mesh
    pipeline - there is exactly one undo owner and one mesh-recompute
    owner per project; this is just a second, canvas-focused entry point
    into it.

    Also the settled home for canvas-view-specific operations that are
    neither project persistence/mesh-refresh (ProjectController's own
    remaining job: saving, undo bookkeeping, palette naming, export scale)
    nor a Tool's job - e.g. a future outline overlay. None of those exist
    yet; add them here as they come up rather than on ProjectController."""

    def __init__(self, projectController):
        self.projectController = projectController

    @property
    def project(self):
        return self.projectController.project

    def transformSelectionLayer(self, delta):
        with self.projectController.editing(affectsMesh=True):
            self.project.canvas.transformSelection(delta)

    def setHollow(self, hollow):
        with self.projectController.editing(affectsMesh=True):
            self.project.viewSettings.hollow = hollow

    def setMargin(self, margin):
        with self.projectController.editing(affectsMesh=True):
            self.project.viewSettings.baseMargin = margin
