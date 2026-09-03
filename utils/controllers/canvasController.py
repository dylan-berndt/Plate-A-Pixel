class CanvasController:
    """The one place a view calls to edit a project's content: height/
    hollow/margin, export cell scale, and palette naming (selection lives
    directly on WandTool/BrushSelectTool instead - see below). Each
    method is a single `with self.projectController.editing(...):` block
    - that context manager (see ProjectController.editing) pushes the
    undo snapshot and, on exit, either rebuilds the mesh or emits
    whichever signal fits that edit, so nothing here repeats that
    bookkeeping by hand.

    ProjectController is the shared infrastructure this (and the tools)
    lean on - the undo stack, editing(), the mesh worker, save/dirty
    state - not a second command surface. Every actual edit belongs here
    (or, for selection, directly on a FunctionalTool), so there's exactly
    one place to look for "how do I change this project."

    Selection (bucketSelect, brushSelect) isn't here - it lives directly
    on WandTool/BrushSelectTool, which call Canvas's own bucketSelect/
    brushSelect and wrap themselves in `with controller.projectController.
    editing(signal=...):`. Those are real, independently-tested domain
    methods on Canvas; putting a same-signature passthrough here on top
    of them would just be a second copy of the same parameter list for no
    benefit.

    Wraps the owning ProjectController rather than a bare Project so every
    edit still goes through that ProjectController's undo stack and mesh
    pipeline - there is exactly one undo owner and one mesh-recompute
    owner per project.

    Also the settled home for canvas-view-specific operations that aren't
    covered above and aren't a Tool's job either - e.g. a future outline
    overlay. None of those exist yet; add them here as they come up
    rather than on ProjectController."""

    def __init__(self, projectController):
        self.projectController = projectController

    @property
    def project(self):
        return self.projectController.project

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

    def setTubeMargin(self, value):
        with self.projectController.editing(affectsMesh=True):
            self.project.viewSettings.tubeMargin = value

    def setWallThickness(self, value):
        with self.projectController.editing(affectsMesh=True):
            self.project.viewSettings.wallThickness = value

    def setBulgeSize(self, value):
        with self.projectController.editing(affectsMesh=True):
            self.project.viewSettings.bulgeSize = value

    # -- export-only view settings (no mesh geometry change) -------------
    # cellWidth/cellHeight only scale coordinates on export (objExport) -
    # Mesh's own triangles are unit-based and don't depend on either, so
    # these don't touch the mesh at all.

    def setCellWidth(self, mm):
        with self.projectController.editing(signal=self.projectController.viewSettingsChanged):
            self.project.viewSettings.cellWidth = mm

    def setCellHeight(self, mm):
        with self.projectController.editing(signal=self.projectController.viewSettingsChanged):
            self.project.viewSettings.cellHeight = mm

    # -- palette ----------------------------------------------------------

    def renameColor(self, index, name):
        with self.projectController.editing(signal=self.projectController.paletteChanged):
            self.project.canvas.palette.rename(index, name)

    def recolorColor(self, index, rgb):
        with self.projectController.editing(signal=self.projectController.paletteChanged):
            self.project.canvas.palette.setColor(index, rgb)
