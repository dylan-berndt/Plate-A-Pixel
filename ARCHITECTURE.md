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
  `bucketSelect` (contiguous or not, from a clicked position, with an
  optional `source` array to test against - see `WandTool.onPress` for
  why the layer canvas passes `layers` instead of the default `map`),
  `brushSelect` (every cell within a radius, color-blind).
  `transformSelection(delta)` raises/lowers the current selection's
  height. `selectAll`/`deselectAll`/`invertSelection` are whole-canvas,
  no position needed.

  When `__init__` auto-detects a fresh palette from the image's own
  unique colors (the `palette=None` path - a brand-new import, not
  `Project.load` reconstructing a saved one), every entry is also
  auto-named right away via `colorNaming.autoNamesForUnnamed` - a
  freshly imported image never sits with blank palette names in the
  rail until the user gets around to naming them, or until
  `ProjectController.save()`'s own auto-naming (a separate, later safety
  net - see `CanvasController.autoNameUnnamedColors`) fills them in as a
  side effect of saving. A `palette` supplied explicitly is never
  touched by this - reloading a saved project must reproduce exactly the
  names that were actually saved, blank or not.
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
    takes both explicitly — never one uniform scale). Every palette
    entry needs a real name before this can produce a sane result (see
    `unnamedColorIndices`/`duplicateColorNames` below) - unlike
    `Project.save`, this doesn't auto-name anything itself, so that stays
    enforced by `ExportDialog` before it ever calls this.
- **`classifyColor`/`autoNamesForUnnamed`** (`colorNaming.py`) — the
  auto-naming behind `CanvasController.autoNameUnnamedColors`.
  `classifyColor(rgb)` is a rough, deliberately approximate HSV-space
  match to a human color family ("Red"/"Green"/"Blue"/"Brown"/... -
  achromatic colors and brown are carved out as special cases before
  falling through to a plain hue bucket, since a gray has no meaningful
  hue and a brown turns out to be mostly a *value* thing, not a
  saturation one, at an orange-ish hue - see its own docstring for why).
  `autoNamesForUnnamed(palette)` returns `{index: name}` for every
  currently-unnamed entry (never touching an already-named one, whether
  hand-typed or auto-named earlier) - entries sharing a family are
  numbered by brightness ascending ("Green 1" is the darkest green
  present), a family with only one unnamed member skips the number
  ("Brown", not "Brown 1"). Doesn't rename anything itself - it's a pure
  function callers apply through `Palette.rename` so it's a real,
  undoable edit.
- **`Command`/`COMMANDS`/`Preferences`/`KeybindConflictError`**
  (`preferences.py`) — user-level (not per-project) settings, currently
  just keybinds. `Command(id, label, default)` is one bindable action's
  static description - a Qt key-sequence string for `default`, not
  `QKeySequence`, since this file has the same no-Qt rule as the rest of
  `utils/data/`; `COMMANDS` is the full list (`selectAll`/`deselectAll`/
  `invertSelection` today - adding a bindable command means adding one
  `Command` here, then wiring its id to a handler in `KeymapController`,
  below). `Preferences` round-trips a single small JSON file
  (`Preferences.load`/`.save`, defaulting to
  `~/.plate_a_pixel/preferences.json` but remembering whatever path it
  was actually loaded from, so a bare `.save()` writes back to the same
  place - also what lets tests point it at a tmp file and never touch a
  real user's saved keybinds) holding `keybinds` (command id -> key
  sequence string, or `""` for deliberately unbound) - always backfilled
  with every `COMMANDS` entry's own default for anything a saved file
  predates, so a command added in a later version doesn't need a
  migration.

  `setKeybind(commandId, sequence)` enforces that two commands can never
  share a non-empty shortcut: `conflictingCommand(commandId, sequence)`
  finds whichever *other* command already holds it (ignoring the
  command's own current binding, and never flagging `""`/unbound), and
  `setKeybind` raises `KeybindConflictError` - changing nothing - if one
  exists. `resetKeybind` is routed through `setKeybind` rather than
  writing the default directly, so resetting can itself raise the same
  error (another command could have claimed this command's default while
  it was pointed elsewhere). Not conflict-checked on load - a bare
  `Preferences()` can't start in conflict (every `COMMANDS` default is
  already distinct) and a saved file with a genuine conflict shouldn't
  fail to even open the app; going forward, `setKeybind` is what actually
  holds the invariant.

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
- **`FunctionalTool(Tool)`** — adds `onPress(controller, pos, useLayers=False)`
  (required), `onDrag(...)`/`onRelease(...)` (no-ops by default, same
  signature). Handlers take the `CanvasController` to act through as an
  explicit argument rather than storing one — see ToolController below
  for why. `useLayers` says which canvas view the gesture started on
  (color canvas vs. layer canvas - see `CanvasArea`/`LayerCanvasArtist`
  in `canvasElement.py`); `ToolController` resolves it from which pane
  sent the event and forwards it uniformly to whichever tool is active,
  but only a tool whose selection logic is actually color/height-
  dependent needs to look at it (`WandTool` does; `BrushSelectTool`
  ignores it - see below). A handler calls `Canvas` methods directly (via
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
  `diagonal`), not a second tool. `bucketSelect` takes an optional
  `source` array to run its equality test against, defaulting to
  `canvas.map` (color); `WandTool.onPress` passes `canvas.layers` instead
  when `useLayers` is set, so a click on the layer canvas groups pixels
  by assigned height instead of by color - the domain method doesn't
  know or care which, since both are just same-shaped arrays to compare
  against.
- **`BrushSelectTool`** — drag-to-select within a radius (`size` option)
  of the pointer, built on `Canvas.brushSelect`. `onPress` and `onDrag`
  share a private `_stamp()` helper (that's an implementation detail of
  this one tool, not a shared base-class mechanism); a drag that started
  in "Replacement" mode downgrades to "add" on every sample after the
  first, since re-applying "replace" on each dragged-over cell would
  erase everything painted earlier in the same stroke. Ignores
  `useLayers` - `Canvas.brushSelect` is a pure radius stamp with no
  color/height test at all, so it already means the same thing on either
  canvas.
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
`ValueError` if there's no path yet and none was given - checked before
anything else, so a doomed-to-fail call touches nothing. Otherwise,
right before writing, calls `canvasController.autoNameUnnamedColors()`
(see `CanvasController`'s table below) - a `*.pap` save doesn't require
every palette entry to already have a name the way an OBJ export still
does (`ExportDialog`'s own guard, unchanged); this is what makes that
true regardless of which caller (`MenuBar`, a test, anything else)
invokes `save()`.

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
editor, rather than resetting per project — and the single
`KeymapController` (below), for the same reason: keybinds are a user-
level setting, not a per-project one.

### `ToolController` — routes canvas interaction to the active tool

Owns the `ToolRegistry`; `setActiveTool(name)` switches it and emits
`activeToolChanged(tool)` (for a tool rail to highlight the right button
and an options bar to swap panels). `press(pos, useLayers=False)`/
`drag(...)`/`release(...)` are the actual entry point from a canvas
view's mouse events: `press` resolves `AppController.activeController`
once, brackets the whole press→drag→release sequence in that
`ProjectController`'s `beginGesture()`/`endGesture()` (even a mid-drag
tab switch can't misattribute later samples to a different project), and
hands each handler that project's `canvasController` — not the
`ProjectController` itself, since tools only ever need what
`CanvasController` exposes plus direct `Canvas` access through it (see
the tool layer above). `useLayers` (set by `CanvasArea` depending on
which pane sent the event) just rides along unchanged to the tool.

### `KeymapController` — the user's keybinds, as live `QAction`s

Owns `Preferences` (`utils/data/preferences.py`) and one `QAction` per
`Command` in `COMMANDS` (`self.actions`, keyed by command id), built once
in `__init__` and kept in sync with `Preferences` by `_applyShortcuts()`
(called after every rebind). A `QAction` is the single source of truth
for both "what shortcut fires this" and "what a menu shows next to this
item's label" - `MenuBar`'s Edit menu just does
`editMenu.addAction(keymapController.actions["selectAll"])` rather than
building its own action with a copy of the same shortcut, so there's
never a second registration of the same key press to go stale.

`_HANDLERS` is a plain `{command id: lambda controller: ...}` dict - the
one place a command id maps to real behavior. Each action's `triggered`
resolves `AppController.activeController` at the moment it *fires* (same
pattern as `ToolController.press`/tool dispatch — see above), not at
bind time, so the same three actions keep working correctly across a tab
switch; triggering with no project open is just a no-op.

`setKeybind(commandId, sequence)` / `resetKeybind(commandId)` update
`Preferences`, call `Preferences.save()` immediately (no separate "Apply"
step - see `SettingsWindow`), refresh every action's shortcut, and emit
`keybindsChanged`. Both simply call the matching `Preferences` method and
let a `KeybindConflictError` (see `Preferences.setKeybind` above)
propagate straight out uncaught - persisting/refreshing/emitting never
run when that happens, so a rejected rebind changes nothing here either;
it's `SettingsWindow`'s `KeybindRow` that actually catches it and tells
the user.

### `CanvasController` — the one place a view calls to edit a project

Created one-per-project (`projectController.canvasController`), wrapping
that `ProjectController` (not a bare `Project`) so every edit still goes
through its undo stack and mesh pipeline. This is the actual command
surface: everything a view (or a menu, or a palette panel) calls to
change a project's content lives here, except *position-based* selection
(which lives directly on `WandTool`/`BrushSelectTool` - see the tool
layer above for why a same-signature passthrough here would add
nothing):

| method | via |
|---|---|
| `transformSelectionLayer(delta)` | `with projectController.editing(affectsMesh=True):` |
| `setHollow(hollow)` | `with projectController.editing(affectsMesh=True):` |
| `setMargin(margin)` | `with projectController.editing(affectsMesh=True):` |
| `setTubeMargin(value)`, `setWallThickness(value)`, `setBulgeSize(value)` | `with projectController.editing(affectsMesh=True):` — these do change `Mesh`'s triangles (see `componentTriangles` in `pixelComponents.py`), unlike `cellWidth`/`cellHeight` below |
| `setCellWidth(mm)`, `setCellHeight(mm)` | `with projectController.editing(signal=projectController.viewSettingsChanged):` — export-only scale, so `affectsMesh` doesn't apply here; these never touch `Mesh`'s own unit-based triangles |
| `renameColor(index, name)`, `recolorColor(index, rgb)` | `with projectController.editing(signal=projectController.paletteChanged):` |
| `autoNameUnnamedColors()` | `with projectController.editing(signal=projectController.paletteChanged):`, skipped entirely (no undo snapshot, no signal) if every entry already has a name — fills in every still-unnamed entry via `colorNaming.autoNamesForUnnamed` as one edit; called by `ProjectController.save()`, not tied to any UI action of its own |
| `selectAll()`, `deselectAll()`, `invertSelection()` | `with projectController.editing(signal=projectController.selectionChanged):` — whole-canvas selection ops with no click position at all, so not a `Tool`'s job either (see `FunctionalTool.onPress`); bound to keyboard shortcuts by `KeymapController`, not a canvas click |

This is also the settled home for general canvas-view operations that
don't fit the table above and aren't a `Tool`'s job either. Decide what
goes here as those needs become concrete — don't invent methods
speculatively.

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
  Canvas/Layer/Mesh work-area switcher - squared tops, rounded bottoms,
  each button sized to its own label rather than a shared fixed size, so
  "Canvas"/"Mesh" aren't clipped to fit whatever "2D"/"3D" needed; not
  built on `Tab`/`TabBar` since it's a fixed small set of mode buttons
  with a different shape, not a per-project tab), plus
  `buildOptionWidget` - which turns a `Tool.Options` schema entry into a
  live widget generically, so a new tool option never needs hand-written
  UI). No project- or controller-specific logic lives here.
- **`utils/ui/menuBar.py`, `toolRail.py`, `toolOptionsBar.py`,
  `paletteRail.py`, `meshSettingsPanel.py`, `statusBar.py`,
  `settingsWindow.py`** — the concrete panels `AppWindow` assembles:
  File/Edit/View menu (`MenuBar`), tool selector (`ToolRail`), the active
  tool's own options plus Undo/Redo (`ToolOptionsBar`), the palette list
  (`PaletteRail`), the Solid/Hollow + margin + structural-geometry +
  export-scale card (`MeshSettingsPanel`), the bottom status strip
  (`StatusBar`), and the Settings window (`SettingsWindow`, below). Each
  of the first six binds to a `ProjectController` (`bindProject`) and
  redraws off its signals; none of them touch `utils/data/` directly.
  `MenuBar`'s Edit menu adds `KeymapController.actions["selectAll"]` /
  `["deselectAll"]` / `["invertSelection"]` directly (not its own
  actions with a copied shortcut - see `KeymapController` above for why
  that matters) plus a "Settings..." entry that emits
  `MenuBar.settingsRequested`, which `AppWindow` connects to open (and,
  on repeat use, just re-raise) a single lazily-built `SettingsWindow`.

  `SettingsWindow` is a plain `QTabWidget`-in-a-`QDialog` - Keybinds
  (`KeybindsTab`) is the only tab that exists yet, but a future settings
  category is just another `addTab()` call, not a restructure. Every
  edit inside it commits immediately through `KeymapController` (one
  `KeybindRow` per `Command`: a `QKeySequenceEdit` capped to a single
  chord via `setMaximumSequenceLength(1)`, plus a Reset button back to
  that command's default) - no Save/Cancel, since there's nothing
  buffered locally to discard. A rebind or reset that collides with
  another command's current shortcut raises `KeybindConflictError` down
  in `Preferences` (see `KeymapController`/`Preferences` above) rather
  than silently letting two commands share a key; `KeybindRow` catches
  that, shows a `QMessageBox` naming the command that already has it,
  and puts its `QKeySequenceEdit` back to whatever's still actually
  bound.
  `MeshSettingsPanel`'s numeric fields (margin, cell width/height,
  tube margin, wall thickness, bulge size) debounce their own
  `CanvasController` calls (`_debounce`/`DEBOUNCE_MS`, separate from
  `ProjectController.MESH_DEBOUNCE_MS` - that one only delays when a
  queued rebuild actually starts computing, not how many undo snapshots
  and rebuild requests get queued getting there): a stepper's +/- update
  the local value and its own displayed text immediately, but the
  controller call - which pushes an undo snapshot - only fires once
  `DEBOUNCE_MS` has passed with no further click on that field, so
  mashing a stepper doesn't cost one undo entry per click. A pending
  edit is flushed (fired immediately), not dropped, if `bindProject`
  switches to a different project before its timer elapses.
- **`utils/ui/appWindow.py`** — `AppWindow`: assembles all of the above
  around an `AppController`, plus a tab strip driving
  `AppController.newProjectFromImage`/`setActiveProject`/`closeProject`.
  `setCanvasArea`/`setLayerCanvasArea`/`setMeshElement` slot in the
  color/layer/mesh views below (kept as a separate seam so `AppWindow`
  doesn't import Qt-OpenGL machinery it doesn't otherwise need);
  `setExportHandler` wires in whatever opens `ExportDialog`. `main.py` is
  what actually calls all four.

  The work area itself is a `QStackedLayout` of three pages - "Canvas"
  (the color canvas), "Layer" (the layer canvas), "Mesh" (the mesh view)
  - with a `ViewModeTabs` (`elements.py`) floated over its top-left
  corner (`move()` + `Qt.WA_AlwaysStackOnTop` + `raise_()`) so the tabs
  and mesh view genuinely share screen area, rather than a separate
  layout row above the stack. Overlapping a `QOpenGLWidget` (the mesh
  page's `MeshElement`) with an ordinary widget only composites reliably
  in Qt when the two are direct siblings under the *same* parent (see
  `QOpenGLWidget`'s own docs on overlaps) - an earlier version put
  `ViewModeTabs` and `MeshElement` two parents apart (each view lived in
  its own wrapper `QWidget` the real widget was added into), which left
  the tabs painted under the mesh view despite `WA_AlwaysStackOnTop`
  being set. `setCanvasArea`/`setLayerCanvasArea`/`setMeshElement` avoid
  that by installing the real view widget directly as a page of the
  stack (`_installPage`, swapping out a placeholder `QWidget` via
  `QStackedLayout.insertWidget`/`removeWidget`) rather than adding it
  into a wrapper - `QStackedLayout` reparents whatever it holds to be a
  direct child of the widget that owns it, so every page ends up a true
  sibling of `_viewModeTabs`. `setLayerCanvasArea` also adds "Show Layer
  Numbers" to the View menu when the layer canvas's artist exposes
  `setShowLabels` (`LayerCanvasArtist`, see below); `setCanvasArea`'s own
  "Zoom to Fit" action resets both the Canvas and Layer pages together
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
  `CanvasArea` fixes `self._useLayers = isinstance(self.artist,
  LayerCanvasArtist)` once at construction and passes it as `useLayers`
  on every `ToolController.press`/`drag`/`release` call, which is what
  lets `WandTool` sample `canvas.layers` instead of `canvas.map` for a
  click on this pane (see the tool layer above) - the same tools run on
  both panes, but a color-dependent one can tell which array to read.
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
