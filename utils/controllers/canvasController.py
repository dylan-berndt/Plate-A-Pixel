class CanvasController:
    """Home for canvas-view-specific operations that are neither project
    persistence/mesh-refresh (ProjectController's job) nor a Tool's job -
    e.g. a future outline overlay for the 2D view. Nothing is defined here
    yet; this exists so those operations have a settled home instead of
    accreting onto ProjectController as they come up.

    Wraps a ProjectController (not a bare Project) so that a future
    operation needing to mutate canvas state goes through that
    ProjectController's undo-tracked methods rather than mutating Canvas
    directly - there is still only one undo owner per project."""

    def __init__(self, projectController):
        self.projectController = projectController

    @property
    def project(self):
        return self.projectController.project
