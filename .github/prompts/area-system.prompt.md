---
agent: agent
description: Build a unified Area/Scene system — a single rendering-side container for entities, camera, and lighting, populated either from a pre-authored Area JSON file or the live SocketIO gameplay stream, and modified imperatively at runtime — powering four run modes (gameplay, viewer, builder, test) from one boot path, plus backend script-driven entity movement that interacts correctly with other entities via a corrected, spatial-grid-accelerated physics pass.
tools:
  - read_file
  - create_file
  - replace_string_in_file
  - multi_replace_string_in_file
  - grep_search
  - file_search
  - get_errors
---

# Task: Area / Scene System — Unified Loading, Four Run Modes

You are building the container that holds "everything in one place" — entities/assets, lighting, and the current camera — and making it loadable two ways (a pre-authored file, or the live gameplay stream) and writable a third way (direct API calls from a script or a builder UI), so the same rendering pipeline serves a map builder, a dev/test harness, a plain asset/scene viewer, and real scripted gameplay without four separate implementations.

**The key architectural insight, stated up front:** there is one runtime container (`Scene`) and two things that populate it (a file load, or the network stream) and one thing that can modify it at any time (an imperative API). Four "modes" fall out of *what drives the Scene*, not four different rendering systems:

| Mode | Populated by | Driven by | Backend connection |
| --- | --- | --- | --- |
| Gameplay | Network stream | Player input → server → network | Yes, live |
| Viewer | File load | Nothing (static) | No |
| Builder | File load | Human, via a crude on-page panel | No |
| Test | File load | A script calling the Scene API | No |

Viewer, builder, and test share one boot path (Step 6) — they are the same page with different things happening after load, not three apps.

This is **not** a full level editor. No drag-and-drop, no undo/redo, no polished editor chrome — a working save/load loop through the existing Area file format matters more than UX polish. This is **not** a new backend simulation concept: lights stay ECS entities (`LightComponent` already exists), a camera is passive metadata with no gameplay effect. This is **not** a rewrite of the working gameplay network path in one step — `Scene` wraps the existing flow via a compatibility shim (Step 5) rather than replacing every consumer at once.

## Required Reading

Read these files before writing any code:

- `backend/game/area.py` — the existing `Area` class; entity list, `to_dict()`/`from_dict()`, `load_area()`/`save_to_file()`. This task extends this schema, not forks it.
- `backend/game/world.py` — sibling `World` class (metadata only); note the same load/save pattern to mirror if a camera/lighting default needs to live at the world rather than area level.
- `backend/save_manager.py` — how `data_dir` is resolved (`saves/<player_id>/` vs. legacy dir) when `Area.load_area()` is called; a standalone viewer/builder needs a *different* `data_dir` (an authored-content directory, not a save slot) — see Step 2.
- `backend/app.py` — where `initial_state` is emitted (`game_loop.current_area.get_full_state()`) — Step 2 extends this payload with camera/lighting.
- `frontend/js/engine/network.js` — `initNetwork()`, `handleInitialState`/`handleStateUpdate` wiring (the handlers themselves currently live in `frontend/js/game/main.js`).
- `frontend/js/game/main.js` — the `gameState` global object and `handleStateUpdate()`; this is what today plays the role `Scene` will formalize. Read it fully — Step 5 refactors it without breaking it.
- `frontend/js/game/playerSelect.js` — `loadGameState()`, the other current populator of `gameState` (initial load, as opposed to `handleStateUpdate`'s deltas).
- `frontend/js/engine/renderer.js` and `frontend/js/engine/entityRenderer.js` — current consumers of `gameState.entities`/`gameState.camera`; Step 5's compatibility shim must keep these working unmodified.
- `.github/prompts/3d-coordinate-mapping.prompt.md` — Step 3 (`camera` object's 3D fields), Step 8 (`fogColor`/`fogNear`/`fogFar`/`ambientColor`), Step 5 (`render_template` — the field that links a networked/Area-file entity to its mesh/material definition; Step 11 of this file depends on it), Step 9 (entity `parts`). This plan's `camera`/`lighting` schema must reuse those exact field names, not invent parallel ones.
- `backend/engine/ecs/entity.py` — `serialize()` vs. `to_dict()`/`from_dict()`: confirms `ScriptComponent` (Step 10) round-trips through the latter (persistence/Area files) but is never part of the former (live network payload) — a script-driven entity's movement reaches clients only via ordinary `x`/`y` fields, never via the client learning a script exists.
- `.github/copilot-instructions.md` — "Physics & Simulation Boundary" section. Step 3's authoritative-vs-local entity rule and Step 8's scripted-dressing guidance follow the same shape: client-only additions must never be mistaken for authoritative ones.
- `backend/game/systems/systems.py` — `MovementSystem`, `PhysicsSystem`, `PathfindingSystem`, `AISystem`, `CombatSystem`. Read every `update()` method fully; Step 9 fixes two real bugs found in how these interact (double integration, uncollided path movement) and Step 10 adds a new system alongside them.
- `backend/game/tick.py` — where all five systems above are constructed and registered with the `SystemScheduler`, in the order that currently produces the Step 9 bugs.
- `backend/engine/ecs/scheduler.py` — `SystemScheduler.build()`'s Kahn's-algorithm topological sort; Step 9 changes `dependencies` declarations on existing systems, so understand exactly how `dependencies` maps to execution order before touching any of them.
- `backend/engine/spatial.py` — `SpatialGrid`'s query API; `PhysicsSystem` already holds a reference to one but doesn't use it for collision candidate lookup. Step 9 fixes that.
- `backend/engine/ecs/component.py` — `ColliderComponent` (`solid` field), `PositionComponent` (already has `z`, unused by movement systems today), `VelocityComponent`, `PathComponent`. Step 10 adds a sibling `ScriptComponent` following the same dataclass/`to_dict`/`from_dict` pattern.
- `backend/engine/behaviour_tree.py` — `Seek`/`Flee` leaves, to see exactly how existing AI-driven movement sets a `PathComponent` today, so Step 10's `ScriptComponent` is positioned correctly relative to it (simple built-in motion patterns) rather than duplicating what a behaviour tree already does (complex decision-making).

## Constraints

- Extend the existing Area file schema (`backend/game/area.py`); do not invent a second, parallel scene-file format. One file format must be loadable by both the save-game system and the standalone viewer/builder/test boot path.
- No new backend simulation concept for camera or lighting — both are passive metadata blocks with no gameplay effect, matching the "Physics & Simulation Boundary" precedent (frontend camera position is cosmetic; if something needs to be simulated, it's an ECS entity, not a metadata block).
- Do not replace `gameState` or rewrite every one of its consumers in this task. `Scene` is introduced underneath it via a compatibility shim (Step 5); `renderer.js`, `ui.js`, and `input.js` must keep working unmodified.
- An entity added directly through the `Scene` API (builder placement, test script, cutscene dressing) is tagged `'local'` and must never silently overwrite or be overwritten by an entity with the same id tagged `'authoritative'` (from network or file) — collision is a loud warning, never a silent pick.
- Builder UI: plain HTML controls and/or keyboard shortcuts are sufficient. No canvas-based drag manipulation, no undo stack — explicitly out of scope.
- Follow the JavaScript Airbnb style guide (2-space indent, single quotes) and PEP 8 (79 cols) per `.github/copilot-instructions.md`.
- Backend changes are limited to Steps 2, 7, 9, and 10 (the file schema extension, an optional dev-only save route, the movement/collision correctness fix, and the new script-movement system). Do not touch `CombatSystem`'s combat-resolution logic itself, `save_format.py`, or anything outside what those steps specify.
- Step 9's reordering must be justified by a stated target execution order and verified against the scheduler's actual computed order (log or print `scheduler._order` and check it) — do not hand-wave the topological sort; Kahn's algorithm's tie-breaking among zero-dependency systems depends on registration order, and getting this wrong reintroduces the exact bugs Step 9 exists to fix.
- `ScriptComponent`-driven entities are real backend ECS entities, not client-side `Scene` additions — per the "Physics & Simulation Boundary," anything that needs to *interact* (collide, trigger, be detected) must be authoritative and server-simulated. A script-driven entity only stays purely client-side/cosmetic if it's added through `Scene.addEntity(..., 'local')` (Step 8's mechanism) — in which case it explicitly cannot interact with anything, by the same rule.

---

## Step 1 — Audit Current State

Before writing code, read every file in Required Reading and summarize:

1. The exact current shape of `Area.to_dict()`'s output and where `get_full_state()`'s payload is emitted to the client (`app.py`).
2. Every place `gameState.entities`, `gameState.camera`, or `gameState.player` is read or written across `main.js`, `network.js`, `playerSelect.js`, `renderer.js`, `entityRenderer.js`, `ui.js`, `input.js` — this is the full blast radius Step 5's shim must not break.
3. Where Area files currently live on disk (`saves/<player_id>/area-<id>.json`) versus where a new "authored/template" area directory should live so viewer/builder/test mode isn't tied to a save slot.

Do not create or edit files in this step.

---

## Step 2 — Extend the Area File Schema

**File:** `backend/game/area.py`

1. Add two optional fields to `Area`: `self.camera: Optional[dict] = None` and `self.lighting: Optional[dict] = None`.
2. `to_dict()`: include `"camera": self.camera` and `"lighting": self.lighting` (both `None` if unset — `json.dump` writes `null`, which is fine and matches "no override, use engine defaults").
3. `from_dict()`: read them back with `.get("camera")`/`.get("lighting")`, defaulting to `None`. This keeps every existing save file (which has neither key) loading identically to before — `None` means "nothing to apply," not an error.
4. Schema for both blocks (document in Step 12, implement here as plain dicts — no new Python classes needed, this is pass-through metadata):
   - `camera`, one of two shapes depending on `mode`:
     - 3D: `{ "mode": "3d", "position": [x,y,z], "target": [x,y,z], "up": [x,y,z], "fov": float, "near": float, "far": float }`
     - 2D: `{ "mode": "2d", "x": float, "y": float, "zoom": float }`
     Reusing exactly the field names from `3d-coordinate-mapping.prompt.md` Step 3's `camera` object.
   - `lighting`: `{ "ambientColor": [r,g,b], "fogColor": [r,g,b], "fogNear": float, "fogFar": float }` — reusing exactly the field names from that prompt file's Step 8. **Note on where these live at runtime**: the *file* schema keeps `camera` and `lighting` as two separate authored blocks (clearer for a human editing the file), but the 3D renderer only ever reads fog/ambient off its single `camera` object each frame — Step 3 task 2's `setLighting()` bridges this by writing `lighting`'s fog/ambient fields onto `Scene.camera`, not `Scene.lighting`, at apply time. Keep the file schema and the runtime merge separate concerns; don't conflate them.

**File:** `backend/app.py`

5. Include `camera`/`lighting` in the payload built from `game_loop.current_area.get_full_state()` (extend `Area.get_full_state()` itself to add the two keys, mirroring `to_dict()`) so a live gameplay client also receives the authored starting camera/lighting on `initial_state`, not only when loading a raw file directly.

**File:** `backend/save_manager.py`

6. No behavioural change required — confirm (don't just assume) that `Area.load_area(data_dir, area_id)` works unmodified when pointed at a *different* `data_dir` than a save slot, since Step 4's standalone loader will call the equivalent file-read logic against an authored-content directory instead of `saves/<player_id>/`.

Verify: an existing save file with no `camera`/`lighting` keys still loads and plays identically (`from_dict` sees `None` for both, nothing downstream changes). A hand-edited Area JSON with a `camera` block, loaded via `save_manager`, produces a `get_full_state()` payload that includes it.

---

## Step 3 — `Scene`: the Single Runtime Container

**New file:** `frontend/js/engine/scene.js`

The one object both the network path and the file-load path populate, and the one object the builder/test/cutscene APIs write into.

1. `class Scene`:
   - `entities: Map<string, object>` — each stored entity record gets an internal `_source: 'authoritative' | 'local'` tag (not sent to or read from any file/network payload — purely an in-memory bookkeeping field).
   - `camera: object` — same shape as the `camera` object already used by `renderer.js` (2D fields today, 3D fields plus `fogColor`/`fogNear`/`fogFar`/`ambientColor` per the coordinate-mapping prompt file's Steps 3 and 8 — this is the one object the renderer actually reads every frame).
   - `lighting: object` — `ambientColor`/`fogColor`/`fogNear`/`fogFar`, kept as the *authored-shape* mirror of the Area file's `lighting` block (Step 2). This object is a record of what was authored, not what the renderer reads — see `setLighting()` below.
2. API:
   - `addEntity(id, data, source = 'local')` — if `id` already exists with a *different* `_source`, log a loud warning and refuse the write (return `false`) rather than picking a winner. Same-source overwrites (e.g. a second network update for the same id) proceed normally.
   - `updateEntity(id, patch)` — `Object.assign` onto the existing record if present; no-op with a warning if not (mirrors the existing defensive style in `handleStateUpdate`).
   - `removeEntity(id)`.
   - `setCamera(cameraData)` — `Object.assign` onto `this.camera`.
   - `setLighting(lightingData)` — `Object.assign` onto `this.lighting` **and** onto `this.camera` (only the `ambientColor`/`fogColor`/`fogNear`/`fogFar` keys — the renderer never reads `Scene.lighting` directly, so without this second write the Area file's `lighting` block would be authored data with nothing consuming it, same class of bug as `ambientColor` had in the 3D prompt file before it was fixed there). Document this dual-write in a code comment; it's the one place this class does something less obvious than a plain `Object.assign`.
3. No rendering logic in this file — `Scene` is pure data plus the API above. `renderer.js`/`entityRenderer.js` read `scene.entities`/`scene.camera` (fog/ambient included) — `scene.lighting` exists for authoring round-trips (`toAreaFileJSON`, Step 4) and any future non-camera lighting consumer, not for the current renderer.

Verify: unit-style manual check in the browser console — construct a `Scene`, `addEntity('a', {...}, 'authoritative')`, then try `addEntity('a', {...}, 'local')` and confirm it's refused with a warning, not silently applied.

---

## Step 4 — File-Load Path

**File:** `frontend/js/engine/scene.js`

1. `static async Scene.loadFromAreaFile(url)` — `fetch(url)`, parse JSON (the Step 2-extended Area schema), construct a `Scene`, call `addEntity(id, data, 'authoritative')` for every entry in `entities`, call `setCamera()`/`setLighting()` if those keys are present (skip entirely if `null`, leaving engine defaults), return the populated `Scene`.
2. `Scene.toAreaFileJSON()` — the inverse: serialize **every** entity in `entities`, regardless of `_source` (see Step 7 task 5 for why `'local'` entities are included — the short version: what a builder places is real content once saved, the `_source` tag is a purely in-memory runtime concept and is dropped, not written, in the output), plus `camera`/`lighting`, in the exact shape `Area.to_dict()` produces, so a file saved from the browser is loadable by `Area.from_dict()` on the backend unmodified.

Verify: point `Scene.loadFromAreaFile()` at an existing save's `area-<id>.json` (copied somewhere fetchable) and confirm every entity, plus camera/lighting if present, lands in the `Scene` correctly — no network connection open at all.

---

## Step 5 — Wire the Network Path Through `Scene` (compatibility shim)

**File:** `frontend/js/game/main.js`

This is the step with the most blast-radius risk — read it twice before editing.

1. Add `const scene = new Scene();` alongside the existing `gameState` object.
2. In `handleStateUpdate()`, replace the direct `gameState.entities[entityId] = ...` / `Object.assign(entity, entityData)` logic with `scene.addEntity(entityId, entityData, 'authoritative')` for new ids and `scene.updateEntity(entityId, entityData)` for existing ones. Keep every existing side effect (interpolation's `prevX`/`prevY` bookkeeping, the `state`/`facing` defaulting, the player-camera-follow logic) — those move to run *after* the `Scene` write, reading back from `scene.entities.get(entityId)`.
3. In `playerSelect.js`'s `loadGameState()`, do the equivalent for the initial full-state payload.
4. Make `gameState.entities` and `gameState.camera` **getters that proxy to `scene`** (e.g. `Object.defineProperty(gameState, 'entities', { get: () => scene.entities })`) rather than separately-maintained copies — this is what makes the shim safe: every existing reader (`renderer.js`, `ui.js`, `input.js`) keeps reading `gameState.entities`/`gameState.camera` exactly as before, unaware `Scene` now exists underneath.
5. Do not touch `renderer.js`, `ui.js`, or `input.js` in this step — if the proxy is implemented correctly, they need zero changes.

Verify: play the existing game end-to-end (`run_browser.py`) — movement, party commands, attacking — with no behavioural difference from before this step. This is a refactor, not a feature change; any observable difference is a bug.

---

## Step 6 — Standalone Boot Path (viewer / builder / test)

**New files:** `frontend/area-viewer.html`, `frontend/js/game/areaViewer.js`, `frontend/js/engine/freeCamera.js`

Mirrors the existing `run_browser.py`/`index.html` alternate-entry-point convention already in this project — a second, simpler page, not a second app.

1. **Create `frontend/assets/data/area/` and put the authored/template Area content there**, decided explicitly here (not left implicit): this is the directory a standalone viewer/builder/test session loads from, deliberately separate from `saves/<player_id>/` — templates aren't anyone's save slot. Author one `area-example.json` here for this step's own verify. If Step 1's audit found reasons to place it elsewhere, use that location instead, but make the choice explicit in this task rather than only inside a verify example.
2. `area-viewer.html`: same `<canvas>`/script-include structure as `index.html`, minus anything player-select/character-creation related.
3. `areaViewer.js`: on load, read an `?area=<path>` query parameter, call `await Scene.loadFromAreaFile(area)` (Step 4), call `initRenderer()`, start the render loop against the loaded `Scene` directly — **no `initNetwork()` call at all**. If `?area=` is absent, fall back to a small hardcoded default (an empty scene with the 3D camera looking at the origin) so the page is useful for smoke-testing the renderer alone.
4. `freeCamera.js`: WASD + mouse-look (or arrow keys + drag, whichever is simpler to wire against the existing `input.js` event patterns) bound directly to `scene.setCamera(...)` — independent of `input.js`'s player-control path, which sends `player_action` over a socket that doesn't exist on this page.
5. This one page and boot script *is* viewer mode as-is. Builder mode (Step 7) and test mode (documented in Step 8) are the same boot path with something additional layered on top — state this explicitly in code comments so a future reader doesn't assume there are three separate pages.

Verify: `python run_browser.py`, navigate to `area-viewer.html?area=/assets/data/area/area-example.json` (an example file authored for this step), confirm the scene renders with free-fly camera control and zero network activity in DevTools.

---

## Step 7 — Minimal Builder Affordances

**File:** `frontend/js/game/areaViewer.js` (extend, gated behind a `?mode=builder` query flag so plain viewer mode stays uncluttered)

1. A small on-page panel: a text input for an entity/mesh id (resolved via `assetLoader`), numeric x/y/z fields, an "Add" button calling `scene.addEntity(generateLocalId(), { ... }, 'local')`.
2. A simple list of current entities (id + source tag) with a "Remove" button per row calling `scene.removeEntity(id)`.
3. A "Save Area" button calling `Scene.toAreaFileJSON()` (Step 4) and downloading it as a `.json` file via a client-side `Blob`/`<a download>` — no backend route required for the simplest version.
4. Optional, only if a save-to-disk workflow is wanted over manual download: a minimal dev-only Flask route in `backend/app.py` (e.g. `POST /dev/save_area`) that writes the posted JSON under the authored-content directory identified in Step 1's audit. Gate this behind a debug flag — it must not be reachable in a packaged build.
5. Explicitly decide and document whether `'local'` entities are included in `toAreaFileJSON()` output: recommended default is **yes** — the whole point of the builder is that what you place becomes real content — but they're written as plain entities with no `_source` tag in the file (the tag is purely an in-memory runtime concept; a reloaded file has no way to distinguish "was local" from "was always authoritative," which is correct — once saved, it's just content).

Verify: place a few entities via the panel, save, reload the page pointed at the saved file, confirm the placed entities round-trip correctly including position and mesh/material reference.

---

## Step 8 — Scripted Gameplay Hook (non-authoritative dressing)

This step is mostly documentation plus a thin wiring point — the mechanism (`scene.addEntity(id, data, 'local')`) already exists from Step 3; what's new is *triggering* it from live gameplay.

**File:** `frontend/js/engine/network.js`

1. Add a handler for a server-sent cue event (e.g. `socket.on('scene_cue', (data) => { ... })`) that calls `scene.addEntity`/`scene.setCamera`/`scene.removeEntity` directly — for purely cosmetic moments (a temporary camera pan, a decorative prop that appears for a cutscene) that don't need to be real, simulated, interactive ECS entities.
2. State the rule explicitly in a code comment at this handler, referencing `.github/copilot-instructions.md`'s "Physics & Simulation Boundary": anything added this way is client-only and non-authoritative. If a designer needs the dressing to be hittable, collidable, or otherwise simulated, it must be a real backend entity added via `Area.add_entity` and delivered through the normal `state_update` path (tagged `'authoritative'`) — not this hook.
3. No backend `scene_cue`-emitting system needs to be built in this task; documenting and wiring the client-side handler is sufficient scope. (If a concrete cutscene system is wanted later, it's a separate task that would define what triggers this event.)

Verify: manually emit a `scene_cue` event from a Python REPL/test script against a running server and confirm the client adds the described local entity without a full backend entity round-trip, and without appearing in any subsequent `state_update` delta (proving it's genuinely non-authoritative).

---

## Step 9 — Fix the Movement/Collision Foundation (prerequisite)

Tracing `tick.py`'s actual registration against `scheduler.py`'s topological sort reveals the real per-tick order today is **`physics → movement → pathfinding → ai → combat`** (not the naive reading of the file). This produces two concrete bugs that any new movement system — script-driven or otherwise — would inherit:

1. **Double integration.** `MovementSystem`'s query (`PositionComponent`, `VelocityComponent`) matches *every* moving entity, including ones that also have a `ColliderComponent` and were already integrated (and collided) by `PhysicsSystem` earlier in the same tick. Those entities get their velocity applied twice per tick, and the second application (`MovementSystem`) has no collision check at all.
2. **Path-driven entities never collide.** `PathfindingSystem` (which drives the existing `Seek`/`Flee` AI behaviours via `PathComponent`) teleports `pos.x/y` directly toward the next waypoint and runs *after* `PhysicsSystem`'s collision resolution for the tick — so any AI-controlled entity following a path can pass through walls or other entities today.

There is a third, related inefficiency fixed in this step: `PhysicsSystem`'s collision loop iterates every `solid` entity for every moving entity (O(n_moving × n_solid)) despite already holding a `SpatialGrid` reference — it's only used for `get_terrain_friction` and post-move grid updates, never to narrow collision candidates.

**File:** `backend/game/systems/systems.py`

1. **Make `MovementSystem` skip collider-bearing entities.** Inside its loop, `if world.get_component(eid, ColliderComponent) is not None: continue` — `PhysicsSystem` owns those entities' integration entirely; `MovementSystem` becomes exclusively the path for simple movers that never collide (e.g. non-solid decorative or projectile entities without a `ColliderComponent`).
2. **Rewrite `PathfindingSystem` to set velocity, not position.** Replace the direct `pos.x = wx; pos.y = wy` teleport with computing the direction to the next waypoint and writing `vel.vx`/`vel.vy` (magnitude from the existing speed calculation) into the entity's `VelocityComponent`. Its query becomes `PositionComponent, VelocityComponent, PathComponent` (add the `VelocityComponent` requirement). Waypoint-arrival detection (advance `current_index`) still reads `pos`, it just no longer *writes* it — `PhysicsSystem` does, later in the tick.
3. **Reorder dependencies so `PhysicsSystem` runs last among movement systems.** Target order: `AISystem` (decision-making; may set a fresh `PathComponent` via `Seek`/`Flee`) → `PathfindingSystem` (consumes `PathComponent`, sets velocity — same-tick responsiveness to a `PathComponent` AI just set, which is a minor behavioural improvement over today's one-tick lag) → `MovementSystem` and the new `ScriptMovementSystem` (Step 10, both independent, either order is fine) → `PhysicsSystem` (integrates + collides everyone, always last) → `CombatSystem`. Concretely: remove `PathfindingSystem.dependencies = [PhysicsSystem]`; add `AISystem.dependencies = []` (was `[PathfindingSystem]` — flip the relationship), `PathfindingSystem.dependencies = [AISystem]`, `PhysicsSystem.dependencies = [MovementSystem, PathfindingSystem]` (extend to include `ScriptMovementSystem` once Step 10 exists), `CombatSystem.dependencies = [PhysicsSystem]` (was `[AISystem]`).
4. **Accelerate collision with the spatial grid.** Replace the flat `solid` list scan with a per-entity query against `self._grid` for nearby cells only (the grid's existing insert/update/query API — see `spatial.py`), falling back to the full scan only if `self._grid` is `None`. This turns collision resolution from O(n_moving × n_solid) into roughly O(n_moving × k), where k is the average entity count in a queried neighbourhood.

**File:** `backend/game/tick.py`

5. Confirm registration order still produces a valid build (no cycle) and update it if the scheduler's tie-breaking among zero-dependency systems needs a specific registration order to land on the target sequence from task 3.

Verify: log `self._scheduler._order` (or add a temporary debug print) and check it against the **partial** order the dependency graph actually guarantees — don't expect one exact sequence: `AISystem` before `PathfindingSystem`; `PathfindingSystem`, `MovementSystem`, and `ScriptMovementSystem` (once Step 10 exists) all before `PhysicsSystem`, in any relative order among themselves (they have no edges between them, so registration order decides their tie-break and it doesn't matter which way it goes); `PhysicsSystem` before `CombatSystem`. Then: an existing party member using `Seek` (chasing an enemy) can no longer walk through a solid obstacle. A moving, collider-bearing entity's velocity is applied exactly once per tick (add a temporary log of position delta per tick to confirm no double-movement).

**Expect a visible gameplay change, not "identical behaviour."** Before this fix, collider-bearing entities were effectively getting velocity applied twice per tick (once fully, once post-damping) — removing that means every such entity will now cover noticeably less distance per tick than before. This is the bug being fixed, not a regression, but existing speed constants (`_STEP_SPEED`, action costs tuned against the old buggy feel, etc.) may now feel too slow and could need retuning as a follow-up — call this out explicitly when reporting this step's completion rather than claiming nothing changed.

---

## Step 10 — `ScriptComponent` + `ScriptMovementSystem`

A lightweight, data-driven movement mechanism for NPCs/objects that need simple, repeatable motion (patrol, orbit, follow) without the overhead of authoring a full behaviour tree. Sits alongside `AIComponent`/`BehaviourTree` (for actual decision-making), not in place of it — and because it only ever writes `VelocityComponent`, every script-driven entity rides Step 9's corrected `PhysicsSystem` pass for integration and collision, for free, exactly like player and AI movement do. This is what makes multiple script-driven entities "interact with other entities or objects": they're ordinary collider-bearing ECS entities, resolved by the same single physics pass as everything else.

**File:** `backend/engine/ecs/component.py`

1. Add `ScriptComponent` (same dataclass/`to_dict`/`from_dict` pattern as every other component):
   ```python
   @dataclass
   class ScriptComponent(Component):
       script_type: str = "waypoint_loop"  # "waypoint_loop" | "orbit" | "follow"
       params: Dict[str, Any] = field(default_factory=dict)
       state: Dict[str, Any] = field(default_factory=dict)  # runtime bookkeeping, e.g. current waypoint index
   ```
   Registers automatically in `_COMPONENT_REGISTRY` via `__init_subclass__`, exactly like every existing component — no extra wiring needed for it to round-trip through `Entity.to_dict()`/`from_dict()` (persistence/Area files, which carry a `components` list). It does **not** round-trip through `Entity.serialize()` (the live network format) — that's `to_dict()`-only, deliberately; see Step 11 for why that's fine.

**File:** `backend/game/systems/systems.py`

2. `class ScriptMovementSystem(System)`, `dependencies = []`, querying `world.query_with_components(PositionComponent, VelocityComponent, ScriptComponent)`. For each entity, dispatch on `script.script_type` and write `vel.vx`/`vel.vy` only — never touch `pos` directly (Step 9's `PhysicsSystem` does that):
   - `"waypoint_loop"` — `params: {waypoints: [[x,y],...], speed}`, `state: {index}`. Direction to the current waypoint × speed; on arrival, advance `index` modulo `len(waypoints)` (loops forever, unlike `PathComponent`'s one-shot consume-and-remove).
   - `"orbit"` — `params: {center: [x,y], radius, angular_speed}`. Derive the current angle from `atan2(pos.y - center.y, pos.x - center.x)` each tick (self-correcting — no drift accumulation from stored state) and set velocity tangential to the circle, scaled by `radius * angular_speed`.
   - `"follow"` — `params: {target_id, distance, speed}`. Look up the target's `PositionComponent` via `world.get_component(target_id, PositionComponent)`; direction toward it × speed, zeroed once within `distance`.
   - Unknown `script_type`: log a warning once (not every tick) and zero velocity — never crash the tick loop on bad data.
3. Register `ScriptMovementSystem` in `tick.py` and add it to `PhysicsSystem.dependencies` per Step 9 task 3.

**File:** `backend/engine/ecs/component.py` and `backend/game/systems/systems.py` — interaction beyond simple push-out

4. Add an optional `trigger: bool = False` field to `ColliderComponent` (default `False`, fully backward compatible). A `trigger=True`, `solid=False` collider participates in overlap detection but never produces a push-out MTV.
5. In `PhysicsSystem`'s (now grid-accelerated) overlap pass, additionally check trigger colliders for pure overlap and publish an `"entity_overlap"` event via the `EventBus` (`{"a": eid, "b": other_eid}`) — the same pattern `CombatEvent`/`"combat_action"` already establishes. This is the generic hook for "interact with an object" (pickups, doors, area markers) without hardcoding specific interaction types into the physics system itself.
6. Script-driven entities can subscribe to `"entity_overlap"` (e.g. a `"follow"` script that stops and publishes its own event on reaching its target) — document this as the extension point rather than building specific interaction types now.

Verify: two `waypoint_loop` entities patrolling paths that cross must resolve collision correctly (neither tunnels through the other) via Step 9's `PhysicsSystem`. An `orbit` entity traces a stable circle with no drift over many ticks. A `follow` entity tracks a moving target and stops at the configured distance. A trigger-collider entity overlapping a `solid=false, trigger=true` zone publishes exactly one `"entity_overlap"` event per overlap transition (not once per tick while overlapping — de-duplicate via a per-pair "currently overlapping" set).

---

## Step 11 — Authoring Scripted Entities

Ties Step 10's backend capability back into this task's Area/Scene work: a script-driven NPC or object should be placeable the same way any other entity is. This requires being precise about **two different files** a single placed NPC touches, which is easy to conflate:

1. **The Area-file entity entry** — `Entity.to_dict()`'s format (`entity_id`, `x`/`y`, and a `components` list of ECS components). This is where `ScriptComponent` and `ColliderComponent` go. It is *not* sent to clients verbatim — the live network format (`Entity.serialize()`) carries no `components` list at all, only flat gameplay fields (position, velocity, state, `race`, `model_version`, `render_template`). A script-driven entity's movement reaches the client the same way any entity's movement does — through the ordinary `x`/`y` fields `serialize()` already sends — not by the client ever learning a `ScriptComponent` exists.
2. **The entity-definition file** (`frontend/assets/data/entity/entity-<uuid>.json`, `3d-coordinate-mapping.prompt.md` Step 5's schema) — `mesh`/`parts`/`material_id`/`transform3d`. This is what makes a placed entity actually *look* like something. The Area-file entry references it via the `render_template` field that prompt file's Step 5 adds to `Entity`.

So a patrolling NPC with a visible mesh needs **both**: an Area-file entry with `render_template: "<entity-definition-id>"` plus a `ScriptComponent`, and a separate entity-definition file that `render_template` points at.

**File:** `docs/graphics/DATA_STRUCTURES.md` (Area/entity schema)

1. Document the Area-file entity `components` list accepting a `ScriptComponent` entry directly (it round-trips automatically per Step 10 task 1 — no new deserialisation code needed): `{"type": "ScriptComponent", "script_type": "waypoint_loop", "params": {...}, "state": {}}`. Document alongside it that `render_template` (a plain top-level field on the same entity entry, not inside `components`) is what selects the entity-definition file for rendering — cross-reference `3d-coordinate-mapping.prompt.md` Step 5 rather than redefining it here.
2. Note explicitly that a script-driven entity needs a `ColliderComponent` to actually collide/interact (Step 9/10's physics pass only resolves collider-bearing entities) — omitting it is valid and means "moves, but passes through everything," which is a legitimate choice for purely decorative moving props.

**File:** `frontend/js/game/areaViewer.js` (Step 7's builder panel, extend)

3. Optional, stretch goal within this step: add a `script_type` dropdown + a raw JSON `params` textarea, **and** a `render_template` picker (resolved via `assetLoader`'s `"entities"` category from the 3D prompt file's Step 7), to the builder's "Add" form — writing both the `ScriptComponent` entry and the `render_template` reference into the placed entity's data. Not required for Step 10's backend capability to work — an Area file can always be hand-authored — but makes the builder able to place a patrolling, visible NPC without writing Python.

**Important limitation to document, not solve here:** standalone viewer/builder/test modes (Step 6) run with no backend connection by design. A `ScriptComponent` placed via the builder is saved as inert data — it will not actually move when previewed in the client-only viewer, because `ScriptMovementSystem` is backend Python that isn't running there. The entity will still *render* correctly (via `render_template`, which is purely client-side resolution), just not move. Seeing a scripted entity actually move requires loading the Area into a real gameplay session (or, as a documented future extension, a local/offline backend tick loop for test mode specifically — out of scope for this task).

Verify: hand-author an entity with both a `ScriptComponent` and a `render_template` in an Area file, load it through the real backend (`save_manager`/gameplay path), confirm it patrols/orbits/follows, collides correctly, **and renders as its referenced mesh** (not a placeholder). Load the same file in the standalone viewer and confirm the entity renders correctly at its initial position (proving `render_template` resolution works with no backend at all) but does not move (documenting, not fixing, the limitation above).

---

## Step 12 — Documentation

**New file:** `docs/graphics/AREA_SYSTEM.md`

1. Document the extended Area file schema (Step 2's `camera`/`lighting` blocks, with the field tables).
2. Document the `Scene` class and its API (Step 3), including the `'authoritative'` vs `'local'` rule and why it exists (cross-reference `.github/copilot-instructions.md`'s "Physics & Simulation Boundary" as the precedent).
3. Document the four run modes and, critically, that viewer/builder/test share one boot path (Step 6) — a table like the one at the top of this prompt file is a good format to reuse.
4. Cross-link from `docs/graphics/OVERVIEW.md`'s "Further Reading" list.

---

## Step 13 — Smoke Test

Run through all four modes:

```text
python run_browser.py
```

- [ ] **Gameplay** (`index.html`, existing flow): movement, party commands, attacking all behave exactly as before Step 5's refactor — no regression from introducing `Scene` underneath `gameState`.
- [ ] **Viewer** (`area-viewer.html?area=...`): loads and renders an Area file with zero network connections; free-fly camera works.
- [ ] **Builder** (`area-viewer.html?area=...&mode=builder`): place an entity, save, reload the saved file, confirm it round-trips.
- [ ] **Test**: a short manual script (browser console or a small `<script>` on the page) calling `scene.addEntity()` in a loop and confirming the renderer keeps up — proves the same boot path supports script-driven population, not just human/file.
- [ ] An `'authoritative'` and a `'local'` entity sharing an id: confirm the collision is refused with a console warning, not silently resolved.
- [ ] A save file with no `camera`/`lighting` blocks still loads identically to before Step 2.
- [ ] `scheduler._order` matches Step 9's target sequence; a collider-bearing entity's velocity is applied exactly once per tick; a `Seek`/`Flee`-driven party member can no longer pass through solid obstacles.
- [ ] Two `waypoint_loop` script entities with crossing patrol paths collide correctly instead of overlapping/tunnelling.
- [ ] An `orbit` script entity holds a stable radius over at least a few dozen ticks (no accumulating drift).
- [ ] A `trigger` collider publishes exactly one `"entity_overlap"` event per overlap transition, not once per tick.
- [ ] A `ScriptComponent`-bearing entity authored in an Area file moves/collides correctly through a real gameplay session, and renders (statically) but does not move in the standalone viewer — confirming the documented limitation rather than a silent failure.
- [ ] `get_errors` reports zero errors on all modified/new files.

---

## Success Criteria

- [ ] `backend/game/area.py` — `camera`/`lighting` optional fields added to `to_dict()`/`from_dict()`/`get_full_state()`; every field absent by default; no existing save file's load behaviour changes
- [ ] `backend/app.py` — `initial_state` payload includes `camera`/`lighting` when present on the current `Area`
- [ ] `frontend/js/engine/scene.js` — `Scene` class: `entities`/`camera`/`lighting`, `addEntity`/`updateEntity`/`removeEntity`/`setCamera`/`setLighting`, `'authoritative'`/`'local'` source tagging with refuse-on-collision, `loadFromAreaFile`/`toAreaFileJSON`
- [ ] `frontend/js/game/main.js` — `gameState.entities`/`gameState.camera` proxy to a `Scene` instance; `renderer.js`/`ui.js`/`input.js` unmodified; existing gameplay behaviourally unchanged
- [ ] `frontend/area-viewer.html` + `frontend/js/game/areaViewer.js` — standalone boot path with no `initNetwork()` call, serving viewer/builder/test modes from one page
- [ ] `frontend/js/engine/freeCamera.js` — free-fly camera control independent of the network-based player-input path
- [ ] Minimal builder panel (add/remove/save) gated behind `?mode=builder`, out of the way of plain viewer usage
- [ ] `frontend/js/engine/network.js` — `scene_cue` handler for non-authoritative scripted dressing, documented as cosmetic-only per the Physics & Simulation Boundary
- [ ] `backend/game/systems/systems.py` — `MovementSystem` skips collider-bearing entities; `PathfindingSystem` sets velocity instead of teleporting position; `PhysicsSystem`'s collision pass uses the spatial grid; dependency graph reordered so `PhysicsSystem` runs last among movement systems, verified against the scheduler's actual computed order
- [ ] `backend/engine/ecs/component.py` — `ScriptComponent` (dataclass, registry-registered) and `ColliderComponent.trigger` added
- [ ] `backend/game/systems/systems.py` — `ScriptMovementSystem` (`waypoint_loop`/`orbit`/`follow`), registered and scheduled correctly; `"entity_overlap"` published via `EventBus` for trigger colliders, de-duplicated per overlap transition
- [ ] `docs/graphics/DATA_STRUCTURES.md` — `ScriptComponent` entity-JSON authoring documented, including the "needs a `ColliderComponent` to interact" note
- [ ] `docs/graphics/AREA_SYSTEM.md` — full schema, API, run-mode, and script-entity documentation, linked from `OVERVIEW.md`
- [ ] No existing gameplay path, save file, or rendering behaviour regresses — every addition in this task is additive, wrapped behind a compatibility shim, or a fix to a demonstrated bug
