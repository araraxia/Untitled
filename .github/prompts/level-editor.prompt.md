--
agent: agent
description: Turn the crude Step 6/7 builder from area-system.prompt.md into a fairly polished level editor and asset viewer — a real launcher for opening/starting areas and previewing assets, viewport picking, a full translate/rotate/scale gizmo, undo/redo, a property panel, an asset browser, grid/snapping, and a proper save/load flow.
tools:
  - read_file
  - create_file
  - replace_string_in_file
  - multi_replace_string_in_file
  - grep_search
  - file_search
  - get_errors
---

# Task: Level Editor & Asset Viewer

`area-system.prompt.md` built a deliberately crude builder: a text input, numeric x/y/z fields, an "Add" button, and a Blob-download save — explicitly scoped that way ("no polished editor chrome... explicitly out of scope"). This task lifts that constraint. You are turning `area-viewer.html`/`areaViewer.js` from that crude builder into a genuinely usable tool: a real entry point for opening or starting areas and browsing assets, click-to-select and drag-to-transform entities in the viewport with a full translate/rotate/scale gizmo, undo/redo, a property panel instead of raw JSON, and a save flow that isn't "download a file and move it yourself."

**This builds on, and must not fork, `area-system.prompt.md`'s work.** `Scene` stays the single data container; this task adds an editing layer *around* it (commands, selection, gizmos, panels), not a competing one. Read that prompt file's Steps 3, 6, and 7 before anything else — this task's Step 1 makes that explicit.

**Scope line, stated up front — this is "fairly polished," not "full editor":**

| In scope | Out of scope |
| --- | --- |
| Single-entity selection | Multi-select / group operations |
| Full transform gizmo: translate, rotate, **and** scale, mode-switchable, in both 2D and 3D | Free-form bounding-box/corner-drag resize — scale is axis-handle-driven only, not a resizable box |
| Undo/redo for editor actions | Branching history / history panel UI |
| Manifest-driven asset browser | A custom asset *import* UI (that's `convert_mesh.py`'s job, unchanged) |
| Grid + position/rotation snapping | Terrain sculpting, procedural placement tools |
| One local editor session | Real-time multi-user/collaborative editing |
| `ScriptComponent` params as a form (type + key/value fields) | A visual behaviour-tree/script editor |

If a request during implementation falls in the right column, it's a follow-up task, not scope creep to absorb here.

## Required Reading

Read these files before writing any code:

- `.github/prompts/area-system.prompt.md` — **all of it**, especially Step 3 (`Scene`'s API and `_source` tagging), Step 6 (the `area-viewer.html`/`areaViewer.js`/`freeCamera.js` boot path this task extends), and Step 7 (the crude builder this task replaces — know exactly what exists before deciding what to keep vs. rebuild).
- `.github/prompts/3d-coordinate-mapping.prompt.md` — Step 2 (`mat4.compose`/`rotationXYZ`, needed for the gizmo's drag math), Step 5 (`render_template`, needed for the asset browser and property panel), Step 8 (stylization flags — `vertex_color`/`affine_uv`/`color_levels`/`fogColor`/`fogNear`/`fogFar`/`ambientColor` — needed for the asset preview mode's toggle panel), Step 9 (`parts[]`/`attachTo`/sockets), Step 10 (`dangle`), Step 11 (`animation_id`), Step 12 (`action_animations`) — the property panel (Step 8 of this task) edits all of these.
- `frontend/js/engine/assetLoader.js` — `loadManifest()`'s `categories` array, now `["images", "animations", "materials", "audio", "meshes", "entities"]` per the two prior prompt files; this task adds `"areas"`.
- `tools/build_manifest.py` — the established per-category scan pattern (`mesh_dir`, `entity_dir`, ...); this task adds a third, identical block for areas.
- `frontend/js/engine/renderer.js` and `frontend/js/engine/entityRenderer.js` — the render loop and draw paths this task's gizmo/highlight overlay draws on top of, without altering normal entity rendering.
- `ROADMAP.md` Phase 9.2 — "Animation Preview: standalone page that loads a `GPUSpriteSheet` and plays animation clips." This task's Step 4 (asset preview mode) generalises and supersedes that idea rather than building a second, separate preview page — cross-reference it in Step 13's docs.

## Constraints

- No new frontend dependencies. Vanilla JS/HTML/CSS/DOM for all editor UI (panels, forms, lists) — consistent with the rest of this codebase, which has never added a UI framework. Plain `<div>`/`<input>`/`<select>` elements styled with CSS are sufficient; do not reach for a component framework to build forms.
- `Scene` (`area-system.prompt.md` Step 3) does not change in this task except additively, if at all. All editor actions go through a new command layer (Step 5) that *calls* `Scene`'s existing API — `addEntity`/`updateEntity`/`removeEntity`/`setCamera`/`setLighting` — it does not reach into `Scene`'s internals or duplicate its bookkeeping.
- Editor-placed entities are still tagged through `Scene`'s existing `'local'`/`'authoritative'` mechanism — this task does not introduce a third tag or change that rule.
- The gizmo, selection highlight, and grid overlay are editor-only rendering, gated behind editor mode (`?mode=builder`, extended in this task — see Step 3) — plain viewer mode and real gameplay must render identically to before this task, with zero added overhead when the editor isn't active.
- Follow the JavaScript Airbnb style guide (2-space indent, single quotes) and PEP 8 (79 cols) per `.github/copilot-instructions.md`.
- Backend changes are limited to Step 2 (the `"areas"` manifest category) and Step 11 (finishing the dev-only save route `area-system.prompt.md` Step 7 task 4 already stubbed as optional) — nothing else. Do not touch simulation systems, ECS internals, or anything already fixed/built in the two prior prompt files.
- The transform gizmo (all three modes) and picking system must degrade gracefully in 2D mode (`camera.mode === '2d'`) — screen-space dragging in 2D is simpler (no raycasting needed, just inverse camera transform; rotate collapses to one Z ring; scale drops its Z handle), implement both, do not make the editor 3D-only.

---

## Step 1 — Audit Current State

Before writing code, read `area-system.prompt.md` in full (if not already implemented, read it as the spec for what exists) and summarize:

1. `Scene`'s exact API surface and the `_source` tagging rule — this task's command layer must not violate it.
2. What `areaViewer.js` currently does for `?mode=builder` (the crude Add/Remove/Save panel) — decide what's replaced outright (the raw text-input Add form) versus what's kept and extended (the entity list, now also used for selection sync).
3. Where Area files and asset-definition files live on disk (`frontend/assets/data/area/`, `.../mesh/`, `.../entity/`, `.../material/`) and how the existing manifest categories resolve them — this task's asset browser (Step 9) and launcher (Step 3) both read the manifest, they do not scan the filesystem directly from the browser.

Do not create or edit files in this step.

---

## Step 2 — Manifest Category for Areas

**File:** `tools/build_manifest.py`

The launcher (Step 3) needs to list available Area files without hardcoding paths — the exact problem meshes and entity-definitions already solved twice.

1. Add an `area_dir = ASSETS_DIR / "data" / "area"` scan, identical in structure to the existing `mesh_dir`/`entity_dir` blocks: walk `*.json`, skip `example_*`, id via `json_asset_id()`, populate a top-level `"areas"` dict (`{path, hash}` per entry).
2. Include `"areas"` in the summary line printed by `main()`.

**File:** `frontend/js/engine/assetLoader.js`

3. Add `"areas"` to `loadManifest()`'s `categories` array.

Verify: run `python tools/build_assets.py`, confirm `manifest.json` gains an `"areas"` entry for every file under `frontend/assets/data/area/`; `assetLoader.resolve('<area-id>')` returns the correct path in the browser console.

---

## Step 3 — Entry Point: the Launcher Screen

**New file:** `frontend/js/game/launcher.js`
**File:** `frontend/area-viewer.html` (extend)

This is the concrete answer to "an easy to use entry point for loading or starting existing areas, scenes, and assets." Today, opening anything requires hand-editing a `?area=<path>` query string. This step replaces that with a real first screen.

1. When `area-viewer.html` loads with **no** `?area=` and **no** `?asset=` query parameter, show the launcher instead of booting straight into an empty scene. Three panels, plain DOM (no canvas needed for this screen):
   - **Open Area** — list every entry from the manifest's `"areas"` category (name, and entity count if cheaply available by fetching and counting — don't block the list on this if it's slow; show it as it resolves). Clicking an entry navigates to `area-viewer.html?area=<resolved-path>&mode=builder`.
   - **New Area** — one or two starter presets ("Empty", "Empty with default lighting" — a scene with just `lighting.ambientColor` set to something non-white so it's visibly not "nothing happened"). Clicking creates a blank `Scene` in memory (no file yet) and enters editor mode directly; the first Save (Step 11) is what actually creates the file, prompting for a name.
   - **View Asset** — list every entry from `"meshes"`, `"entities"`, and `"materials"` manifest categories (grouped under those headings). Clicking navigates to `area-viewer.html?asset=<key>&type=mesh|entity|material` (Step 4).
2. Add a "Continue" shortcut if a most-recently-opened area/asset is recorded (`localStorage`, a single key, best-effort — don't build a full recent-files list, one "last opened" entry is enough for "easy to use").
3. This screen must work with **zero backend connection**, consistent with every other standalone mode — it reads the manifest via `fetch`, nothing else.

Verify: with several Area files, mesh files, and entity-definition files present under their respective `frontend/assets/data/` subdirectories, loading `area-viewer.html` with no query params shows all of them, grouped and clickable; choosing one navigates correctly; "New Area" opens a blank, empty, editable scene.

---

## Step 4 — Asset Preview Mode

**File:** `frontend/js/game/areaViewer.js` (extend)

Handles `?asset=<key>&type=mesh|entity|material` from Step 3's launcher — a single-asset viewer, generalising and superseding the `ROADMAP.md` Phase 9.2 "Animation Preview" page idea (note this in Step 13's docs update).

1. Load just the one referenced asset (a `Mesh` directly for `type=mesh`, an entity-definition JSON — which may itself reference a mesh/parts/material — for `type=entity`, or a bare textured quad for `type=material`) into an otherwise-empty `Scene`, positioned at the origin.
2. Orbit camera by default (reuse `freeCamera.js`'s math, or add an `orbitCamera` mode to it — orbiting a fixed point is simpler than full fly controls and more appropriate for inspecting one object): mouse-drag orbits, scroll zooms, no WASD needed here.
3. A small toggle panel exposing the Step 8 stylization flags from `3d-coordinate-mapping.prompt.md` live — `vertex_color`, `affine_uv`, `color_levels` (a slider), `fogColor`/`fogNear`/`fogFar`, `ambientColor` — each toggle calling `scene.setCamera()`/mutating the previewed entity's material data and re-rendering immediately. This is the fastest way to answer "what does this look like with X enabled" without hand-editing JSON.
4. If the asset (or its referenced entity-definition) has an `animation_id` (`3d-coordinate-mapping.prompt.md` Step 11) or sprite animation clip, show basic playback controls (play/pause, scrub, loop toggle) — reuse `sampleTransformClip`/the existing `AnimationController`, do not build a second clip player.
5. No editing affordances in this mode — it's read-only inspection. A "Back to Launcher" link returns to Step 3's screen.

Verify: previewing a mesh with a `dangle`-capable part (if using an entity-definition with `parts`) orbits correctly; toggling `vertex_color` visibly changes the render immediately; toggling it off restores the exact prior appearance (no residual state).

---

## Step 5 — Command Stack (Undo/Redo)

**New file:** `frontend/js/engine/editorCommands.js`

Explicitly lifting `area-system.prompt.md`'s "no undo stack — explicitly out of scope" now that this task's whole point is polish. Wraps `Scene`'s API; `Scene` itself stays unaware undo exists.

1. `class EditorCommands`:
   - `constructor(scene)` — holds a reference to the target `Scene`, an `undoStack: []`, a `redoStack: []`.
   - `execute(command)` — calls `command.do()`, pushes `command` onto `undoStack`, clears `redoStack` (a new action invalidates any redo history — standard editor behaviour, don't try to preserve branching history, that's explicitly out of scope).
   - `undo()` — pops from `undoStack`, calls its `.undo()`, pushes it onto `redoStack`. No-op if `undoStack` is empty.
   - `redo()` — pops from `redoStack`, calls its `.do()`, pushes back onto `undoStack`. No-op if `redoStack` is empty.
2. Command shape: `{ do(), undo(), label }` (a short `label` string for Step 12's optional "last action" display). Provide small factory functions rather than hand-building objects at every call site:
   - `moveEntityCommand(scene, id, oldPos, newPos)`
   - `rotateEntityCommand(scene, id, oldRotation, newRotation)`
   - `scaleEntityCommand(scene, id, oldScale, newScale)`
   - `addEntityCommand(scene, id, data)` — `undo()` calls `scene.removeEntity(id)`
   - `removeEntityCommand(scene, id, data)` — capture `data` before removal so `undo()` can `addEntity` it back
   - `updateEntityCommand(scene, id, oldPatch, newPatch)` — the generic fallback for property-panel field edits (Step 8) that aren't one of the three transform-specific commands above
3. Every editor mutation from this task onward (gizmo drag, property panel edit, asset-browser placement, delete) goes through `EditorCommands.execute()` — never call `scene.addEntity`/`updateEntity`/`removeEntity` directly from UI code once this step lands.
4. Bind `Ctrl+Z` / `Ctrl+Shift+Z` (or `Ctrl+Y`) to `undo()`/`redo()`, active only in editor mode.

Verify: place an entity, move it, delete it — three `Ctrl+Z` presses restore it to un-placed; three `Ctrl+Shift+Z` presses replay all three actions back to the deleted state.

---

## Step 6 — Viewport Picking & Selection

**File:** `frontend/js/engine/areaViewer.js` or a new `frontend/js/engine/picking.js`

The prerequisite for the gizmo (Step 7) and property panel (Step 8) — you can't move or edit what you haven't selected.

1. On viewport click (not drag — distinguish a click from the start of a gizmo drag by movement threshold), in 3D mode: build a ray from the camera through the clicked screen pixel (standard inverse-view-projection unprojection using `mat4.js`'s existing functions — no new matrix math needed beyond what Step 2 of the coordinate-mapping task already built), test it against each entity's bounding sphere (derive a radius from `size`/mesh bounds — an approximate, cheap test is fine, this is editor tooling, not gameplay-critical precision), pick the nearest hit.
2. In 2D mode: inverse the camera's screen transform to get world coordinates, hit-test against each entity's `size`-derived rectangle.
3. Maintain a single `selectedEntityId` (or `null`). Clicking empty space deselects. Clicking an entity in Step 3-derived... — no, clicking an entity in the **entity list panel** (carried over from `area-system.prompt.md` Step 7, now repurposed as a selection list rather than only a delete-target list) also sets `selectedEntityId`, kept in sync both directions (list click ↔ viewport click).
4. Render a selection highlight: an outline or wireframe bounding box around the selected entity, drawn as a cheap additional draw call (a line-list `GPURenderPipeline`, or simplest: reuse the existing quad/mesh pipeline with a flat unlit colour and `topology: 'line-list'`) — gated entirely behind editor mode, zero cost otherwise.

Verify: clicking a mesh in the 3D viewport selects it (visible highlight); clicking empty space deselects; selecting via the entity list highlights the same entity in the viewport.

---

## Step 7 — Transform Gizmo (Translate, Rotate, Scale)

**New file:** `frontend/js/engine/gizmo.js`

The concrete fix for "the builder can only place new entities, never adjust them" — the gap identified when this editor was first scoped out. Three modes, one at a time (like Blender's G/R/S or a Unity/Unreal toolbar), not all three handle sets visible simultaneously — that would be cluttered and error-prone to click precisely.

1. A `gizmoMode` state: `'translate' | 'rotate' | 'scale'`, default `'translate'`. Switch via toolbar buttons and keyboard shortcuts `T`/`R`/`S` (guarded, like Step 12's shortcuts, against stealing focus from text inputs).
2. Shared setup: when an entity is selected (Step 6), compute its world transform via `mat4.compose` (position/rotation/scale) and derive a fixed **screen-space** gizmo size (scale inversely with camera distance so it neither shrinks to invisibility far away nor balloons up close — an explicit correction factor, not physically based). All three modes render at the entity's position using this shared sizing logic.
3. **Translate mode**: three coloured drag handles (arrows or simple line+cone, conventional red/green/blue for X/Y/Z). Pointer-down on a handle starts a drag constrained to that axis: unproject two points along the axis into screen space, form a screen-space direction vector, dot the mouse delta against it to get a world-space delta along that one axis. In 2D mode, only X/Y handles render (no Z).
4. **Rotate mode**: three coloured rings/arcs around each axis (a ring in the plane perpendicular to that axis). Pointer-down on a ring starts a drag: track the angle between the gizmo center and the mouse position, projected onto that ring's plane, each pointer-move; the *change* in angle since the previous move becomes a delta rotation applied via `mat4.rotationXYZ` on that single axis (accumulate into the entity's stored Euler rotation using Step 2 of `3d-coordinate-mapping.prompt.md`'s documented Z-then-Y-then-X convention — do not invent a different composition order here). In 2D mode there is exactly one ring (Z/roll — "the" 2D rotation).
5. **Scale mode**: three small box handles at the end of each axis, dragging one scales that axis only (screen-space distance from gizmo center to cursor, relative to the drag-start distance, as the scale factor) — plus one uniform-scale handle at the gizmo's own origin (drag-out/drag-in scales all axes together equally). No corner/bounding-box drag handles (see the scope table) — axis and uniform handles only. In 2D mode, only X/Y axis handles plus the uniform handle render.
6. On drag end (any mode), call the appropriate `editorCommands` factory (Step 5) — `moveEntityCommand` for translate, and new `rotateEntityCommand`/`scaleEntityCommand` following the same `{do, undo, label}` shape — never a direct `scene.updateEntity` call, and never one command per intermediate drag frame (coalesce into a single command on pointer-up).

Verify: each mode's handles render only when that mode is active; dragging a translate handle moves only along its axis; dragging a rotate ring rotates smoothly and continuously (no snapping to a wrong direction partway through a drag — a common bug from recomputing absolute angle instead of accumulating delta angle); dragging a scale handle scales only that axis, the uniform handle scales all axes together; every drag (any mode) is exactly one undo step.

---

## Step 8 — Property Panel

**File:** `frontend/js/game/areaViewer.js` (extend, new DOM panel)

Replaces "raw JSON textarea" with actual form fields, for whatever entity is selected (Step 6).

1. Numeric fields for `transform3d.position`/`rotation`/`scale` (or 2D `x`/`y` in 2D mode) — typed values in degrees for rotation (converted to radians before calling `mat4.rotationXYZ`) rather than raw radians, since that's what a person actually wants to type. These fields are a **second way to reach the same three commands Step 7's gizmo uses** (`moveEntityCommand`/`rotateEntityCommand`/`scaleEntityCommand`), not a separate mechanism — keep both in sync: dragging the gizmo updates these fields live, and committing a typed value updates the gizmo's rendered position/orientation/size immediately. Typed fields remain useful even with a full gizmo for precise values a mouse drag can't hit exactly (e.g. "rotate exactly 90°").
2. A `render_template` picker — a dropdown populated from the `"entities"` manifest category (reuses Step 9's asset browser data source, doesn't duplicate the fetch).
3. If the entity's Area-file `components` list has a `ScriptComponent` (`area-system.prompt.md` Step 10/11): a `script_type` dropdown (`waypoint_loop`/`orbit`/`follow`) and a small generated form for that type's `params` (waypoint list as a repeatable x/y row; orbit's center/radius/angular_speed as three numeric fields; follow's target entity id as a dropdown of other placed entities) — not a raw JSON textarea. If there's no `ScriptComponent`, show an "Add Script" button that adds one with sensible defaults via `editorCommands`.
4. If the selected entity's definition has `parts[]` (`3d-coordinate-mapping.prompt.md` Step 9): a collapsible sub-section per part exposing its `dangle` (Step 10) and `animation_id`/`action_animations` (Steps 11/12) fields as toggles/dropdowns.
5. Every field change calls `editorCommands.execute(updateEntityCommand(...))` on blur/commit (not on every keystroke — debounce or commit-on-blur, so undo doesn't need one press per typed character).

Verify: editing an entity's position numerically moves it in the viewport and is undoable; changing `render_template` swaps the rendered mesh live; adding a `ScriptComponent` via the panel produces the same result as hand-authoring one in the JSON (cross-check against `area-system.prompt.md` Step 11's verify).

---

## Step 9 — Asset Browser Panel

**File:** `frontend/js/game/areaViewer.js` (extend)

Replaces the crude "type a raw asset id into a text box" `Add` flow from `area-system.prompt.md` Step 7.

1. A panel listing available meshes/entity-definitions (from the `"meshes"`/`"entities"` manifest categories, same data Step 3's launcher and Step 8's `render_template` picker use — fetch once, share the result, don't re-fetch the manifest per panel), with a text filter input for quick search by name.
2. Clicking an entry either places it directly at a sensible default position (world origin, or the camera's look-at point on the ground plane) or arms a "click in viewport to place" mode — pick whichever is simpler to implement well; a fixed default position with the gizmo (Step 7) available immediately after to reposition it is likely the simpler, still-usable choice.
3. Placement calls `editorCommands.execute(addEntityCommand(...))` — undoable, consistent with every other mutation in this task.

Verify: filtering the asset list narrows results correctly; placing an asset adds a selected, immediately-repositionable entity; the placement is a single undo step.

---

## Step 10 — Grid, Snapping, and Viewport Aids

**File:** `frontend/js/engine/gizmo.js` or a new `frontend/js/engine/viewportGrid.js`

1. A ground-plane grid overlay in 3D mode (simple line-list, fixed spacing, faint colour, gated behind editor mode) so placement has a visual reference — this is also a good place to reuse the flat-colour line pipeline Step 6's selection highlight already needed.
2. Position snapping: an editor-only "grid size" setting (default e.g. `1.0` world unit); when enabled, Step 7's gizmo drag and Step 9's placement round to the nearest grid multiple. A toggle (keyboard `G` or a checkbox) turns it on/off — off by default is reasonable, or on by default with an easy toggle; pick one and be consistent.
3. Rotation snapping: an optional 15°/45° increment toggle for Step 8's rotation fields (hold a modifier key while adjusting, or a separate checkbox — simplest is a checkbox next to the rotation fields).
4. A small stats readout (entity count in the current scene, current FPS) — cheap, and directly useful while placing many entities. This is the same information `ROADMAP.md` Phase 9.2's "Perf Overlay" describes; implement it here rather than as a separate future page.

Verify: with snapping enabled, dragging the gizmo lands on grid-aligned positions only; disabling snapping restores free movement; the stats readout updates live as entities are added/removed.

---

## Step 11 — Proper Save/Load Flow

**File:** `backend/app.py` (finish the route `area-system.prompt.md` Step 7 task 4 left optional)

1. Implement `POST /dev/save_area` for real: accept the JSON body (`Scene.toAreaFileJSON()`'s output), validate it has an `area_id`, write it to `frontend/assets/data/area/area-<id>.json`. Gate behind a debug/dev-mode flag exactly as that step specified — confirm it's unreachable in a packaged build before considering this step done.

**File:** `frontend/js/game/areaViewer.js` (extend)

2. "Save" (`Ctrl+S` or a button): if the current scene was opened from an existing file, `POST` to `/dev/save_area` with that file's id, overwriting in place — no confirmation needed for a plain save. If the scene is new (Step 3's "New Area" path, no backing file yet) or the user chooses "Save As," prompt for a name/id first, then `POST`.
3. If `/dev/save_area` is unreachable (network error, or the route is disabled in this build), fall back to the Step 4-era Blob-download behaviour from `area-system.prompt.md` Step 7 task 3, with a visible notice explaining why ("dev save route unavailable — downloaded instead").
4. "Load" is Step 3's launcher — do not build a second, separate load dialog inside the editor; a "Back to Launcher" action (also useful for Step 4's asset preview) reuses the same screen.

Verify: editing and saving an existing area, then reopening it via the launcher, shows the saved changes; a brand-new area, saved for the first time, appears in the launcher's "Open Area" list afterward (proving the manifest-driven list and the save route agree on where files live).

---

## Step 12 — Keyboard Shortcuts & Polish

**File:** `frontend/js/game/areaViewer.js` (extend)

1. `Delete`/`Backspace` — remove the selected entity (via `editorCommands`, undoable).
2. `Ctrl+D` — duplicate the selected entity at a small offset (via `editorCommands`'s `addEntityCommand`).
3. `F` — snap the camera to focus on/orbit the selected entity (useful after placing something off-screen).
4. `Escape` — deselect.
5. A small always-visible "last action" label (using command `label`s from Step 5) so undo/redo feels legible rather than mysterious.

Verify: each shortcut works only while the viewport has focus and an editor mode is active (not while typing in a property-panel text field — guard against that explicitly, a common and annoying bug class).

---

## Step 13 — Documentation

**File:** `docs/graphics/AREA_SYSTEM.md` (extend, created by `area-system.prompt.md` Step 12)

1. Add a section documenting the launcher (Step 3), asset preview mode (Step 4), and the editor's capabilities (selection, gizmo, undo/redo, property panel, asset browser, snapping, save flow) — screenshots optional, a clear feature list is the minimum bar.
2. Note explicitly that this supersedes `ROADMAP.md` Phase 9.2's separate "Animation Preview" page concept — Step 4's asset preview mode covers that use case; update `ROADMAP.md` Phase 9.2 to point here instead of describing a second, redundant page.
3. Document the scope line from this prompt file's introduction (what's in vs. out) so a future reader doesn't assume multi-select or a script editor already exist.

---

## Step 14 — Smoke Test

```text
python run_browser.py
```

- [ ] Loading `area-viewer.html` with no query params shows the launcher, listing real Area files, meshes, entity-definitions, and materials.
- [ ] "New Area" opens a blank, empty, immediately-editable scene with no backend connection.
- [ ] "View Asset" on a mesh opens the asset preview mode; stylization toggles visibly change the render in real time.
- [ ] Clicking an entity in the 3D viewport selects it (visible highlight); the entity list and viewport selection stay in sync both directions.
- [ ] `T`/`R`/`S` switch gizmo modes; each mode's handles render only when active. Translate handles move the entity along the correct axis; rotate rings rotate smoothly with no direction snapping mid-drag; scale handles (axis and uniform) scale correctly, in both 3D and 2D modes.
- [ ] The property panel's numeric transform fields and the gizmo stay in sync in both directions (dragging updates the fields live; typing a value moves/rotates/scales the gizmo).
- [ ] The property panel edits position/rotation/scale, `render_template`, `ScriptComponent` params, and part-level fields (`dangle`/`animation_id`/`action_animations`) without ever exposing raw JSON.
- [ ] The asset browser places a new entity from a filtered search, immediately selected and repositionable.
- [ ] Grid snapping, when enabled, constrains gizmo drags and placements to grid points; disabling it restores free movement.
- [ ] `Ctrl+Z`/`Ctrl+Shift+Z` correctly undo/redo placement, movement, deletion, and property edits — including a multi-step sequence.
- [ ] `Delete`, `Ctrl+D`, `F`, and `Escape` work as specified and are correctly disabled while a text field has focus.
- [ ] Saving an existing area persists changes and they survive a reload via the launcher; saving a brand-new area makes it appear in the launcher afterward.
- [ ] Plain viewer mode (no `?mode=builder`) and real gameplay (`index.html`) render with zero visible or measurable change from this task — all editor-only rendering (gizmo, grid, highlight) is fully gated off.
- [ ] `get_errors` reports zero errors on all modified/new files.

---

## Success Criteria

- [ ] `tools/build_manifest.py` / `frontend/js/engine/assetLoader.js` — `"areas"` manifest category added, following the established `"meshes"`/`"entities"` pattern exactly
- [ ] `frontend/js/game/launcher.js` — Open Area / New Area / View Asset panels, manifest-driven, zero backend connection required
- [ ] Asset preview mode (`?asset=<key>&type=...`) — orbit camera, live stylization toggles, animation playback if applicable, read-only
- [ ] `frontend/js/engine/editorCommands.js` — `EditorCommands` with `execute`/`undo`/`redo`; every editor mutation from Step 6 onward routes through it; `Scene` itself unmodified by this requirement
- [ ] Viewport picking (3D raycast, 2D hit-test) and a selection highlight, synced with the entity list panel
- [ ] `frontend/js/engine/gizmo.js` — mode-switchable (`T`/`R`/`S`) translate/rotate/scale gizmo, axis-constrained drags (plus uniform scale), each drag coalesced into one undo step, working in both 2D and 3D, synced live with the property panel's numeric fields
- [ ] Property panel covering transform, `render_template`, `ScriptComponent`, and part-level (`dangle`/`animation_id`/`action_animations`) fields with no raw-JSON editing required for any of them
- [ ] Asset browser panel with search/filter, sourced from the same manifest fetch the launcher and property panel already use
- [ ] Grid overlay, position snapping, optional rotation snapping, and a live entity-count/FPS readout
- [ ] `POST /dev/save_area` implemented for real (not just stubbed), dev-mode-gated, with a working Blob-download fallback
- [ ] Keyboard shortcuts (`Delete`, `Ctrl+D`, `F`, `Escape`, undo/redo) correctly disabled while any text input has focus
- [ ] `docs/graphics/AREA_SYSTEM.md` updated; `ROADMAP.md` Phase 9.2 updated to point at this task instead of describing a separate preview page
- [ ] Plain viewer mode and real gameplay have zero rendering or performance change from this task
- [ ] Nothing in the out-of-scope table (multi-select, free-form bounding-box/corner-drag resize, history UI, custom asset import, terrain tools, collaborative editing, visual script editor) was built — flag any of it found half-started rather than finishing it under this task
