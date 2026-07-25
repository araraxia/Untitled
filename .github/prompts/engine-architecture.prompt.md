---
agent: agent
description: Establish the engine–game separation and core Python API surface (Phase 1 of ROADMAP.md).
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

# Task: Engine–Game Separation (Phase 1)

You are restructuring the repository to establish a clean boundary between reusable engine infrastructure and game-specific content. This is Phase 1 of `ROADMAP.md`. Complete all steps in order; verify each step compiles and the application still runs before proceeding to the next.

## Required Reading

Read these files before writing any code:

- `ROADMAP.md` — Phase 1 specification
- `ARCHITECTURE.md` — current file-by-file description
- `backend/app.py` — Flask + SocketIO setup; understand existing imports
- `backend/game_loop.py` — existing tick loop and action queues
- `backend/config.py` — existing constants
- `backend/simulation/` — all files; understand coupling before moving anything
- `backend/__init__.py` — existing package exports
- `main.py` — startup sequence; must not break

## Constraints

- The application must remain runnable via `main.py` and `run_browser.py` at all times. Do not enter a broken state between steps.
- Do not rename or move files unless explicitly instructed. Within each step, complete all moves atomically before updating imports.
- Follow PEP 8. Maximum 79 characters per line in all Python files.
- Do not alter any JavaScript files in this task. Frontend restructure is a separate later task.
- Do not add features. Refactor only.

---

## Step 1 — Audit Current Coupling ✅

Before moving a single file, produce a coupling map. Read every Python file and list:

1. Which modules import which others (draw the dependency graph in comments or as output).
2. Which symbols in `backend/simulation/` are referenced outside `backend/simulation/`.
3. Which game-specific constants live in `backend/config.py` (tick rate, world size, etc.) versus which are engine-level.

Do not create or edit any files in this step. Output your findings as a brief summary and then proceed.

---

## Step 2 — Create Package Skeletons ✅

Create the new directory structure without moving any code yet. Add only `__init__.py` files:

```text
backend/engine/__init__.py
backend/engine/ecs/__init__.py
backend/game/__init__.py
backend/game/entities/__init__.py
backend/game/systems/__init__.py
```

Each `__init__.py` should be empty or contain only a one-line module docstring.

Verify: `python -m py_compile backend/engine/__init__.py` and equivalent for each new file — should produce no output.

---

## Step 3 — Split `config.py` ✅

Separate configuration into two files:

**`backend/engine/config.py`** — engine-level constants only:

```python
# Engine configuration defaults. Override by passing EngineConfig at startup.
TICK_RATE: int = 10            # Simulation ticks per second
HOST: str = '0.0.0.0'
PORT: int = 5000
LOG_DIR: str = 'logs'
```

**`backend/game/config.py`** — game-specific constants:

```python
# Game-specific configuration. Specific to this game's content.
DEF_AREA_WIDTH: int = 1000
DEF_AREA_HEIGHT: int = 1000
SPATIAL_GRID_SIZE: int = 32
```

Update `backend/config.py` to re-export both for backwards compatibility:

```python
from backend.engine.config import *   # noqa: F401,F403
from backend.game.config import *     # noqa: F401,F403
```

This preserves all existing `from backend.config import X` statements without changes. Verify by running `python -c "from backend.config import TICK_RATE, DEF_AREA_WIDTH; print('ok')"`.

---

## Step 4 — Move Spatial Partitioning to Engine ✅

`backend/simulation/spatial.py` is pure-infrastructure; it has no game-specific content.

Tasks:

1. Copy the file to `backend/engine/spatial.py`. Do not delete the original yet.
2. Update the copy's internal imports if any exist.
3. Add to `backend/engine/__init__.py`:
   ```python
   from backend.engine.spatial import SpatialGrid  # noqa: F401
   ```
4. Update `backend/simulation/spatial.py` to re-export from the new location:
   ```python
   # Deprecated location — import from backend.engine.spatial instead.
   from backend.engine.spatial import SpatialGrid  # noqa: F401
   ```
5. Verify no import errors: `python -c "from backend.simulation.spatial import SpatialGrid; print('ok')"` and `python -c "from backend.engine.spatial import SpatialGrid; print('ok')"`.

---

## Step 5 — Move `Entity` Base Class to Engine ECS ✅

`backend/simulation/entity.py` contains the `Entity` base class, which should be engine-level. Game-specific entity types will subclass it.

Tasks:

1. Copy `backend/simulation/entity.py` to `backend/engine/ecs/entity.py`.
2. Update `backend/engine/ecs/__init__.py`:
   ```python
   from backend.engine.ecs.entity import Entity  # noqa: F401
   ```
3. Replace `backend/simulation/entity.py` with a shim:
   ```python
   # Deprecated location — import from backend.engine.ecs instead.
   from backend.engine.ecs.entity import Entity  # noqa: F401
   ```
4. Verify nothing in `backend/simulation/` breaks: run `python -c "from backend.simulation.entity import Entity; print('ok')"`.

---

## Step 6 — Move Game Entities to `backend/game/entities/` ✅

The concrete entity classes (`player.py`, `party.py`, `races.py`) are game content, not engine infrastructure.

Tasks:

1. Copy `backend/simulation/player.py` → `backend/game/entities/player.py`
2. Copy `backend/simulation/party.py` → `backend/game/entities/party.py`
3. Copy `backend/simulation/races.py` → `backend/game/entities/races.py`
4. In each copied file, update imports from `backend.simulation.entity` to `backend.engine.ecs.entity`, and from `backend.config` to `backend.game.config`.
5. Replace each original with a shim (same pattern as Step 5).
6. Update `backend/game/entities/__init__.py`:
   ```python
   from backend.game.entities.player import PlayerCharacter  # noqa: F401
   from backend.game.entities.party import PartyMember, PartyManager  # noqa: F401
   ```
7. Verify: `python -c "from backend.game.entities import PlayerCharacter, PartyMember; print('ok')"`.

---

## Step 7 — Move Game Systems to `backend/game/systems/` ✅

`backend/simulation/systems.py` and `backend/simulation/actions.py` contain game-specific logic.

Tasks:

1. Copy `backend/simulation/systems.py` → `backend/game/systems/systems.py`
2. Copy `backend/simulation/actions.py` → `backend/game/systems/actions.py`
3. Update imports in each copied file to point to `backend.engine.ecs` and `backend.game.entities`.
4. Replace originals with shims.
5. Update `backend/game/systems/__init__.py`:
   ```python
   from backend.game.systems.systems import MovementSystem, AISystem, CombatSystem  # noqa: F401
   from backend.game.systems.actions import MoveAction, AttackAction, UseItemAction  # noqa: F401
   ```
6. Verify: `python -c "from backend.game.systems import MovementSystem; print('ok')"`.

---

## Step 8 — Move `area.py` and `world.py` ✅

`backend/simulation/area.py` and `backend/simulation/world.py` are game-state managers that use game entities. They belong in `backend/game/`.

Tasks:

1. Copy both to `backend/game/area.py` and `backend/game/world.py`.
2. Update imports in each to use the new engine and game namespaces.
3. Replace originals with shims.
4. Verify: `python -c "from backend.game.area import Area; print('ok')"`.

---

## Step 9 — Update `game_loop.py` and `app.py` ✅

`backend/game_loop.py` imports from `backend.simulation.*`. Update all imports to use the new namespaces.

Tasks:

1. Read `backend/game_loop.py` and `backend/app.py` in full.
2. Replace all `from backend.simulation.X import Y` statements with the correct new path (`backend.engine.*` or `backend.game.*`).
3. Verify: `python -c "import backend.game_loop; print('ok')"` and `python -c "import backend.app; print('ok')"`.

---

## Step 10 — Smoke Test ✅

Run the application and confirm it reaches the ready state:

```cmd
python main.py
```

Expected: server starts, WebView opens (or logs "server ready"), no `ImportError` or `ModuleNotFoundError` in the log.

If running headlessly for CI, use:

```cmd
python -c "from backend.app import create_app; app = create_app(); print('app ok')"
```

Also run:

```cmd
python -c "
from backend.engine.ecs import Entity
from backend.engine.spatial import SpatialGrid
from backend.game.entities import PlayerCharacter, PartyMember
from backend.game.systems import MovementSystem, AISystem, CombatSystem
from backend.game.area import Area
from backend.config import TICK_RATE, DEF_AREA_WIDTH
print('all imports ok')
"
```

---

## Step 11 — Remove Shims (Cleanup) ✅

Once the smoke test passes:

1. Delete the original files in `backend/simulation/` that now contain only a shim re-export: `entity.py`, `spatial.py`, `player.py`, `party.py`, `races.py`, `systems.py`, `actions.py`, `area.py`, `world.py`.
2. Do **not** delete `backend/simulation/__init__.py` yet — leave the package in place with an empty init to avoid any path references in logs or configuration.
3. Run the smoke test again to ensure nothing was relying on the shim indirection.

---

## Success Criteria

- [x] `python main.py` starts without errors
- [x] `backend/engine/` contains: `config.py`, `spatial.py`, `ecs/entity.py`
- [x] `backend/game/` contains: `config.py`, `area.py`, `world.py`, `entities/`, `systems/`
- [x] `backend/simulation/` contains only `__init__.py` (empty) and `backgrounds.py`, `new_game.py` (not yet migrated — defer to Phase 3 ECS overhaul)
- [x] `backend/config.py` re-exports both engine and game config symbols
- [x] All original `from backend.simulation.X import Y` statements in `game_loop.py` and `app.py` point to the new namespaces
- [x] No new features introduced; behaviour is identical to pre-refactor
