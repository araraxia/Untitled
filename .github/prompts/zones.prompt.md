---
agent: agent
description: Add spatial Zones to the backend — an AABB (two-corner) or mesh-footprint volume that fires events, manages GroupRegistry membership, or applies tag data/components to entities inside it. The generic trigger substrate other systems (UI menu triggers, area transitions, environmental effects) build on.
tools:
  - read_file
  - create_file
  - replace_string_in_file
  - multi_replace_string_in_file
  - grep_search
  - file_search
  - get_errors
---

# Task: Zones — Spatial Trigger Volumes

You are adding **Zones**: named spatial regions that entities can be inside or outside of, checked each tick, driving declarative `on_enter`/`on_exit` effects — publish an `EventBus` event, add/remove the entity from a `GroupRegistry` group, or write/clear tag data (`Entity.set_data`) or an attached `Component`. This is the generic substrate `level-editor.prompt.md`'s zone-authoring and UI-menu-trigger steps build on, and the natural extension of `area-system.prompt.md` Step 10's `ColliderComponent.trigger`/`"entity_overlap"` mechanism from *entity-vs-entity* overlap to *entity-vs-region* overlap.

**Two zone shapes, no third**: a simple two-corner axis-aligned box (`aabb`), or a mesh-footprint volume (`mesh`) for irregular room/area shapes. Neither is a full 3D collision system — see Constraints for exactly what "mesh zone" does and does not mean.

## Required Reading

- `area-system.prompt.md` Step 10 — `ColliderComponent.trigger` and the `"entity_overlap"` `EventBus` event, de-duplicated per overlap transition (a per-pair "currently overlapping" set). Zones generalize this exact pattern (per-entity-per-zone "currently inside" state, diffed each tick) from entity-pairs to entity-region pairs — read this before writing any zone code, don't re-derive the de-dup logic from scratch.
- `backend/engine/group.py` — `Group`/`GroupRegistry`, built this session specifically as a *layered-lookup* alternative to the ECS `World`/`Component` pipeline (see the gap noted below). Zones' group-membership effects call this directly (`area.groups.add_to_group`/`remove_from_group`/`set_group_attribute`) — this task does not reimplement group membership.
- `backend/engine/ecs/entity.py` — `Entity.get_data`/`set_data` (the tag-data-bag API, same session) and `Entity.add_component`/`get_component` (the entity-local component store — round-trips through `to_dict`/`from_dict`, but is **not** the same thing as `World`'s component store, see below). Zones' `set_data`/`add_component` effects operate on these.
- `backend/game/area.py` — holds `self.groups = GroupRegistry()` and `self.spatial_grid = SpatialGrid(...)` today; this task adds a sibling `self.zones`. Also read `Area.update(delta_time)` — the actual per-tick entry point (see below).
- `backend/engine/spatial.py` — `SpatialGrid`'s query API, for narrowing which entities are even worth testing against a given zone's bounds.
- `backend/engine/events.py` — `EventBus` pub/sub, the same one `"entity_overlap"`/`"combat_action"` already use.

**A real, confirmed gap this task must not paper over, and must not silently reproduce**: `GameTick.__init__` creates `self.ecs_world = World()` and the `SystemScheduler` runs registered `System`s (`PhysicsSystem`, `MovementSystem`, etc., from `simulation-systems.prompt.md`) against it every tick — but nothing anywhere in this codebase ever calls `ecs_world.add(entity)` or `ecs_world.add_component(...)`. Confirm this yourself (`grep -rn "ecs_world\." backend/`) before assuming otherwise. Every registered `System` therefore queries a permanently empty `World` and has zero effect on live gameplay today, regardless of how correct its own logic is. The actually-live per-tick path is `GameTick._do_tick()` → `self.current_area.update(TICK_DURATION)` → `Area.update()` iterating `self.entities.values()` directly. `backend/engine/group.py`'s `GroupRegistry` was deliberately built against *this* live path, not `World`/`System` — **`ZoneRegistry` follows the identical reasoning in this task**: it is driven from `Area.update()`, not registered as a `System` with the `SystemScheduler`. Do not register a `ZoneSystem` with the scheduler; it would compile, look correct, and never actually run against real data, exactly like every other registered `System` today.

## Constraints

- Two shapes only: `aabb` (`min`/`max` corner points) and `mesh` (a mesh asset key + placement, reduced to a 2D XZ-plane footprint polygon + a Y range — see Step 3). Do not add a third shape type or a general "any convex/concave 3D volume" system in this task.
- **Mesh-zone containment is a documented approximation, not true volumetric containment**: the mesh's vertices are projected onto the XZ (ground) plane once, at zone-load time, into a 2D polygon; per-tick containment is a point-in-polygon test against that cached footprint plus a plain Y-range check (the mesh's own min/max Y, scaled/offset by the zone's transform). A mesh with an actual 3D interior shape (e.g. a dome) is *not* correctly handled by this — that's an explicit non-goal, not a bug to fix here.
- No third-party computational-geometry dependency. Hand-roll the point-in-polygon test (ray-casting/even-odd rule — a well-known, short, dependency-free algorithm), matching this project's established stdlib-only preference (`tools/pack_param_map.py`, `tools/convert_mesh.py`).
- Zone effects are **declarative data** (plain dicts, JSON-serializable), never arbitrary executable code — no `eval`/`exec`. A zone file is authorable by hand or by the level editor without writing Python.
- `Zone`/`ZoneRegistry` live in `backend/engine/zone.py` (engine-layer, generic — any game can use zones), mirroring exactly where `SpatialGrid`/`GroupRegistry` already live. The concrete per-tick driving code (the loop that calls into `ZoneRegistry` each tick) lives in `backend/game/area.py`'s `Area.update()`, matching where `PhysicsSystem`-equivalent per-tick logic conceptually belongs today (game-layer orchestration of engine-layer primitives).
- Backend-only, backend-authoritative — per `.github/copilot-instructions.md`'s "Physics & Simulation Boundary," a zone that affects gameplay (group membership, component/tag data) must be server-simulated, same reasoning `ScriptComponent`/trigger colliders already follow. A purely cosmetic, client-only "zone" (e.g. a local lighting transition with no gameplay effect) is a different, simpler mechanism — out of scope here, not something this task's `Zone` type should also try to serve.
- Follow PEP 8 (79 cols, 4-space indent). Backend Python only — no client/`frontend/js/` work in this task (the level editor's zone-*authoring* UI is `level-editor.prompt.md`'s job, not this one's).

---

## Step 1 — Audit Current State

Before writing code, confirm (don't assume):

1. `area-system.prompt.md` Step 10's own checkmarks — has `ColliderComponent.trigger`/`"entity_overlap"` actually landed? This task's de-dup pattern mirrors it either way, but if it exists, read the real code, not just the prompt's description.
2. `backend/engine/group.py` and `backend/game/area.py`'s current `self.groups`/`self.spatial_grid` wiring (this session's work) — the exact shape `self.zones` must match.
3. Re-confirm the `ecs_world` gap yourself via `grep -rn "ecs_world\." backend/` — this task's entire System-vs-`Area.update()` placement decision depends on it still being true.
4. `Area.update()`'s current body — exactly where the new zone-check call slots in relative to entity position updates (after, so zones test settled positions, not mid-integration).

Do not create or edit files in this step.

---

## Step 2 — `Zone` / `ZoneRegistry` ✅

**New file:** `backend/engine/zone.py`

```python
@dataclass
class Zone:
    zone_id: str
    shape: dict          # see Step 3
    on_enter: list        # list of effect dicts, see Step 4
    on_exit: list          # list of effect dicts, see Step 4
    tags: list = field(default_factory=list)  # free-form labels, e.g. for editor filtering
```

`ZoneRegistry` (mirror `GroupRegistry`'s shape exactly — same constructor-less-registration, same `to_dict`/`from_dict` pair):

- `create_zone(zone_id, shape, on_enter=None, on_exit=None, tags=None) -> Zone`
- `get_zone(zone_id) -> Zone | None`
- `remove_zone(zone_id) -> None`
- `all_zones() -> list[Zone]`
- `_inside: dict[str, set[str]]` — `zone_id -> set of entity_ids currently inside`, the de-dup state from `area-system.prompt.md` Step 10's pattern, applied per-zone instead of per-entity-pair.
- `update(entities: dict, effect_dispatcher)` — for each zone, for each entity, test containment (Step 3); diff against `_inside[zone_id]`; for newly-inside entities call `effect_dispatcher(entity_id, zone.on_enter)`, for newly-outside call `effect_dispatcher(entity_id, zone.on_exit)`; update `_inside[zone_id]` to the new set. `effect_dispatcher` is injected (Step 4's function), not imported directly here — keeps `zone.py` free of dependencies on `Component`/`EventBus`/entity internals, matching `group.py`'s own "just data and membership" scope.
- `to_dict()`/`from_dict()` — same pattern as `GroupRegistry`, for `Area.to_dict()`/`from_dict()` to persist zones in the Area file.

Verify: construct a `ZoneRegistry`, add an `aabb` zone, call `update()` with a fake `entities` dict and a dispatcher that just records calls; confirm enter fires once when an entity's position moves inside, exit fires once when it moves back out, and repeated `update()` calls while stationary fire neither.

---

## Step 3 — Containment Tests ✅

**File:** `backend/engine/zone.py`

1. `contains_point(zone: Zone, x: float, y: float, z: float) -> bool` — dispatches on `zone.shape["type"]`.
2. `aabb`: `shape = {"type": "aabb", "min": [x, y, z], "max": [x, y, z]}` — a plain per-axis min/max compare. This is the "simple two-coordinate square zone" — two corner points, nothing else.
3. `mesh`: `shape = {"type": "mesh", "mesh": "<mesh-asset-key>", "position": [x, y, z], "rotation": [rx, ry, rz], "scale": [sx, sy, sz]}`.
   - At zone-load time (not per-tick): resolve the mesh asset key the same way any backend code resolves an asset path (read the JSON directly via `open()`/`json.load()` — the mesh format is plain project JSON, no GPU/`wgpu` involvement needed here at all, this is pure geometry read on the backend), extract vertex positions, project onto the XZ plane (drop Y), and cache the resulting 2D point list plus the mesh's own min/max Y as `zone._cached_footprint`/`zone._cached_y_range` (computed once, invalidated only if the zone's shape data changes). **Correction, found while verifying (`run_zone_test.py`)**: "the resulting 2D point list" cannot be fed to ray-casting point-in-polygon directly — a mesh's stored vertices come in triangle/face order, not a perimeter walk, so the raw projected list is a self-intersecting, meaningless "polygon." The cached footprint must be the 2D **convex hull** of the projected points (Andrew's monotone chain, hand-rolled, same dependency-free spirit as the point-in-polygon test itself) — documented as an additional, permanent approximation: a concave footprint (an L-shaped room) flattens to its hull, same class of scope boundary as the Y-range check already is.
   - Per-tick test: transform the query point into the mesh's local space (inverse of `position`/`rotation`/`scale`, reusing whatever matrix helper `client/engine/mat4.py`'s *math* is already hand-rolled from — this is backend Python, so re-derive the equivalent small transform functions here rather than importing from `client/`, but do not diverge from its column-major/row convention), then: (a) Y-range check against `_cached_y_range`, (b) 2D point-in-polygon test (ray-casting/even-odd) against `_cached_footprint`.
4. Write the point-in-polygon function as a small, standalone, testable function — not inlined into `contains_point` — so Step 2's verify (and this step's own) can exercise it directly with a hand-built polygon.

Verify: a point clearly inside a simple rectangular mesh footprint returns `True`; a point clearly outside returns `False`; a point exactly on an edge is documented as an accepted ambiguous case (standard point-in-polygon edge-case behaviour, not a bug). Rotating the zone 90° and re-testing the same world-space point flips the expected result correctly (proves the local-space transform, not just the polygon test in isolation).

---

## Step 4 — Effects ✅ (reclassified engine-layer — see note)

**Reclassified during implementation, 2026-08-20**: originally scoped to `backend/game/area.py` ("game-layer, since it touches `Area`'s own `groups`/`entities` and `EventBus`") — but every effect type below only touches generic engine primitives (`GroupRegistry`, `Entity.set_data`/`add_component`, `EventBus`), nothing game-specific. Same reasoning that already reclassified `client/engine/area_viewer.py` (see `area-system.prompt.md`'s branch-reconciliation banner). Implemented instead in **`backend/engine/zone.py`** (alongside `Zone`/`ZoneRegistry`), as `apply_zone_effect(entities, entity_id, effect, groups, event_bus, zone)` — explicit `entities`/`groups`/`event_bus` parameters instead of a full `area` object. A game branch's `Area.update()` calls this exactly like any other engine-layer helper, passing its own `self.entities`/`self.groups`/`self.event_bus`. This unblocked Steps 2–4 to be built and verified on `engine` today (`run_zone_test.py`) — only Step 5's literal `Area.update()` wiring call stays blocked, since `Area` itself doesn't exist here.

**Second correction, also found during implementation**: task 8 below references `zone.zone_id` for the `fire_event` payload, but the dispatcher signature as originally sketched (`apply_zone_effect(area, entity_id, effect)`, and `ZoneRegistry.update()`'s injected callback as `(entity_id, effects)`) never actually receives which zone triggered the effect. Fixed by having `ZoneRegistry.update()`'s injected `effect_dispatcher` receive the `Zone` itself: `effect_dispatcher(zone, entity_id, effects)` — see Step 2's `update()` for the corrected signature.

**File:** `backend/engine/zone.py`

An effect is one dict from a zone's `on_enter`/`on_exit` list. Implemented as `apply_zone_effect(entities, entity_id, effect, groups, event_bus=None, zone=None)`, handling:

1. `{"type": "add_group", "group": "<name>"}` — `groups.add_to_group(entity_id, group_name)`.
2. `{"type": "remove_group", "group": "<name>"}` — `groups.remove_from_group(entity_id, group_name)`.
3. `{"type": "set_group_attribute", "group": "<name>", "key": "...", "value": ...}` — `groups.set_group_attribute(group_name, key, value)` — convenience for a zone that configures a group's shared attribute inline (e.g. an `on_enter` effect that both adds the entity to `"gravity"` and, the first time, sets `"gravity"`'s `strength` attribute).
4. `{"type": "set_data", "key": "...", "value": ...}` — `entity.set_data(key, value)` (the tag-data-bag API, this session's `Entity.get_data`/`set_data`). This is the practical "apply an attribute to entities within" mechanism — deliberately *not* routed through the ECS `Component`/`World` system, per the gap noted in Required Reading.
5. `{"type": "clear_data", "key": "..."}` — removes `key` from the entity's `DataComponent` if present (a small addition to `Entity`/`DataComponent`'s existing API may be needed — a `clear_data`/`remove_data` method that pops the key, following the exact same lazy-get-or-create pattern `get_data`/`set_data` already use; add it there if it doesn't already exist, don't reimplement the lookup here).
6. `{"type": "add_component", "component": {"type": "ComponentClassName", ...}}` — `entity.add_component(Component.from_dict(effect["component"]))`, using the entity-local component store (`Entity.add_component`/`get_component`, round-trips through `to_dict`/`from_dict`). **State explicitly, in a code comment at this branch, that this attaches to the entity's own local store, not `World`'s** — it will not be picked up by any `System` that queries `world.query_with_components(...)`, because of the same `ecs_world` gap. It *is* visible to any code that calls `entity.get_component(SomeType)` directly, and *does* persist/round-trip through save files.
7. `{"type": "remove_component", "component_type": "ComponentClassName"}` — looks the class up via `Component`'s registry (`_COMPONENT_REGISTRY`, already used internally by `Component.from_dict`'s dispatch — confirm whether it's already exposed for lookup by name, or needs a one-line accessor added) and calls `entity._components.pop(...)` or an equivalent public removal method (add `Entity.remove_component(component_type)` if one doesn't already exist, mirroring `add_component`/`get_component`'s existing shape).
8. `{"type": "fire_event", "event": "<name>", "payload": {...}}` — `event_bus.publish(effect["event"], {**effect.get("payload", {}), "entity_id": entity_id, "zone_id": zone.zone_id})`. The generic hook for anything not covered above — `level-editor.prompt.md`'s UI-menu zone-trigger step uses exactly this effect type to fire a `"show_menu"`/`"hide_menu"` event, rather than this task inventing menu-specific effect types it has no business knowing about.
9. Unknown effect `type`: log a warning once per unique unknown type (not per occurrence) and skip — never crash the tick loop on bad/hand-authored data, matching `ScriptMovementSystem`'s own "unknown script_type" handling in `area-system.prompt.md` Step 10.

Verify: each effect type produces the expected, isolated change (group membership changes, tag data changes, a component appears/disappears from the entity's local store, the named event is published with the right payload) and nothing else. An unknown effect type logs once and does not raise.

---

## Step 5 — Wire Into `Area.update()`

**File:** `backend/game/area.py` — **blocked, still**: this file doesn't exist on `engine` (see `area-system.prompt.md`'s branch-reconciliation banner). Everything this step needs from `zone.py` (`ZoneRegistry`, `apply_zone_effect`) is done and verified; only this literal wiring call is pending a game branch.

1. `Area.__init__` gains `self.zones = ZoneRegistry()`, alongside the existing `self.groups`/`self.spatial_grid`.
2. `Area.update(delta_time)`: after the existing per-entity `entity.update(delta_time)` loop (so zones test settled, post-move positions, not mid-integration — same ordering reasoning `area-system.prompt.md` Step 9 established for `PhysicsSystem` running last), call:
   ```python
   self.zones.update(
       self.entities,
       lambda zone, eid, effects: [
           apply_zone_effect(self.entities, eid, e, self.groups, self.event_bus, zone)
           for e in effects
       ],
   )
   ```
   **Corrected call shape** (see Step 4's note): the dispatcher receives `zone` now, not just `(eid, effects)`, and `apply_zone_effect` takes explicit `entities`/`groups`/`event_bus` rather than a full `area` object.
3. `to_dict()`/`from_dict()`: add `"zones": self.zones.to_dict()` / `self.zones = ZoneRegistry.from_dict(data.get("zones", {}))`, mirroring exactly how `self.groups` was wired into these two methods this session.

Verify: an `Area` with one AABB zone and an entity that moves through it (via a few manual `entity.x =`/`update()` calls in a test script) fires the zone's `on_enter`/`on_exit` effects at the right ticks, and the zone (with its effects) round-trips correctly through `to_dict()`/`from_dict()`. **Not run** — needs `Area` to exist; the equivalent wiring shape (`ZoneRegistry.update()` → `apply_zone_effect`, against a plain fake entities dict/`GroupRegistry`/`EventBus` standing in for `Area`) is verified in `run_zone_test.py`'s `test_full_tick_through_dispatcher`.

---

## Step 6 — Documentation ✅

**File:** `docs/graphics/AREA_SYSTEM.md` (extended — `area-system.prompt.md` Step 12 landed first this session, so this is a real extension, not the fallback "Zones-only" file the original text anticipated).

1. Document `Zone`'s two shapes, the effect types (Step 4's list, with an example JSON snippet per type), and the enter/exit de-dup semantics. Done.
2. Document the `ZoneRegistry`-is-driven-from-`Area.update()`-not-`SystemScheduler` decision and *why* (the `ecs_world` gap). Done.
3. Document the mesh-zone containment approximation (2D footprint + Y-range, not true volumetric containment) as an explicit, permanent scope boundary, not a TODO. Done — plus the convex-hull correction found during implementation.

---

## Step 7 — Smoke Test

**Run this session, 2026-08-20, via `run_zone_test.py`** (new, no GPU, no backend server, no game branch — mirrors `run_gametick_test.py`/`run_scene_test.py`'s pattern):

- [x] An AABB zone's `on_enter`/`on_exit` fire exactly once per crossing, never once per tick while inside/outside.
- [x] A mesh-footprint zone correctly includes/excludes points inside/outside an irregular (non-rectangular — a synthetic 10×40 rectangle, since a square footprint is 90°-rotation-invariant and can't demonstrate a flip) footprint, and correctly respects the mesh's Y range. Also verified against the real `mesh-example-crate.json` fixture (translation path).
- [x] `add_group`/`remove_group`/`set_group_attribute` effects produce the expected `GroupRegistry` state.
- [x] `set_data`/`clear_data` effects produce the expected `Entity.get_data()` state.
- [x] `add_component`/`remove_component` effects produce the expected `Entity.get_component()` state, and round-trip through `Entity.to_dict()`/`from_dict()`.
- [x] `fire_event` publishes on the shared `EventBus` with the documented payload shape (`entity_id`/`zone_id` merged onto the effect's own `payload`).
- [x] A zone with an unknown effect type logs once (confirmed by calling it twice and checking the log) and does not crash.
- [ ] An `Area` with zones round-trips through `to_dict()`/`from_dict()` with no data loss — **not run**, `Area` doesn't exist on `engine`. `ZoneRegistry.to_dict()`/`from_dict()` itself is verified directly (not through `Area`).
- [x] No lint/type errors on any modified/new file (`backend/engine/zone.py`, `entity.py`'s/`component.py`'s additions, `run_zone_test.py`).

---

## Success Criteria

- [x] `backend/engine/zone.py` — `Zone`, `ZoneRegistry` (enter/exit de-dup, `to_dict`/`from_dict`), `contains_point` (aabb + mesh dispatch), a standalone point-in-polygon function, a standalone convex-hull function (the correction found during implementation) — all done, verified via `run_zone_test.py`
- [x] `apply_zone_effect` (all 8 effect types from Step 4) — done, in `backend/engine/zone.py` (reclassified engine-layer, see Step 4's note), not `backend/game/area.py`
- [ ] `backend/game/area.py` — `self.zones`, `Area.update()` wired to run zone checks after entity position updates, `to_dict`/`from_dict` persistence — **blocked**, `Area` doesn't exist on `engine`; the exact wiring snippet is documented in `docs/graphics/AREA_SYSTEM.md`'s "Zones' one remaining piece" section for whoever lands it on a game branch
- [x] `ZoneRegistry` is driven from `Area.update()`, **not** registered with `SystemScheduler` — confirmed consistent with `backend/engine/group.py`'s own precedent and documented reasoning (the `ecs_world` gap)
- [x] `docs/graphics/AREA_SYSTEM.md` — Zones section: shapes, effects, the `Area.update()`-not-`System` decision and why, the mesh-zone approximation's documented scope boundary (including the convex-hull addition)
- [x] No third-party geometry dependency added — convex hull (Andrew's monotone chain) and point-in-polygon (ray-casting) both hand-rolled
- [x] Nothing in this task touches `client/`/`frontend/` — backend-only, per the Constraints section (zone *authoring* UI is `level-editor.prompt.md`'s job). `run_zone_test.py` (repo root) reads one existing `frontend/assets/data/mesh/` fixture file for its containment test but adds no `client/`/`frontend/` code.
