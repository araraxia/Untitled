# Real-Time Game Engine

A modular, genre-agnostic real-time game engine supporting 2D, 2.5D, and full 3D graphics in the same scene. The engine runs as a standalone desktop application with a Python simulation backend and a native WebGPU-accelerated client (GLFW + `wgpu-py` + `imgui-bundle`, `client/`). An earlier PyWebView + JavaScript/WebGPU frontend has been deleted entirely — see [ARCHITECTURE.md](ARCHITECTURE.md) and `.github/prompts/wgpu-py-migration.prompt.md` for the migration.

The primary goal of this repository is to develop a reusable, extensible engine with a clean boundary between engine infrastructure and game-specific content — not just a single game prototype. The backend simulation loop and ECS scheduler are designed to scale toward parallelized, multi-threaded entity processing, so a large number of on- and off-screen entities can be simulated without blocking the tick loop.

For a detailed breakdown of the architecture see [ARCHITECTURE.md](ARCHITECTURE.md).
For the phased development plan see [ROADMAP.md](ROADMAP.md).

---

## Architecture

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

### Backend (Python + Flask + SocketIO)

- **`backend/engine/`** — Engine infrastructure: ECS framework, spatial grid, game loop, config
- **`backend/game/`** — Game content: entities, systems, world, area management
- Fixed-timestep simulation loop (20 TPS); only changed entity state is broadcast as deltas
- WebSocket server (SocketIO) is the sole boundary between simulation and clients
- Unmodified by the native client migration — either client is just a Socket.IO client connecting to the same server

### Client (Python + wgpu-py + imgui-bundle)

- **`client/engine/`** — Renderer, input, network, interpolation; 2D, 2.5D (billboard), and 3D (textured mesh) draw paths all live side by side in `entity_renderer.py`, chosen per-entity — the engine is not locked to one dimensionality
- **`client/game/`** — Player select, character creation, and HUD, built as `imgui-bundle` immediate-mode UI
- 60 FPS render loop with position interpolation between simulation ticks
- Sprite atlas + animation clip system; JSON-driven material/parameter map pipeline; glTF-authored mesh pipeline for 3D content — reads `frontend/assets/` (a git submodule) directly off disk

---

## Project Structure

```text
├── main.py                        # Desktop app entry point (thin wrapper -> client/main.py)
├── client/                        # Native desktop client (current) -- GLFW + wgpu-py + imgui-bundle
│   ├── main.py                    # Server bootstrap + native window/render loop
│   ├── engine/                    # Renderer, input, network, interpolation, asset loader
│   └── game/                      # Player select, character creation, HUD (imgui-bundle)
├── backend/
│   ├── app.py                     # Flask + SocketIO server
│   ├── engine/                    # Engine infrastructure
│   │   ├── game_loop.py           # GameLoop (loop.py re-exports it)
│   │   ├── config.py              # EngineConfig (tick rate, world size, etc.)
│   │   ├── spatial.py             # SpatialGrid — spatial partitioning
│   │   └── ecs/
│   │       └── entity.py          # Entity base class
│   └── game/                      # Game-specific content
│       ├── tick.py                # GameTick(GameLoop) — simulation tick loop
│       ├── world.py               # World state manager
│       ├── area.py                # Area (chunk) management
│       ├── config.py              # GameConfig (races, stats, etc.)
│       ├── entities/              # Player, party, races
│       └── systems/               # Movement, AI, actions, combat
├── frontend/
│   └── assets/                    # Git submodule (untitled-assets) — shared by client/
│       ├── data/                  # Animation clips, materials, entity data (JSON)
│       ├── images/sprites/        # Sprite atlases
│       └── audio/                 # Music and SFX
├── tools/
│   └── pack_param_map.py          # Channel-packing tool for parameter maps
├── docs/                          # Design and reference documentation
│   └── graphics/                  # WebGPU pipeline specs and workflows
├── requirements.txt
├── setup.bat                      # Automated environment setup (Windows)
└── run.bat                        # Run the desktop application (Windows)
```

---

## Setup

`frontend/assets/` is a git submodule ([untitled-assets](https://github.com/araraxia/untitled-assets)) using Git LFS for binary files — install [Git LFS](https://git-lfs.github.com) before cloning, and run `git submodule update --init --recursive` after cloning (or use `setup.bat`, which does this for you).

### Desktop Application (Windows or Linux)

```bat
setup.bat    :: Fetch asset submodule, create venv, install dependencies
run.bat      :: Launch the native GLFW/wgpu-py/imgui-bundle desktop window
```

Or manually:

```bat
git submodule update --init --recursive
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

`run.bat`/`python main.py` launch `client/main.py`'s native window — no browser, no PyWebView, no WebKitGTK dependency. Works the same way on Linux; see [docs/DEBIAN_SETUP.md](docs/DEBIAN_SETUP.md) for system packages.

---

## Roadmap Status

| Phase | Name | Status |
| ----- | ---- | ------ |
| 0 | WebGPU Foundation | ✅ Complete |
| 1 | Engine–Game Separation | ✅ Complete |
| 2 | Graphics Pipeline Completion | ✅ Complete |
| 3 | ECS Overhaul | ✅ Complete |
| 4 | Simulation Systems | ✅ Complete |
| 5 | Asset Pipeline | ✅ Complete |
| 6 | Save / Load / Persistence | ✅ Complete |
| 7 | UI Framework | 🔲 Not started |
| 8 | Audio | 🔲 Not started |
| 9 | Distribution & Tooling | 🔲 Not started |
| 10 | 3D Coordinate Mapping | 🔲 In Progress |
| 11 | Area / Scene System | 🔲 Not started |
| 12 | Level Editor & Asset Viewer | 🔲 Not started |

See [ROADMAP.md](ROADMAP.md) for full phase specs and sequencing notes — this table mirrors it and may lag slightly; ROADMAP.md is authoritative.

---

## Performance Targets

| Metric | Target |
| ------ | ------ |
| Simulation rate | 20 TPS |
| Render rate | 60 FPS |
| Active entities | 100–1 000 (current); scaling toward parallelized backend processing |
| Network latency (localhost) | < 50 ms |

Key strategies: spatial partitioning (grid-based), dirty-flag delta broadcasts, entity sleeping, viewport culling. The ECS system scheduler (`backend/engine/ecs/scheduler.py`) resolves systems into a dependency-ordered graph each tick — the same structure that independent, non-conflicting systems will run across worker threads/processes as the engine scales toward simulating large numbers of on- and off-screen entities.
