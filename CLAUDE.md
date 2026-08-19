# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A general-purpose, genre-agnostic real-time game engine: a native desktop client (GLFW + `wgpu-py` + `imgui-bundle`, `client/`) → Flask/SocketIO backend (Python, `backend/`). The engine renders 2D sprites, 2.5D billboards, and fully 3D textured meshes side by side in the same scene (see `client/engine/entity_renderer.py`) — it is not built around any one genre or dimensionality. The backend simulation loop is architected to scale toward parallelized, multi-threaded entity processing so large numbers of on- and off-screen entities can be simulated without blocking the tick loop (see `backend/engine/ecs/scheduler.py`). See [ARCHITECTURE.md](ARCHITECTURE.md) for structure and [ROADMAP.md](ROADMAP.md) for phased development plan (Phases 0–12).

An earlier PyWebView + WebGPU/JavaScript frontend (`frontend/js/`, launched via `run_browser.py`/`run_desktop_test.py`) has been deleted entirely — superseded by `client/`. See `.github/prompts/wgpu-py-migration.prompt.md` for the migration. All engine/game work goes in `client/engine/`/`client/game/`.

Each phase has an agent prompt in `.github/prompts/`. When working through a prompt, add completion indicators to headers and update any progress trackers as phases complete. When implementation deviates from the prompt, update the prompt file to reflect the actual changes.

## Running

### Windows or Linux
```cmd
setup.bat   # Create venv + install deps
run.bat     # Launch the native GLFW/wgpu-py/imgui-bundle desktop window (client/main.py)
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
backend/game/     ← game content: entities, systems, world, area, character flow
client/engine/    ← renderer, input, network, interpolation, asset loader
client/game/      ← character creation, player select, game UI (imgui-bundle)
```
Engine code never imports game content. Game code only calls engine APIs. New game features go in `backend/game/systems/`/`client/game/`, not `backend/engine/`/`client/engine/`.

### Simulation
- **Tick rate: 20 TPS** (`TICK_DURATION = 0.05s`) — old docs may say 10 TPS, disregard
- `GameTick` (`backend/game/tick.py`) extends `GameLoop`; drains `player_action_queue` and `party_command_queue` each tick, runs the system scheduler, then broadcasts state deltas
- System scheduler (`backend/engine/ecs/scheduler.py`) does topological sort on `System.dependencies`

### ECS
- `world.query(ComponentA, ComponentB)` for component queries
- New components: subclass in `backend/engine/ecs/component.py` (or game layer), use `@component` decorator or `ComponentRegistry.register()`
- New systems: extend `System`, implement `update(world, event_bus)`, register in `GameTick.__init__()`, declare `dependencies`

### Graphics (WebGPU)
- 60 FPS rendering with position interpolation between ticks
- Material system is JSON-driven; parameter map packs roughness/emission/palette into RGB channels — tool at `tools/pack_param_map.py`
- WGSL shaders compiled per material variant via `client/engine/shader_cache.py`
- Game-specific shaders/materials go in `client/game/`; add materials to `frontend/assets/data/materials/*.json`

### Networking
- On player load: `player_loaded` (full world snapshot) — not a literal `initial_state` event; `backend/app.py`'s `handle_load_game()` is what actually emits it, after player selection, confirmed against the running server (see `.github/prompts/wgpu-py-migration.prompt.md` Step 11/15's network client testing)
- Each tick: `state_update` (delta — only dirty entities, changed fields only)
- Dirty flag is set on entity change; cleared after broadcast

### Save/Load
- Format: `saves/<slot>/world.json`, `area-<id>.json`, `player-<id>.json`
- Each `Component` subclass implements `to_dict()` / `from_dict()`; save files include version field for migration
- Autosave: every 300 ticks (configurable via `autosave_interval_ticks` in `backend/engine/config.py`)

### Configuration
- `config/engine.json` → tick rate, host, port, save/log dirs, autosave interval
- `config/game.json` → area size, starting world/area, base stats
- Both fall back to defaults if absent; see `backend/engine/config.py` and `backend/game/config.py`

### Logging
Use `backend/independant_logger.py` Logger class for all backend logging. Logs written to `logs/` directory.
