# Plate-A-Pixel — Architecture

This documents the actual current design of `utils/`, not a proposal. An
earlier draft of this file (never committed) got some of this wrong by
guessing ahead of what the domain layer actually supported; where this
disagrees with that draft, this file is correct. Update this file
whenever the shape of a layer changes.

## Layering

```
utils/data/         domain layer   - no Qt imports at all
utils/tools/         tool layer    - no Qt imports (Tool/FunctionalTool/ToolRegistry);
                                       Options is UI-schema data, not a widget
utils/controllers/   controller    - Qt-aware (QObject/Signal), no QWidget
utils/ui/, canvasElement.py, meshElement.py, exportDialog.py   views
```

A view widget only ever talks to the controller layer: it reads state
off `Project`/`Canvas`/`Palette` through a controller, calls the
controller's methods to make edits, and connects to its signals to know
when to redraw. It never calls into `utils/data/` directly.

## Domain layer (`utils/data/`)

- **`Canvas`** (`canvas.py`) — `image` (scale-reduced RGB array), `map`
  (per-pixel palette index), `layers` (per-pixel height, `-1` = empty),
  `selection` (bool mask), `palette` (a `Palette`). Selection ops:
  `bucketSelect` (contiguous or not, from a clicked position),
  `brushSelect` (every cell within a radius, color-blind).
  `transformSelection(delta)` raises/lowers the current selection's
  height.
- **`Palette`** (`palette.py`) — an ordered list of `PaletteEntry(color,
  name)`, indexed the same way `Canvas.map`'s values are. `.colors` gives
  the numeric code (selection, mesh, export) an Nx3 array when it just
  wants RGB rows.
- **`Mesh`** (`mesh.py`, `pixelPlan.py`, `pixelComponents.py`) — turns
  `Canvas.map`/`.layers` into one printable solid per color via
  `PixelPlanner`/`componentTriangles`. Recomputes only when its cached
  copy of `map`/`layers`/`hollow`/`fastPreview`/`baseMargin`/`tubeMargin`/
  `wallThickness`/`bulgeSize` actually changed. `fastPreview` swaps in
  `componentTrianglesFast` - much cheaper but not actually watertight
  (see its own docstring), used only by the live-viewport background
  worker (`ProjectController._MeshWorker`); export always forces a fresh
  recompute with it off (`Project.rebuildMesh`). The next three are
  passed straight through to `componentTriangles` (see
  `pixelComponents.py`'s `TUBE_MARGIN`/`WALL_THICKNESS`/`BULGE_SIZE`
  constants, which are now just their defaults, not the only values in
  play) - world-unit fractions of one grid cell, not millimeters.
  `componentTriangles(plans, hollow, tubeMargin, wallThickness,
  bulgeSize)` takes one physically-connected group's `PixelPlan`s
  directly (`_calculateMesh` groups plans via union-find on `fused`/
  diagonal connectivity, same as before) and builds its cap and tube as
  hull extrusions read straight off each plan's already-computed
  fused/bulged/flush classification - fused sides are traced as interior
  (no wall), bulged sides bulge, plainWalls stay flush - then dog-ear
  triangulates and extrudes. Boolean CSG is used only to combine a
  handful of already-simplified pieces (a hole cut from a hull, cavities
  cut from the tube, or the final cap+tube union), not per pixel; this
  replaced an earlier version that built one box per pixel and
  boolean-unioned the whole group, which didn't scale past a few thousand
  pixels in one component (e.g. the auto-generated base plate on a large
  canvas). A rare topological ambiguity - two pixels touching only at one
  grid corner with no shared edge (diagonal pixels whose bulges overlap,
  no fusing) - makes the native-resolution boundary trace ambiguous (which
  of the two crossing edges continues the loop?), so that group falls back
  to tracing a finer coordinate-compressed coverage grid instead (see
  `_capCoverageFine`/`_tubeCoverageFine` in `pixelComponents.py`), where the
  overlap shows up as real covered area rather than one ambiguous point;
  real usage essentially never hits it, since the base plate already
  occupies both of a diagonal pair's flanking cells.

  `componentTrianglesFast` is a second, deliberately non-watertight
  pipeline used only for the live viewport (see `fastPreview` below) - it
  tiles flat faces directly and draws one quad per merged boundary run
  instead of ear-clipping and CSG, trading a real printable solid for
  speed. Its coverage-grid helpers (`_fastCapCoverage`/`_fastTubeCoverage`)
  parallel `_capCoverageFine`/`_tubeCoverageFine` but only cut the grid
  finer where a pixel's own side actually needs it, rather than
  unconditionally for every pixel - profiling found the unconditional
  version too slow to run on every edit. This duplication between the two
  pipelines is intentional, not drift: exactness and interactive speed are
  genuinely different goals, and the fast path never feeds export or an
  actual solid.
- **`Project`** (`project.py`) — one open document: a `Canvas` + its
  `Palette` + a `Mesh` + `ViewSettings` (`hollow`, `baseMargin`,
  `cellWidth`, `cellHeight` in mm, `tubeMargin`, `wallThickness`,
  `bulgeSize`) + `filePath` (where it was last loaded from/saved to,
  `None` if never saved) + `name`.
  - `Project.save(filePath)` / `Project.load(filePath)` round-trip a
    single `*.pap` zip bundle: `image.png` (the reduced image),
    `layers.npy`, and `project.json` (palette colors/names, view
    settings, format version). Reloading reconstructs `Canvas` by
    matching pixels against the *saved* palette order, not by re-deriving
    it from the image, so a later recolor can't desync a reload.
    Selection, undo history, and any in-progress tool state are
    intentionally not part of the format — a reload always starts clean.
  - `Project.exportObjs(dir)` writes one OBJ per mesh component, scaling
    X/Z by `cellWidth` and Y by `cellHeight` independently (`objExport.py`
    takes both explicitly — never one uniform scale).

## Tool layer (`utils/tools/`)

**Tools are selection-only.** Every tool that exists changes
`canvas.selection`; nothing about *height* goes through a tool — raising
or lowering the current selection is a separate part of the interface
(the layer-height stepper in `utils/ui/toolRail.py`) that calls
`CanvasController.transformSelectionLayer` directly. Don't add a "height
tool" without revisiting this.

- **`Tool`** (`tool.py`) — pure state: `name`, `options` (a schema of
  `Options(label, type, choices)` describing what's configurable), and
  `selections` (the user's current values for those options). A `Tool`
  by itself doesn't know how to edit anything.
- **`FunctionalTool(Tool)`** — adds `onPress(controller, pos)` (required),
  `onDrag(controller, pos)`/`onRelease(controller, pos)` (no-ops by
  default). Handlers take the `CanvasController` to act through as an
  explicit argument rather than storing one — see ToolController below
  for why. A handler calls `Canvas` methods directly (via
  `controller.project.canvas`) and wraps its own mutation in
  `with controller.projectController.editing():` - there is no
  `CanvasController.bucketSelect`/`brushSelect` standing in the middle;
  that would just be a second copy of the same parameter list `Canvas`
  already has, for no benefit. `Canvas.bucketSelect`/`brushSelect`
  themselves are unchanged, real, independently-tested domain methods.
- **`WandTool`** — click-to-select, built on `Canvas.bucketSelect`. There
  is no separate "bucket tool": `bucketSelect(contiguous=False)` is
  already identical to picking every cell matching the clicked color, so
  "contiguous" is just one of Wand's three options (`mode`, `contiguous`,
  `diagonal`), not a second tool.
- **`BrushSelectTool`** — drag-to-select within a radius (`size` option)
  of the pointer, built on `Canvas.brushSelect`. `onPress` and `onDrag`
  share a private `_stamp()` helper (that's an implementation detail of
  this one tool, not a shared base-class mechanism); a drag that started
  in "Replacement" mode downgrades to "add" on every sample after the
  first, since re-applying "replace" on each dragged-over cell would
  erase everything painted earlier in the same stroke.
- **`ToolRegistry`** — the list of available tools and which is active;
  what a tool rail/options bar bind to. `setActiveTool(name)` raises on
  an unknown name.

Explicitly not built (skip unless asked): palette-swatch-click-to-select
(`Canvas.bucketSelect(pos, contiguous=False)` already selects every cell
of a given color from a clicked position - a swatch-click variant would
need something equivalent driven by a color instead of a position; there
used to be a `Canvas.wandSelect(color)` for exactly that, removed since
nothing called it), a radius-based *height* brush (no domain support for
that), palette drag-reordering (`Canvas.map`'s indices are tied to
palette order — reordering would need new domain support to remap them;
decided not needed for now).

## Controller layer (`utils/controllers/`)

### `ProjectController` — shared infrastructure: undo stack, mesh pipeline, persistence

Owns no editing methods of its own. It's the infrastructure every actual
edit runs through - the undo/redo stack, the mesh-recompute pipeline, and
save/dirty tracking - not a second command surface competing with
`CanvasController`. Concretely:

- **`pushUndo()`** — record an undo point before a mutation. Public so
  `CanvasController` and the tool layer can call it.
- **`rebuildMesh()`** — kick off a mesh recompute (see below). Public for
  the same reason.
- **`editing(affectsMesh=False, signal=None)`** — a context manager
  combining both: `pushUndo()` on entry, then either `rebuildMesh()` (if
  `affectsMesh`) or the given signal's `.emit()` on exit. Exactly one of
  `affectsMesh`/`signal` applies - there's no implicit default signal,
  since different `CanvasController` methods announce themselves
  differently (`selectionChanged`, `paletteChanged`,
  `viewSettingsChanged`). Every `CanvasController` method, and each
  `FunctionalTool` handler, is just a `with controller.projectController.
  editing(...):` block around the actual domain call, instead of
  repeating pushUndo-then-emit by hand.

**Undo/redo** is a plain stack of whole-`Project`-state snapshots
(`layers`, `selection`, `palette`, `viewSettings`) — not a command
pattern with a bespoke inverse per operation; there isn't enough state in
a `Project` to justify one. `undo()`/`redo()` pop a snapshot and restore
it wholesale, then re-emit every signal rather than tracking what
specifically changed. **The view is responsible for deciding whether to
grey out Undo/Redo menu items** — it reads `controller.canUndo` /
`controller.canRedo` (plain bool properties); there is no
`canUndoChanged` signal, since calling `undo()`/`redo()` with an empty
stack is already a safe no-op.

**Gestures**: a multi-call sequence (a tool's `onPress`/`onDrag`/.../
`onRelease`) must undo as one step, not one per call — `beginGesture()`/
`endGesture()` bracket that. Only the first `pushUndo()` inside a
gesture actually pushes a snapshot; a `BrushSelectTool` drag calling
`editing()` (and so `pushUndo()`) fifty times still costs exactly one
undo entry.

**Dirty tracking**: `controller.isDirty` is `True` from the first edit
(or `undo`/`redo`) since the project was created or last saved, `False`
right after `save()`. `save(filePath=None)` defaults to `project.
filePath` (plain "Save"); pass a path explicitly for "Save As". Raises
`ValueError` if there's no path yet and none was given.

**Mesh recomputation runs on a background `QThread`** (`_MeshWorker`,
same file) — a full image's boolean-union work (~0.6s) is long enough to
visibly stall the UI otherwise. `rebuildMesh()` snapshots exactly what
the computation needs (`_CanvasSnapshot`: copies of `map`/`layers`,
`len(palette)`) so the worker thread never touches the live, possibly
still-mutating `Canvas`; `meshInvalidated` fires immediately and
`meshReady(mesh)` once the worker's `meshComputed` signal is delivered
back on the main thread. If another edit arrives while a computation is
already running, only the *latest* request is kept (`_pendingMeshRequest`)
and started when the current one finishes — a burst of edits collapses
into one follow-up recompute, not a growing queue. `AppController.
closeProject` blocks on any in-flight worker before letting a
`ProjectController` (its parent) be destroyed, since Qt aborts the
process if a `QThread` is destroyed while still running.

`ProjectController.canvasController` is a `CanvasController` (below),
created alongside every project.

### `AppController` — the open projects ("tabs") and the one `ToolController`

`projectControllers` (list) + which index is active; `newProjectFromImage`
/ `openProject` / `closeProject` / `setActiveProject` / `saveActiveProject`
(delegates to the active `ProjectController.save`, so it inherits Save
vs. Save As); signals `projectOpened` / `projectClosed` /
`activeProjectChanged`. Also owns the single `ToolController` — the
selected tool and its options persist across tabs, like a normal image
editor, rather than resetting per project.

### `ToolController` — routes canvas interaction to the active tool

Owns the `ToolRegistry`; `setActiveTool(name)` switches it and emits
`activeToolChanged(tool)` (for a tool rail to highlight the right button
and an options bar to swap panels). `press(pos)`/`drag(pos)`/
`release(pos)` are the actual entry point from a canvas view's mouse
events: `press` resolves `AppController.activeController` once, brackets
the whole press→drag→release sequence in that `ProjectController`'s
`beginGesture()`/`endGesture()` (even a mid-drag tab switch can't
misattribute later samples to a different project), and hands each
handler that project's `canvasController` — not the `ProjectController`
itself, since tools only ever need what `CanvasController` exposes plus
direct `Canvas` access through it (see the tool layer above).

### `CanvasController` — the one place a view calls to edit a project

Created one-per-project (`projectController.canvasController`), wrapping
that `ProjectController` (not a bare `Project`) so every edit still goes
through its undo stack and mesh pipeline. This is the actual command
surface: everything a view (or a menu, or a palette panel) calls to
change a project's content lives here, except selection (which lives
directly on `WandTool`/`BrushSelectTool` - see the tool layer above for
why a same-signature passthrough here would add nothing):

| method | via |
|---|---|
| `transformSelectionLayer(delta)` | `with projectController.editing(affectsMesh=True):` |
| `setHollow(hollow)` | `with projectController.editing(affectsMesh=True):` |
| `setMargin(margin)` | `with projectController.editing(affectsMesh=True):` |
| `setTubeMargin(value)`, `setWallThickness(value)`, `setBulgeSize(value)` | `with projectController.editing(affectsMesh=True):` — these do change `Mesh`'s triangles (see `componentTriangles` in `pixelComponents.py`), unlike `cellWidth`/`cellHeight` below |
| `setCellWidth(mm)`, `setCellHeight(mm)` | `with projectController.editing(signal=projectController.viewSettingsChanged):` — export-only scale, so `affectsMesh` doesn't apply here; these never touch `Mesh`'s own unit-based triangles |
| `renameColor(index, name)`, `recolorColor(index, rgb)` | `with projectController.editing(signal=projectController.paletteChanged):` |

This is also the settled home for general canvas-view operations that
don't fit the table above and aren't a `Tool`'s job either. The concrete
example on the table is a future outline overlay for the 2D view; there
may be others. Decide what goes here as those needs become concrete —
don't invent methods speculatively.

## Views (`utils/ui/`, `canvasElement.py`, `meshElement.py`, `exportDialog.py`)

Built entirely against the controller-layer signals/methods above; nothing
here calls into `utils/data/` directly (the one exception is `Vector2`,
`canvasElement.py`'s own screen-space pan/zoom helper - a UI-layer
concern, not domain state).

- **`utils/ui/base.py`** — `Theme`: the app's colors/fonts/chrome metrics
  as one dataclass (lifted from `design/ui-mockup.html`'s draft palette),
  so retheming is one object instead of a grep across widgets. Every
  composite widget below takes a `Theme` instead of hardcoding colors.
- **`utils/ui/elements.py`** — the shared widget primitives everything
  else is built from (`Text`/`SectionLabel`/`MonoText`, `Button`/
  `IconButton`/`PillToggle`, `Slider`/`Stepper`/`Dropdown`/
  `SegmentedControl`, `PaletteRow`, `Tab`/`TabBar`, `ViewModeTabs` (the
  Canvas/Layer/Mesh work-area switcher - squared tops, rounded bottoms;
  not built on `Tab`/`TabBar` since it's a fixed small set of mode
  buttons with a different shape, not a per-project tab), plus
  `buildOptionWidget` - which turns a `Tool.Options` schema entry into a
  live widget generically, so a new tool option never needs hand-written
  UI). No project- or controller-specific logic lives here.
- **`utils/ui/menuBar.py`, `toolRail.py`, `toolOptionsBar.py`,
  `paletteRail.py`, `meshSettingsPanel.py`, `statusBar.py`** — the
  concrete panels `AppWindow` assembles: File/Edit/View menu
  (`MenuBar`), tool selector (`ToolRail`), the active tool's own options
  plus Undo/Redo (`ToolOptionsBar`), the palette list (`PaletteRail`),
  the Solid/Hollow + margin + structural-geometry + export-scale card
  (`MeshSettingsPanel`), and the bottom status strip (`StatusBar`). Each
  binds to a `ProjectController` (`bindProject`) and redraws off its
  signals; none of them touch `utils/data/` directly.
- **`utils/ui/appWindow.py`** — `AppWindow`: assembles all of the above
  around an `AppController`, plus a tab strip driving
  `AppController.newProjectFromImage`/`setActiveProject`/`closeProject`.
  `setCanvasArea`/`setLayerCanvasArea`/`setMeshElement` slot in the
  color/layer/mesh views below (kept as a separate seam so `AppWindow`
  doesn't import Qt-OpenGL machinery it doesn't otherwise need);
  `setExportHandler` wires in whatever opens `ExportDialog`. `main.py` is
  what actually calls all four.

  The work area itself is a `ViewModeTabs` (`elements.py`) row in normal
  document flow, immediately above a `QStackedLayout` of three pages -
  "Canvas" (the color canvas), "Layer" (the layer canvas), "Mesh" (the
  mesh view) - one view visible at a time. The tabs are a real layout
  row, not a widget floated on top of the stack: an earlier version
  positioned them with manual coordinates over the stack, which both
  fought Qt's compositing of the mesh page's `QOpenGLWidget` (an overlay
  widget can end up painted *under* a `QOpenGLWidget` unless it opts into
  `Qt.WA_AlwaysStackOnTop` - see that class's own docs - and even then it
  proved unreliable here) and needed a hand-tuned offset to line up with
  the tool options bar above it. Laying the tabs out in flow instead
  means they can never overlap the GL surface at all, and alignment
  falls out of the layout rather than a magic-number `move()`.
  `setLayerCanvasArea` also adds "Show Layer Numbers" to the View menu
  when the layer canvas's artist exposes `setShowLabels`
  (`LayerCanvasArtist`, see below); `setCanvasArea`'s own "Zoom to Fit"
  action resets both the Canvas and Layer pages together
  (`_resetCanvasViews`) rather than needing a second action for whichever
  of the two isn't currently on screen.
- **`canvasElement.py`** — the 2D views: `CanvasArtist` (paints
  `canvas.map` through `canvas.palette.colors`, the selection overlay and
  its marching-ants outline, and owns pan/zoom) and `CanvasArea` (routes
  mouse events to `ToolController.press`/`drag`/`release`, and handles
  middle-drag pan / wheel zoom directly since those are view navigation,
  not an edit). `LayerCanvasArtist(CanvasArtist)` is the layer view - same
  class, same `CanvasArea` shell (passed as `artistClass=LayerCanvasArtist`
  rather than a second near-duplicate widget), but `_paintImage` renders
  `canvas.layers` as grayscale (darker = lower height; a flat, out-of-
  range tone for cells with `layers < 1` - unassigned, same test
  `pixelPlan.py`'s `PixelPlan.empty` uses - so they read as "no height"
  rather than a real low one) instead of `canvas.map`/the palette, and
  `_paintOverlay` (a hook `CanvasArtist.paintEvent` calls after the
  selection overlay, a no-op on the base class) draws each cell's height
  as text when `showLabels` is on and the cell is large enough to read.
  Because only the fill differs, the same Wand/Brush tools select
  identically on both panes - selection is canvas-wide state, not
  per-view.
- **`meshElement.py`** — the 3D print preview: `MeshElement`, a
  `QOpenGLWidget` doing one flat-shaded draw call per palette color (plus
  the base plate) straight off `Project.mesh.meshes`, with simple
  orbit/pan/zoom camera controls.
- **`exportDialog.py`** — `ExportDialog`: File > Export's window - a live
  `MeshElement` preview, the destination path, cell-size steppers (driving
  the same `CanvasController.setCellWidth`/`setCellHeight` the mesh
  settings card uses), and the save-guard/warnings checks from
  `objExport.py` (`unnamedColorIndices`, `duplicateColorNames`,
  `mesh.warnings`) surfaced before the user can hit Export.
