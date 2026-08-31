class CanvasController:
    """Canvas-editing operations for one project: selection (bucketSelect,
    brushSelect) and the geometry-affecting settings (transformSelectionLayer,
    setHollow, setMargin). Each is a single `with self.projectController.
    editing():` block - that context manager (see ProjectController.editing)
    pushes the undo snapshot and, on exit, either rebuilds the mesh or
    announces the selection changed, so nothing here repeats that
    bookkeeping by hand.

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

    # -- selection ----------------------------------------------------

    def bucketSelect(self, pos, contiguous=True, diagonal=False, mode="replace"):
        with self.projectController.editing():
            self.project.canvas.bucketSelect(pos, contiguous=contiguous, diagonal=diagonal, mode=mode)

    def brushSelect(self, pos, radius, mode="replace"):
        with self.projectController.editing():
            self.project.canvas.brushSelect(pos, radius, mode=mode)

    # -- height / mesh geometry -----------------------------------------

    def transformSelectionLayer(self, delta):
        with self.projectController.editing(affectsMesh=True):
            self.project.canvas.transformSelection(delta)

    def setHollow(self, hollow):
        with self.projectController.editing(affectsMesh=True):
            self.project.viewSettings.hollow = hollow

    def setMargin(self, margin):
        with self.projectController.editing(affectsMesh=True):
            self.project.viewSettings.baseMargin = margin
