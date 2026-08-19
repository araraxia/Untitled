# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A general-purpose, genre-agnostic real-time game engine: a native desktop client (GLFW + `wgpu-py` + `imgui-bundle`, `client/engine/`) → Flask/SocketIO backend (Python, `backend/engine/`). The engine renders 2D sprites, 2.5D billboards, and fully 3D textured meshes side by side in the same scene (see `client/engine/entity_renderer.py`) — it is not built around any one genre or dimensionality. The backend simulation loop is architected to scale toward parallelized, multi-threaded entity processing so large numbers of on- and off-screen entities can be simulated without blocking the tick loop (see `backend/engine/ecs/scheduler.py`). See [ARCHITECTURE.md](ARCHITECTURE.md) for structure and [ROADMAP.md](ROADMAP.md) for phased development plan (Phases 0–12).

**Branch model:** this `engine` branch carries engine/tooling code only — no game content, and (see Running, below) no bootable server. Each game lives on its own branch forked from `engine` (e.g. `legacy`, the fantasy-RPG-flavored game previously built here), adding its own `backend/game/`/`client/game/` on top. Branches don't auto-sync — pulling an engine improvement into a game branch is an explicit `git merge engine`/rebase, done deliberately, not automatic. This is a plain-branch relationship, not a submodule/pinned-version one.

An earlier PyWebView + WebGPU/JavaScript frontend (`frontend/js/`, launched via `run_browser.py`/`run_desktop_test.py`) was deleted entirely during the `client/` migration; see `.github/prompts/wgpu-py-migration.prompt.md`.

Each phase has an agent prompt in `.github/prompts/`. When working through a prompt, add completion indicators to headers and update any progress trackers as phases complete. When implementation deviates from the prompt, update the prompt file to reflect the actual changes.

## Running

**This branch alone does not run a game.** `backend/app.py` (the Flask/SocketIO server entry point), `backend/save_manager.py`, `backend/game/`, and `client/game/` all lived on top of the engine and moved to game branches along with the rest of the game they belonged to — `backend/engine/game_loop.py`'s `GameLoop` is only an abstract base (override `_do_tick`), with no concrete engine-layer subclass. To actually run something, check out a game branch (e.g. `git checkout legacy`) and follow its own setup — the game layer there supplies the server entry point, tick loop, and playable content this branch intentionally leaves out.

### Windows or Linux
```cmd
setup.bat   # Create venv + install deps
run.bat     # Launch the native GLFW/wgpu-py/imgui-bundle desktop window (client/main.py) -- requires a game branch's backend/app.py + client/game/ to actually boot
```
On Linux, the equivalent is `python -m venv venv && source venv/bin/activate && pip install -r requirements.txt && python main.py` — no browser, no WebKitGTK; see [docs/DEBIAN_SETUP.md](docs/DEBIAN_SETUP.md) for system packages.

No test framework is configured yet. If adding tests: `pytest backend/` for Python, `pytest client/` (or similar) for the client.

## Code Style

- **Python:** PEP 8, 4-space indent, 79-char line limit, type hints for complex signatures
- **File naming:** `snake_case.py`
- **Markdown tables:** compact style — space between pipes and content in all cells
- **Markdown code blocks:** always specify language; use `text` if nothing applies
- **Python packages:** add to `requirements.txt` with pinned versions; install with `pip install <pkg>==<ver>`

## Architecture

### Engine vs. Game Separation (critical)
```
backend/engine/   ← stable APIs: ECS, spatial grid, game loop, events, save format
client/engine/    ← renderer, input, network, interpolation, asset loader
```
On this branch, that's the whole tree — no `backend/game/`, no `client/game/`, no `backend/app.py`. A game branch adds those back on top, following the same rule that held while the fantasy-RPG game lived here: engine code never imports game content; game code only calls engine APIs; game features go in `backend/game/systems/`/`client/game/`, not `backend/engine/`/`client/engine/`. `legacy` is the reference example — its `backend/game/`/`client/game/` show the expected shape (entities, systems, world, area, character flow / character creation, player select, game UI).

### Simulation (contract for a game branch, not code present here)
- **Tick rate: 20 TPS** (`TICK_DURATION = 0.05s`) — old docs may say 10 TPS, disregard
- A game branch's concrete tick loop subclasses `backend/engine/game_loop.py`'s `GameLoop` (an abstract base — override `_do_tick`); `legacy`'s version (`GameTick` in `backend/game/tick.py`) drains `player_action_queue`/`party_command_queue` each tick, runs the system scheduler, then broadcasts state deltas
- System scheduler (`backend/engine/ecs/scheduler.py`) does topological sort on `System.dependencies` — this part is real, present, engine-layer code

### ECS
- `world.query(ComponentA, ComponentB)` for component queries
- New components: subclass in `backend/engine/ecs/component.py` (or a game branch's own game layer), use `@component` decorator or `ComponentRegistry.register()`
- New systems: extend `System`, implement `update(world, event_bus)`, register in the game branch's concrete `GameLoop` subclass, declare `dependencies`
- Note: as of the `legacy` split, `World`/`Component`/`System` were not yet wired into any branch's live tick loop — a `GameTick`-style subclass created its own `World()` but never populated it. A game branch resuming ECS-system work needs to close that gap, not assume it already works.

### Graphics (WebGPU)
- 60 FPS rendering with position interpolation between ticks
- Material system is JSON-driven; parameter map packs roughness/emission/palette into RGB channels — tool at `tools/pack_param_map.py`
- WGSL shaders compiled per material variant via `client/engine/shader_cache.py`
- Game-specific shaders/materials go in a game branch's `client/game/`; add materials to `frontend/assets/data/materials/*.json`

### Networking (contract for a game branch)
- On player load: `player_loaded` (full world snapshot) — not a literal `initial_state` event; `legacy`'s `backend/app.py`'s `handle_load_game()` is what actually emits it, after player selection, confirmed against the running server (see `.github/prompts/wgpu-py-migration.prompt.md` Step 11/15's network client testing)
- Each tick: `state_update` (delta — only dirty entities, changed fields only)
- Dirty flag is set on entity change; cleared after broadcast

### Save/Load
- Format: `saves/<slot>/world.json`, `area-<id>.json`, `player-<id>.json`
- Each `Component` subclass implements `to_dict()` / `from_dict()`; save files include a version field (`backend/engine/save_format.py`, present on this branch) for migration
- A game branch's save orchestrator (`legacy`'s is `backend/save_manager.py`) ties `World`/`Area`/`PlayerCharacter`-equivalents together; autosave interval is configurable via `autosave_interval_ticks` in `backend/engine/config.py`

### Configuration
- `config/engine.json` → tick rate, host, port, save/log dirs, autosave interval (present on this branch, see `backend/engine/config.py`)
- `config/game.json` → area size, starting world/area, base stats — a game branch's own config; not present here

### Logging
Use `backend/independant_logger.py` Logger class for all backend logging. Logs written to `logs/` directory.
