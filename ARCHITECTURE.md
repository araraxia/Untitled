# Architecture

## Overview

This repository is a general-purpose, genre-agnostic real-time game engine, not a single game. It ships as a standalone desktop application with a Python simulation backend and a native, GPU-accelerated Python client (GLFW + `wgpu-py` WebGPU + `imgui-bundle`). The rendering path supports 2D sprites, 2.5D camera-facing billboards, and fully modeled 3D meshes side by side in the same scene — an entity's dimensionality is a per-entity data choice, not an engine-wide assumption. The backend simulation is a fixed-timestep tick loop built on an ECS (entity-component-system) with a dependency-ordered system scheduler, structured so independent systems can scale toward parallel/multi-threaded execution as entity counts grow, rather than assuming a small, hand-authored cast of on-screen actors.

A game built on top of the engine (currently the in-repo example content under `backend/game/` and `client/game/`) is one consumer of that API surface, not the definition of what the engine is for.

An earlier PyWebView + browser/JavaScript client existed during this project's WebGPU-migration phase but has been deleted entirely (`.github/prompts/wgpu-py-migration.prompt.md`) — WebKitGTK's incomplete Linux WebGPU support was the reason it existed, and the native client above has no such dependency. It isn't referenced further in this document; check git history from before that migration if you need it for reference.

---

## Two-Layer Architecture

1. **Desktop Application Layer** (`client/main.py`, invoked via root `main.py`) — launches the Flask/SocketIO server in a background thread, waits for a health check, then opens a native GLFW window with a `wgpu-py` WebGPU device and an `imgui-bundle` UI (`client/engine/`, `client/game/`). One Python process handles both server bootstrap and rendering.
2. **Backend Simulation Layer** (`backend/`) — Python, Flask + SocketIO, fixed-timestep ECS tick loop. Authoritative for all gameplay state.

```text
┌─────────────────────────────────────────┐
│  GAME LAYER  (content, rules, world)    │
├─────────────────────────────────────────┤
│  ENGINE API  (stable, versioned)        │
├──────────────┬──────────────────────────┤
│  Simulation  │  Rendering               │
│  (Python)    │  (Python / wgpu-py)      │
└──────────────┴──────────────────────────┘
```

---

## Engine vs. Game Separation (critical)

```text
backend/engine/   ← stable APIs: ECS, spatial grid, game loop, events, save format, physics, pathfinding, procgen
backend/game/     ← game content: entities, systems, world, area, character flow
client/engine/    ← renderer, input, network, interpolation, asset loader, 2D/3D draw paths
client/game/      ← character creation, player select, game-specific UI (imgui-bundle)
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

- `backend/app.py` — Flask app + `SocketIO(..., async_mode="threading")`; the SocketIO endpoint only, no HTTP page/static routes (the client reads `frontend/assets/` directly off disk)
- On player load: server emits `player_loaded` (full world snapshot) — not a literal `initial_state` event; `handle_load_game()` is what actually emits it, after player selection
- Each tick: server emits `state_update` (delta — only dirty entities, only changed fields)
- Client → server: `player_action`, `party_command` (queued, drained on the next tick)
- Dirty flag set on entity change, cleared after broadcast

### Save/Load

- Format: `saves/<slot>/world.json`, `area-<id>.json`, `player-<id>.json`
- Each `Component` subclass implements `to_dict()`/`from_dict()`; save files carry a version field for migration
- Autosave every `autosave_interval_ticks` (default 300, `backend/engine/config.py`), run off the tick thread via a background executor so it never stalls simulation

---

## Client (`client/`) — current

The native desktop client: GLFW window, `wgpu-py` WebGPU device, `imgui-bundle` UI. `client/main.py` is the entry point (launched via root `main.py` / `run.bat`) — see "Two-Layer Architecture" above for its server-bootstrap/render-loop responsibilities; it also owns the per-frame entity-render orchestration (`get_entity_renderer`/`render_entities`/`draw_game_scene`) rather than `client/engine/renderer.py`, because `entity_renderer.py` already imports `renderer.py` for device/canvas access — `renderer.py` importing back would be a circular import.

### Engine (`client/engine/`)

| File | Purpose |
| --- | --- |
| `renderer.py` | GLFW window + wgpu device/canvas bootstrap; camera/view-projection matrix (`get_view_projection_matrix`); depth/scene texture allocation; `init_lighting_pass()`/`resize()`; a bare `run()` render-loop skeleton the entry point overrides with its own real draw function |
| `entity_renderer.py` | Per-entity draw path — the same routing as the legacy `entityRenderer.js`: 2D sprite atlas, 3D camera-facing billboard (depth-tested), or 3D textured mesh (`render_template` → mesh + material), all coexisting in one scene. No Canvas-2D-style fallback exists here — this client is always on the GPU path |
| `mat4.py` | Dependency-free column-major 4×4 matrix helpers (`perspective`, `look_at`, `compose`, `rotation_xyz`, …) — no `numpy`/`pyglm`, matching the legacy client's own no-third-party-math-library constraint |
| `mesh.py` | `Mesh` — loads this project's interleaved-vertex-buffer mesh JSON format and uploads GPU vertex/index buffers |
| `asset_loader.py` | Maps short asset keys to `FRONTEND_DIR`-relative on-disk paths; manifest-driven registration — direct filesystem reads (this client runs on the same machine as the server), not an HTTP `fetch` |
| `shader_cache.py` | WGSL pipeline compilation/caching for both sprite and mesh variants — WGSL source ported verbatim from the legacy client's shaders |
| `gpu_buffers.py`, `gpu_sprite_sheet.py`, `material_loader.py`, `particle_system.py`, `lighting_pass.py`, `animation.py` | GPU buffer helpers; sprite atlas GPU upload (`Pillow` for texture decode, replacing the browser's `Image`/`createImageBitmap`); JSON-driven material → `GPUBindGroup`; compute-shader particle system; two-pass lighting composite; animation clip playback |
| `network.py` | `socketio.Client()` (synchronous) — same emitted event names/payloads as the legacy client, zero backend changes required |
| `interpolation.py` | 20 TPS simulation → 60 FPS render interpolation (exponential-decay easing toward each entity's authoritative position) |
| `input.py` | Keyboard/mouse input via `rendercanvas`'s own cross-backend event system (`canvas.add_event_handler(...)`, *not* raw GLFW callbacks — `renderer.py`'s `RenderCanvas` already owns those; see the module's docstring for the real bug this avoids), driven by the same `input_config.json` |
| `imgui_wgpu_compat.py` | One-line compatibility shim for a confirmed upstream `wgpu`/`imgui-bundle` version-incompatibility bug ([pygfx/wgpu-py#829](https://github.com/pygfx/wgpu-py/issues/829)); delete once a released `wgpu` version ships the fix ([#830](https://github.com/pygfx/wgpu-py/pull/830)) |

### Game (`client/game/`)

`ui.py`, `character_creation.py`, `player_select.py`, `character_flow/` — the example game's UI and flow, rebuilt as `imgui-bundle` immediate-mode widgets on the engine API above (functional, not pixel-for-pixel, parity with the legacy DOM screens — DOM/CSS has no 1:1 imgui equivalent). New games built on this engine would replace this directory without touching `client/engine/`.

### Dependencies

Added: `wgpu`, `glfw`, `imgui-bundle`, plus `requests`/`websocket-client` (both required by `socketio.Client()`'s synchronous connection path, not auto-installed by `python-socketio` alone). Removed: `pywebview` and Linux's `PyGObject` — nothing imports `webview` anymore now that the legacy PyWebView client and its dev-test launcher are gone.

---

## Frontend Assets (`frontend/assets/`)

The only thing left under `frontend/` — the legacy browser/JavaScript client that used to live alongside it (`frontend/js/`, `frontend/index.html`, `frontend/test-3d.html`) has been deleted (see the Overview section above). This directory is a git submodule ([untitled-assets](https://github.com/araraxia/untitled-assets)) holding animation clips, materials, entity definitions, and (for 3D) mesh JSON as plain JSON, resolved through `client/engine/asset_loader.py`'s `AssetLoader` at runtime rather than hardcoded paths. See `docs/graphics/DATA_STRUCTURES.md` for the schemas.

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

### Desktop Application (Windows or Linux)

```bat
setup.bat    :: Create venv and install dependencies
run.bat      :: Launch the native wgpu-py/GLFW/imgui desktop window
```

Or manually:

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

`run.bat`/`python main.py` launch `client/main.py`'s native window (GLFW + `wgpu-py` + `imgui-bundle`) — no browser, no PyWebView, no WebKitGTK dependency. Works the same way on Linux; see [docs/DEBIAN_SETUP.md](docs/DEBIAN_SETUP.md) for system packages.

---

## See also

- [README.md](README.md) — project summary and quick start
- [ROADMAP.md](ROADMAP.md) — phased development plan
- [docs/graphics/](docs/graphics/) — WebGPU pipeline specs, data structure schemas, 3D asset authoring
- `.github/copilot-instructions.md` — repo-wide coding rules, including the physics/cosmetic-motion boundary
