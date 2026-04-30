---
agent: agent
description: Implement persistent save/load with clean versioning (Phase 6 of ROADMAP.md). Covers save-file format, Component serialisation, auto-save, and save management UI.
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

# Task: Save / Load / Persistence (Phase 6)

You are implementing the save/load system for this project. This is Phase 6
of `ROADMAP.md`. Phase 3 (ECS Overhaul) is a prerequisite.

Complete all steps in order. Each step must leave the application in a
runnable state before proceeding to the next.

---

## Required Reading

Read these files before writing any code:

- `ROADMAP.md` — Phase 6 specification
- `backend/save_manager.py` — existing `SaveManager`; currently stores
  player data under `frontend/assets/data/player/`. This is the primary
  file to understand before touching persistence code.
- `backend/engine/ecs/component.py` — all `Component` subclasses that
  need `to_dict()` / `from_dict()` implementations
- `backend/engine/ecs/entity.py` — `Entity` class; how components are
  attached and retrieved
- `backend/engine/ecs/world.py` — `World` (ECS world, not the game
  world); understand current entity storage
- `backend/game/world.py` — game `World` class (area registry); already
  has `save_to_file()` / `load_world()` stubs
- `backend/game/area.py` — `Area` class; has `to_dict()` stub, needs
  component-level serialisation
- `backend/game/entities/player.py` — `PlayerCharacter` controller;
  already serialises to JSON; understand the current format before
  changing it
- `backend/game/tick.py` — `GameTick`; tick count is the auto-save clock
- `backend/app.py` — SocketIO event handlers; `save_game` event will be
  added here
- `frontend/js/game/playerSelect.js` — existing load/new-game UI (DOM
  built in JS); the save management screen will extend this
- `config/engine.json` — runtime config; `autosave_interval_ticks` will
  be added here
- `frontend/assets/data/player/player-00000000-0000-0000-0000-000000000001.json`
  — example of the current player JSON on disk

---

## Constraints

- Follow PEP 8 for all Python: 4-space indent, max 79 characters per line.
- Use Python type hints throughout. All new public functions and classes
  must be fully typed.
- All new Python classes must have docstrings. Do not add docstrings to
  existing code you did not touch.
- Follow the Airbnb JavaScript style guide for JS changes: 2-space indent,
  single quotes.
- The new save directory layout (`saves/<slot>/`) must coexist with the
  existing `frontend/assets/data/player/` files during transition — do not
  delete or break existing player data on disk.
- Every serialised file must include a `"save_version"` integer field.
  Start at version `1`. Migration functions must be registered for any
  future version bumps.
- Do not break the existing SocketIO `state_update` event contract.
- Run `python -c "from backend.app import app; print('app ok')"` after
  each step to confirm no import errors.
- Auto-save must be non-blocking: it must run in a background thread and
  never stall the game tick.

---

## Step 1 — Audit Current State ✅

Before writing any code, read the key files listed above and produce a
short summary covering:

1. Where save data currently lives on disk, what files are written, and
   what JSON keys each file contains.
2. Which `Component` subclasses in `component.py` do **not** yet have
   `to_dict()` / `from_dict()` methods, and which (if any) already do.
3. What `Area.to_dict()` currently serialises (entities? components?
   spatial grid?) versus what it will need to serialise.
4. What the current `SaveManager.save_game()` and `load_game()` flows do
   step by step, and where they fall short of a complete round-trip.
5. What SocketIO save/load events (if any) exist in `app.py` today.
6. What the `playerSelect.js` UI currently supports for loading vs. what
   will need to be added.

Do not create or edit any files in this step. Output findings, then
proceed.

---

## Step 2 — Save File Format & Directory Layout (Phase 6.1) ✅

**Files to modify:** `config/engine.json`
**New file:** `backend/engine/save_format.py`

### Directory layout

All save data for a player lives under:

```text
saves/
  <player_id>/
    player.json       — PlayerCharacter controller state
    world.json        — World metadata + tick count
    area-<id>.json    — One file per serialised area
```

`saves/` is at the project root. Do not use `frontend/assets/data/player/`
for new saves; that path is legacy. `SaveManager` must read from both
paths for backward compatibility during load (try `saves/` first, fall
back to legacy path).

### `backend/engine/save_format.py`

```python
"""Save-file format constants and version-migration registry."""
```

Define:

```python
SAVE_VERSION: int = 1

# Maps save_version → callable(data: dict) -> dict
# Each migration upgrades data from version N to N+1.
_MIGRATIONS: dict[int, Callable[[dict], dict]] = {}


def register_migration(from_version: int, fn: Callable[[dict], dict]) -> None:
    """Register a migration function for save_version == from_version."""
    ...


def migrate(data: dict) -> dict:
    """Apply all registered migrations to bring data up to SAVE_VERSION.

    Reads ``data['save_version']``, applies migrations sequentially, and
    returns the updated dict.  Raises ``SaveVersionError`` if the version
    is newer than ``SAVE_VERSION``.
    """
    ...


class SaveVersionError(Exception):
    """Raised when a save file's version is newer than the engine supports."""
```

### `config/engine.json` additions

```json
"autosave_interval_ticks": 300,
"save_dir": "saves"
```

---

## Step 3 — Component Serialisation (Phase 6.2) ✅

**Files to modify:** `backend/engine/ecs/component.py`,
`backend/engine/ecs/entity.py`

### `Component` base class

Add two abstract-like methods to the `Component` base class:

```python
def to_dict(self) -> dict[str, Any]:
    """Serialise this component to a JSON-compatible dict.

    The returned dict must include ``"type"`` set to the component's
    class name (used by ``from_dict`` to reconstruct the correct type).
    """
    ...

@classmethod
def from_dict(cls, data: dict[str, Any]) -> "Component":
    """Reconstruct a component from a serialised dict."""
    ...
```

Implement `to_dict()` / `from_dict()` on **every** concrete `Component`
subclass in `component.py`:

- `PositionComponent`
- `VelocityComponent`
- `StateComponent`
- `AnimationComponent`
- `LightComponent`
- `EmitterComponent`
- `PathComponent`
- `AIComponent`
- `StatsComponent`
- `StatusComponent`
- `ColliderComponent`

Each `to_dict()` must emit `{"type": "<ClassName>", ...fields}`. Each
`from_dict()` must reconstruct the dataclass from those fields.

### Component registry

Add a module-level `_COMPONENT_REGISTRY: dict[str, type[Component]]`
dict and a `register_component` decorator or function that maps class
name → class. Auto-register every concrete subclass via
`__init_subclass__`. `from_dict` on the base class dispatches to the
correct subclass via this registry.

### `Entity` serialisation

Add to `Entity`:

```python
def to_dict(self) -> dict[str, Any]:
    """Serialise the entity and all attached components."""
    ...

@classmethod
def from_dict(cls, data: dict[str, Any]) -> "Entity":
    """Reconstruct an entity and its components from a serialised dict."""
    ...
```

Verify:

```python
python -c "
from backend.engine.ecs.component import PositionComponent, StatsComponent
from backend.engine.ecs.entity import Entity

e = Entity('test-01')
e.add_component(PositionComponent(x=10, y=20))
e.add_component(StatsComponent(hp=50, max_hp=100))
d = e.to_dict()
e2 = Entity.from_dict(d)
pos = e2.get_component(PositionComponent)
assert pos.x == 10 and pos.y == 20, pos
print('entity round-trip ok')
"
```

---

## Step 4 — Area & World Serialisation (Phase 6.2 continued) ✅

**Files to modify:** `backend/game/area.py`, `backend/game/world.py`

### `Area.to_dict()` / `Area.from_dict()`

Extend `Area.to_dict()` to include full entity serialisation:

```python
{
  "save_version": 1,
  "area_id": "...",
  "area_name": "...",
  "width": 1000,
  "height": 1000,
  "entities": [entity.to_dict(), ...]
}
```

Add `Area.from_dict(data: dict) -> "Area"` that reconstructs the area
and calls `Entity.from_dict()` for each entity entry. The spatial grid
must be rebuilt from loaded entity positions.

### `Area.save_to_file()` / `Area.load_area()`

Update `save_to_file(save_dir: Path)` to write to:

```text
saves/<player_id>/area-<area_id>.json
```

Update `load_area(save_dir: Path, area_id: str)` to read from the same
path, run `migrate()` on the loaded data before deserialising, and fall
back to the legacy player data directory if the new path does not exist.

### `World.to_dict()` / `World.save_to_file()` / `World.load_world()`

Extend `World.to_dict()`:

```python
{
  "save_version": 1,
  "world_id": "...",
  "world_name": "...",
  "tick_count": 0
}
```

Apply the same save-dir convention and `migrate()` call on load.

Verify:

```python
python -c "
import tempfile, pathlib, json
from backend.game.area import Area
from backend.engine.ecs.component import PositionComponent

a = Area(area_id='test-area', area_name='Test')
from backend.engine.ecs.entity import Entity
e = Entity('e-001')
e.add_component(PositionComponent(x=5, y=7))
a.add_entity(e)

with tempfile.TemporaryDirectory() as tmp:
    p = pathlib.Path(tmp)
    a.save_to_file(p)
    saved = list(p.glob('*.json'))
    print('saved files:', [f.name for f in saved])
    a2 = Area.load_area(p, 'test-area')
    e2 = a2.entities.get('e-001')
    pos = e2.get_component(PositionComponent)
    assert pos.x == 5 and pos.y == 7
    print('area round-trip ok')
"
```

---

## Step 5 — SaveManager Overhaul (Phase 6.1 + 6.2)

**Files to modify:** `backend/save_manager.py`

Rewrite `SaveManager` to use the new save-dir layout and serialisation
path. Preserve the existing method signatures so `app.py` call sites do
not break.

### `save_game(player, game_loop)`

1. Pause the game loop (already done).
2. Write `saves/<player_id>/player.json` — `player.to_dict()` plus
   `"save_version": SAVE_VERSION`.
3. Write `saves/<player_id>/world.json` — `world.to_dict()`.
4. Write `saves/<player_id>/area-<id>.json` for every loaded area.
5. Resume the game loop.

### `load_game()`

1. Try `saves/<player_id>/player.json`; fall back to legacy path.
2. Run `migrate()` on each loaded dict.
3. Reconstruct `PlayerCharacter`, `World`, and the current `Area`.
4. Return the `GameLoop` (unchanged from current signature).

### `list_saves() -> list[dict]`

New method. Scans `saves/` for subdirectories that contain a
`player.json`. Returns a list of summary dicts:

```python
{
  "player_id": "...",
  "player_name": "...",
  "last_save": "<ISO-8601 timestamp>",  # from player.json
  "tick_count": 0,                       # from world.json if present
}
```

Used by the save management UI.

---

## Step 6 — Auto-Save (Phase 6.3) ✅

**Files to modify:** `backend/game/tick.py`, `backend/app.py`

### `GameTick` auto-save hook

In `GameTick`, after each tick increment, check whether
`tick_count % autosave_interval_ticks == 0`. If so, submit a background
save task via `concurrent.futures.ThreadPoolExecutor` (one worker,
reuse across calls). Do not block the tick thread.

Read `autosave_interval_ticks` from `engine_config` (already loaded in
`app.py`; pass it into `GameTick` or read it from the engine config
module directly). If the value is `0`, auto-save is disabled.

Emit a SocketIO event `autosave_complete` with
`{'tick': tick_count, 'status': 'ok'|'error'}` after the background task
finishes.

### Manual save via SocketIO

Add a `save_game` SocketIO handler in `app.py`:

```python
@socketio.on('save_game')
def handle_save_game():
    """Trigger a manual save for the current player."""
    ...
```

It must run the save synchronously (player is waiting for confirmation)
and emit `save_complete` with `{'status': 'ok'|'error', 'message': '...'}`.

---

## Step 7 — Save Management UI (Phase 6.3) ✅

**Files to modify:** `frontend/js/game/playerSelect.js`

Extend the existing player-select screen to show save-slot metadata and
add a **Delete** button per slot.

### New SocketIO event: `request_save_list`

Add a handler to `app.py`:

```python
@socketio.on('request_save_list')
def handle_request_save_list():
    """Return a list of save-slot summaries."""
    saves = SaveManager.list_saves()
    emit('save_list', {'saves': saves})
```

### UI additions in `playerSelect.js`

- Each save-slot entry in `#player-list` must display:
  `<player_name>` · last saved `<last_save>` · tick `<tick_count>`
- Add a `Delete` button per slot (calls `delete_player` with the
  `player_id`; already wired in `app.py`).
- After deletion, refresh the list by re-emitting `request_save_list`.
- The "New Player" button remains unchanged.

---

## Step 8 — Smoke Tests ✅

Run all checks. All must pass before marking Phase 6 complete.

```cmd
python -c "from backend.app import app; print('app ok')"
```

```cmd
python -c "
from backend.engine.ecs.component import PositionComponent, StatsComponent
from backend.engine.ecs.entity import Entity
e = Entity('t1')
e.add_component(PositionComponent(x=3, y=9))
e.add_component(StatsComponent(hp=42))
e2 = Entity.from_dict(e.to_dict())
pos = e2.get_component(PositionComponent)
assert pos.x == 3 and pos.y == 9
print('component serialisation ok')
"
```

```cmd
python -c "
import tempfile, pathlib
from backend.game.area import Area
from backend.engine.ecs.entity import Entity
from backend.engine.ecs.component import PositionComponent
a = Area(area_id='smoke', area_name='Smoke')
e = Entity('s1')
e.add_component(PositionComponent(x=1, y=2))
a.add_entity(e)
with tempfile.TemporaryDirectory() as tmp:
    p = pathlib.Path(tmp)
    a.save_to_file(p)
    a2 = Area.load_area(p, 'smoke')
    assert a2.entities['s1'].get_component(PositionComponent).x == 1
print('area round-trip ok')
"
```

```cmd
python tools/build_assets.py
```

Manual checks:

- [ ] `python -c "from backend.app import app; print('app ok')"` passes.
- [ ] Entity + component round-trip serialisation passes.
- [ ] Area round-trip serialisation passes.
- [ ] `save_game` SocketIO event writes files to `saves/<player_id>/`.
- [ ] `load_game` reconstructs the area with the correct entity positions.
- [ ] Auto-save fires after N ticks and emits `autosave_complete`.
- [ ] `request_save_list` returns a list with the correct metadata.
- [ ] Delete button in the UI removes the slot and refreshes the list.
- [ ] Legacy `frontend/assets/data/player/` files still load correctly.

---

## Success Criteria

- [ ] `backend/engine/save_format.py` — `SAVE_VERSION`, `migrate()`,
      `SaveVersionError`, `register_migration()`
- [ ] `config/engine.json` — `autosave_interval_ticks` and `save_dir` added
- [ ] `backend/engine/ecs/component.py` — all concrete components have
      `to_dict()` / `from_dict()`; component registry auto-populated
- [ ] `backend/engine/ecs/entity.py` — `to_dict()` / `from_dict()`
- [ ] `backend/game/area.py` — full entity serialisation in `to_dict()`;
      `from_dict()`; `save_to_file()` / `load_area()` use new save dir
- [ ] `backend/game/world.py` — `to_dict()` includes `tick_count`;
      save/load uses new save dir
- [ ] `backend/save_manager.py` — new dir layout; `list_saves()`;
      backward-compatible load fallback
- [ ] `backend/game/tick.py` — auto-save hook; non-blocking background thread
- [ ] `backend/app.py` — `save_game` and `request_save_list` SocketIO handlers;
      `autosave_complete` emission
- [ ] `frontend/js/game/playerSelect.js` — slot metadata display; Delete button;
      list refresh on delete
- [ ] `saves/` directory created on first save
- [ ] No game-layer Python files modified beyond what is listed above
- [ ] SocketIO `state_update` payload unchanged
