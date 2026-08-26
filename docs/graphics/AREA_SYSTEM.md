# Area / Scene System

`Scene` (`client/engine/scene.py`) is the single runtime container for
entities, camera, lighting, and zones — populated either by loading a
pre-authored Area JSON file or, on a game branch, by the live SocketIO
gameplay stream, and writable at any time through an imperative API
(builder placement, a test script, cutscene dressing). See
[`.github/prompts/area-system.prompt.md`](../../.github/prompts/area-system.prompt.md)
for the originating task and its branch-reconciliation banner — this
document covers what's actually built today (`Scene` itself, the
file-load path, and the standalone viewer/builder tool, all on
`engine`), not the backend `Area`-file schema extension or the
movement/`ScriptComponent` work, which are blocked on a game branch
existing (`backend/game/` isn't present on `engine` — see
`CLAUDE.md`'s Branch model note). That section of this document is
written ahead of the code, describing the target shape, and is marked
as such below.

## Run modes

One runtime container, two things that can populate it, one thing that
can modify it at any time. Four "modes" fall out of *what drives the
Scene*, not four different rendering systems:

| Mode | Populated by | Driven by | Backend connection |
| --- | --- | --- | --- |
| Gameplay | Network stream | Player input → server → network | Yes, live (game-branch only — see below) |
| Viewer | File load | Nothing (static) | No |
| Builder | File load | Human, via a crude imgui panel | No |
| Test | File load | A script calling the `Scene` API | No |

Viewer, builder, and test share one boot path: `client/engine/area_viewer.py`,
entered via `python -m client.engine.area_viewer --area=<path>
[--mode=builder]`, or `python client/main.py --area=<path>` (a thin
`--area=` check ahead of `client/main.py`'s own game-coupled `main()` —
see that file's `if __name__ == "__main__":` block). Gameplay mode
(the live SocketIO stream driving `Scene` instead of a file) is a game
branch's work — `client/main.py`'s live `game_state` dict is owned by
`client.game.player_select`, which doesn't exist on `engine`; see the
prompt file's banner for the full trace of why that shim is blocked
while `Scene` itself is not.

## `Scene`

```python
from client.engine.scene import Scene

scene = Scene.load_from_area_file("frontend/assets/data/area/area-example.json")
scene.add_entity("local_abc123", {"x": 0, "y": 0, "z": 0, "render_template": "entity-example-crate"}, "local")
scene.save_to_area_file("frontend/assets/data/area/area-example.json")
```

### Fields

| Field | Type | Read by the render loop? | Purpose |
| --- | --- | --- | --- |
| `entities` | `dict[str, dict]` | Yes | Every placed entity, keyed by id — the exact dict shape a `state_update`/Area-file entry carries. |
| `camera` | `dict` | Yes, every frame | The live camera — position/mode/fov/etc. **and** `fogColor`/`fogNear`/`fogFar`/`ambientColor` (see `set_lighting()` below). Mutated continuously by free-fly/follow logic. |
| `lighting` | `dict` | No | Authored-shape mirror of the Area file's `lighting` block — a record of what was authored, not what the renderer reads. |
| `start_camera` | `dict \| None` | No | The *authored* starting camera, deliberately decoupled from `camera`'s constant live movement — flying the free camera around to inspect a scene never silently changes what gets saved as the spawn point. |
| `zones` | `dict[str, dict]` | No | Raw zone-definition dicts (`.github/prompts/zones.prompt.md`'s `Zone` shape) — stored/round-tripped for editor visualization only; `Scene` never simulates containment (that's backend-only, `ZoneRegistry`). |

Each entity record also carries an internal, in-memory-only source tag
(`'authoritative'` or `'local'`, via `add_entity`'s `source` argument),
read back with `entity_source(entity_id)`. An entity added directly
through the API (builder placement, test script, cutscene dressing) is
`'local'`; one that arrived via file load or network is `'authoritative'`.
The two must never silently collide — `add_entity` refuses (returns
`False`, logs a warning) rather than picking a winner whenever an id
already exists under a *different* source. Same-source re-adds (a second
network update for the same id, or re-placing the same builder entity)
proceed normally.

### API

- `add_entity(entity_id, data, source='local')` / `update_entity(entity_id, patch)` / `remove_entity(entity_id)`
- `set_camera(camera_data)` — merges onto the live `camera`. Called every frame by follow/free-fly code, not an authoring action.
- `set_lighting(lighting_data)` — merges onto `lighting` **and** onto `camera` (only the `ambientColor`/`fogColor`/`fogNear`/`fogFar` keys). The renderer only ever reads fog/ambient off the live camera object it already has each frame — without this dual-write, an authored `lighting` block would be data with nothing consuming it (the same class of bug `ambientColor` had in `3d-coordinate-mapping.prompt.md`'s Step 8, before it was fixed there).
- `set_start_camera(camera_data)` — merges onto `start_camera`. An explicit, deliberate authoring action; only `load_from_area_file()` and (once it exists) `level-editor.prompt.md`'s "Set Start Camera" action may call this. No per-frame camera-movement code may.
- `add_zone(zone_id, data)` / `update_zone(zone_id, patch)` / `remove_zone(zone_id)`
- `Scene.load_from_area_file(path)` (classmethod) — reads a file directly (`open()`/`json.load`, no HTTP), populates every field above.
- `to_area_file_json()` / `save_to_area_file(path)` — the inverse. Every entity is included regardless of source (what a builder places is real content once saved — the source tag is dropped, not written). The saved `camera` is `start_camera` if one has been authored, falling back to the live `camera` only for a scene that was never given one — this is what keeps free-fly movement from silently changing the saved spawn point.

No rendering logic lives in `Scene` at all — `client/main.py`'s
`draw_game_scene`/`render_entities`/`_gather_lights` already take a
plain `{"entities": ..., "camera": ...}`-shaped dict as a parameter
(confirmed while implementing this, not assumed), so they need zero
changes to read `scene.entities`/`scene.camera` directly.

## Standalone viewer/builder tool

`client/engine/area_viewer.py` — reclassified engine-layer (originally
scoped `client/game/area_viewer.py`; nothing in its spec is game-specific,
the same reasoning that put `client/engine/ui/` on `engine` instead of a
game branch). Self-contained boot (its own `renderer.init_renderer()`,
its own `ImguiRenderer`, its own render loop — mirrors
`run_client_test.py`'s pattern rather than going through
`client/main.py`'s game-coupled `main()`) — **no network connection is
ever opened**, in any mode.

- **Viewer**: loads an Area file (or falls back to an empty scene with a
  default 3D camera if `--area` is omitted or doesn't resolve), free-fly
  camera (`client/engine/free_camera.py` — WASD + right-drag look,
  Q/E for down/up; bound via `canvas.add_event_handler(...)`, never a raw
  GLFW callback — see that module's docstring for why a raw registration
  would silently break `rendercanvas`'s, and therefore imgui's, event
  handling).
- **Builder** (`--mode=builder`): the full level editor — see "Level
  editor" below. `python -m client.main` with no arguments reaches this
  through the launcher; `--area=<path> --mode=builder` opens it directly.
- **Test**: the same boot path, driven by a script calling the `Scene`
  API instead of a human — no separate entry point.

Try it: `python -m client.engine.area_viewer --area=frontend/assets/data/area/area-example.json --mode=builder`

## Launcher

`client/engine/launcher.py` (`.github/prompts/level-editor.prompt.md`
Step 3) — the real first screen, replacing hand-typed `--area=`/
`--asset=` flags. `python -m client.main` with no `--area`/`--asset`/
`--play` argument opens it (fixed during this work — that invocation
previously fell through to real gameplay `main()`, which needs
`backend.app`/`client.game` and crashed immediately on `engine`; see
`client/main.py`'s `if __name__ == "__main__":` block). Three panels,
manifest-driven, zero backend connection:

- **Open Area** — every entry in the manifest's `"areas"` category.
- **New Area** — "Empty" or "Empty with default lighting," opening a
  blank in-memory `Scene` directly into the editor (Step 11's Save flow
  is what actually creates the file).
- **View Asset** — every `"meshes"`/`"entities"`/`"materials"` manifest
  entry, opening asset preview mode (below).

Choosing an option closes the launcher's window and calls directly into
`area_viewer.run()`/`asset_preview.run()` (same process, no subprocess)
— not a literally-seamless single window, since `renderer.py`'s
`run()` blocks until its canvas closes; confirmed during implementation
that `canvas.close()` does terminate that blocking loop cleanly. A
single "last opened" entry persists to `client/.editor_state.json`
(best-effort, not a full recent-files list).

## Asset preview mode

`client/engine/asset_preview.py` (Step 4) — a read-only, single-asset
viewer with an orbit camera (drag to orbit, scroll to zoom), generalising
and superseding `ROADMAP.md` Phase 9.2's separate "Animation Preview"
page concept. Loads one mesh/entity/material into an otherwise-empty
`Scene` at the origin — a `mesh`/`material` asset is wrapped in a small
throwaway entity-definition file (`_write_synthetic_definition`, never
manifest-registered) since `draw_entity` always resolves through
`render_template` → a definition file, with no "just render this raw
mesh" shortcut; an `entity` asset is already a definition, no wrapping
needed. Material preview is a documented simplification — there's no
standalone flat-quad mesh asset in this project, so it reuses the
example crate mesh's geometry as a stand-in preview surface.

Live toggles: `vertex_color`/`affine_uv`/`color_levels` mutate the
cached material handle directly (`EntityRenderer._material_handles`,
reached into deliberately — these three fields aren't covered by
`set_entity_runtime`'s override mechanism, which only covers a
different field set); `fogColor`/`fogNear`/`fogFar`/`ambientColor`
mutate `scene.camera` directly, read every frame by the normal render
path with no special plumbing. "Simulate Motion" sways the previewed
entity's position, the only way to see a `dangle`-equipped part actually
move (dangle reacts to frame-to-frame position delta; an orbit-only
camera never moves the object itself).

## Level editor

Everything below lives in `client/engine/area_viewer.py`'s
`--mode=builder`, per `.github/prompts/level-editor.prompt.md` — "fairly
polished," explicitly not a full editor (no multi-select, no branching
undo history, no terrain tools; see that prompt file's scope table for
the complete in/out list).

- **`client/engine/editor_commands.py`** — `EditorCommands`
  (`execute`/`undo`/`redo`, a `label` per command for the HUD's "last
  action" line) wraps `Scene`'s existing API; `Scene` itself stays
  unaware undo exists. Every editor mutation — placement, transform,
  delete, zone edits, action-registry edits — routes through it, never
  a direct `Scene` mutator call from UI code.
- **`client/engine/picking.py`** — 3D: a world-space ray built directly
  from the camera's basis vectors and FOV (no general 4x4 matrix
  inverse needed — `mat4.py` doesn't have one), tested against each
  entity's bounding sphere (a fixed-radius heuristic, not exact mesh
  bounds — cheap and good enough for editor click-to-select). 2D:
  inverse the camera's screen offset, rect hit-test. Nearest hit wins
  either way, correctly resolving occlusion.
- **`client/engine/gizmo.py`** — mode-switchable (`T`/`R`/`S`)
  translate/rotate/scale. **Rendered via imgui's foreground draw list**
  (`world_to_screen()` projects handle endpoints to screen pixels every
  frame), not a new GPU line-list pipeline — a deliberate scope
  decision, avoiding new WGSL/pipeline surface area entirely; see the
  module's own docstring. Translate/scale drag math unprojects two axis
  points to screen and dots the mouse delta against that direction;
  rotate tracks the *change* in screen-space angle around the gizmo's
  projected center between pointer-move events (never the absolute
  angle — recomputing that causes a snap at the ±π wraparound). Degrades
  in 2D mode per the prompt's own rule: no Z translate/scale handle, one
  rotate ring instead of three.
- **Property panel** — instance-level fields (position, rotation, scale,
  `render_template`) edit *only* the selected entity; a template section
  (dangle/`localOffset`/per-action clip assignment) edits the shared
  entity-*definition* file every placement of that template uses,
  gated behind an explicit "Confirm & Save Template" button with a
  persistent warning banner — see "Instance vs. template," below.
- **Asset browser** — manifest-driven (`asset_loader.list_category()`,
  a small addition needed because `AssetLoader.load_manifest()`
  originally flattened every category into one flat `{id: path}`
  registry with no way to ask "every mesh" back out), with a text
  filter. "Place" adds an entity at the camera's look-at point; "Place
  as Zone" (mesh entries only) does the same but into `Scene.zones`
  instead of `Scene.entities` — see "Zone authoring," below.
- **Grid + snapping** — a faint ground-plane grid overlay (same
  imgui-draw-list-overlay mechanism as the gizmo), position snapping
  (rounds gizmo drags/placements to a configurable grid size), optional
  rotation snapping (configurable degree increment).
- **Scene Settings panel** — read-only display of `Scene.start_camera`/
  `Scene.lighting` plus "Set Start Camera to Current View"/"Set Start
  Lighting" buttons — the *only* code path in the whole editor allowed
  to call `Scene.set_start_camera()` (per that method's own contract).
- **Save/load** — `client/engine/area_io.py`'s `save_area`/
  `save_entity_definition`, both refreshing `manifest.json` in-process
  (a plain Python import/call to `tools/build_manifest.py`, not a
  subprocess) so a new save is immediately visible in the launcher —
  no manual rebuild step.
- **Keyboard shortcuts** — `T`/`R`/`S` (gizmo mode), `Delete`/
  `Backspace` (remove selection), `Ctrl+D` (duplicate), `F` (focus
  selection), `Escape` (deselect), `Ctrl+Z`/`Ctrl+Shift+Z`/`Ctrl+Y`
  (undo/redo), `G` (grid toggle) — all gated behind
  `imgui.get_io().want_capture_keyboard`/`want_text_input`, so a
  focused property-panel text field correctly swallows them first.

### Instance vs. template

Two entity-definition-related edits look similar in the property panel
but have very different blast radii, and the editor is deliberately
careful never to blur them:

- **Instance-level** (position, `transform3d.rotation`/`scale`,
  `render_template`, and — once `ScriptComponent` exists —
  `ScriptComponent` params) affects *only the selected placement*.
  Committed on field-deactivate, routed through `EditorCommands` like
  any other edit, no confirmation needed.
- **Template-level** (a part's `dangle`, `localOffset`, and
  `action_animations`) edits the shared `entity-<id>.json` definition
  file — every entity anywhere referencing that `render_template` picks
  up the change. Requires an explicit "Confirm & Save Template" click
  (never a silent field-blur commit) and shows a persistent warning
  banner while editing. Undo only reverts the in-session `EditorCommands`
  state, not a save that's already gone out to disk — an accepted
  limitation of editing shared, non-Area-file content from inside the
  Area editor, not a bug.

### Live camera vs. authored start_camera/lighting

Flying the free camera around to inspect a scene must never silently
change what gets saved. `Scene.camera` is the live, constantly-mutated
view; `Scene.start_camera`/`Scene.lighting` are the *authored* values,
changed only by the Scene Settings panel's two explicit buttons — see
`Scene`'s own API section above for the mechanics.

## Zone authoring

Editor-side placement/property-panel/save story for
[Zones](#zones) (below) — `.github/prompts/level-editor.prompt.md` Step
13 adds **no new backend zone mechanics**, only visualizes/edits what
`Zone`/`ZoneRegistry` already define:

- **AABB placement** — "Add Zone (AABB)" creates a 2×2×2 box at the
  camera's look-at point; the *same* translate/scale gizmo used for
  entities repositions/resizes it, reframed via a small pose conversion
  (`_zone_gizmo_pose`/`_zone_shape_from_pose`: AABB position = box
  center, gizmo "scale" = half-extents, converted back to `min`/`max`
  on every drag update) — no gizmo code duplicated or modified.
- **Mesh-footprint placement** — the asset browser's existing "Place"
  flow, just routed to `Scene.zones` via a "Place as Zone" button next
  to each mesh entry instead of `Scene.entities`.
- **Visualization** — an AABB zone draws as its exact wireframe box
  (imgui draw-list overlay, translucent yellow); a mesh zone draws a
  tinted cyan wireframe box around its placement point, **a documented
  simplification** of "draws its actual mesh, alpha-blended" — genuine
  alpha-blended GPU mesh rendering for zones would need real
  renderer/material-pipeline work this pass didn't build.
- **Effect editing** — a combo box over the 8 effect types plus a
  per-row Remove button; shape fields are read-only in the panel
  (re-derived from the gizmo's live transform, never hand-typed).
- **Selection sync** — zones appear in the entity list with a `[ZONE]`
  prefix, selectable/deletable from there like any entity.

## UI menu authoring

`client/engine/ui_editor.py` (Step 14) — a 2D-only screen-space editor
built directly on `client/engine/ui/`'s real widget functions
(`draw.begin_frame()`/`widgets.panel`/`label`/`button`/`progress_bar`),
so the live preview *is* the runtime appearance, never separate editor
chrome. `MenuDocument` (the menu-authoring equivalent of `Scene`) plus a
matching set of `EditorCommands` factories
(`add_ui_element_command`/`update_ui_element_command`/
`remove_ui_element_command`/`add_trigger_command`/
`remove_trigger_command`) — `EditorCommands` itself needed no changes to
support this, since it never actually calls a `Scene`-specific method,
only stores whatever's passed to it for command closures to use.

Schema: `{"menu_id", "elements": [{"id", "type", "rect": [[x0,y0],
[x1,y1]], ...type fields}], "triggers": {"show": [...], "hide": [...]}}`
— `type` maps 1:1 onto `widgets.py` functions (`panel`/`label`/`button`/
`progress_bar` fully wired; `image_button` renders as a labeled
placeholder panel in the editor until a texture asset is assigned).
Click-select (rect hit-test), drag-move, drag-resize (bottom-right
corner handle) — all plain screen-space math, no 3D raycasting anywhere
in this tool.

**Triggers**, three types:

- `keybind` — fully functional, purely client-local. `client/engine/
  ui_menu_runtime.py`'s `MenuRuntime.poll_keybind_triggers()` is
  edge-triggered against `client/engine/input.py`'s key state.
  **Authoring gotcha** (found while verifying `MenuRuntime`): `show`
  and `hide` are independent lists, not a toggle — the same key in both
  fires both in one frame and nets to "stays hidden." Use distinct keys,
  or a different close mechanism (a Resume button), for an
  escape-to-toggle menu.
- `zone` — on save, writes a `{"type": "fire_event", "event":
  "show_menu:<id>"}`/`"hide_menu:<id>"` entry directly into the
  *referenced zone's* own `on_enter`/`on_exit` effect list
  (`zones.prompt.md`'s existing `fire_event` type) — the menu system is
  just one more `fire_event` listener, not a new zone capability.
- `entity_interact` — same idea, reusing `area-system.prompt.md` Step
  10's `"entity_overlap"` event.

**Both `zone` and `entity_interact` are authoring-only, not verifiable
end to end on `engine`**: both fire server-side and need a
`menu_trigger` SocketIO event to reach the client. Neither
`area-system.prompt.md` nor `zones.prompt.md` built an EventBus↔SocketIO
bridge (confirmed by audit) — `MenuRuntime.on_menu_trigger_event()` is
the client-side registration point, ready but with nothing to register
against yet. A game branch adding that bridge should call it the same
way `client/engine/network.py`'s `on_scene_cue` callback slot is
registered.

Save flow reuses the Area/entity-definition save pattern exactly: write
`frontend/assets/data/ui/menu-<id>.json` via `open()`, refresh
`manifest.json`'s new `"ui_menus"` category before returning.

## Action Definitions panel

Editor authoring for
[`docs/graphics/ACTION_TRIGGERED_ANIMATIONS.md`](ACTION_TRIGGERED_ANIMATIONS.md)'s
pattern — **data only** (Step 15). `ActionRegistry`
(`client/engine/area_viewer.py`) is a flat `{action_name:
{"duration_ms"}}` map persisted to `frontend/assets/data/actions.json`
(a single well-known asset, like `ui_theme.json` — no manifest category,
unlike areas/meshes/entities), the editor-authored equivalent of
`backend/engine/example_game_loop.py`'s `ACTION_DURATIONS` constant.
Add/remove routes through the same `EditorCommands` stack as everything
else in this editor.

The property panel's template section (above) gains one text field per
*registered* action, per selected mesh part — assigning/clearing that
part's `action_animations[action_name]` transform-clip id, written on
the same "Confirm & Save Template" click as `dangle`/`localOffset`.

**Deciding when an action fires stays real gameplay code on a game
branch, never authored here** — this panel manages exactly two things
that genuinely are data (an action's duration, which clip plays for it
on a part) and nothing else. The sprite-path one-shot clip (frame
indices, atlas region) stays hand-authored JSON; a visual frame-picker
is a distinct, larger tool this step doesn't build.

## Zones

`backend/engine/zone.py` — `Zone`/`ZoneRegistry`, both containment
shapes, and all 8 declarative effect types. Reclassified engine-layer
during implementation (2026-08-20): `.github/prompts/zones.prompt.md`'s
original Step 4 placed the effect dispatcher in `backend/game/area.py`
("game-layer, since it touches Area's own groups/entities and
EventBus") — but every effect only touches generic engine primitives
(`GroupRegistry`, `Entity.set_data`/`add_component`, `EventBus`),
nothing game-specific, the same reasoning that already reclassified
`client/engine/area_viewer.py`. So `Zone`/`ZoneRegistry`/
`apply_zone_effect` are all real, done, and verified
(`run_zone_test.py`, no backend server or game branch needed) — only
Step 5's one-line wiring into a game branch's `Area.update()` stays
blocked, since `Area` itself doesn't exist on `engine`.

### Shapes

- **`aabb`** — `{"type": "aabb", "min": [x,y,z], "max": [x,y,z]}`, a
  plain per-axis min/max compare. The simple two-corner box zone.
- **`mesh`** — `{"type": "mesh", "mesh": "<mesh-asset-key>", "position":
  [x,y,z], "rotation": [rx,ry,rz], "scale": [sx,sy,sz]}`. A **documented
  approximation, not true volumetric containment**: the mesh's vertices
  are projected onto the XZ (ground) plane, reduced to their 2D convex
  hull (**necessary, not optional** — a mesh's stored vertices come in
  triangle/face order, not a perimeter walk; feeding them to the
  ray-casting test directly produces a self-intersecting, meaningless
  polygon — found and fixed while verifying this module), cached once
  per `Zone` instance. Per-tick containment is a Y-range check plus a
  point-in-polygon (ray-casting/even-odd rule) test against that cached
  hull, after transforming the query point into the mesh's local space
  (inverse of position/rotation/scale — rotation convention matches
  `client/engine/mat4.py`'s `rotation_xyz()` exactly, re-derived
  locally since backend Python must not import the client package). A
  concave footprint (an L-shaped room) is flattened to its convex hull;
  a mesh with real 3D interior shape (a dome) isn't correctly handled —
  both explicit, permanent scope boundaries, not bugs to fix later.

### Effects

Each of a zone's `on_enter`/`on_exit` lists holds effect dicts,
dispatched by `apply_zone_effect(entities, entity_id, effect, groups,
event_bus, zone)`:

| `type` | Effect |
| --- | --- |
| `add_group` | `groups.add_to_group(entity_id, group)` |
| `remove_group` | `groups.remove_from_group(entity_id, group)` |
| `set_group_attribute` | `groups.set_group_attribute(group, key, value)` |
| `set_data` | `entity.set_data(key, value)` (tag data bag) |
| `clear_data` | `entity.clear_data(key)` |
| `add_component` | `entity.add_component(Component.from_dict(component))` — the entity's own local store, not `World`'s (see the `ecs_world` gap below) |
| `remove_component` | `entity.remove_component(Component.lookup(component_type))` |
| `fire_event` | `event_bus.publish(event, {**payload, "entity_id": ..., "zone_id": ...})` — the generic hook `level-editor.prompt.md`'s UI-menu zone triggers use to fire `show_menu:<id>`/`hide_menu:<id>` |

An unknown effect `type` (or shape `type`) logs a warning once per
unique unknown value and is skipped — never crashes the tick loop on
bad/hand-authored data.

### Enter/exit de-dup

`ZoneRegistry.update(entities, effect_dispatcher)` tests every entity
against every zone each tick, diffs against the previous tick's
inside-set per zone, and fires `on_enter`/`on_exit` only on the
transition — never once per tick while an entity sits inside or
outside. `effect_dispatcher(zone, entity_id, effects)` is injected, not
imported directly, keeping `ZoneRegistry` itself free of any dependency
beyond entity position (mirrors `group.py`'s "just data and
membership" scope) — `apply_zone_effect` is the separate, thicker
function that actually touches groups/components/events.

### Why `Area.update()`, never a `System`

The confirmed, load-bearing reason `ZoneRegistry` is driven from a
plain per-tick `update()` call rather than registered with
`SystemScheduler`: nothing in this codebase ever calls
`ecs_world.add(entity)`/`add_component(...)`, so every registered
`System` queries a permanently empty `World` and has zero effect on
live gameplay, regardless of how correct its own logic is (confirmed
via `grep -rn "ecs_world\." backend/`). `backend/engine/group.py`'s
`GroupRegistry` was built against the *real* live path
(`Area.update()` iterating `self.entities.values()` directly) —
`ZoneRegistry` follows the identical reasoning.

## Pending: backend Area-file schema (blocked on a game branch)

`backend/game/area.py`'s `Area` class — the `camera`/`lighting`/`zones`
optional fields on the backend side, `to_dict()`/`from_dict()`/
`get_full_state()` extensions, and `backend/app.py`'s `initial_state`
payload inclusion — doesn't exist on `engine` (see
`area-system.prompt.md`'s branch-reconciliation banner, Step 2). The
file *shape* `Scene.load_from_area_file`/`to_area_file_json` already
read/write matches what that class is specified to produce
(`{"entities": ..., "camera": ..., "lighting": ..., "zones": ...}`), so
a game branch implementing Step 2 against this same shape should
round-trip with the client side unmodified.

Also pending, same reason: the movement/collision fix and
`ScriptComponent`/`ScriptMovementSystem` (Steps 9–10 of
`area-system.prompt.md`) — and, independent of the branch issue, both
need the `ecs_world`-never-populated gap re-confirmed before resuming,
per that prompt file's own warning.

**Zones' one remaining piece** (`zones.prompt.md` Step 5): a single
line in a game branch's `Area.update()`, after the per-entity position
update loop —

```python
self.zones.update(
    self.entities,
    lambda zone, eid, effects: [
        apply_zone_effect(self.entities, eid, e, self.groups, self.event_bus, zone)
        for e in effects
    ],
)
```

— plus `to_dict`/`from_dict` wiring for `self.zones = ZoneRegistry()`,
mirroring exactly how `self.groups` was wired in this session. Nothing
else in `Zone`/`ZoneRegistry`/`apply_zone_effect` needs touching.
