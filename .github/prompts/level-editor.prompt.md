---
agent: agent
description: Turn the crude Step 6/7 builder from area-system.prompt.md into a fairly polished level editor and asset viewer — a real launcher for opening/starting areas and previewing assets, viewport picking, a full translate/rotate/scale gizmo, undo/redo, a property panel, an asset browser, grid/snapping, a proper save/load flow, zones.prompt.md's Zone authoring, and a UI-menu editor built on client/engine/ui/ with keybind/zone/entity triggers.
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

> **Target client, read before anything else:** this task targets the native Python `client/` (wgpu-py + GLFW + imgui-bundle), per `.github/prompts/wgpu-py-migration.prompt.md`, not the legacy JS/WebGPU browser frontend. It builds directly on `area-system.prompt.md`, which was itself rewritten against the same Python target — every `Scene` method name below (`add_entity`, `set_start_camera`, etc.) is that file's Python API, `snake_case`, not the browser-era `camelCase` originally drafted for `frontend/js/`. If `area-system.prompt.md`'s own Steps 3, 6, and 7 (and, transitively, `wgpu-py-migration.prompt.md`'s client port) haven't landed yet, this task has nothing to build on top of — check those checkmarks first.

`area-system.prompt.md` built a deliberately crude builder: a text field, numeric x/y/z fields, an "Add" button, and a direct-to-disk save — explicitly scoped that way ("no polished editor chrome... explicitly out of scope"). This task lifts that constraint. You are turning `client/game/area_viewer.py` from that crude builder into a genuinely usable tool: a real entry point for opening or starting areas and browsing assets, click-to-select and drag-to-transform entities in the viewport with a full translate/rotate/scale gizmo, undo/redo, a property panel instead of raw JSON, and a save flow that's a first-class "Save"/"Save As," not "hope you remembered the file path."

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
| Zone placement (AABB via the reused gizmo, mesh-footprint via the reused asset browser) and effect-list editing | New zone shapes/effect types (that's `zones.prompt.md`'s scope, not this file's) |
| UI menu authoring on `client/engine/ui/`'s real widgets, with keybind/zone/entity-interact triggers | A general-purpose visual scripting/logic-graph system beyond the three named trigger types |
| Action *definitions* — an action's name/duration and its per-part animation-clip assignment (data) | Action *trigger-wiring* — deciding when/how an action fires (real gameplay logic, a game branch's own code, not editor-authorable) |

If a request during implementation falls in the right column, it's a follow-up task, not scope creep to absorb here.

## Required Reading

Read these files before writing any code:

- `.github/prompts/area-system.prompt.md` — **all of it**, especially Step 3 (`Scene`'s API, `_source` tagging, and the `camera`/`lighting`/`start_camera` three-way split — `start_camera` and `lighting` are *authored* values only ever changed by explicit action, `camera` is the live, constantly-mutating view; this task's Step 11 Scene Settings panel is the only thing that calls `set_start_camera()`), Step 4 (`to_area_file_json()`'s use of `start_camera`, not the live `camera`), Step 6 (the `client/game/area_viewer.py`/`free_camera.py` boot path this task extends, and its `--area=`/`--mode=builder` command-line-flag convention, replacing the browser-era design's URL query string), and Step 7 (the crude builder this task replaces — know exactly what exists before deciding what to keep vs. rebuild).
- `.github/prompts/3d-coordinate-mapping.prompt.md` — Step 2 (`mat4.compose`/`rotationXYZ`, needed for the gizmo's drag math — note the system-change banner partway through that file: Step 2 itself lives in `frontend/js/engine/mat4.js`, already done, but this task's own gizmo math is new Python code written against whatever `client/engine/mat4.py` exists per `wgpu-py-migration.prompt.md`'s port), **Step 5 (`render_template` and `transform3d` — read this carefully: `render_template` and the entity-definition's `mesh` are shared/template-level; `transform3d` and position are per-instance, live on the networked `Entity`, never on the definition file — this task's property panel, Step 8, depends on getting this distinction right)**, Step 8 (stylization flags — `vertex_color`/`affine_uv`/`color_levels`/`fogColor`/`fogNear`/`fogFar`/`ambientColor` — needed for the asset preview mode's toggle panel), Step 9 (`parts[]`/`attachTo`/`localOffset`/sockets — all definition-level, unlike `transform3d`), Step 10 (`dangle`), Step 11 (`animation_id`), Step 12 (`action_animations`) — the property panel (Step 8 of this task) edits all of these. Field *names* in JSON stay exactly as documented regardless of which client reads them.
- `client/engine/asset_loader.py` (`wgpu-py-migration.prompt.md` Step 10's port of `assetLoader.js`) — its manifest `categories`, now including `"images"`, `"animations"`, `"materials"`, `"audio"`, `"meshes"`, `"entities"` per the prior prompt files; this task adds `"areas"`.
- `tools/build_manifest.py` — the established per-category scan pattern (`mesh_dir`, `entity_dir`, ...) and the `build_manifest()` function itself; this task adds a third, identical scan block for areas, and Step 11 calls `build_manifest()` directly (in-process Python import, not a subprocess or HTTP call) from the new save flow to keep `manifest.json` in sync after a save.
- `client/engine/renderer.py` and `client/engine/entity_renderer.py` — the render loop and draw paths this task's gizmo/highlight overlay draws on top of, without altering normal entity rendering.
- `ROADMAP.md` Phase 9.2 — "Animation Preview: standalone page that loads a `GPUSpriteSheet` and plays animation clips." This task's Step 4 (asset preview mode) generalises and supersedes that idea rather than building a second, separate preview mode — cross-reference it in Step 16's docs.
- `.github/prompts/zones.prompt.md` — **all of it** before Step 13. Owns `Zone`'s two shapes and 8 effect types, `ZoneRegistry`'s enter/exit de-dup, and — critically — *why* zones are driven from `Area.update()` rather than registered as a `System` (the `ecs_world`-never-populated gap, confirmed in that file). Step 13 here only visualizes/edits what that file defines; it must not redefine or duplicate any of it.
- `client/engine/ui/` — `draw.py`'s module docstring (the frame-bracket safety rule every draw-list/texture call in this codebase follows), `widgets.py`/`templates.py` (the exact functions Step 14's element types map onto), `theme.py` (`Theme.font`/`color`/`skin_view` — Step 14's property panel exposes theme keys, it doesn't invent new ones), and `run_ui_test.py` (the existing, verified reference for how to construct/drive this package outside a full game — Step 14's editor mode is architecturally the same kind of thing).
- `client/engine/network.py` — the `character_flow_callbacks`/`_state_handlers` callback-registration pattern Step 14 task 7's client-side trigger listener must follow, not a new ad hoc mechanism.

## Constraints

- No new dependencies beyond what `wgpu-py-migration.prompt.md` already introduced (`wgpu`, `glfw`, `imgui-bundle`). All editor *chrome* (panels, forms, lists — Steps 1–13's property panels, the launcher, etc.) is imgui-bundle immediate-mode widgets, consistent with that task's decision to use imgui for every screen. **Exception, deliberate**: Step 14's UI-menu editor renders the menu being authored through `client/engine/ui/`'s own custom-drawn primitives (`draw.py`/`widgets.py`), not imgui widgets — because the whole point of that step is that the live preview *is* the real runtime appearance, and `client/engine/ui/` is what real menus are built from. Editor-only chrome *around* that preview (the property panel, the trigger list) still uses plain imgui, same as everywhere else.
- `Scene` (`area-system.prompt.md` Step 3) does not change in this task except additively, if at all. All editor actions go through a new command layer (Step 5) that *calls* `Scene`'s existing API — `add_entity`/`update_entity`/`remove_entity`/`set_camera`/`set_lighting`/`set_start_camera` — it does not reach into `Scene`'s internals or duplicate its bookkeeping.
- Editor-placed entities are still tagged through `Scene`'s existing `'local'`/`'authoritative'` mechanism — this task does not introduce a third tag or change that rule.
- `set_start_camera()` is called from exactly one place in this entire task: the Scene Settings panel's explicit "Set Start Camera" button (Step 11). No other code — not the gizmo, not free-fly movement, not any per-frame logic — may call it. This is the whole point of `start_camera` existing separately from the live `camera`.
- Property-panel edits to instance-level fields (position/rotation/scale/`render_template`/`ScriptComponent`, Step 8 sections 1–3) and edits to shared-template fields (`parts[]` sub-fields, Step 8 section 4) are visually and mechanically distinct — the latter requires an explicit confirm and a persisted write to the entity-definition file, never a silent blur/commit like the former.
- The gizmo, selection highlight, and grid overlay are editor-only rendering, gated behind editor mode (`--mode=builder`, extended in this task — see Step 3) — plain viewer mode and real gameplay must render identically to before this task, with zero added overhead when the editor isn't active.
- Follow PEP 8 (79 cols, 4-space indent) per `.github/copilot-instructions.md`. This task is Python-only — no `frontend/js/` work.
- Backend changes are limited to Step 2 (the `"areas"` manifest category, actually just `tools/build_manifest.py` — no Flask involvement), Step 11 (finishing the save mechanism `area-system.prompt.md` Step 7 stubbed as a direct file write), and Step 14 task 7 (the narrowly-scoped `menu_trigger` SocketIO event) — nothing else. Do not touch simulation systems, ECS internals, or anything already fixed/built in the prior prompt files (including `zones.prompt.md`'s own `Zone`/`ZoneRegistry`/effect-dispatch code, which Step 13 calls but never modifies).
- The transform gizmo (all three modes) and picking system must degrade gracefully in 2D mode (`camera.mode == '2d'`) — screen-space dragging in 2D is simpler (no raycasting needed, just inverse camera transform; rotate collapses to one Z ring; scale drops its Z handle), implement both, do not make the editor 3D-only.
- **No Blob-download/`<a download>` fallback anywhere in this task** — that mechanism existed only because the browser-era design couldn't write files directly. The native client always can (`open(path, 'w')`); per `area-system.prompt.md`'s own constraint, saves write straight to disk. Do not build a download-and-move-it-yourself UX path that doesn't apply to this client.

---

## Step 1 — Audit Current State

Before writing code, read `area-system.prompt.md` in full (if not already implemented, read it as the spec for what exists) and summarize:

1. `Scene`'s exact API surface and the `_source` tagging rule — this task's command layer must not violate it.
2. What `area_viewer.py` currently does for `--mode=builder` (the crude Add/Remove/Save panel) — decide what's replaced outright (the raw text-input Add form) versus what's kept and extended (the entity list, now also used for selection sync).
3. Where Area files and asset-definition files live on disk (`frontend/assets/data/area/`, `.../mesh/`, `.../entity/`, `.../material/`) and how the existing manifest categories resolve them — this task's asset browser (Step 9) and launcher (Step 3) both read the manifest, they do not scan the filesystem directly.
4. Confirm how far `wgpu-py-migration.prompt.md`'s client port and `area-system.prompt.md` have actually gotten (their own step checkmarks) — this task cannot proceed meaningfully without `Scene`, `area_viewer.py`, and a working `client/engine/renderer.py`/`entity_renderer.py` already in place.

Do not create or edit files in this step.

---

## Step 2 — Manifest Category for Areas

**File:** `tools/build_manifest.py`

The launcher (Step 3) needs to list available Area files without hardcoding paths — the exact problem meshes and entity-definitions already solved twice.

1. Add an `area_dir = ASSETS_DIR / "data" / "area"` scan, identical in structure to the existing `mesh_dir`/`entity_dir` blocks: walk `*.json`, skip `example_*`, id via `json_asset_id()`, populate a top-level `"areas"` dict (`{path, hash}` per entry).
2. Include `"areas"` in the summary line printed by `main()`.

**File:** `client/engine/asset_loader.py`

3. Add `"areas"` to the manifest-loading `categories` list.

Verify: run `python tools/build_assets.py`, confirm `manifest.json` gains an `"areas"` entry for every file under `frontend/assets/data/area/`; `asset_loader.resolve('<area-id>')` returns the correct path.

---

## Step 3 — Entry Point: the Launcher Screen

**New file:** `client/game/launcher.py`
**File:** `client/game/area_viewer.py` (extend)

This is the concrete answer to "an easy to use entry point for loading or starting existing areas, scenes, and assets." Today, opening anything requires hand-typing an `--area=<path>` command-line flag. This step replaces that with a real first screen — an imgui window shown at startup, not a second executable.

1. When the client starts with **no** `--area` and **no** `--asset` argument, show the launcher instead of booting straight into an empty scene. Three imgui panels/sections in one window:
   - **Open Area** — list every entry from the manifest's `"areas"` category (name, and entity count if cheaply available by reading the file and counting — don't block the list on this if it's slow; populate it lazily/async and show what's resolved so far). Clicking an entry re-enters the area-viewer flow with that resolved path and `mode=builder`, in-process (no subprocess relaunch — this is a UI-state transition within the same running client).
   - **New Area** — one or two starter presets ("Empty", "Empty with default lighting" — a scene with just `lighting.ambientColor` set to something non-white so it's visibly not "nothing happened"). Clicking creates a blank `Scene` in memory (no file yet) and enters editor mode directly; the first Save (Step 11) is what actually creates the file, prompting for a name.
   - **View Asset** — list every entry from `"meshes"`, `"entities"`, and `"materials"` manifest categories (grouped under those headings). Clicking navigates into asset preview mode (Step 4) with that asset key and type.
2. Add a "Continue" shortcut if a most-recently-opened area/asset is recorded (a single small local settings file, e.g. `client/.editor_state.json`, best-effort — don't build a full recent-files list, one "last opened" entry is enough for "easy to use").
3. This screen must work with **zero backend connection**, consistent with every other standalone mode — it reads the manifest via `asset_loader.py`'s direct filesystem access, nothing else.

Verify: with several Area files, mesh files, and entity-definition files present under their respective `frontend/assets/data/` subdirectories, launching the client with no arguments shows all of them, grouped and clickable; choosing one transitions correctly; "New Area" opens a blank, empty, editable scene.

---

## Step 4 — Asset Preview Mode

**File:** `client/game/area_viewer.py` (extend)

Handles the launcher's "View Asset" selection (or a direct `--asset=<key> --asset-type=mesh|entity|material` startup argument) — a single-asset viewer, generalising and superseding the `ROADMAP.md` Phase 9.2 "Animation Preview" page idea (note this in Step 16's docs update).

1. Load just the one referenced asset (a `Mesh` directly for `type=mesh`, an entity-definition JSON — which may itself reference a mesh/parts/material — for `type=entity`, or a bare textured quad for `type=material`) into an otherwise-empty `Scene`, positioned at the origin.
2. Orbit camera by default (reuse `free_camera.py`'s math, or add an orbit mode to it — orbiting a fixed point is simpler than full fly controls and more appropriate for inspecting one object): mouse-drag orbits, scroll zooms, no WASD needed here.
3. A small imgui toggle panel exposing the Step 8 stylization flags from `3d-coordinate-mapping.prompt.md` live — `vertex_color`, `affine_uv`, `color_levels` (a slider), `fogColor`/`fogNear`/`fogFar`, `ambientColor` — each toggle mutating the previewed entity's material data / calling `scene.set_camera(...)` and re-rendering immediately. This is the fastest way to answer "what does this look like with X enabled" without hand-editing JSON.
4. If the asset (or its referenced entity-definition) has an `animation_id` (`3d-coordinate-mapping.prompt.md` Step 11) or sprite animation clip, show basic playback controls (play/pause, scrub, loop toggle) — reuse `sample_transform_clip`/the existing `AnimationController`, do not build a second clip player.
5. **"Simulate Motion" toggle**, off by default: applies a small automatic back-and-forth sway/rotation to the previewed root entity's position. Without this, a `dangle`-equipped part (`3d-coordinate-mapping.prompt.md` Step 10) has nothing to react to — dangle is driven entirely by the parent's frame-to-frame position delta, and an orbit-only camera never moves the previewed object itself. This is the only way asset preview mode can actually demonstrate what a dangling part looks like, as opposed to just sitting motionless at rest.
6. No editing affordances in this mode — it's read-only inspection. A "Back to Launcher" button returns to Step 3's screen.

Verify: previewing an entity-definition with a `dangle`-capable part shows it motionless at rest with "Simulate Motion" off, and visibly swaying once it's turned on; toggling `vertex_color` visibly changes the render immediately; toggling it off restores the exact prior appearance (no residual state).

---

## Step 5 — Command Stack (Undo/Redo)

**New file:** `client/engine/editor_commands.py`

Explicitly lifting `area-system.prompt.md`'s "no undo stack — explicitly out of scope" now that this task's whole point is polish. Wraps `Scene`'s API; `Scene` itself stays unaware undo exists.

1. `class EditorCommands`:
   - `__init__(self, scene)` — holds a reference to the target `Scene`, an `undo_stack: list`, a `redo_stack: list`.
   - `execute(command)` — calls `command.do()`, pushes `command` onto `undo_stack`, clears `redo_stack` (a new action invalidates any redo history — standard editor behaviour, don't try to preserve branching history, that's explicitly out of scope).
   - `undo()` — pops from `undo_stack`, calls its `.undo()`, pushes it onto `redo_stack`. No-op if `undo_stack` is empty.
   - `redo()` — pops from `redo_stack`, calls its `.do()`, pushes back onto `undo_stack`. No-op if `redo_stack` is empty.
2. Command shape: an object/small dataclass with `do()`, `undo()`, and a `label` string (for Step 12's optional "last action" display). Provide small factory functions rather than hand-building objects at every call site:
   - `move_entity_command(scene, entity_id, old_pos, new_pos)`
   - `rotate_entity_command(scene, entity_id, old_rotation, new_rotation)`
   - `scale_entity_command(scene, entity_id, old_scale, new_scale)`
   - `add_entity_command(scene, entity_id, data)` — `undo()` calls `scene.remove_entity(entity_id)`
   - `remove_entity_command(scene, entity_id, data)` — capture `data` before removal so `undo()` can `add_entity` it back
   - `update_entity_command(scene, entity_id, old_patch, new_patch)` — the generic fallback for property-panel field edits (Step 8) that aren't one of the three transform-specific commands above
3. Every editor mutation from this task onward (gizmo drag, property panel edit, asset-browser placement, delete) goes through `EditorCommands.execute()` — never call `scene.add_entity`/`update_entity`/`remove_entity` directly from UI code once this step lands.
4. Bind `Ctrl+Z` / `Ctrl+Shift+Z` (or `Ctrl+Y`) to `undo()`/`redo()` via GLFW key callbacks, active only in editor mode.

Verify: place an entity, move it, delete it — three `Ctrl+Z` presses restore it to un-placed; three `Ctrl+Shift+Z` presses replay all three actions back to the deleted state.

---

## Step 6 — Viewport Picking & Selection

**File:** `client/game/area_viewer.py` or a new `client/engine/picking.py`

The prerequisite for the gizmo (Step 7) and property panel (Step 8) — you can't move or edit what you haven't selected.

1. On viewport click (not drag — distinguish a click from the start of a gizmo drag by movement threshold, via GLFW mouse-button/cursor-position callbacks), in 3D mode: build a ray from the camera through the clicked screen pixel (standard inverse-view-projection unprojection using `client/engine/mat4.py`'s existing functions — no new matrix math needed beyond what `wgpu-py-migration.prompt.md`'s port of Step 2 already ported), test it against each entity's bounding sphere (derive a radius from `size`/mesh bounds — an approximate, cheap test is fine, this is editor tooling, not gameplay-critical precision), pick the nearest hit.
2. In 2D mode: inverse the camera's screen transform to get world coordinates, hit-test against each entity's `size`-derived rectangle.
3. Maintain a single `selected_entity_id` (or `None`). Clicking empty space deselects. Clicking an entity in the **entity list panel** (carried over from `area-system.prompt.md` Step 7, now repurposed as a selection list rather than only a delete-target list) also sets `selected_entity_id`, kept in sync both directions (list click ↔ viewport click).
4. Render a selection highlight: an outline or wireframe bounding box around the selected entity, drawn as a cheap additional draw call (a line-list `GPURenderPipeline`, or simplest: reuse the existing quad/mesh pipeline with a flat unlit colour and `topology: 'line-list'`) — gated entirely behind editor mode, zero cost otherwise.

Verify: clicking a mesh in the 3D viewport selects it (visible highlight); clicking empty space deselects; selecting via the entity list highlights the same entity in the viewport.

---

## Step 7 — Transform Gizmo (Translate, Rotate, Scale)

**New file:** `client/engine/gizmo.py`

The concrete fix for "the builder can only place new entities, never adjust them" — the gap identified when this editor was first scoped out. Three modes, one at a time (like Blender's G/R/S or a Unity/Unreal toolbar), not all three handle sets visible simultaneously — that would be cluttered and error-prone to click precisely.

1. A `gizmo_mode` state: `'translate' | 'rotate' | 'scale'`, default `'translate'`. Switch via toolbar buttons (imgui) and keyboard shortcuts `T`/`R`/`S` (guarded, like Step 12's shortcuts, against stealing focus from imgui text inputs — imgui exposes `io.want_capture_keyboard`/similar for exactly this check).
2. Shared setup: when an entity is selected (Step 6), compute its world transform via `mat4.compose` (position/rotation/scale) and derive a fixed **screen-space** gizmo size (scale inversely with camera distance so it neither shrinks to invisibility far away nor balloons up close — an explicit correction factor, not physically based). All three modes render at the entity's position using this shared sizing logic.
3. **Translate mode**: three coloured drag handles (arrows or simple line+cone, conventional red/green/blue for X/Y/Z). Pointer-down on a handle starts a drag constrained to that axis: unproject two points along the axis into screen space, form a screen-space direction vector, dot the mouse delta against it to get a world-space delta along that one axis. In 2D mode, only X/Y handles render (no Z).
4. **Rotate mode**: three coloured rings/arcs around each axis (a ring in the plane perpendicular to that axis). Pointer-down on a ring starts a drag: track the angle between the gizmo center and the mouse position, projected onto that ring's plane, each pointer-move; the *change* in angle since the previous move becomes a delta rotation applied via `mat4.rotation_xyz` on that single axis (accumulate into the entity's stored Euler rotation using `3d-coordinate-mapping.prompt.md` Step 2's documented Z-then-Y-then-X convention — do not invent a different composition order here). In 2D mode there is exactly one ring (Z/roll — "the" 2D rotation).
5. **Scale mode**: three small box handles at the end of each axis, dragging one scales that axis only (screen-space distance from gizmo center to cursor, relative to the drag-start distance, as the scale factor) — plus one uniform-scale handle at the gizmo's own origin (drag-out/drag-in scales all axes together equally). No corner/bounding-box drag handles (see the scope table) — axis and uniform handles only. In 2D mode, only X/Y axis handles plus the uniform handle render.
6. On drag end (any mode), call the appropriate `editor_commands` factory (Step 5) — `move_entity_command` for translate, and new `rotate_entity_command`/`scale_entity_command` following the same `{do, undo, label}` shape — never a direct `scene.update_entity` call, and never one command per intermediate drag frame (coalesce into a single command on pointer-up).

Verify: each mode's handles render only when that mode is active; dragging a translate handle moves only along its axis; dragging a rotate ring rotates smoothly and continuously (no snapping to a wrong direction partway through a drag — a common bug from recomputing absolute angle instead of accumulating delta angle); dragging a scale handle scales only that axis, the uniform handle scales all axes together; every drag (any mode) is exactly one undo step.

---

## Step 8 — Property Panel

**File:** `client/game/area_viewer.py` (extend, new imgui window/panel)

Replaces "raw JSON textarea" with actual imgui form fields, for whatever entity is selected (Step 6).

This panel edits two genuinely different things, and must not blur them (per `3d-coordinate-mapping.prompt.md` Step 5's fix): the selected **instance's** placement (unambiguously this one entity, never shared) versus the **shared template** it references (affects every placement of that `render_template`, everywhere). Sections 1–3 below are instance-level; section 4 is template-level and treated with corresponding weight.

1. **Placement (instance-level).** Numeric fields (`imgui.input_float`/`drag_float`) for position (`entity.x`/`y`/`z`) and `entity.transform3d.rotation`/`scale` (or 2D `x`/`y` in 2D mode) — typed values in degrees for rotation (converted to radians before calling `mat4.rotation_xyz`) rather than raw radians. These fields are a **second way to reach the same three commands Step 7's gizmo uses** (`move_entity_command`/`rotate_entity_command`/`scale_entity_command`), not a separate mechanism — keep both in sync: dragging the gizmo updates these fields live, and committing a typed value updates the gizmo's rendered position/orientation/size immediately. Editing these only ever affects the selected entity — never its template.
2. **Appearance (instance chooses, template defines).** A `render_template` picker — an imgui combo box populated from the `"entities"` manifest category (reuses the same manifest read Step 3's launcher already made, per Step 9's note on sharing it — don't re-read the manifest a second time). Changing it is instance-level (this entity now points at a different template); it does not modify either template's contents.
3. **Script (instance-level).** If the entity's Area-file `components` list has a `ScriptComponent` (`area-system.prompt.md` Step 10/11): a `script_type` combo box (`waypoint_loop`/`orbit`/`follow`) and a small generated form for that type's `params` (waypoint list as a repeatable x/y row; orbit's center/radius/angular_speed as three numeric fields; follow's target entity id as a combo box of other placed entities) — not a raw JSON textarea. If there's no `ScriptComponent`, show an "Add Script" button that adds one with sensible defaults via `editor_commands`. `ScriptComponent` lives on the Area-file entity itself, so this is unambiguously per-instance — no shared-template concern here.
4. **Template editing (shared — edits the definition file, not this instance).** If the selected entity's `render_template` definition has `parts[]` (`3d-coordinate-mapping.prompt.md` Step 9): a collapsible sub-section per part exposing its `localOffset`, `dangle` (Step 10), and `animation_id`/`action_animations` (Steps 11/12) fields. **Editing any of these writes to the shared entity-definition file** — show a persistent, impossible-to-miss banner at the top of this sub-section ("Editing shared template `<id>` — affects every entity using it") and require an explicit confirm (a button, not just field blur) before the write goes out, since the blast radius is every placed instance of that template, in every area, not just this one. See Step 11 for how this persists (a separate save path from the Area file itself).
5. Sections 1–3: every field change calls `editor_commands.execute(update_entity_command(...))` on blur/commit (not on every keystroke — debounce, or commit when the imgui widget reports it was deactivated-after-edit, so undo doesn't need one press per typed character). Section 4: still routed through `editor_commands` for in-session undo, but *additionally* persisted immediately to the definition file on confirm (Step 11) — undoing it in this session does not automatically un-persist a save that already went out; that's an accepted limitation of editing shared, non-Area-file content from inside the Area editor, not a bug to fix here.

Verify: editing an entity's position numerically moves it in the viewport and is undoable, and never affects any other entity sharing its `render_template`. Changing `render_template` swaps the rendered mesh live. Adding a `ScriptComponent` via the panel produces the same result as hand-authoring one in the JSON (cross-check against `area-system.prompt.md` Step 11's verify). Editing a part's `dangle` value, confirming, then opening a *different* entity that shares the same `render_template` shows the updated value too — proving the shared-template write actually took effect broadly, not just locally.

---

## Step 9 — Asset Browser Panel

**File:** `client/game/area_viewer.py` (extend)

Replaces the crude "type a raw asset id into a text box" Add flow from `area-system.prompt.md` Step 7.

1. An imgui panel listing available meshes/entity-definitions (from the `"meshes"`/`"entities"` manifest categories, same data Step 3's launcher and Step 8's `render_template` picker use — read the manifest once, share the result, don't re-read it per panel), with a text filter input for quick search by name.
2. Clicking an entry either places it directly at a sensible default position (world origin, or the camera's look-at point on the ground plane) or arms a "click in viewport to place" mode — pick whichever is simpler to implement well; a fixed default position with the gizmo (Step 7) available immediately after to reposition it is likely the simpler, still-usable choice.
3. Placement calls `editor_commands.execute(add_entity_command(...))` — undoable, consistent with every other mutation in this task.

Verify: filtering the asset list narrows results correctly; placing an asset adds a selected, immediately-repositionable entity; the placement is a single undo step.

---

## Step 10 — Grid, Snapping, and Viewport Aids

**File:** `client/engine/gizmo.py` or a new `client/engine/viewport_grid.py`

1. A ground-plane grid overlay in 3D mode (simple line-list, fixed spacing, faint colour, gated behind editor mode) so placement has a visual reference — this is also a good place to reuse the flat-colour line pipeline Step 6's selection highlight already needed.
2. Position snapping: an editor-only "grid size" setting (default e.g. `1.0` world unit); when enabled, Step 7's gizmo drag and Step 9's placement round to the nearest grid multiple. A toggle (keyboard `G` or an imgui checkbox) turns it on/off — off by default is reasonable, or on by default with an easy toggle; pick one and be consistent.
3. Rotation snapping: an optional 15°/45° increment toggle for Step 8's rotation fields (hold a modifier key while adjusting, or a separate checkbox — simplest is a checkbox next to the rotation fields).
4. A small stats readout (entity count in the current scene, current FPS) in its own small imgui window — cheap, and directly useful while placing many entities. This is the same information `ROADMAP.md` Phase 9.2's "Perf Overlay" describes; implement it here rather than as a separate future page.

Verify: with snapping enabled, dragging the gizmo lands on grid-aligned positions only; disabling snapping restores free movement; the stats readout updates live as entities are added/removed.

---

## Step 11 — Proper Save/Load Flow

**File:** `client/engine/scene.py` or a small new `client/engine/area_io.py`

1. Implement the real save mechanism (`area-system.prompt.md` Step 7 task 3 already established the direct-filesystem-write approach — this step finishes it into a proper flow): a function that takes `Scene.to_area_file_json()`'s output plus an `area_id`, and writes it to `frontend/assets/data/area/area-<id>.json` via `open(path, 'w')`. No Flask route, no dev-mode gate needed — the client already has direct filesystem access on the same machine as the assets, per `area-system.prompt.md`'s constraint.
2. A second, small function, same shape: accept an entity-definition dict and an `id`, write it to `frontend/assets/data/entity/entity-<id>.json`. This is what Step 8 task 4's shared-template edits actually persist through — it's a second, small function, not a generalisation of the area-save function into something that guesses which directory to write based on content shape (keep them separate and explicit).
3. **Both save paths must refresh the manifest after writing**: call `tools/build_manifest.py`'s `build_manifest()` function directly (it's already Python — `import` it, don't shell out) and rewrite `manifest.json` before returning. Without this, a newly-saved area or entity-definition would silently not appear in the Step 3 launcher's lists until someone manually reran the build tool — the launcher and the save flow would disagree about what exists, which defeats the point of a manifest-driven launcher. This is the concrete mechanism that makes this step's verify (below) actually true.

   **Forward-looking note, not in scope for this task:** each game is expected to eventually get its own hand-maintained `backend/game/<game_name>/asset_manifest.json` — a flat list of pool-manifest ids (mostly area ids) that game actually references, used by a future packaging step so a distributed build ships only the assets a game uses, not the whole shared pool. The in-process `build_manifest()` refresh this task already does on every area/entity save (point 3 above) is the natural future hook for also unioning the saved area's id — and its resolved entity/mesh/material/animation dependencies — into the current game's `asset_manifest.json`, keeping it current without manual upkeep. That requires the editor to know which game it's editing for (an as-yet-undesigned `--game=<name>` launch flag or equivalent), and any such auto-update should stay strictly additive — never auto-remove entries — so dropping something still needs a reviewed, deliberate step. Do not build this now; there's no real game with saved areas yet to validate it against.

**File:** `client/game/area_viewer.py` (extend)

4. "Save" (`Ctrl+S` or a button): if the current scene was opened from an existing file, write to that file's id in place — no confirmation needed for a plain save. If the scene is new (Step 3's "New Area" path, no backing file yet) or the user chooses "Save As," prompt for a name/id first (a small imgui text-input modal), then write.
5. "Load" is Step 3's launcher — do not build a second, separate load dialog inside the editor; a "Back to Launcher" action (also useful for Step 4's asset preview) reuses the same screen.

**Scene Settings panel** (new small imgui panel, e.g. a collapsible section separate from the per-entity property panel):

6. Read-only display of the scene's currently-authored `start_camera` and `lighting` (`area-system.prompt.md` Step 3's `Scene.start_camera`/`Scene.lighting` — deliberately separate from the live free-fly `camera`, so flying around to inspect the scene never silently changes what gets saved).
7. A **"Set Start Camera to Current View"** button — calls `scene.set_start_camera({ ...current camera fields })`, capturing wherever the free-fly camera happens to be *right now* as the authored spawn point. This is the only thing in this entire task that's allowed to write `start_camera` — no other code path may call `set_start_camera()` implicitly.
8. Numeric/colour fields for `lighting.ambientColor`/`fogColor`/`fogNear`/`fogFar`, with an explicit **"Set Start Lighting"** button calling `scene.set_lighting(...)` with the panel's current values (not applied live per-keystroke — lighting changes are visible immediately in the viewport since `set_lighting` also writes onto `scene.camera`, but the *authored* `scene.lighting` value only updates on this explicit action, mirroring the start-camera pattern).
9. Both actions route through `editor_commands` (undoable within the session) exactly like any other edit in this task.

Verify: editing and saving an existing area, then reopening it via the launcher, shows the saved changes, including whatever `start_camera`/`lighting` were last explicitly set (not wherever the camera happened to be at save time). A brand-new area, saved for the first time, appears in the launcher's "Open Area" list *immediately* afterward, with no manual manifest rebuild step. Flying the free-fly camera around after opening an area and then saving does **not** change the saved starting camera unless "Set Start Camera" was explicitly clicked. Editing a shared template's `dangle` value (Step 8 task 4) and confirming makes it appear in `manifest.json`/reload without a manual rebuild, same as an area save.

---

## Step 12 — Keyboard Shortcuts & Polish

**File:** `client/game/area_viewer.py` (extend)

1. `Delete`/`Backspace` — remove the selected entity (via `editor_commands`, undoable).
2. `Ctrl+D` — duplicate the selected entity at a small offset (via `editor_commands`'s `add_entity_command`).
3. `F` — snap the camera to focus on/orbit the selected entity (useful after placing something off-screen).
4. `Escape` — deselect.
5. A small always-visible "last action" label (using command `label`s from Step 5) in the imgui HUD so undo/redo feels legible rather than mysterious.

Verify: each shortcut works only while the viewport has focus and an editor mode is active (not while typing in a property-panel text field — guard against that explicitly via imgui's keyboard-capture query, a common and annoying bug class).

---

## Step 13 — Zone Authoring

**File:** `client/game/area_viewer.py` (extend), `client/engine/scene.py` (small additive extension), `client/engine/editor_commands.py` (extend)

Authoring UI for `zones.prompt.md`'s `Zone`/`ZoneRegistry` — read that file in full before this step; it owns the shapes, effect types, and backend containment/dispatch logic this step only visualizes and edits. **This step adds no new backend zone mechanics of its own** — it is purely the editor-side placement/property-panel/save story for zones that already exist as a backend concept once that task lands.

1. **`Scene` gains a `zones` collection**, additive per `area-system.prompt.md`'s own "`Scene` does not change in this task except additively" constraint (already anticipated there, exercised here for the first time): `Scene.zones: dict[str, dict]`, `add_zone`/`update_zone`/`remove_zone` mirroring `add_entity`/`update_entity`/`remove_entity`'s exact shape (no `'authoritative'`/`'local'` source tagging needed — zones are always editor/file-authored, never delivered over the live network stream). `Scene.load_from_area_file()`/`to_area_file_json()` read/write the Area file's `zones` key (`zones.prompt.md` Step 5) the same way they already handle `entities`/`camera`/`lighting`.
2. **AABB zone placement**: on "Add Zone → AABB," place a zone at a small default size (e.g. 2×2×2 world units) at the camera's look-at point — then reuse Step 7's existing translate/scale gizmo unmodified to reposition/resize it. On save, convert the zone's placement (position + scale, both already tracked by the gizmo like any other placed object) into the `{"type": "aabb", "min": [...], "max": [...]}` shape `zones.prompt.md` Step 3 expects — this conversion is the only zone-specific new math in this whole step; the gizmo interaction itself is entirely reused, not reinvented.
3. **Mesh zone placement**: reuse Step 9's asset-browser placement flow exactly (pick a mesh asset, place, reposition/rotate/scale via the same gizmo) — a mesh zone is placed exactly like a mesh entity. The only difference is a "this is a zone, not a renderable entity" flag set at placement time, which routes it to `Scene.zones` instead of `Scene.entities` and to this step's property panel instead of Step 8's.
4. **Visual representation** (editor mode only, zero cost otherwise — same rule Step 6/10's overlays already follow): an AABB zone draws as a translucent, flat-colored box outline (reuse the line-list pipeline Step 6's selection highlight and Step 10's grid already established). A mesh zone draws its actual mesh, alpha-blended, distinctly tinted from normal entities (e.g. a translucent cyan) so it reads as "a zone, not a solid object" at a glance.
5. **Property panel** for a selected zone (a variant of Step 8's panel, not a third, unrelated UI): shape fields are read-only after creation (re-derived from the gizmo's live transform, not hand-typed). Below that, two repeatable effect lists — "On Enter" and "On Exit" — each row: an effect-type combo box (the 8 types from `zones.prompt.md` Step 4) plus that type's specific fields (group name, key/value, component-type + field form, event name + payload), generated the same way Step 8 section 3 already generates a form from `ScriptComponent`'s `script_type`/`params` — reuse that form-generation approach rather than writing a second one. A "+"/"−" per row adds/removes an effect entry.
6. **Undo/redo**: new `editor_commands` factories — `add_zone_command`, `remove_zone_command`, `update_zone_command` (covering shape-transform edits and effect-list edits alike, same `{do, undo, label}` shape as every existing command) — every zone mutation from this step routes through `EditorCommands.execute()`, no exceptions, matching this task's standing rule for every other editor mutation.
7. Zones appear in the entity-list panel (Step 6) too, visually distinguished (an icon or `[ZONE]` prefix) from real entities, and are selectable/deletable from there the same way.

Verify: place an AABB zone, resize it with the scale gizmo, add an `on_enter` effect (e.g. `add_group`), save, reload via the launcher — the zone's shape and effects round-trip correctly. Place a mesh zone, confirm it renders translucently and distinctly from solid entities. Undo/redo correctly reverts zone placement, transform edits, and effect-list edits as individual steps.

---

## Step 14 — UI Menu Authoring & Triggers

**New file:** `client/game/ui_editor.py`
**New file format:** `frontend/assets/data/ui/menu-<id>.json`
**Files to modify:** `client/game/launcher.py` (extend, Step 3), `tools/build_manifest.py` / `client/engine/asset_loader.py` (new `"ui_menus"` manifest category, following Step 2's exact pattern), `client/engine/network.py` (small, narrowly-scoped addition — see task 7)

Authoring UI screens/menus with `client/engine/ui/` (this repo's custom-drawn, art-asset-skinned UI framework — `draw.py`/`theme.py`/`widgets.py`/`templates.py`/`nav.py`, already built and verified against `run_ui_test.py`) instead of hand-writing Python for every screen a game needs. **This is squarely engine-layer tooling** — the editor and the menu-JSON format it produces are reusable by any game on this engine, exactly like `client/engine/ui/` itself; a specific game's *actual* menus (art, copy, real triggers) are that game's own content on its own branch, same distinction this repo's engine/game branch split already draws elsewhere. Don't let this step's own verify content (a placeholder pause menu, say) be mistaken for real game content.

1. **UI-layout JSON schema** — a flat list of elements plus a trigger block:
   ```json
   {
     "menu_id": "example_menu",
     "elements": [
       {"id": "bg", "type": "panel", "rect": [[0, 0], [400, 300]]},
       {"id": "title", "type": "label", "rect": [[20, 20], [380, 50]], "text": "Title", "font_key": "title"},
       {"id": "resume_btn", "type": "button", "rect": [[40, 240], [360, 280]], "text": "Resume"}
     ],
     "triggers": {"show": [...], "hide": [...]}
   }
   ```
   `type` maps 1:1 onto `client/engine/ui/widgets.py`'s functions (`panel`/`label`/`button`/`image_button`/`progress_bar`) plus `templates.py`'s composite ones (`window`/`confirm_dialog`/`chat_box`) — do not invent a parallel element-type vocabulary; if a widget function's signature needs a field this schema doesn't have yet, add the field, don't add a new type that duplicates an existing one.
2. **Editor mode**: a 2D-only screen-space viewport (no 3D raycasting needed at all — reuses this task's own established "2D mode is simpler" precedent from Step 6/7, taken to its logical conclusion: UI elements never have a 3D mode). Click-select an element (rect hit-test, no picking math beyond a bounds check); drag to reposition (Step 7's translate gizmo, restricted to 2D, X/Y handles only — no rotate mode, UI elements don't rotate in this system); drag a corner/edge handle to resize (Step 7's scale gizmo, same 2D restriction, adapted to resize a rect's `p_max` rather than scale a 3D transform — a small, explicitly-new interaction, since Step 7's scale gizmo scales a transform, not a rect; keep it visually consistent with Step 7's handle styling even though the underlying math differs).
3. **Live preview, not editor chrome standing in for the real thing**: because `client/engine/ui/`'s widgets are real, functional draw calls, this editor mode can and must render the actual menu as it's being built — call `draw.begin_frame()` and the matching `widgets.*`/`templates.*` function per element, every editor frame, with a selection outline (reuse Step 6's highlight-overlay concept, adapted to 2D rects) drawn on top of whichever element is selected. What you see while editing is what the menu actually looks like at runtime — no separate "preview mode" toggle needed.
4. **Property panel** per selected element (Step 8's pattern, a third variant after entities and zones): `rect` (numeric fields, kept in sync with the gizmo exactly like Step 8 section 1), plus type-specific fields — `label`/`button`: `text`, `font_key` (combo box over the current theme's loaded fonts); `image_button`: an asset-key picker (reuses Step 9's asset-browser pattern, filtered to image assets); `progress_bar`: `fill_key`/`bg_key` (combo boxes over the current theme's color keys); `panel`: `bg_key`/`border_key`/`rounding`.
5. **Trigger authoring** — a separate panel listing this menu's "Show" and "Hide" triggers, each one of three types, and each editable/addable/removable the same repeatable-row way Step 13 task 5 edits zone effects:
   - `{"type": "keybind", "key": "..."}` — a text field using the same key-name strings `input_config.json`/`client/engine/input.py` already use (`"escape"`, `"tab"`, etc.) — purely client-local, no backend/network involvement at all: the runtime piece (task 7) checks `imgui.is_key_pressed`/`client/engine/input.py`'s key state directly, every frame.
   - `{"type": "zone", "zone_id": "...", "on": "enter" | "exit"}` — a combo box populated from the currently-open area's zones (Step 13). Selecting this **does not invent new runtime wiring**: on save, the editor writes a `{"type": "fire_event", "event": "show_menu:<menu_id>"}` (or `"hide_menu:<menu_id>"`) entry into the *referenced zone's* own `on_enter`/`on_exit` effect list (`zones.prompt.md` Step 4's existing `fire_event` effect type) — the menu system is just one more listener for an event a zone already knows how to fire, not a new zone capability.
   - `{"type": "entity_interact", "entity_id": "..."}` — reuses `area-system.prompt.md` Step 10's existing `"entity_overlap"` `EventBus` event (a trigger-collider entity) the same way — no new backend event type, just another consumer of one that already exists.
6. **Undo/redo**: `add_ui_element_command`/`update_ui_element_command`/`remove_ui_element_command`/`add_trigger_command`/`remove_trigger_command`, same `{do, undo, label}` shape as everything else, routed through `EditorCommands.execute()`.
7. **The runtime piece — a real, narrowly-scoped backend/network touch, not editor-only work**: `zone`/`entity_interact` triggers fire *server-side* (they're `EventBus` events published from backend zone/collider code) and must reach the client to actually show/hide anything. Add a small SocketIO event (e.g. `menu_trigger`, `{"event": "show_menu:<menu_id>" | "hide_menu:<menu_id>"}`) emitted wherever the backend already has `EventBus` → SocketIO bridging for comparable events — check `area-system.prompt.md`/`zones.prompt.md` for whether one already exists before adding a new emission point; if the `EventBus` doesn't have any existing bridge to SocketIO at all, add the minimal one needed for this event only, not a general-purpose EventBus-to-network relay (that's a bigger, separate task if ever needed broadly). Client-side, a small `client/game/ui_menu_runtime.py` (or an extension of `client/engine/network.py`'s existing callback-registration pattern — `character_flow_callbacks`/`_state_handlers`'s shape, not a new mechanism) loads a menu's JSON, registers for its named trigger events, and calls the matching `widgets.*`/`templates.*` render calls when triggered — plus polls keybind triggers locally, every frame, independent of any event.
8. **Save flow**: reuses Step 11's exact pattern — write to `frontend/assets/data/ui/menu-<id>.json` via `open()`, refresh the manifest (new `"ui_menus"` category) before returning, exactly like an Area or entity-definition save.

Verify: build a small menu (a panel, a title label, one button) entirely in the editor with no hand-written JSON, save it, and confirm it appears in the launcher's menu list immediately. Add a keybind trigger (`escape`) and confirm, in a real running client (gameplay or standalone), pressing it shows the menu with no network involvement. Add a zone `on_enter` trigger to a zone from Step 13, confirm the zone's saved Area file now carries the corresponding `fire_event` effect, and that entering the zone in a real gameplay session shows the menu. Deleting a trigger row and re-saving removes the corresponding `fire_event` effect from the zone's Area file (not just from the menu's own JSON) — proving the write-back is bidirectional, not a one-way trap door.

---

## Step 15 — Action Definitions Panel

**New file:** `frontend/assets/data/actions.json` (schema documented in `docs/graphics/ACTION_TRIGGERED_ANIMATIONS.md`)
**File:** `client/game/area_viewer.py` (extend — a new panel, plus a small addition to Step 8/14's per-part property panel)

Editor authoring for `docs/graphics/ACTION_TRIGGERED_ANIMATIONS.md`'s pattern (Step 12 of `3d-coordinate-mapping.prompt.md`) — **the data half only**. Deciding when an action actually fires (player input, AI, an item being used) is real gameplay logic in a game branch's `player.py`/`actions.py`, not something this editor authors or should try to; this step only manages the two things that genuinely are data: an action's name/duration, and which clip plays for it on a given mesh part.

1. **`actions.json`**: a flat registry, `{"<action_name>": {"duration_ms": number}}` — the editor-authored equivalent of `backend/engine/example_game_loop.py`'s `ACTION_DURATIONS` constant. A single well-known asset (like `ui_theme.json`), not an enumerated directory of many files — no new manifest category needed, unlike Step 2's `"areas"`. **Forward-looking note, not built in this task**: for this to actually drive backend timing, a real game's concrete `GameLoop` subclass needs to load this file instead of hardcoding a Python dict — same relationship `config/game.json` already has to the code that reads it. Loading it is that game branch's job when it adopts the pattern, not this editor task's.
2. **Registry panel**: list existing actions (name + duration_ms), add/rename/delete, each through `editor_commands` (undoable) like every other mutation in this task. Writes `actions.json` directly (`open(path, 'w')`), same convention as every other save in this task.
3. **Per-part action-clip assignment**: extend Step 8/14's per-part property panel with an "Action Animations" section — for the selected mesh part, an optional transform-clip picker per registered action (reuse Step 9's asset browser, filtered to transform clips), writing/clearing that part's `action_animations[action_name]` (Step 12's schema, `3d-coordinate-mapping.prompt.md`) exactly like any other instance-level part field.
4. **Sprite-path scope line, explicit**: a sprite entity's one-shot action clip (frame indices, atlas region, `loop: false`) stays hand-authored JSON — this panel manages the action registry and the mesh-path clip assignment only. A frame-based sprite-animation-clip editor (picking/arranging atlas frames visually) is a distinct, larger tool; do not build it as part of this step.

Verify: add a new action via the registry panel, assign it to a part's `action_animations` via the asset browser, save, reload via the launcher — both the registry and the assignment round-trip correctly. Confirm this step produced only data (`actions.json`, an entity-definition's `action_animations` field) — no backend trigger-wiring code exists or was touched.

---

## Step 16 — Documentation

**File:** `docs/graphics/AREA_SYSTEM.md` (extend, created by `area-system.prompt.md` Step 12)

1. Add a section documenting the launcher (Step 3), asset preview mode (Step 4), and the editor's capabilities (selection, gizmo, undo/redo, property panel, asset browser, snapping, save flow) — screenshots optional, a clear feature list is the minimum bar.
2. Add a section explicitly documenting the two architectural distinctions this task depends on getting right, since both are easy for a future reader to miss: (a) instance-level vs. template-level entity fields (position/`transform3d`/`render_template`/`ScriptComponent` are per-placement; `mesh`/`parts`/`localOffset`/`dangle`/`animation_id`/`action_animations` are per-template, edited with an explicit warning because the write reaches every placement everywhere), and (b) the live `camera` vs. authored `start_camera`/`lighting` split (free exploration never silently changes what gets saved; only the Scene Settings panel's explicit actions do).
3. Note explicitly that this supersedes `ROADMAP.md` Phase 9.2's separate "Animation Preview" page concept — Step 4's asset preview mode covers that use case; update `ROADMAP.md` Phase 9.2 to point here instead of describing a second, redundant page.
4. Document the scope line from this prompt file's introduction (what's in vs. out) so a future reader doesn't assume multi-select or a script editor already exist.
5. Add a section documenting zone authoring (Step 13) — cross-reference `zones.prompt.md` for the backend shapes/effects, don't re-document them here; this section only covers the editor-side placement/property-panel/save story.
6. Add a section documenting UI menu authoring and triggers (Step 14) — the element-type-to-`client/engine/ui/`-function mapping, the three trigger types and the "editor writes back into the referenced zone's/entity's own data, not a new runtime mechanism" design, and the `menu_trigger` SocketIO event task 7 added.
7. Add a section documenting the Action Definitions panel (Step 15) — cross-reference `docs/graphics/ACTION_TRIGGERED_ANIMATIONS.md` for the pattern itself; this section only covers the registry panel and per-part clip assignment, and should restate plainly that trigger-wiring is not, and will not be, something this editor authors.
8. Note that this entire editor lives in the native Python `client/`, not the legacy JS frontend — a reader should not go looking for it under `frontend/js/`.

---

## Step 17 — Smoke Test

```text
python -m client.main
```

- [ ] Launching with no arguments shows the launcher, listing real Area files, meshes, entity-definitions, materials, and UI menus.
- [ ] "New Area" opens a blank, empty, immediately-editable scene with no backend connection.
- [ ] "View Asset" on a mesh opens the asset preview mode; stylization toggles visibly change the render in real time.
- [ ] Clicking an entity in the 3D viewport selects it (visible highlight); the entity list and viewport selection stay in sync both directions.
- [ ] `T`/`R`/`S` switch gizmo modes; each mode's handles render only when active. Translate handles move the entity along the correct axis; rotate rings rotate smoothly with no direction snapping mid-drag; scale handles (axis and uniform) scale correctly, in both 3D and 2D modes.
- [ ] The property panel's numeric transform fields and the gizmo stay in sync in both directions (dragging updates the fields live; typing a value moves/rotates/scales the gizmo).
- [ ] The property panel edits position/rotation/scale (instance-level, per-entity, never shared) and `render_template`/`ScriptComponent` (also instance-level) without ever exposing raw JSON.
- [ ] Editing a part's `dangle`/`animation_id`/`action_animations` in the property panel requires an explicit confirm, shows the "shared template" warning, and the change is visible on *every* other placed entity using the same `render_template` after reload — not just the one being edited.
- [ ] Asset preview mode's "Simulate Motion" toggle makes a `dangle`-equipped part visibly sway; it sits motionless with the toggle off.
- [ ] The asset browser places a new entity from a filtered search, immediately selected and repositionable.
- [ ] Placing two entities with the same `render_template` at different positions/rotations renders two independent, correctly-placed copies — not two copies stacked at whatever position the template happens to specify (it specifies none).
- [ ] Grid snapping, when enabled, constrains gizmo drags and placements to grid points; disabling it restores free movement.
- [ ] `Ctrl+Z`/`Ctrl+Shift+Z` correctly undo/redo placement, movement, deletion, and property edits — including a multi-step sequence.
- [ ] `Delete`, `Ctrl+D`, `F`, and `Escape` work as specified and are correctly disabled while an imgui text field has focus.
- [ ] Saving an existing area persists changes and they survive a reload via the launcher; saving a brand-new area makes it appear in the launcher's list **immediately**, with no manual manifest rebuild.
- [ ] Flying the free-fly camera around an open area and then saving does **not** change the saved starting camera; clicking "Set Start Camera" does, and only then.
- [ ] An AABB zone and a mesh zone can both be placed, resized via the gizmo, given effects, saved, and reloaded correctly; both render as visually distinct, translucent, editor-only overlays.
- [ ] A UI menu can be built entirely in the editor (no hand-written JSON), saved, and reappears correctly on reload; its live preview while editing matches its real runtime appearance exactly.
- [ ] All three menu trigger types (keybind, zone, entity-interact) work in a real running client; the zone/entity-interact triggers correctly write back into the referenced zone's/entity's own Area-file data, not just the menu's own file.
- [ ] An action can be added/renamed/deleted in the Action Definitions panel and persists in `actions.json`; assigning it to a mesh part's `action_animations` via the asset browser round-trips on reload. No backend/trigger-wiring code exists anywhere in this task's own files.
- [ ] Plain viewer mode (no `--mode=builder`) and real gameplay render with zero visible or measurable change from this task — all editor-only rendering (gizmo, grid, highlight, zone overlays, UI-editor chrome) is fully gated off.
- [ ] No lint/type errors on any modified/new file.

---

## Success Criteria

- [ ] `tools/build_manifest.py` / `client/engine/asset_loader.py` — `"areas"` manifest category added, following the established `"meshes"`/`"entities"` pattern exactly
- [ ] `client/game/launcher.py` — Open Area / New Area / View Asset panels, manifest-driven, zero backend connection required
- [ ] Asset preview mode (launcher's "View Asset", or `--asset=<key> --asset-type=...`) — orbit camera, live stylization toggles, animation playback if applicable, read-only
- [ ] `client/engine/editor_commands.py` — `EditorCommands` with `execute`/`undo`/`redo`; every editor mutation from Step 6 onward routes through it; `Scene` itself unmodified by this requirement
- [ ] Viewport picking (3D raycast, 2D hit-test) and a selection highlight, synced with the entity list panel
- [ ] `client/engine/gizmo.py` — mode-switchable (`T`/`R`/`S`) translate/rotate/scale gizmo, axis-constrained drags (plus uniform scale), each drag coalesced into one undo step, working in both 2D and 3D, synced live with the property panel's numeric fields
- [ ] Property panel covering instance-level transform (position/rotation/scale via `entity.x/y/z`+`transform3d`, never the definition file), `render_template`, `ScriptComponent`, and template-level part fields (`localOffset`/`dangle`/`animation_id`/`action_animations`, gated behind an explicit confirm and warning) with no raw-JSON editing required for any of them
- [ ] Asset browser panel with search/filter, sourced from the same manifest read the launcher and property panel already use
- [ ] Grid overlay, position snapping, optional rotation snapping, and a live entity-count/FPS readout
- [ ] Area-save and entity-definition-save functions implemented for real (direct filesystem writes, no Flask route, no dev-mode gate needed), both refreshing `manifest.json` via `build_manifest()` before returning
- [ ] Scene Settings panel — `Scene.start_camera`/`Scene.lighting` shown and editable only via explicit "Set Start Camera"/"Set Start Lighting" actions; nothing else in this task calls `set_start_camera()`
- [ ] Keyboard shortcuts (`Delete`, `Ctrl+D`, `F`, `Escape`, undo/redo) correctly disabled while any imgui text input has focus
- [ ] `client/engine/scene.py` — `Scene.zones` + `add_zone`/`update_zone`/`remove_zone`, additive per `area-system.prompt.md`'s own constraint; `to_area_file_json`/`load_from_area_file` round-trip the Area file's `zones` key
- [ ] Zone authoring — AABB (via the reused translate/scale gizmo) and mesh-footprint zone placement, a property panel editing `zones.prompt.md`'s 8 effect types as repeatable `on_enter`/`on_exit` rows, distinct translucent editor-only rendering, full undo/redo — no new backend zone mechanics invented here, all of it calls into `zones.prompt.md`'s existing `Zone`/`ZoneRegistry`
- [ ] `client/game/ui_editor.py` + `frontend/assets/data/ui/menu-<id>.json` schema — a 2D-only UI-layout editor built directly on `client/engine/ui/`'s real widget functions (live preview *is* the runtime appearance, not separate editor chrome), with a property panel, undo/redo, and a `"ui_menus"` manifest category/launcher entry
- [ ] Three menu trigger types (keybind, zone, entity-interact) — zone/entity-interact triggers write back into the *referenced* zone's/entity's own data (`fire_event` effects / `"entity_overlap"` subscriptions) rather than inventing parallel mechanisms; a narrowly-scoped `menu_trigger` SocketIO event (or equivalent) delivers server-fired triggers to the client
- [ ] `frontend/assets/data/actions.json` (registry: name + `duration_ms`) — add/rename/delete through a dedicated panel, undoable; a per-part "Action Animations" section in the property panel assigns a transform clip per registered action, writing `action_animations`; the sprite-path one-shot clip itself stays explicitly out of scope (hand-authored JSON, not this editor). No backend trigger-wiring code written or implied anywhere in this task — data only, same boundary `docs/graphics/ACTION_TRIGGERED_ANIMATIONS.md` draws
- [ ] `docs/graphics/AREA_SYSTEM.md` updated (including zone-authoring, UI-menu-authoring, and action-definitions sections); `ROADMAP.md` Phase 9.2 updated to point at this task instead of describing a separate preview page
- [ ] Plain viewer mode and real gameplay have zero rendering or performance change from this task
- [ ] Two entities sharing one `render_template` render as independently positioned/rotated copies — the placement bug found during the original (browser-era) version of this task's integration audit stays fixed in the Python port
- [ ] Nothing in the out-of-scope table (multi-select, free-form bounding-box/corner-drag resize, history UI, custom asset import, terrain tools, collaborative editing, visual script editor) was built — flag any of it found half-started rather than finishing it under this task
- [ ] Nothing in this task touches `frontend/js/` — it targets the native Python client exclusively, per the banner at the top of this file
