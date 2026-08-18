# Architecture

## Overview

This repository is a general-purpose, genre-agnostic real-time game engine, not a single game. It ships as a standalone desktop application (PyWebView) with a Python simulation backend and a WebGPU-accelerated JavaScript frontend. The rendering path supports 2D sprites, 2.5D camera-facing billboards, and fully modeled 3D meshes side by side in the same scene — an entity's dimensionality is a per-entity data choice, not an engine-wide assumption. The backend simulation is a fixed-timestep tick loop built on an ECS (entity-component-system) with a dependency-ordered system scheduler, structured so independent systems can scale toward parallel/multi-threaded execution as entity counts grow, rather than assuming a small, hand-authored cast of on-screen actors.

A game built on top of the engine (currently the in-repo example content under `backend/game/` and `frontend/js/game/`) is one consumer of that API surface, not the definition of what the engine is for.

---

## Three-Layer Architecture

1. **Desktop Application Layer** (`main.py`) — launches the Flask/SocketIO server in a background thread, waits for a health check, then opens a PyWebView window pointing at it. `run_browser.py` is the Linux/dev alternative: it starts the same server and opens a normal browser tab instead of a native window (PyWebView's WebKitGTK backend doesn't yet have stable WebGPU).
2. **Backend Simulation Layer** (`backend/`) — Python, Flask + SocketIO, fixed-timestep ECS tick loop. Authoritative for all gameplay state.
3. **Frontend Rendering Layer** (`frontend/`) — JavaScript, WebGPU (with a Canvas 2D fallback path). Renders interpolated state received from the backend; never authoritative for gameplay.

```text
┌─────────────────────────────────────────┐
│  GAME LAYER  (content, rules, world)    │
├─────────────────────────────────────────┤
│  ENGINE API  (stable, versioned)        │
├──────────────┬──────────────────────────┤
│  Simulation  │  Rendering               │
│  (Python)    │  (JavaScript / WebGPU)   │
└──────────────┴──────────────────────────┘
```

---

## Engine vs. Game Separation (critical)

```text
backend/engine/      ← stable APIs: ECS, spatial grid, game loop, events, save format, physics, pathfinding, procgen
backend/game/         ← game content: entities, systems, world, area, character flow
frontend/js/engine/   ← renderer, input, network, interpolation, asset loader, 2D/3D draw paths
frontend/js/game/     ← character creation, player select, game-specific UI
```

Engine code never imports game content. Game code only calls engine APIs. New reusable capability goes in the engine layer; new game-specific behavior goes in the game layer — see `backend/game/systems/` for the pattern on the backend side.

---

## Backend (`backend/`)

### Engine infrastructure (`backend/engine/`)

| File | Purpose |
| --- | --- |
| `game_loop.py` (`loop.py` re-exports it) | `GameLoop` — fixed-timestep tick scheduling, runs in a daemon background thread, `start()`/`stop()`/`pause()`/`resume()` |
| `config.py` | `EngineConfig` — tick rate, host, port, save/log dirs, autosave interval; loaded from `config/engine.json`, falls back to defaults |
| `events.py` | `EventBus` — decoupled system-to-system communication |
| `ecs/entity.py` | `Entity` base class — id, position, dirty-flag, `serialize()`/`to_dict()`/`from_dict()` |
| `ecs/component.py` | `Component` base class + registry/decorator for defining new component types |
| `ecs/world.py` | `World` — entity registry with O(1) component-based queries (`world.query(ComponentA, ComponentB)`) |
| `ecs/scheduler.py` | `SystemScheduler` — Kahn's-algorithm topological sort over `System.dependencies`, runs systems in dependency order each tick. This dependency graph is also what makes independent systems safe to parallelize later — see "Scaling" below |
| `ecs/system.py` | `System` base class — `update(world, event_bus)`, declares `dependencies` |
| `spatial.py` | `SpatialGrid` — grid-based spatial partitioning for neighbor/radius queries |
| `physics.py` | Authoritative backend physics — the *only* code allowed to be called "physics" in this repo, see `.github/copilot-instructions.md` |
| `pathfinding.py` | A*-style pathfinding over the world/area grid |
| `behaviour_tree.py` | Behaviour-tree primitives for AI-driven entities |
| `procgen/wfc.py` | Wave-function-collapse procedural generation |
| `save_format.py` | Versioned save/load helpers shared by every `Component` |
| `hot_reload.py` | Dev-time hot reload support |

### Game content (`backend/game/`)

| File | Purpose |
| --- | --- |
| `tick.py` | `GameTick(GameLoop)` — drains `player_action_queue`/`party_command_queue`, runs the `SystemScheduler` against the shared `ecs_world`, broadcasts state deltas over SocketIO, background autosave via a single-worker `ThreadPoolExecutor` |
| `world.py` | `World` state manager — area registry, player tracking |
| `area.py` | `Area` (chunk) management |
| `config.py` | `GameConfig` — starting world/area, base stats; loaded from `config/game.json` |
| `entities/player.py`, `entities/party.py`, `entities/races.py` | Player character, party members/AI, race data — **not** `Entity` subclasses uniformly; see each file for its own serialization path |
| `systems/systems.py` | `MovementSystem`, `PhysicsSystem`, `PathfindingSystem`, `AISystem`, `CombatSystem` — the registered ECS systems for this example game |
| `systems/actions.py` | Command-pattern player/party actions |
| `character_flow_service.py`, `new_game.py`, `backgrounds.py` | Character creation flow |

### Networking

- `backend/app.py` — Flask app + `SocketIO(..., async_mode="threading")`; serves `frontend/` as static content and the SocketIO endpoint
- On connect: server emits `initial_state` (full world snapshot)
- Each tick: server emits `state_update` (delta — only dirty entities, only changed fields)
- Client → server: `player_action`, `party_command` (queued, drained on the next tick)
- Dirty flag set on entity change, cleared after broadcast

### Save/Load

- Format: `saves/<slot>/world.json`, `area-<id>.json`, `player-<id>.json`
- Each `Component` subclass implements `to_dict()`/`from_dict()`; save files carry a version field for migration
- Autosave every `autosave_interval_ticks` (default 300, `backend/engine/config.py`), run off the tick thread via a background executor so it never stalls simulation

---

## Frontend (`frontend/`)

### Engine (`frontend/js/engine/`)

| File | Purpose |
| --- | --- |
| `renderer.js` | Render loop coordinator — camera/view-projection matrix, depth texture, dispatches per-entity draws |
| `entityRenderer.js` | Per-entity draw path. Routes each entity, per-frame, to one of: 2D sprite atlas (Canvas 2D or base WebGPU pipeline), 3D camera-facing billboard (depth-tested sprite), or 3D textured mesh (`render_template` → mesh + material). All three coexist in the same scene |
| `mat4.js` | Dependency-free column-major 4×4 matrix helpers (`perspective`, `lookAt`, `compose`, `rotationXYZ`, …) |
| `mesh.js` | `Mesh` — loads this project's interleaved-vertex-buffer mesh JSON format and uploads GPU vertex/index buffers |
| `assetLoader.js` | Maps short asset keys to server-relative paths; manifest-driven registration |
| `sprites/` | `shaderCache.js` (WGSL pipeline compilation/caching for both sprite and mesh variants), `materialLoader.js` (JSON-driven material → `GPUBindGroup`), `gpuSpriteSheet.js`, `gpuBuffers.js`, `animation.js`, `particleSystem.js`, `lightingPass.js` |
| `network.js` | SocketIO client abstraction |
| `interpolation.js` | 20 TPS simulation → 60 FPS render interpolation |
| `input.js` | Input event stream + game-context routing |

### Game (`frontend/js/game/`)

`main.js`, `ui.js`, `characterCreation.js`, `playerSelect.js`, `characterFlow/` — the example game's UI and flow, built entirely on the engine API above. New games built on this engine would replace this directory without touching `frontend/js/engine/`.

### Data-driven content (`frontend/assets/data/`)

Animation clips, materials, entity definitions, and (for 3D) mesh JSON all live here as plain JSON, resolved through `AssetLoader` at runtime rather than hardcoded paths. See `docs/graphics/DATA_STRUCTURES.md` for the schemas.

---

## Simulation

- Tick rate: 20 TPS (`TICK_DURATION = 0.05s` in `backend/engine/config.py`)
- Render rate: 60 FPS, decoupled from tick rate via client-side interpolation
- Fixed-timestep loop protects against slow frames with elapsed-time checks each tick

---

## Scaling: toward a multi-threaded backend

The current tick loop executes registered ECS systems sequentially, in the dependency order `SystemScheduler.build()` computes via topological sort. That dependency graph is deliberately the unit of scheduling: systems with no dependency relationship between them have no ordering requirement, which is exactly the property needed to dispatch them across worker threads/processes safely instead of one after another. That parallel execution isn't implemented yet — today's scheduler runs everything on the single tick thread — but the graph structure exists specifically so entity/system throughput can scale without a redesign once large entity counts (including many off-screen/simulated-but-not-rendered entities) make single-threaded execution the bottleneck. Spatial partitioning (`spatial.py`) and dirty-flag delta broadcasting already exist to keep the *network* and *query* costs low independent of this.

---

## Setup

### Desktop Application (Windows)

```bat
setup.bat    :: Create venv and install dependencies
run.bat      :: Launch the PyWebView desktop window
```

Or manually:

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### Browser Mode (Development / Linux)

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python run_browser.py
# Open http://localhost:5000 in a WebGPU-capable browser (Chrome 121+, Edge, Firefox 141+)
```

> **Linux note:** The packaged PyWebView build is deferred until WebKitGTK ships stable WebGPU support. Use browser mode for development. See [docs/DEBIAN_SETUP.md](docs/DEBIAN_SETUP.md).

---

## See also

- [README.md](README.md) — project summary and quick start
- [ROADMAP.md](ROADMAP.md) — phased development plan
- [docs/graphics/](docs/graphics/) — WebGPU pipeline specs, data structure schemas, 3D asset authoring
- `.github/copilot-instructions.md` — repo-wide coding rules, including the physics/cosmetic-motion boundary
