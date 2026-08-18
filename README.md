# Real-Time Game Engine

A modular, genre-agnostic real-time game engine supporting 2D, 2.5D, and full 3D graphics in the same scene. The engine runs as a standalone desktop application (PyWebView) with a Python simulation backend and a WebGPU-accelerated JavaScript frontend.

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
│  (Python)    │  (JavaScript / WebGPU)   │
└──────────────┴──────────────────────────┘
```

### Backend (Python + Flask + SocketIO)

- **`backend/engine/`** — Engine infrastructure: ECS framework, spatial grid, game loop, config
- **`backend/game/`** — Game content: entities, systems, world, area management
- Fixed-timestep simulation loop (20 TPS); only changed entity state is broadcast as deltas
- WebSocket server (SocketIO) is the sole boundary between simulation and frontend

### Frontend (JavaScript + WebGPU)

- **`frontend/js/`** — Renderer, input, network, interpolation; 2D, 2.5D (billboard), and 3D (textured mesh) draw paths all live side by side in `entityRenderer.js`, chosen per-entity — the engine is not locked to one dimensionality
- 60 FPS render loop with position interpolation between simulation ticks
- Sprite atlas + animation clip system; JSON-driven material/parameter map pipeline; glTF-authored mesh pipeline for 3D content
- Overlay canvas pattern: WebGPU surface for world + Canvas 2D for HUD

---

## Project Structure

```text
├── main.py                        # Desktop app entry point (PyWebView)
├── backend/
│   ├── app.py                     # Flask + SocketIO server
│   ├── game_loop.py               # Simulation tick loop
│   ├── config.py                  # Top-level config
│   ├── engine/                    # Engine infrastructure
│   │   ├── config.py              # EngineConfig (tick rate, world size, etc.)
│   │   ├── spatial.py             # SpatialGrid — spatial partitioning
│   │   └── ecs/
│   │       └── entity.py          # Entity base class
│   └── game/                      # Game-specific content
│       ├── world.py               # World state manager
│       ├── area.py                # Area (chunk) management
│       ├── config.py              # GameConfig (races, stats, etc.)
│       ├── entities/              # Player, party, races
│       └── systems/               # Movement, AI, actions, combat
├── frontend/
│   ├── index.html
│   ├── css/style.css
│   ├── js/
│   │   ├── main.js                # Frontend entry point
│   │   ├── renderer.js            # WebGPU render coordinator
│   │   ├── entityRenderer.js      # Per-entity GPU draw path
│   │   ├── interpolation.js       # 20 TPS → 60 FPS position interpolation
│   │   ├── input.js               # Input event stream + game context routing
│   │   ├── network.js             # SocketIO abstraction
│   │   ├── ui.js                  # HUD and UI panels
│   │   ├── characterCreation.js   # Character creation flow
│   │   ├── playerSelect.js        # Player/save select screen
│   │   └── sprites/               # WebGPU sprite pipeline
│   │       ├── shaderCache.js     # WGSL pipeline compilation and caching
│   │       ├── gpuBuffers.js      # GPU buffer helpers
│   │       ├── gpuSpriteSheet.js  # Texture load, UV rect, bind group
│   │       └── animation.js       # Animation clip playback
│   └── assets/
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
# Open http://localhost:5000 in Chrome 121+
```

> **Linux note:** The packaged PyWebView build is deferred until WebKitGTK ships stable WebGPU support. Use the browser mode for development. See [docs/DEBIAN_SETUP.md](docs/DEBIAN_SETUP.md).

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
