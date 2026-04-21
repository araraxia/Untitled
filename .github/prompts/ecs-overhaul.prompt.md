---
agent: agent
description: Replace the current loose entity class hierarchy with a proper Entity-Component-System that scales to hundreds of entity types and thousands of instances (Phase 3 of ROADMAP.md).
tools:
  - read_file
  - create_file
  - replace_string_in_file
  - multi_replace_string_in_file
  - grep_search
  - file_search
  - get_errors
  - run_in_terminal
---

# Task: ECS Overhaul (Phase 3)

You are replacing the current entity class system with a proper Entity-Component-System (ECS) architecture. This is Phase 3 of `ROADMAP.md`. The goal is a clean, performant data model that game systems operate on uniformly, without the current tight coupling between entity attribute bags and system logic.

Complete all steps in order. Each step must leave the application in a runnable state before proceeding to the next.

## Required Reading

Read these files before writing any code:

- `ROADMAP.md` — Phase 3 specification
- `backend/engine/ecs/entity.py` — current `Entity` class (monolithic attribute bag)
- `backend/engine/ecs/world.py` — current `World` (dict-based registry; query stub only)
- `backend/engine/ecs/system.py` — current `System` base class (entity list + delta_time)
- `backend/engine/ecs/__init__.py` — current ECS exports
- `backend/engine/__init__.py` — current engine-level exports
- `backend/engine/events.py` — existing `EventBus` implementation
- `backend/engine/spatial.py` — existing `SpatialGrid` implementation
- `backend/engine/game_loop.py` — existing `GameLoop` base class
- `backend/game/systems/systems.py` — existing game systems (MovementSystem, AISystem, CombatSystem)
- `backend/game/tick.py` — game tick that drives system execution
- `backend/app.py` — Flask app; wires `GameTick` to SocketIO

## Constraints

- Follow PEP 8 for all Python: 4-space indent, max 79 characters per line.
- Use Python type hints throughout. All new public functions and classes must be fully typed.
- Do not break the existing SocketIO `state_update` event contract — `app.py` and the frontend depend on entity state being emitted in the same format. The `to_dict()` / serialisation shape of entities must not change.
- Do not alter any JavaScript or frontend files in this task.
- Do not add features beyond what is scoped in each step.
- Preserve the existing `EventBus` and `SpatialGrid` — they are already implemented correctly and do not need changes.
- All new classes must have docstrings. Do not add docstrings to functions you did not write or modify.
- Run `python -c "from backend.app import app; print('app ok')"` after each step to confirm no import errors.

---

## Step 1 — Audit Current State ✅

Before writing any code, read the key files listed above. Produce a short summary covering:

1. How the current `Entity` class stores data (attributes as instance variables vs. components).
2. What `World.query()` currently does and what the placeholder comment says about Phase 3.
3. How `System.update()` receives data and what that means for filtering (every system sees every entity).
4. How `GameTick` currently drives systems — does it call `system.update()` directly or through a scheduler?
5. Which game systems (`MovementSystem`, `AISystem`, `CombatSystem`) currently have real implementations vs. placeholders.

Do not create or edit any files in this step. Output your findings and then proceed.

---

## Step 2 — Component Registry (Phase 3.1) ✅

**Files to create/modify:**

- `backend/engine/ecs/component.py` — new file
- `backend/engine/ecs/world.py` — extend with component storage
- `backend/engine/ecs/__init__.py` — export `Component`

### Component base class

Create `backend/engine/ecs/component.py`:

```python
class Component:
    """Base class for all ECS components.

    Every concrete component subclass is assigned a unique integer
    type ID automatically via __init_subclass__.  The ID is stable
    within a process lifetime and used as a storage key.
    """
    _next_id: int = 0
    type_id: int  # set by __init_subclass__

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        cls.type_id = Component._next_id
        Component._next_id += 1
```

Concrete component examples (declare these in `component.py` as well, so systems can import from one place):

| Component            | Fields                                |
| -------------------- | ------------------------------------- |
| `PositionComponent`  | `x: float`, `y: float`, `z: float`    |
| `VelocityComponent`  | `vx: float`, `vy: float`              |
| `StateComponent`     | `state: str`, `facing: str`           |
| `AnimationComponent` | `animation_data_paths: list[str]`     |
| `LightComponent`     | `color: list[float]`, `radius: float` |
| `EmitterComponent`   | `config: dict`                        |

### Tasks:

1. Create `backend/engine/ecs/component.py` with `Component` base and the six concrete component types listed above.
2. Extend `backend/engine/ecs/world.py`:
   - Add `_components: dict[int, dict[str, Component]]` — maps `component type_id → entity_id → component instance`.
   - Add `add_component(entity_id, component)` — registers the component under its `type_id`.
   - Add `remove_component(entity_id, component_type)` — removes the component of that type for the entity.
   - Add `get_component(entity_id, component_type)` — returns the component or `None`.
   - Replace the placeholder `query(*attribute_names)` stub with `query(*component_types)` — returns `list[str]` of entity IDs that possess **all** of the given component types. This is the hot path; keep it O(min-set-size).
3. Update `backend/engine/ecs/__init__.py` to export `Component`.

### Backward compatibility

`World.add()`, `World.get()`, `World.remove()`, and `World.all()` must continue to work unchanged — existing code uses them.

Verify:

```python
python -c "
from backend.engine.ecs.component import PositionComponent
from backend.engine.ecs.world import World
from backend.engine.ecs.entity import Entity

w = World()
e = Entity('e1', x=0.0, y=0.0)
w.add(e)
w.add_component('e1', PositionComponent(x=1.0, y=2.0, z=0.0))
ids = w.query(PositionComponent)
print('query result:', ids)  # expect ['e1']
c = w.get_component('e1', PositionComponent)
print('component:', c.x, c.y)  # expect 1.0 2.0
"
```

---

## Step 3 — World Queries (Phase 3.2) ✅

**Files to modify:**

- `backend/engine/ecs/world.py` — performance pass on `query()`

The `query()` added in Step 2 is correct but may scan all entity IDs. Optimise it by intersecting the sets of entity IDs stored per component type rather than iterating all entities.

### Tasks:

1. Change `_components` storage to `dict[int, set[str]]` for the ID sets (keep separate storage for the component instances: `dict[int, dict[str, Component]]` — both are needed).
2. Update `query(*component_types)` to intersect the ID sets. When called with a single type, return `list(self._component_ids[type_id])`. When called with multiple types, `result = first_set & second_set & ...`; convert to list at the end.
3. Add `query_with_components(*component_types)` — returns `list[tuple[str, tuple[Component, ...]]]`, yielding `(entity_id, (comp_a, comp_b, ...))` tuples for each matching entity. Systems that need both the ID and the component values use this.

Verify:

```python
python -c "
from backend.engine.ecs.component import PositionComponent, VelocityComponent
from backend.engine.ecs.world import World
from backend.engine.ecs.entity import Entity

w = World()
for i in range(3):
    e = Entity(str(i))
    w.add(e)
    w.add_component(str(i), PositionComponent(x=float(i), y=0.0, z=0.0))
    if i < 2:
        w.add_component(str(i), VelocityComponent(vx=1.0, vy=0.0))

ids = w.query(PositionComponent, VelocityComponent)
print('moving entities:', sorted(ids))  # expect ['0', '1']
results = w.query_with_components(PositionComponent)
print('count:', len(results))  # expect 3
"
```

---

## Step 4 — System Scheduler (Phase 3.3) ✅

**New file:** `backend/engine/ecs/scheduler.py`
**Files to modify:** `backend/engine/ecs/__init__.py`, `backend/game/tick.py`

Replace the direct system call in `GameTick._do_tick()` with a `SystemScheduler` that respects declared dependencies.

### `SystemScheduler` design:

```python
class SystemScheduler:
    def register(self, system: System) -> None: ...
    def build(self) -> None: ...          # topological sort; call once after all register()
    def run(self, world: World, delta_time: float) -> None: ...
```

### Updated `System` base class changes:

Extend `backend/engine/ecs/system.py`:

- Add `dependencies: list[type[System]] = []` class variable — systems listed here must run before this one.
- Change `update(entities, delta_time)` signature to `update(world, delta_time)` — systems now receive the `World` and call `world.query()` themselves to filter entities. This eliminates the "every system sees every entity" problem.

### Topological sort:

Use Kahn's algorithm (BFS-based). Raise `RuntimeError` if a cycle is detected.

### Tasks:

1. Update `System.update()` signature: `(self, world: World, delta_time: float) -> None`.
2. Create `backend/engine/ecs/scheduler.py` with `SystemScheduler`.
3. Update `backend/game/systems/systems.py` — rewrite `MovementSystem` and `AISystem` to call `world.query_with_components(...)` instead of iterating a flat entity list.
4. Update `backend/game/tick.py` — replace any direct `system.update(entities, dt)` calls with a `SystemScheduler` instance that holds all registered game systems.
5. Export `SystemScheduler` from `backend/engine/ecs/__init__.py`.

Verify:

```python
python -c "from backend.app import app; print('app ok')"
```

---

## Step 5 — EventBus Integration (Phase 3.4) ✅

**Files to modify:** `backend/game/systems/systems.py`, `backend/game/tick.py`

The `EventBus` already exists at `backend/engine/events.py`. This step wires it into the tick loop and updates systems to publish and subscribe instead of calling each other directly.

### Tasks:

1. Create a single `EventBus` instance in `GameTick.__init__()` and pass it to each system's constructor (or inject it via a method — your choice, but be consistent).
2. Update `MovementSystem` to publish a `'entity_moved'` event with payload `{'id': entity_id, 'x': x, 'y': y}` whenever an entity's position is updated.
3. Update `CombatSystem.resolve_attack()` to publish a `'entity_attacked'` event with payload `{'attacker': attacker_id, 'defender': defender_id}` instead of returning a value.
4. In `GameTick`, subscribe a handler for `'entity_moved'` that updates the `SpatialGrid`.
5. Do not replace the SocketIO `state_update` emit path — that stays in `GameTick` and reads directly from `World.all()`.

Verify:

```python
python -c "
from backend.engine.events import EventBus
bus = EventBus()
received = []
bus.subscribe('entity_moved', lambda p: received.append(p))
bus.publish('entity_moved', {'id': 'e1', 'x': 10.0, 'y': 5.0})
print('received:', received)  # expect [{'id': 'e1', 'x': 10.0, 'y': 5.0}]
"
```

---

## Step 6 — Smoke Test ✅

Run the application and confirm no errors:

```cmd
python -c "from backend.app import app; print('app ok')"
```

Then start the server and confirm a tick completes without exception:

```cmd
python main.py
```

Manual checks:

- [x] `World.add()`, `World.get()`, `World.remove()`, `World.all()` work as before.
- [x] `world.query(PositionComponent, VelocityComponent)` returns only entities with both components.
- [x] `SystemScheduler.run()` calls systems in dependency order (not alphabetical, not registration order).
- [x] `EventBus` delivers `'entity_moved'` events to the spatial grid handler each tick.
- [x] `python -c "from backend.app import app; print('app ok')"` passes cleanly.
- [ ] No existing game behaviour has changed from the player's perspective.

---

## Success Criteria

- [x] `backend/engine/ecs/component.py` — `Component` base class with `type_id`; six concrete component types
- [x] `backend/engine/ecs/world.py` — `add_component`, `remove_component`, `get_component`, `query(*component_types)`, `query_with_components(*component_types)`; existing CRUD methods intact
- [x] `backend/engine/ecs/system.py` — `System.update(world, delta_time)` signature; `dependencies` class variable
- [x] `backend/engine/ecs/scheduler.py` — `SystemScheduler` with topological sort; cycle detection
- [x] `backend/game/systems/systems.py` — `MovementSystem` and `AISystem` use `world.query_with_components()`; `CombatSystem` publishes `EventBus` events
- [x] `backend/game/tick.py` — drives systems through `SystemScheduler`; `EventBus` instance created and passed to systems
- [x] `backend/engine/events.py` — unchanged (already correct)
- [x] `backend/engine/spatial.py` — unchanged (already correct)
- [x] SocketIO `state_update` event payload format unchanged
- [x] No frontend or JavaScript files modified
