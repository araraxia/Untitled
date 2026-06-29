# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Real-time simulation game (Rimworld/Dwarf Fortress-style) using PyWebView desktop app → Flask/SocketIO backend (Python) → WebGPU frontend (JavaScript). See [ARCHITECTURE.md](ARCHITECTURE.md) for structure and [ROADMAP.md](ROADMAP.md) for phased development plan (Phases 0–9).

Each phase has an agent prompt in `.github/prompts/`. When working through a prompt, add completion indicators to headers and update any progress trackers as phases complete. When implementation deviates from the prompt, update the prompt file to reflect the actual changes.

## Running

### Windows
```cmd
setup.bat   # Create venv + install deps
run.bat     # Launch PyWebView desktop window
```

### Linux / Development (browser mode)
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python run_browser.py  # Opens http://localhost:5000
```

PyWebView on Linux is deferred (no stable WebGPU in WebKitGTK). Use browser mode for Linux development.

No test framework is configured yet. If adding tests: `pytest backend/` for Python, Jest/Vitest for JS.

## Code Style

- **Python:** PEP 8, 4-space indent, 79-char line limit, type hints for complex signatures
- **JavaScript:** Airbnb style guide, 2-space indent, single quotes, async/await preferred
- **File naming:** `snake_case.py`, `camelCase.js`, lowercase-hyphenated HTML/CSS
- **Markdown tables:** compact style — space between pipes and content in all cells
- **Markdown code blocks:** always specify language; use `text` if nothing applies
- **Python packages:** add to `requirements.txt` with pinned versions; install with `pip install <pkg>==<ver>`

## Architecture

### Engine vs. Game Separation (critical)
```
backend/engine/   ← stable APIs: ECS, spatial grid, game loop, events, save format
backend/game/     ← game content: entities, systems, world, area, character flow
frontend/js/engine/  ← renderer, input, network, interpolation, asset loader
frontend/js/game/    ← character creation, player select, game UI
```
Engine code never imports game content. Game code only calls engine APIs. New game features go in `backend/game/systems/`, not `backend/engine/`.

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
- WGSL shaders compiled per material variant via `frontend/js/engine/sprites/shaderCache.js`
- Game-specific shaders/materials go in `frontend/js/game/`; add materials to `frontend/assets/data/materials/*.json`

### Networking
- On connect: `initial_state` (full world snapshot)
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
