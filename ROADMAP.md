# Engine Packaging Roadmap

This document tracks the incremental work required to turn this repository from a monolithic game prototype into a modular, extensible game engine with a clear boundary between engine infrastructure and game-specific content.

---

## Philosophy

The engine is not a separate product — it is the lower half of this same repository. "Packaging" means establishing a clean API surface between the two halves so that game content can be replaced, extended, or swapped without touching engine code.

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

## Phase Progress

| Phase | Name | Status |
| ----- | ---- | ------ |
| 0 | WebGPU Foundation | ✅ Complete |
| 1 | Engine–Game Separation | ✅ Complete |
| 2 | Graphics Pipeline Completion | 🔲 Not started |
| 3 | ECS Overhaul | ✅ Complete |
| 4 | Simulation Systems | 🔲 Not started |
| 5 | Asset Pipeline | ✅ Complete |
| 6 | Save / Load / Persistence | 🔲 In Progress |
| 7 | UI Framework | 🔲 Not started |
| 8 | Audio | 🔲 Not started |
| 9 | Distribution & Tooling | 🔲 Not started |

---

## Phase 0 — WebGPU Foundation ✅

**Goal:** Replace Canvas 2D with a WebGPU render pipeline.

**Completed work:**

- `initWebGPU()` in `renderer.js` — device acquisition, canvas context, feature flag
- `shaderCache.js` — WGSL sprite pipeline, `ShaderCache` class
- `gpuBuffers.js` — `createUniformBuffer`, `writeUniformBuffer`, `createQuadVertexBuffer`
- `gpuSpriteSheet.js` — `GPUSpriteSheet` (load, UV rect, bind group)
- `entityRenderer.js` — GPU draw path; Canvas 2D entity path removed
- `renderer.js` — GPU render loop with `GPURenderPassEncoder` threading
- Overlay canvas pattern for 2D HUD over WebGPU surface

**Remaining graphics milestones** are tracked in Phase 2.

---

## Phase 1 — Engine–Game Separation ✅

**Goal:** Establish a clear directory boundary and API contract between engine-level infrastructure and game-specific content. No engine module should import content; no content module should reach into engine internals.

### 1.1 — Directory Restructure ✅ ✅

Reorganise source into two top-level namespaces:

```text
backend/
  engine/           ← ECS framework, event bus, spatial, save/load base, loop
  game/             ← entities, systems, actions specific to THIS game
frontend/js/
  engine/           ← renderer, input, network, interpolation, asset loader
  game/             ← character creation, party UI, world-specific shaders
```

Key moves:
- `backend/simulation/` → split: `engine/ecs/`, `engine/spatial.py`, `game/entities/`
- `backend/game_loop.py` → `engine/game_loop.py` (loop mechanics) + `game/tick.py` (game rules)
- `frontend/js/renderer.js`, `entityRenderer.js`, `interpolation.js` → `engine/`
- `frontend/js/characterCreation.js`, `playerSelect.js` → `game/`

### 1.2 — Configuration Injection ✅

Replace hard-coded constants in `config.py` with an injectable config schema:

- `EngineConfig` dataclass: tick rate, world size, grid cell size, log paths
- `GameConfig` dataclass: race definitions, base stats, starting conditions
- Both loaded from JSON at startup; validated against a schema

### 1.3 — Engine API Surface ✅

Define the stable API that game code calls into:

**Python:**
- `engine.ecs.World` — entity/component CRUD
- `engine.ecs.System` — base class for systems
- `engine.events.EventBus` — publish/subscribe message broker
- `engine.spatial.SpatialGrid` — spatial queries
- `engine.loop.GameLoop` — configurable tick loop

**JavaScript:**
- `engine.Renderer` — WebGPU render coordinator
- `engine.Input` — input event stream
- `engine.Network` — SocketIO abstraction
- `engine.AssetLoader` — asset registry and loading

**Prompt file:** `.github/prompts/engine-architecture.prompt.md`

---

## Phase 2 — Graphics Pipeline Completion

**Goal:** Complete the material system, parameter maps, and combiner as specified in `docs/graphics/OVERVIEW.md` (steps 3–5), then extend with lighting.

### 2.1 — Material System (OVERVIEW.md Step 3) ✅

- Define bind group layout for: uniform buffer (slot 0), albedo texture (slot 1), param map (slot 2), sampler (slot 3)
- `MaterialLoader` class: parses `material/*.json`, creates `GPUBindGroup` per material
- `EntityRenderer` selects bind group by entity material key

### 2.2 — Parameter Map Support (OVERVIEW.md Step 4) ✅

- Complete `tools/pack_param_map.py`: packs R=roughness, G=emission mask, B=palette index, A=alpha into a single RGBA texture per sprite
- Upload param maps as `GPUTexture` objects in `GPUSpriteSheet`
- Update material JSON schema (see `docs/graphics/DATA_STRUCTURES.md`)

### ✅ 2.3 — Combiner / Fragment Shader (OVERVIEW.md Step 5)

- Parameterise the WGSL fragment shader with combiner formula driven by material JSON
- `ShaderCache` generates pipeline variants from material flags (emission, palette swap, etc.)
- See `docs/graphics/COMBINER.md` and `RENDER_WORKFLOWS.md` for full specification

### ✅ 2.4 — Lighting Pass

- Second render pass: additive point-light contribution; lights defined as entities with a `light` component
- WGSL shader: screen-space light accumulation, output multiplied into base pass
- Deferred or simple forward approach (TBD based on entity count)

### ✅ 2.5 — Particle System (Compute)

- `GPUComputePipeline` for particle simulation (position + velocity integration)
- Emitter component on entities; particle data lives entirely on GPU
- Render pass reads particle buffer via storage binding

**Prompt file:** `.github/prompts/material-system.prompt.md`

---

## Phase 3 — ECS Overhaul ✅

**Goal:** Replace the current loose entity class hierarchy with a proper Entity-Component-System that scales to hundreds of entity types and thousands of instances.

### 3.1 — Component Registry ✅

- `Component` base class with a unique type ID
- `ComponentRegistry` maps type → storage array
- Struct-of-arrays storage layout for cache efficiency on hot paths (movement, AI)

### 3.2 — World Queries ✅

- `world.query(ComponentA, ComponentB)` — yields entities possessing all listed component types
- Archetype-based storage (optional optimisation if benchmarks demand it)
- Iterator-compatible; systems iterate queries in their `update()` method

### 3.3 — System Scheduler ✅

- `System` base class with `dependencies: list[type[System]]`
- Topological sort constructs an execution order per tick
- Systems can declare `PARALLEL` flag; scheduler runs non-overlapping parallel groups via `concurrent.futures`

### 3.4 — Event Bus ✅

- `EventBus.publish(event_type, payload)` — synchronous dispatch within a tick
- `EventBus.subscribe(event_type, handler)` — handler registration
- Replaces direct SocketIO calls for internal simulation communication (SocketIO remains only for client ↔ server boundary)

**Prompt file:** `.github/prompts/ecs-overhaul.prompt.md`

---

## Phase 4 — Simulation Systems ✅

**Goal:** Replace placeholder system bodies with real implementations.

### 4.1 — Pathfinding ✅

- A* over the spatial grid; heuristic = Chebyshev distance for 8-directional movement
- Flow fields for large groups (party members all moving toward same goal)
- Path cache with invalidation on entity add/remove near path tiles

### 4.2 — AI / Behaviour Trees ✅

- `BehaviourTree` + `BehaviourNode` base classes
- Leaf nodes: `Seek`, `Flee`, `Idle`, `UseItem`, `Attack`
- Composite nodes: `Sequence`, `Selector`, `Parallel`
- Party members use BTs; tree data loaded from JSON for moddability

### 4.3 — Combat System ✅

- Turn-based resolution within real-time simulation (action points)
- Stat derivation: damage formula, dodge, hit chance from entity stats
- Status effects as Components (poisoned, stunned, burning)
- `CombatEvent` published to `EventBus`; other systems (audio, UI, particles) subscribe

### 4.4 — Simple Physics ✅

- AABB collision response for solid entities
- Velocity damping; slope/terrain friction coefficients
- No rigid-body physics; keep it lightweight

**Prompt file:** `.github/prompts/simulation-systems.prompt.md`

---

## Phase 5 — Asset Pipeline

**Goal:** Build a reliable, repeatable pipeline from source assets to engine-ready data.

### 5.1 — Asset Manifest

- `frontend/assets/manifest.json` auto-generated from the assets directory
- Maps logical asset IDs to file paths, metadata (frame size, frame count, material key)
- `AssetLoader` reads manifest at startup; all asset requests go through it by ID, not path

### 5.2 — Build Tools

- `tools/build_assets.py` — orchestrates all pre-processing: pack param maps, compile animation JSON to binary, verify manifest
- Run as part of `setup.bat`; results cached; invalidated by source file hash

### 5.3 — Procedural Generation Framework

- `engine/procgen/` — wave function collapse (WFC) implementation
- Tile rule sets loaded from JSON; weighted outcomes; key cell injection
- Used for area generation; see `notes.md` for design intent

### 5.4 — Hot Reload (Dev Mode)

- Watch `frontend/assets/` for file changes
- On change: re-run `pack_param_map.py` for the changed asset, send reload event via SocketIO
- Shaders watched separately; pipeline recompiled on WGSL change without full restart

---

## Phase 6 — Save / Load / Persistence

**Goal:** Persistent game state that survives process restarts, with clean versioning.

### 6.1 — Save File Format

- One directory per save slot: `saves/<slot_name>/`
- `world.json` — world metadata, player ref, tick count
- `area-<id>.json` — serialised entity list + component data per area
- `player-<id>.json` — player controller state, inventory, stats

### 6.2 — Serialisation / Deserialisation

- Each `Component` subclass implements `to_dict()` / `from_dict()`
- `World.serialise()` iterates all entities and their components
- Version field in each file; migration functions for format upgrades

### 6.3 — Save Management UI

- Load / new game screen (already partially stubbed in `playerSelect.js`)
- Auto-save every N ticks (configurable)
- Manual save via keybind; save slots with timestamps

---

## Phase 7 — UI Framework

**Goal:** A data-driven UI system that renders over the WebGPU canvas without mixing Canvas 2D and DOM concerns.

### 7.1 — HUD Layer

- Overlay canvas (already implemented) hosts all 2D HUD elements
- Separate renderer class (`HUDRenderer`) manages Canvas 2D draw calls on overlay
- HUD data bound to game state; updated once per render frame

### 7.2 — UI Component System

- `UIComponent` base: position, size, visibility, z-order
- Leaf types: `Label`, `ProgressBar`, `Icon`, `Button`, `Panel`
- Flexbox-inspired layout engine (no DOM, pure JS)
- Theme system: colour palette + font config loaded from JSON

### 7.3 — Inventory & Dialogue

- `InventoryPanel` — grid layout, drag-and-drop, item tooltips
- `DialogueBox` — scripted conversation trees; script format TBD (JSON or simple DSL)
- Both driven by data fetched from server via SocketIO events

---

## Phase 8 — Audio

**Goal:** Integrated audio engine for music and spatial sound effects.

### 8.1 — Web Audio API Wrapper

- `AudioEngine` class: initialise `AudioContext` on first user interaction
- Master gain, music bus, sfx bus, ambient bus
- All audio routed through buses for global volume control

### 8.2 — Music Playback

- Streaming from `assets/audio/music/`
- Crossfade between tracks on area transition
- Loop points defined in audio manifest

### 8.3 — Spatial SFX

- `PannerNode` per active sound source
- Entity position → panner x/y, camera defines listener position
- Fire-and-forget API: `audioEngine.playSFX(sfxId, worldX, worldY)`

---

## Phase 9 — Distribution & Tooling

**Goal:** A one-step build that produces a distributable executable with no Python installation required.

### 9.1 — PyInstaller Packaging

- `tools/build.py` — runs PyInstaller with spec file; bundles Flask, SocketIO, PyWebView, and all game assets into a single directory or `.exe`
- Windows: sign with code signing certificate (optional)
- macOS: bundle as `.app`, notarise (optional)
- Linux: defer until WebKitGTK ships WebGPU; distribute via `run_browser.py` or AppImage

### 9.2 — Developer Tools

- **Entity Inspector**: overlay panel listing all entities in the current area with live component values
- **Perf Overlay**: frame time, tick time, entity count, GPU memory (available via `GPUDevice.limits`)
- **Animation Preview**: standalone page that loads a `GPUSpriteSheet` and plays animation clips; linked from `run_browser.py`

### 9.3 — Release Versioning

- Semantic versioning (`MAJOR.MINOR.PATCH`): MAJOR = save format break, MINOR = new engine feature, PATCH = bug fix
- Version baked into build artifact names and reported in `engine.version`

---

## Prompt Files

Each phase has a companion agent prompt in `.github/prompts/`:

| Phase | Prompt file |
| ----- | ----------- |
| 0 | `webgpu-migration.prompt.md` ✅ |
| 1 | `engine-architecture.prompt.md` |
| 2 | `material-system.prompt.md` |
| 3 | `ecs-overhaul.prompt.md` ✅ |
| 4 | `simulation-systems.prompt.md` |
| 5 | `asset-pipeline.prompt.md` |
| 6 | `save-load.prompt.md` |
| 7 | `ui-framework.prompt.md` |
| 8 | `audio.prompt.md` |
| 9 | `distribution.prompt.md` |

---

## Sequencing Notes

Phases 1 and 3 are **prerequisites** for everything else — a clean architecture and a proper ECS are the foundation every other phase depends on. Tackle them before adding more features.

Phase 2 is largely independent and can proceed in parallel with Phase 3, since it lives entirely in the JavaScript/WebGPU layer while Phase 3 lives in Python.

Phases 4–9 depend on Phase 3 completing. They can largely proceed in any order after that, with one exception: the save/load format (Phase 6.1) should be stabilised before Phase 4 adds many new component types, to avoid excessive migration work.
