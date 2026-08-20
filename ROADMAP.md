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

## Branch model (current)

As of the split after Phase 13, this `engine` branch carries engine/tooling code only (`backend/engine/`, `client/engine/`) — no game content. The game-specific work this document's Phase 1 ("Engine–Game Separation") originally pulled into `backend/game/`/`client/game/` moved to its own branch, `legacy`, forked from `engine`. Future games branch from `engine` the same way; branches don't auto-sync, an engine improvement reaches a game branch only via an explicit `git merge engine`/rebase. Phases below that reference `backend/game/`/`client/game/` paths describe that layer as it exists on a game branch (`legacy` today), not code present on `engine` itself — see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Phase Progress

| Phase | Name | Status |
| ----- | ---- | ------ |
| 0 | WebGPU Foundation | ✅ Complete |
| 1 | Engine–Game Separation | ✅ Complete |
| 2 | Graphics Pipeline Completion | ✅ Complete |
| 3 | ECS Overhaul | ✅ Complete |
| 4 | Simulation Systems | ✅ Complete |
| 5 | Asset Pipeline | ✅ Complete |
| 6 | Save / Load / Persistence | ✅ Complete |
| 7 | UI Framework | 🔲 In Progress — engine-layer half done & verified (`client/engine/ui/`: custom-drawn primitives, theme, nav w/ gamepad, render-to-texture panels, `run_ui_test.py`); game-layer half (rebuild the HUD, add inventory panel + dialogue box on a game branch) not started. See ui-framework.prompt.md. |
| 8 | Audio | 🔲 Not started |
| 9 | Distribution & Tooling | 🔲 Not started |
| 10 | 3D Coordinate Mapping | ✅ Complete (engine-branch scope) — Steps 1–14 all done; see `docs/graphics/ACTION_TRIGGERED_ANIMATIONS.md` and a full-repo audit logged in `completed/3d-coordinate-mapping.prompt.md`, 2026-08-20. Every step independently re-confirmed against current code, not just against the prompt's own prior claims; `run_gametick_test.py` re-run clean. Two things remain deliberately open, neither blocking "complete" on this branch: (1) Step 12's real backend wiring — `example_game_loop.py` is verified generic reference content, but a real game still needs its own `ACTION_DURATIONS`/revert logic in `player.py`/`actions.py`/`tick.py` on a game branch, which doesn't exist here by design (see CLAUDE.md's Branch model); (2) Step 8's fog/`ambientColor` stylization hooks are correctly ported to `client/engine/shader_cache.py` and documented, but `run_client_test.py` only isolates `vertex_color`/`affine_uv`/`color_levels` — fog/ambient have never been visually exercised on the Python client, a test-coverage gap, not a known defect. |
| 11 | Area / Scene System | 🔲 Not started — **prompt not yet reconciled with the branch split**: `area-system.prompt.md` is written against `backend/game/area.py`, `backend/game/systems/systems.py`, `backend/game/tick.py`, and `client/game/area_viewer.py`, none of which exist on `engine` anymore. Needs a decision before starting: revise the prompt to target `client/engine/`/`backend/engine/` generically, or do this work on a game branch instead. |
| 12 | Zones & Triggers | 🔲 Not started — new this session. Backend-only: `Zone`/`ZoneRegistry` (AABB or mesh-footprint volumes), declarative `on_enter`/`on_exit` effects (EventBus events, `GroupRegistry` membership, tag data/component application). Same `ecs_world`-not-populated caveat as everything else touching the ECS System pipeline — driven from `Area.update()`, not registered as a `System`, mirroring `backend/engine/group.py`'s own precedent. See zones.prompt.md. Depends on Phase 11 (`Area`/`Scene`) for the Area-file schema it extends. |
| 13 | Native wgpu-py Desktop Client | ✅ Complete (18 of 18 steps; legacy PyWebView/JS client fully deleted, not just deprecated) — numbered out of chronological order (added after Phase 12 was already assigned); left as-is per this repo's own convention of not renumbering a completed, widely-cross-referenced phase. |
| 14 | Level Editor & Asset Viewer | 🔲 Not started — same branch-split caveat as Phase 11 (`level-editor.prompt.md` extends `client/game/area_viewer.py`/adds `client/game/launcher.py`); also depends on Phase 11 landing first either way. Scope extended this session with Steps 13–15: Zone authoring (depends on Phase 12, above), a UI-menu editor built on Phase 7's `client/engine/ui/` with keybind/zone/entity-interact triggers, and an Action Definitions panel (Phase 10 Step 12's `actions.json`/`action_animations` *data* only — trigger-wiring stays real game code, deliberately not editor-authorable; see `docs/graphics/ACTION_TRIGGERED_ANIMATIONS.md`). |

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

## Phase 2 — Graphics Pipeline Completion ✅

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

## Phase 5 — Asset Pipeline ✅

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

## Phase 6 — Save / Load / Persistence ✅

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

**Goal:** A fully custom-drawn, art-asset-skinned UI — imgui-bundle used only as the input/hit-testing/frame-lifecycle engine, never its default widget chrome — supporting keyboard/mouse/gamepad navigation, animated elements, and 3D/shader content embedded inside UI panels (e.g. a liquid health orb). Redesigned mid-phase from an earlier, narrower "use imgui's default widgets" draft once the real scope was clear — see `.github/prompts/ui-framework.prompt.md`.

**Engine-layer half: done and verified**, ships on `engine` as `client/engine/ui/` (`draw.py`/`theme.py`/`gamepad.py`/`nav.py`/`widgets.py`/`panel3d.py`/`templates.py`) plus a new `shader_cache.py` `'orb'` variant and a standalone smoke test, `run_ui_test.py` (confirmed: runs 20+ seconds, zero draw errors). One real bug found and fixed during verification: `Panel3D` must default its offscreen texture format to `renderer.canvas_format`, not a hardcoded format, since every existing render pipeline in this codebase is compiled against the former.

**Game-layer half: not started**, belongs on a game branch (`legacy` today), not `engine` — see the prompt file's "Remaining work" section: rebuild `client/game/ui.py`'s existing HUD (built ad hoc during Phase 13, not previously tracked here) plus a new inventory panel and dialogue box using `client/engine/ui/` instead of plain imgui widgets.

### 7.1 — Core drawing/input primitives (`client/engine/ui/`) — ✅ done, engine-layer

- `draw.py`'s `ImDrawList`-based primitives + the confirmed `imgui_renderer.backend.register_texture()` wgpu-to-imgui texture bridge
- `nav.py`'s input-method-agnostic focus (keyboard + `gamepad.py`'s GLFW polling, mouse hover claims focus so the two never disagree)
- `widgets.py`'s composable functions (not a class hierarchy) and `templates.py`'s game-agnostic patterns (confirm/deny, chat box, titled window)

### 7.2 — Theme + embedded 3D/shader content — ✅ done, engine-layer

- `theme.py`: JSON colour palette + optional custom fonts/skin images, applied via `draw.py`'s primitives directly (no `imgui.push_style_color` widget-chrome dependency)
- `panel3d.py`'s render-to-texture bridge for embedding 3D content or a shader effect in a UI rect; `shader_cache.py`'s new `'orb'` variant is the first real consumer (liquid fill + fresnel rim, reusing existing unused `MatUniforms` slots — no new bind-group layout needed)

### 7.3 — Inventory & Dialogue — 🔲 not started, game-layer (see prompt file)

- `InventoryPanel` — grid layout, drag-and-drop (`imgui`'s own drag-drop API, confirmed present), item tooltips, built on `widgets.image_button`
- `DialogueBox` — scripted conversation trees (JSON schema in the prompt file), built on `templates.window` + `widgets.button`
- Both driven by data fetched from server via SocketIO, wired through `network.py`'s existing callback-dict pattern; both must reuse `ui.py`'s pending-request pattern for anything triggered outside the imgui frame bracket (confirmed SIGSEGV otherwise — the same rule `client/engine/ui/draw.py`'s whole design enforces)

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

### 8.4 — Live Coding Option (SuperCollider + OSC)

- Optional external audio pipeline for live-coded or procedural music design
- Launch and supervise SuperCollider (`scsynth`/`sclang`) from backend startup
- Use OSC bridge (`python-osc`) to send tempo, pattern, and event messages
- Map game events (`area_enter`, `combat_start`, `low_health`) to OSC cues
- Fallback to in-engine Web Audio playback if SuperCollider is unavailable
- Keep this path optional so packaged builds can ship without requiring SuperCollider

---

## Phase 9 — Distribution & Tooling

**Goal:** A one-step build that produces a distributable executable with no Python installation required.

### 9.1 — PyInstaller Packaging

> **Updated for the native client (Phase 13, `.github/prompts/wgpu-py-migration.prompt.md`) — do not bundle PyWebView or plan around `run_browser.py`; this project doesn't use either anymore.**

- `tools/build.py` — runs PyInstaller with spec file; bundles Flask, SocketIO, `client/` (GLFW + `wgpu-py` + `imgui-bundle`), and all game assets into a single directory or `.exe`
- Windows: sign with code signing certificate (optional)
- macOS: bundle as `.app`, notarise (optional)
- Linux: ships directly, same as Windows/macOS — the native client doesn't depend on WebKitGTK, so there's nothing to defer and no `run_browser.py`/AppImage fallback needed

### 9.2 — Developer Tools

- **Entity Inspector**: overlay panel listing all entities in the current area with live component values
- **Perf Overlay**: frame time, tick time, entity count, GPU memory (available via `GPUDevice.limits`)
- **Animation Preview**: a `client/`-native imgui tool that loads a `GPUSpriteSheet` and plays animation clips — not a `run_browser.py`-linked HTML page (that plan predates the native client and no longer applies)

### 9.3 — Release Versioning

- Semantic versioning (`MAJOR.MINOR.PATCH`): MAJOR = save format break, MINOR = new engine feature, PATCH = bug fix
- Version baked into build artifact names and reported in `engine.version`

---

## Phase 10 — 3D Coordinate Mapping (Future)

**Goal:** Implement the "2.5D / 3D (Future)" section of `docs/graphics/COORDINATE_MAPPING.md` — a real perspective camera, billboarded sprites in a 3D world, and a minimal textured-mesh draw path — without disturbing the existing 2D orthographic rendering. This phase is a **foundation**, not a commitment to a single art direction: stylization is layered on as opt-in flags so later rendering techniques can build on the same camera/mesh plumbing without inheriting assumptions from whatever look ships first.

### 10.1 — Matrix Helpers & 3D Camera ✅

- `frontend/js/engine/mat4.js` — explicit, dependency-free `identity`/`perspective`/`lookAt`/`multiply`/`translationScale`/`rotationXYZ`/`compose` helpers, matching the project's existing hand-built flat-`Float32Array` MVP convention
- `camera` object gains optional `mode` (`'2d'` default / `'3d'`), `position`, `target`, `up`, `fov`, `near`, `far`; `getViewProjectionMatrix()` added to `renderer.js`, returns `null` in 2D mode
- Fog/ambient fields (`fogColor`/`fogNear`/`fogFar`/`ambientColor`) land with Step 8 (stylization hooks), not here

### 10.2 — Billboarded Sprites ✅

- Sprite quads built from the camera's right/up vectors so 2.5D sprites face the camera in a 3D world without per-entity meshes
- Reuses existing sprite/material pipelines and bind groups — only the model matrix construction differs
- Depth testing added via a separate, depth-tested pipeline variant (`ShaderCache.getSpritePipeline3D`) and a depth texture/attachment, kept fully independent of the existing 2D pipeline so 2D rendering is provably unaffected
- Verified rendering and depth-sorting correctly via a throwaway dev harness (`frontend/test-3d.html` + `run_desktop_test.py`, opened through the real PyWebView/WebView2 client rather than a browser, to sidestep browser-default WebGPU availability issues)

### 10.3 — Minimal Textured Mesh Path

- Small project-defined mesh JSON format (`position`/`normal`/`uv`/optional `color` per vertex + index list) under `frontend/assets/data/mesh/` — a project-specific runtime format, not a glTF subset
- `Mesh` class uploads interleaved vertex + index buffers; new `'mesh'` `ShaderCache` pipeline variant issues indexed draws
- An entity-**definition** file (`frontend/assets/data/entity/entity-<uuid>.json`) references a `mesh` — shared appearance data, no placement. A networked entity opts in via `render_template` (which definition to use) plus `transform3d` (this instance's rotation/scale — position is its existing `x`/`y`/`z`); entities without either are unaffected. Position/rotation/scale are deliberately never on the shared definition — two placed copies of one template must be independently positioned

### 10.4 — Mesh Authoring Pipeline

- `tools/convert_mesh.py` — build-time-only converter (stdlib `json`/`struct`, no new pip dependency) from Blender-exported glTF 2.0 (`.gltf`/`.glb`) into the 10.3 mesh JSON format; reads geometry only (position/normal/uv/color, single mesh/primitive) and refuses skins, morph targets, or multiple primitives rather than mishandling them
- Not a runtime import path — glTF is never loaded by the engine itself, only consumed offline by this tool
- `tools/build_manifest.py` gains a `"meshes"` manifest category (mirroring `animations`/`materials`); `assetLoader.js`'s `loadManifest()` category list is extended to match, so mesh assets resolve by id like every other asset type

### 10.5 — Optional Stylization Hooks

- Independent, opt-in flags — `vertex_color` (Gouraud tint), `affine_uv` (N64-style texture warp), `color_levels` (colour banding), scene fog (`fogColor`/`fogNear`/`fogFar`) — each defaulting to off/neutral
- Happen to compose into a low-poly N64 look, but are named and gated generically so any future rendering technique can adopt some, all, or none of them independently
- A mesh/material that sets none of these renders identically to the plain Step 10.3 path

### 10.6 — Multi-Part Meshes & Attachment Sockets

- Mesh JSON gains optional named `sockets` (local anchor points); `convert_mesh.py` extracts them from unmeshed, named glTF nodes (Blender Empties) without widening the converter into a general importer
- Entities gain an optional `parts` array — each part a mesh + an optional `attachTo: { part, socket }` — composed through the attachment chain at render time; entities using a plain `mesh` field are unaffected
- The foundation both 10.7 and 10.8 build on: a staff and its separately-modeled hanging charm are two parts, not one rigid mesh

### 10.7 — Secondary-Motion "Dangle" Spring

- `frontend/js/engine/dangle.js` — a hand-rolled, client-side-only spring-damper per dangling part (inertial kick from parent motion, gravity, spring-to-rest, damping), **not** a physics engine and **not** connected to the backend ECS/collision system in any way
- Opt-in per part via a `dangle: { stiffness, damping, gravity, maxOffset }` block; the cosmetic-motion answer for something like a charm hanging off a staff swaying slightly as the player moves
- Governed by `.github/copilot-instructions.md`'s "Physics & Simulation Boundary": lives strictly on the frontend/cosmetic side, is never named "physics," and never writes back into authoritative entity state — see `backend/engine/physics.py`'s module docstring for the same boundary stated from the backend side

### 10.8 — Transform Animation Clips

- New `"type": "transform"` animation clip (keyframed `position`/`rotation`/`scale`, reusing the existing clip-JSON pattern) for authored, repeating part motion — a spinning coin, a bobbing lid
- `sampleTransformClip()` — hand-rolled linear interpolation, matching `RENDER_WORKFLOWS.md` Workflow E's `lerpPreset` style
- Composes with 10.7's dangle offset — a part can spin *and* wobble from movement simultaneously

### 10.9 — Action-Triggered Animation Playback

- One-shot animations for discrete actions (attack, jump) — the *only* backend-touching sub-phase, since action start/duration must be server-authoritative to avoid client desync
- Backend: `ACTION_DURATIONS` table + `state_started_at` timestamp + per-tick auto-revert (`player.py`, `actions.py`, `tick.py`); reuses the existing `state_update` broadcast, no new message type; adds a `"jump"` action alongside the existing `move`/`attack`/`use_item`/`interact`
- Frontend: extends the existing `entity.state` → animation mapping with one-shot (`loop: false`) sprite clips, and an `action_animations` map on mesh parts for one-shot transform-clip playback; composes with 10.7 (dangle) and 10.8 (looping clips)

**Scope note:** No skeletal animation, skinning, rigid-body/collision physics, or shadow mapping — perspective projection, camera, billboards, static/multi-part meshes, a build-time mesh authoring tool, opt-in stylization toggles, attachment sockets, a cosmetic dangle spring, transform animation clips, and server-timed one-shot action playback only.

**Prompt file:** `.github/prompts/3d-coordinate-mapping.prompt.md`

---

## Phase 11 — Area / Scene System (Future)

**Goal:** A single runtime container (`Scene`) for entities, camera, and lighting, populated either from a pre-authored Area file or the live SocketIO gameplay stream, and writable at any time via a small imperative API — so the same rendering pipeline serves a map builder, a dev/test harness, a plain asset/scene viewer, and scripted gameplay dressing without four separate implementations. Depends on Phase 10 for the `camera`/`fog`/mesh-`parts` fields this phase's schema reuses, and extends Phase 6's `Area` file format rather than forking it.

### 11.1 — Area File Schema Extension

- `backend/game/area.py` gains optional `camera`/`lighting` blocks (passive metadata, no gameplay effect) in `to_dict()`/`from_dict()`/`get_full_state()`; absent by default, so every existing save file is unaffected
- Field names reuse Phase 10's `camera` object and `fogColor`/`fogNear`/`fogFar` exactly, rather than inventing parallel ones

### 11.2 — `Scene`: Single Runtime Container

- `frontend/js/engine/scene.js` — the one object both the network path and a file load populate; `entities`/`camera`/`lighting`/`startCamera` plus `addEntity`/`updateEntity`/`removeEntity`/`setCamera`/`setLighting`/`setStartCamera`
- `camera` is the live, constantly-moving view; `lighting` and `startCamera` are the authored values actually written to a save file — separated specifically so flying around to inspect a scene never silently changes what gets saved as the spawn point/ambience (Phase 14's editor is the only thing that calls `setStartCamera`)
- Every entity tagged `'authoritative'` (network or file) or `'local'` (runtime-injected); a same-id collision across tags is refused with a warning, never silently arbitrated
- `gameState` (the existing global in `main.js`) becomes a thin proxy onto `Scene`, so `renderer.js`/`ui.js`/`input.js` need zero changes — this phase wraps the working gameplay path, it doesn't rewrite it

### 11.3 — Four Run Modes, One Boot Path

- Gameplay: unchanged, network-driven, existing `index.html`
- Viewer / Builder / Test: one new page (`frontend/area-viewer.html`), file-loaded, zero network connection, free-fly camera — differentiated only by what runs after load (nothing / a crude on-page panel / a script), not by separate implementations
- Builder stays intentionally crude (plain form controls, a save-to-file button) — a working round-trip through the Phase 11.1 schema matters more than editor polish

### 11.4 — Scripted Gameplay Dressing

- A server-sent cue can trigger `scene.addEntity(..., 'local')` for purely cosmetic, non-networked moments (a cutscene camera pan, a decorative prop)
- Governed by the same rule as `.github/copilot-instructions.md`'s "Physics & Simulation Boundary": anything added this way is non-authoritative; if it needs to be simulated or interactive, it must be a real backend entity delivered through `state_update` instead

### 11.5 — Movement/Collision Foundation Fix (prerequisite for 11.6)

- Tracing the actual per-tick execution order (`tick.py` registration × `scheduler.py`'s topological sort) surfaced two real bugs: collider-bearing entities are double-integrated (`MovementSystem` and `PhysicsSystem` both move them, the second pass uncollided), and path-driven AI movement (`Seek`/`Flee` → `PathfindingSystem`) teleports position and skips collision entirely because it currently runs after `PhysicsSystem` resolves for the tick
- Fix: `MovementSystem` skips collider-bearing entities; `PathfindingSystem` sets velocity instead of teleporting position; dependency graph reordered so `PhysicsSystem` is always the last movement system to run each tick, integrating and colliding everyone exactly once
- Also switches `PhysicsSystem`'s collision candidate lookup from an O(n²) full scan to the already-present `SpatialGrid`
- Not scope creep — building script-driven movement on top of these bugs would make "interact with other entities" unreliable and "multiple entities" scale badly, which is exactly what 11.6 needs to avoid

### 11.6 — Script-Driven Entity Movement

- `ScriptComponent` (`waypoint_loop`/`orbit`/`follow`, params + runtime state) processed by a new `ScriptMovementSystem` that only ever writes `VelocityComponent` — never position directly — so every script-driven entity rides 11.5's single corrected `PhysicsSystem` pass for integration and collision, the same as player and AI-driven entities
- Real backend ECS entities, not client-side `Scene` additions — per the Physics & Simulation Boundary, only authoritative, server-simulated entities can genuinely interact (collide, trigger, be detected); a script-driven entity is only ever purely cosmetic if added via `Scene.addEntity(..., 'local')` instead, in which case it explicitly cannot interact with anything
- `ColliderComponent` gains an optional `trigger` flag (overlap-only, no push-out) publishing an `"entity_overlap"` `EventBus` event — the generic hook for pickups/doors/area markers, following the same event pattern `CombatEvent` already established
- Authored the same way as any other entity — a `ScriptComponent` entry in an entity's `components` list round-trips through the existing serialization/Area-file machinery with no new code; needs a `ColliderComponent` too if it should actually collide, which is optional (a script entity with no collider moves but passes through everything)
- Known limitation, documented not solved here: standalone viewer/builder/test modes (11.3) have no backend running, so a placed `ScriptComponent` entity is inert data there — it only actually moves/interacts inside a real gameplay session

**Prompt file:** `.github/prompts/area-system.prompt.md`

---

## Phase 12 — Zones & Triggers (Future)

**Goal:** Spatial trigger volumes — `Zone`/`ZoneRegistry`, added this session (not part of the original phase plan). Two shapes: a simple two-corner AABB, or a mesh-footprint volume (a cached 2D XZ-plane point-in-polygon test plus a Y-range check — an explicit, documented approximation, not true volumetric containment). Declarative `on_enter`/`on_exit` effects: fire an `EventBus` event, add/remove the entity from a `GroupRegistry` group (`backend/engine/group.py`), or set/clear tag data / attach a `Component` on the entity directly. Depends on Phase 11 (the Area-file schema this extends with a `zones` key).

**Architectural note carried over from `backend/engine/group.py`'s own precedent this session**: `ZoneRegistry` is driven from `Area.update()` each tick, *not* registered as an ECS `System` with the `SystemScheduler` — because nothing in this codebase ever populates `ecs_world` (confirmed: no call to `ecs_world.add()`/`add_component()` anywhere), so a registered `System` would compile correctly and never see real data. This is the same reasoning, not a new one.

**Scope note:** exactly two shapes, no general 3D-volume system; no third-party geometry dependency (hand-rolled point-in-polygon); effects are declarative data, never `eval`/`exec`.

**Prompt file:** `.github/prompts/zones.prompt.md`

---

## Phase 14 — Level Editor & Asset Viewer (Future)

**Goal:** Turn Phase 11's deliberately crude builder mode into a fairly polished level editor and asset viewer — a real launcher for opening/starting areas and previewing assets, a full translate/rotate/scale gizmo, undo/redo, a property panel, an asset browser, grid/snapping, and a proper save flow. Depends on Phase 11 (`Scene`, the standalone boot path) and Phase 10 (`mat4.compose`/`rotationXYZ`, `render_template`, stylization hooks, `parts`/`dangle`/`animation_id`). Extended this session with zone authoring (depends on Phase 12, above), a UI-menu editor built on Phase 7's `client/engine/ui/`, and an Action Definitions panel (Phase 10 Step 12's data half only).

### 14.1 — Entry Point / Launcher

- One landing screen (Open Area / New Area / View Asset), shown by `client/game/launcher.py` when the native client starts with no `--area`/`--asset` argument — manifest-driven (`"areas"` category, alongside the existing `"meshes"`/`"entities"`), zero backend connection required
- Asset preview mode generalises and supersedes this document's own Phase 9.2 "Animation Preview" page concept — one orbit-camera viewer with live stylization toggles and animation playback, not a second redundant page

### 14.2 — Full Transform Gizmo

- Mode-switchable (`T`/`R`/`S`) translate/rotate/scale gizmo — axis handles for translate and scale, rotation rings per axis, plus a uniform-scale handle — working in both 2D and 3D, synced live with numeric property-panel fields
- No free-form bounding-box/corner-drag resize (axis and uniform handles only) and no multi-select — explicit scope boundaries

### 14.3 — Undo/Redo, Property Panel, Asset Browser

- `EditorCommands` command-stack layer wraps `Scene`'s existing API (`add_entity`/`update_entity`/`remove_entity`/`set_camera`/`set_lighting`) — `Scene` itself stays unaware undo exists
- Property panel splits instance-level fields (transform, `render_template`, `ScriptComponent`) — plain edit, no confirmation — from template-level fields (`parts[]`'s `localOffset`/`dangle`/`animation_id`/`action_animations`) — explicit confirm + warning, since a write there changes every placement of that template, everywhere, not just the selected one
- Manifest-driven, searchable asset browser replaces the crude "type a raw asset id" flow from Phase 11.3

### 14.4 — Grid/Snapping and Save Flow

- Ground grid, position snapping, optional rotation snapping, live entity-count/FPS readout
- A Scene Settings panel with explicit "Set Start Camera"/"Set Start Lighting" actions — the only calls to `Scene.set_start_camera()` in the whole system
- Area-save and entity-definition-save finished for real as direct filesystem writes (`open(path, 'w')` — no Flask dev route, matching the native client's direct-filesystem-access convention), both refreshing `manifest.json` after writing so new/edited files are immediately discoverable via the 14.1 launcher; "Load" is the 14.1 launcher, not a second dialog

### 14.5 — Zone Authoring and UI Menu Authoring (added this session)

- Zone placement reuses this phase's own gizmo (AABB) and asset browser (mesh-footprint) rather than inventing new interactions; a property panel edits Phase 12's 8 effect types as repeatable `on_enter`/`on_exit` rows
- A 2D-only UI-menu editor built directly on Phase 7's `client/engine/ui/` real widget functions — the live preview *is* the runtime appearance, not separate editor chrome — with keybind, zone, and entity-interact triggers; zone/entity triggers write back into the *referenced* zone's/entity's own data rather than inventing a parallel mechanism

### 14.6 — Action Definitions Panel (added this session)

- An `actions.json` registry (name + `duration_ms`, the editor-authored equivalent of `backend/engine/example_game_loop.py`'s `ACTION_DURATIONS`) plus a per-part "Action Animations" section assigning a transform clip per action, both undoable and manifest-free (a single well-known asset, like `ui_theme.json`)
- Deliberately data-only: deciding *when* an action fires is real gameplay logic in a game branch's own `player.py`/`actions.py`, not something this panel authors — see `docs/graphics/ACTION_TRIGGERED_ANIMATIONS.md`'s data/trigger split

**Scope note:** No multi-select, no history-panel UI, no custom asset import UI, no terrain tools, no real-time collaborative editing, no visual behaviour-tree/script editor, no new zone shapes/effect types beyond what Phase 12 already defines, no action trigger-wiring (data authoring only).

**Prompt file:** `.github/prompts/level-editor.prompt.md`

---

## Prompt Files

Each phase has a companion agent prompt in `.github/prompts/`. Completed
phases (all steps done) move to `.github/prompts/completed/` to keep the
working directory to just what's still active — a plain relocation, not
a rewrite; see each file's own historical content for what actually
shipped.

| Phase | Prompt file |
| ----- | ----------- |
| 0 | `completed/webgpu-migration.prompt.md` ✅ |
| 1 | `completed/engine-architecture.prompt.md` ✅ |
| 2 | `completed/material-system.prompt.md` ✅ |
| 3 | `completed/ecs-overhaul.prompt.md` ✅ |
| 4 | `completed/simulation-systems.prompt.md` ✅ |
| 5 | `completed/asset-pipeline.prompt.md` ✅ |
| 6 | `completed/save-load.prompt.md` ✅ |
| 7 | `ui-framework.prompt.md` 🔶 in progress |
| 8 | `audio.prompt.md` |
| 9 | `distribution.prompt.md` |
| 10 | `completed/3d-coordinate-mapping.prompt.md` ✅ |
| 11 | `area-system.prompt.md` |
| 12 | `zones.prompt.md` |
| 13 | `completed/wgpu-py-migration.prompt.md` ✅ |
| 14 | `level-editor.prompt.md` |

---

## Sequencing Notes

Phases 1 and 3 are **prerequisites** for everything else — a clean architecture and a proper ECS are the foundation every other phase depends on. Tackle them before adding more features.

Phase 2 is largely independent and can proceed in parallel with Phase 3, since it lives entirely in the JavaScript/WebGPU layer while Phase 3 lives in Python.

Phases 4–9 depend on Phase 3 completing. They can largely proceed in any order after that, with one exception: the save/load format (Phase 6.1) should be stabilised before Phase 4 adds many new component types, to avoid excessive migration work.
