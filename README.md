# Real-Time Simulation Game Engine

A modular 2D/2.5D game engine and simulation game inspired by Rimworld and Dwarf Fortress. The engine runs as a standalone desktop application (PyWebView) with a Python simulation backend and a WebGPU-accelerated JavaScript frontend.

The primary goal of this repository is to develop a reusable, extensible engine with a clean boundary between engine infrastructure and game-specific content — not just a single game prototype.

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

- **`frontend/js/`** — Renderer, input, network, interpolation; sprite rendering via WebGPU pipeline
- 60 FPS render loop with position interpolation between simulation ticks
- Sprite atlas + animation clip system; material/parameter map pipeline in progress
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
| 2 | Graphics Pipeline Completion | 🔲 Not started |
| 3 | ECS Overhaul | 🔲 Not started |
| 4 | Simulation Systems | 🔲 Not started |
| 5 | Asset Pipeline | 🔲 Not started |
| 6 | Save / Load / Persistence | 🔲 In Progress |
| 7 | UI Framework | 🔲 Not started |
| 8 | Audio | 🔲 Not started |
| 9 | Distribution & Tooling | 🔲 Not started |

See [ROADMAP.md](ROADMAP.md) for full phase specs and sequencing notes.

---

## Performance Targets

| Metric | Target |
| ------ | ------ |
| Simulation rate | 20 TPS |
| Render rate | 60 FPS |
| Active entities | 100–1 000 |
| Network latency (localhost) | < 50 ms |

Key strategies: spatial partitioning (grid-based), dirty-flag delta broadcasts, entity sleeping, viewport culling.
