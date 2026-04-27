---
agent: agent
description: Replace placeholder system bodies with real implementations for pathfinding, AI behaviour trees, combat, and simple physics (Phase 4 of ROADMAP.md).
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

# Task: Simulation Systems (Phase 4)

You are replacing stub implementations in `backend/game/systems/` with real, working simulation logic. This is Phase 4 of `ROADMAP.md`. The Phase 3 ECS Overhaul is a prerequisite — `World.query()`, `SystemScheduler`, and `EventBus` must already be in place before starting this task.

Complete all steps in order. Each step must leave the application in a runnable state before proceeding to the next.

## Required Reading

Read these files before writing any code:

- `ROADMAP.md` — Phase 4 specification
- `backend/engine/ecs/world.py` — `World` with `query()` and `query_with_components()`
- `backend/engine/ecs/component.py` — existing component types (`PositionComponent`, `VelocityComponent`, `StateComponent`, etc.)
- `backend/engine/ecs/system.py` — `System` base class with `update(world, delta_time)`
- `backend/engine/ecs/scheduler.py` — `SystemScheduler`
- `backend/engine/events.py` — `EventBus`
- `backend/engine/spatial.py` — `SpatialGrid`
- `backend/game/systems/systems.py` — current stub systems (`MovementSystem`, `AISystem`, `CombatSystem`)
- `backend/game/tick.py` — how systems are registered and driven per tick
- `backend/engine/config.py` — `EngineConfig` (tick rate, world size, grid cell size)
- `backend/game/config.py` — `GameConfig` (race definitions, base stats)
- `config/engine.json` — runtime engine configuration values
- `config/game.json` — runtime game configuration values

## Constraints

- Follow PEP 8 for all Python: 4-space indent, max 79 characters per line.
- Use Python type hints throughout. All new public functions and classes must be fully typed.
- Do not break the existing SocketIO `state_update` event contract — the payload shape emitted by `GameTick` must not change.
- Do not alter any JavaScript or frontend files in this task.
- Do not add features beyond what is scoped in each step.
- All new classes must have docstrings. Do not add docstrings to existing code you did not touch.
- Prefer composition over inheritance for behaviour tree nodes.
- Run `python -c "from backend.app import app; print('app ok')"` after each step to confirm no import errors.

---

## Step 1 — Audit Current State ✅

Before writing any code, read the key files listed above. Produce a short summary covering:

1. Which methods in `MovementSystem`, `AISystem`, and `CombatSystem` are stubs (pass / raise NotImplementedError / print-only).
2. What data is currently stored on entities vs. what will need to be stored as `Component` subclasses after Phase 3.
3. How `SpatialGrid` currently stores and queries entity positions, and how its cell size is configured.
4. What events (if any) are already published to `EventBus` vs. what still uses direct method calls or print statements.
5. Which component types from `component.py` will be needed for pathfinding, combat, and physics, and which are missing.

Do not create or edit any files in this step. Output your findings and then proceed.

---

## Step 2 — New Component Types (Phase 4 prerequisite) ✅

**Files to modify:** `backend/engine/ecs/component.py`, `backend/engine/ecs/__init__.py`

Several new component types are needed across all four sub-systems. Declare them all here before implementing the systems themselves.

### New components to add to `component.py`:

| Component           | Fields                                                                                                                  |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `PathComponent`     | `waypoints: list[tuple[float, float]]`, `current_index: int`                                                            |
| `AIComponent`       | `behaviour_tree_id: str`, `active_node_path: list[str]`                                                                 |
| `StatsComponent`    | `max_hp: int`, `hp: int`, `attack: int`, `defence: int`, `action_points: int`, `max_action_points: int`, `speed: float` |
| `StatusComponent`   | `effects: list[dict]` — each effect dict: `{'type': str, 'duration': int, 'magnitude': float}`                          |
| `ColliderComponent` | `width: float`, `height: float`, `solid: bool`                                                                          |
| `FactionComponent`  | `faction: str`                                                                                                          |

### Tasks:

1. Add the six components above to `backend/engine/ecs/component.py`.
2. Export them from `backend/engine/ecs/__init__.py`.

Verify:

```python
python -c "
from backend.engine.ecs.component import (
    PathComponent, AIComponent, StatsComponent,
    StatusComponent, ColliderComponent, FactionComponent
)
print('components ok')
"
```

---

## Step 3 — Pathfinding (Phase 4.1) ✅

**New file:** `backend/engine/pathfinding.py`
**Files to modify:** `backend/game/systems/systems.py`, `backend/game/tick.py`

### Implementation

Create `backend/engine/pathfinding.py` containing a standalone `astar` function and a `FlowField` class.

#### `astar(grid, start, goal, cell_size)`

```python
def astar(
    grid: SpatialGrid,
    start: tuple[float, float],
    goal: tuple[float, float],
    cell_size: float,
) -> list[tuple[float, float]]:
    """Return a list of world-space waypoint coordinates from start to
    goal using A* over the spatial grid.  Returns an empty list if no
    path exists.  Heuristic: Chebyshev distance for 8-directional
    movement.
    """
```

- Convert world coordinates to grid cell indices for the open/closed sets.
- 8-directional neighbours; cardinal cost = 1.0, diagonal cost = 1.414.
- A cell is blocked if `grid.query_cell(cx, cy)` returns any entity with a `ColliderComponent` where `solid=True`.
- Reconstruct the path and convert cell centres back to world coordinates.
- Return waypoints as `list[tuple[float, float]]`.

#### `FlowField`

```python
class FlowField:
    """Pre-computed movement vectors for a single goal cell.

    Useful when many entities share the same destination (e.g. a party
    all moving to the same target tile).  Each cell stores the
    normalised direction vector toward the goal.
    """

    def __init__(
        self,
        grid: SpatialGrid,
        goal: tuple[float, float],
        cell_size: float,
    ) -> None: ...

    def direction_at(
        self, world_x: float, world_y: float
    ) -> tuple[float, float]: ...
```

- Build via BFS from goal outward (Dijkstra-style, ignoring diagonal cost differences).
- `direction_at(wx, wy)` returns the pre-computed normalised vector for the cell containing that world position, or `(0.0, 0.0)` if outside the grid.

### Path cache

```python
class PathCache:
    """LRU cache mapping (start_cell, goal_cell) -> waypoint list.

    Invalidated automatically when an entity with a solid
    ColliderComponent is added to or removed from a grid cell that
    falls on an existing cached path.
    """

    def __init__(self, capacity: int = 256) -> None: ...
    def get(self, start, goal) -> list[tuple[float, float]] | None: ...
    def put(self, start, goal, path) -> None: ...
    def invalidate_near(self, cell: tuple[int, int]) -> None: ...
```

Use `collections.OrderedDict` for O(1) LRU eviction.

### `PathfindingSystem`

Add a new `PathfindingSystem` to `backend/game/systems/systems.py`:

- Query: `world.query_with_components(PositionComponent, PathComponent)`
- Each tick: advance entities along their `PathComponent.waypoints` using their `StatsComponent.speed` (if present) or a default speed. Update `PositionComponent` and `SpatialGrid`.
- When all waypoints are consumed, remove the `PathComponent` from the entity.
- Register `PathfindingSystem` in `backend/game/tick.py` with no dependencies (it only reads/writes `PositionComponent` and `PathComponent`).

Verify:

```python
python -c "
from backend.engine.pathfinding import astar
from backend.engine.spatial import SpatialGrid
g = SpatialGrid(cell_size=1.0)
path = astar(g, (0.0, 0.0), (3.0, 3.0), 1.0)
print('path length:', len(path))   # expect > 0
print('first waypoint:', path[0])
print('last waypoint:', path[-1])
"
```

---

## Step 4 — AI / Behaviour Trees (Phase 4.2) ✅

**New file:** `backend/engine/behaviour_tree.py`
**Files to modify:** `backend/game/systems/systems.py`, `backend/game/tick.py`, `config/game.json`

### Core classes in `backend/engine/behaviour_tree.py`

#### Node status

```python
from enum import Enum, auto

class NodeStatus(Enum):
    SUCCESS = auto()
    FAILURE = auto()
    RUNNING = auto()
```

#### Base node

```python
class BehaviourNode:
    """Abstract base for all behaviour tree nodes."""

    name: str

    def tick(self, entity_id: str, world: World, bus: EventBus) -> NodeStatus:
        raise NotImplementedError
```

#### Composite nodes

| Class      | Behaviour                                                                                 |
| ---------- | ----------------------------------------------------------------------------------------- |
| `Sequence` | Tick children left-to-right; return `FAILURE` on first failure, `SUCCESS` if all succeed  |
| `Selector` | Tick children left-to-right; return `SUCCESS` on first success, `FAILURE` if all fail     |
| `Parallel` | Tick all children every frame; return `SUCCESS` when a configurable minimum count succeed |

#### Leaf nodes

| Class     | Behaviour                                                                                                                       |
| --------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `Idle`    | Always returns `SUCCESS`; publishes no events                                                                                   |
| `Seek`    | Sets a `PathComponent` toward the nearest enemy faction entity; returns `RUNNING` until in range                                |
| `Flee`    | Sets a `PathComponent` away from the nearest threat; returns `RUNNING` until safe distance                                      |
| `Attack`  | If target is in range and entity has action points, publishes a `'combat_action'` event; returns `SUCCESS`; otherwise `FAILURE` |
| `UseItem` | Placeholder; returns `SUCCESS` immediately with a log message                                                                   |

#### `BehaviourTree`

```python
class BehaviourTree:
    """Wraps a root BehaviourNode and drives it each tick."""

    def __init__(self, tree_id: str, root: BehaviourNode) -> None: ...

    def tick(
        self, entity_id: str, world: World, bus: EventBus
    ) -> NodeStatus: ...
```

### Tree loader

Add a `BehaviourTreeLoader` class to `behaviour_tree.py`:

```python
class BehaviourTreeLoader:
    """Loads behaviour tree definitions from JSON and returns
    BehaviourTree instances.

    JSON format (stored under config/game.json key 'behaviour_trees'):

    {
      "tree_id": {
        "type": "Sequence",
        "children": [
          {"type": "Seek"},
          {"type": "Attack"}
        ]
      }
    }
    """

    def load(self, tree_def: dict) -> BehaviourTree: ...
```

Add a `"behaviour_trees"` key to `config/game.json` with at least one tree definition: `"default_enemy"` using a `Selector` root with `Seek` and `Idle` children.

### `AISystem` rewrite

Replace the stub `AISystem` in `backend/game/systems/systems.py`:

- Query: `world.query_with_components(AIComponent, PositionComponent)`
- Each tick: look up the entity's `AIComponent.behaviour_tree_id`; retrieve or instantiate the corresponding `BehaviourTree`; call `tree.tick(entity_id, world, bus)`.
- Cache instantiated trees by ID in `AISystem.__init__()` to avoid re-parsing JSON every tick.
- Declare `dependencies = [PathfindingSystem]`.

Register the updated `AISystem` in `backend/game/tick.py`.

Verify:

```python
python -c "
from backend.engine.behaviour_tree import (
    BehaviourTree, Sequence, Seek, Idle, NodeStatus
)
print('behaviour_tree imports ok')
"
```

---

## Step 5 — Combat System (Phase 4.3) ✅

**Files to modify:** `backend/game/systems/systems.py`, `backend/game/tick.py`

Replace the stub `CombatSystem` with a real implementation. Combat is **turn-based resolution inside the real-time simulation**: entities accumulate action points each tick and spend them to perform actions.

### Action point accumulation

In `CombatSystem.update()`, iterate all entities with `StatsComponent`:

```python
entity.stats.action_points = min(
    entity.stats.action_points + entity.stats.speed,
    entity.stats.max_action_points,
)
```

Speed is a float (e.g. `1.0` = 1 AP per tick at base tick rate).

### `'combat_action'` event handler

Subscribe to the `'combat_action'` event published by the `Attack` leaf node. The payload is:

```python
{'attacker': str, 'target': str, 'action': str}
```

Where `action` is one of `'attack'`, `'flee'` (for future expansion).

For `action == 'attack'`:

1. Verify attacker has enough action points (cost = 10); if not, ignore.
2. Deduct 10 AP from attacker.
3. Compute hit chance: `hit_chance = 0.65 + (attacker.attack - target.defence) * 0.05`, clamped to `[0.05, 0.95]`.
4. Roll `random.random()`; if less than `hit_chance`, it is a hit.
5. On hit: `damage = max(1, attacker.attack - target.defence // 2)`; apply to `target.hp`.
6. Publish `'combat_result'` event: `{'attacker': id, 'target': id, 'hit': bool, 'damage': int, 'target_hp': int}`.
7. If `target.hp <= 0`, publish `'entity_died'` event: `{'entity_id': target_id}`.

### Status effect processing

Each tick, iterate all entities with `StatusComponent.effects`:

- Decrement `duration` by 1 for each active effect.
- For `type == 'poisoned'`: apply `magnitude` damage to `StatsComponent.hp`.
- For `type == 'stunned'`: set `action_points = 0`.
- Remove effects with `duration <= 0`.

### `CombatSystem` dependencies

Declare `dependencies = [AISystem]`.

Verify:

```python
python -c "
from backend.engine.ecs.component import StatsComponent, StatusComponent
s = StatsComponent(
    max_hp=100, hp=100, attack=10, defence=5,
    action_points=0, max_action_points=100, speed=1.0,
)
print('StatsComponent ok:', s.hp, s.attack)
"
```

---

## Step 6 — Simple Physics (Phase 4.4) ✅

**New file:** `backend/engine/physics.py`
**Files to modify:** `backend/game/systems/systems.py`, `backend/game/tick.py`

### AABB collision response

Create `backend/engine/physics.py`:

```python
def aabb_overlap(
    ax: float, ay: float, aw: float, ah: float,
    bx: float, by: float, bw: float, bh: float,
) -> tuple[float, float] | None:
    """Return the minimum translation vector (dx, dy) needed to push
    A out of B, or None if they do not overlap.  Positions are the
    top-left corner of each box.
    """
```

### `PhysicsSystem`

Add `PhysicsSystem` to `backend/game/systems/systems.py`. This runs **before** `PathfindingSystem` (declare `dependencies = []`; `PathfindingSystem` declares no dependency on `PhysicsSystem`, letting the scheduler order them fairly — see note below).

- Query: `world.query_with_components(PositionComponent, VelocityComponent, ColliderComponent)`
- Each tick:
  1. Integrate position: `pos.x += vel.vx * delta_time`; `pos.y += vel.vy * delta_time`.
  2. Apply velocity damping: `vel.vx *= 0.85`; `vel.vy *= 0.85`. Zero out velocity components below `0.001`.
  3. Resolve collisions against all **solid** entities by calling `aabb_overlap`. On overlap, translate the moving entity by the MTV and zero out the velocity component in the direction of the overlap.
  4. Update `SpatialGrid` position after integration.

> **Scheduler note:** Add `PhysicsSystem` to `PathfindingSystem.dependencies` so physics resolves first.

### Terrain friction

Before damping, check if the entity's cell in `SpatialGrid` contains a terrain tile with a `friction` coefficient. If so, apply `vel *= (1.0 - friction * delta_time)` instead of the default `0.85` multiplier. Terrain tiles are out of scope for this phase — stub with a `get_terrain_friction(grid, x, y) -> float` helper that always returns `0.0` for now.

Verify:

```python
python -c "
from backend.engine.physics import aabb_overlap
mtv = aabb_overlap(0.0, 0.0, 2.0, 2.0, 1.0, 1.0, 2.0, 2.0)
print('mtv:', mtv)   # expect a non-None tuple
no_overlap = aabb_overlap(0.0, 0.0, 1.0, 1.0, 5.0, 5.0, 1.0, 1.0)
print('no overlap:', no_overlap)  # expect None
"
```

---

## Step 7 — Smoke Test

Run the full import check and then launch the server:

```cmd
python -c "from backend.app import app; print('app ok')"
```

Then start the backend and confirm at least one game tick completes without exception:

```cmd
python main.py
```

Manual checks:

- [ ] `PathfindingSystem` advances entities along waypoints without errors.
- [ ] `AISystem` ticks behaviour trees; `default_enemy` tree is loaded from `config/game.json`.
- [ ] `CombatSystem` accumulates action points and resolves `'combat_action'` events.
- [ ] `PhysicsSystem` integrates velocity and resolves AABB collisions without crashing.
- [ ] `'combat_result'` and `'entity_died'` events appear in logs when combat occurs.
- [ ] `'entity_moved'` events continue to update `SpatialGrid` as before.
- [ ] SocketIO `state_update` payload shape is unchanged.
- [ ] `python -c "from backend.app import app; print('app ok')"` passes cleanly.

---

## Success Criteria

- [ ] `backend/engine/pathfinding.py` — `astar()`, `FlowField`, `PathCache`
- [ ] `backend/engine/behaviour_tree.py` — `NodeStatus`, `BehaviourNode`, `Sequence`, `Selector`, `Parallel`, `Idle`, `Seek`, `Flee`, `Attack`, `UseItem`, `BehaviourTree`, `BehaviourTreeLoader`
- [ ] `backend/engine/physics.py` — `aabb_overlap()`, `get_terrain_friction()`
- [ ] `backend/engine/ecs/component.py` — six new component types added: `PathComponent`, `AIComponent`, `StatsComponent`, `StatusComponent`, `ColliderComponent`, `FactionComponent`
- [ ] `backend/game/systems/systems.py` — `PathfindingSystem`, `AISystem`, `CombatSystem`, `PhysicsSystem` all fully implemented with correct `world.query_with_components()` usage and `EventBus` publishing
- [ ] `backend/game/tick.py` — all four systems registered in `SystemScheduler`; `EventBus` handlers subscribed for `'combat_action'`, `'combat_result'`, `'entity_died'`
- [ ] `config/game.json` — `"behaviour_trees"` key present with at least a `"default_enemy"` definition
- [ ] SocketIO `state_update` event payload format unchanged
- [ ] No frontend or JavaScript files modified
