# Graphics System — Overview

> **Note:** This doc was written during the Phase 0/2 WebGPU migration and much of it (the "Migration Path" checklist, "New Systems Required" table, and "target state" framing below) is a snapshot from that period — Phases 1–6 have since completed and Phase 10 (3D rendering) is in progress, ahead of what's described here. [ROADMAP.md](../../ROADMAP.md) is authoritative for current status; treat the historical sections below as background on how the WebGPU pipeline came to exist, not as a live status board.

## Goals

Prefer explicit control and mathematical clarity over convenience abstractions. Prioritise efficiency in the rendering path — minimise draw calls, GPU state changes, and CPU-GPU data transfers.

---

## Current System: WebGPU, with Canvas 2D as a Compatibility Fallback

WebGPU is the primary, live rendering path (see `initWebGPU()`/`useGPU` in `frontend/js/engine/renderer.js`) — this is no longer aspirational. `entityRenderer.js` dispatches each entity, per-frame, to whichever draw path its data calls for: a 2D sprite atlas blit, a depth-tested 2.5D camera-facing billboard, or a fully 3D textured mesh (`render_template` → mesh + material, Phase 10 Step 5). Canvas 2D (`getContext('2d')`) only remains as the fallback path when `navigator.gpu.requestAdapter()` fails — it has no programmable shader stage and cannot express materials, lighting, or 3D at all, so entities render flat there regardless of their configured dimensionality.

Both the sprite path and the mesh path are backed by the same underlying data-driven idea: a **sprite atlas** (or mesh vertex/index buffer) holds the geometry/pixels, and **animation clips** (JSON: ordered frame indices with per-frame durations) or **material JSON** drive how it's drawn, keeping art data separate from engine code.

---

## Platform Targets & WebGPU Status

> **This entire section describes a problem that no longer exists and referenced files that have since been deleted.** It was written when this project's only options were a PyWebView window (blocked on Linux by WebKitGTK's incomplete WebGPU) or a system browser tab via `run_browser.py`. As of `.github/prompts/wgpu-py-migration.prompt.md`, the desktop client is native (`client/`, GLFW + `wgpu-py` + `imgui-bundle`) and works identically on Windows and Linux without depending on *any* browser's WebGPU support — `python main.py` on every platform. The legacy PyWebView/browser client (`frontend/js/`, `run_browser.py`, `run_desktop_test.py`) has been deleted entirely; the table and notes below are kept only as historical background on why WebGPU was chosen, not as current guidance.

| Platform | PyWebView engine | WebGPU | Notes |
| --- | --- | --- | --- |
| Windows | Edge WebView2 (Chromium) | **Yes** | Fully supported |
| macOS | WKWebView (WebKit) | **Yes** | Safari 17+ / macOS Sonoma |
| Linux (browser) | Chrome 121+ | **Yes** | Historical — the browser client this row describes no longer exists |
| Linux (PyWebView) | WebKitGTK | **No** | Historical — no longer relevant, `client/` doesn't use PyWebView |

**Historical, no longer the current decision:** ~~Commit to **WebGPU** as the primary rendering API. The Linux PyWebView packaged build is deferred until WebKitGTK ships stable WebGPU support.~~ Superseded: `client/`'s native `wgpu-py` client ships on Linux today, no deferral.

**Historical Linux development workflow, no longer possible to follow:** ~~Use Chrome via `run_browser.py` for all development and testing on Linux.~~ `run_browser.py` has been deleted; use `python main.py` instead.

> **TRACK (resolved, kept for context):** this used to track WebKitGTK's WebGPU progress as a blocker for the Linux PyWebView build. It's no longer a blocker for anything — the native `client/` app sidesteps WebKitGTK entirely.

**Historical caveat, no longer relevant:** the browser-mode WebGPU-support caveat that used to live here no longer applies to anything current — `client/`'s native `wgpu-py` device doesn't depend on a browser at all, and the script it described (`run_browser.py`) has been deleted.

---

## Frontend Engine Directory Structure (historical — this JavaScript tree has been deleted)

Following the engine–game separation (Phase 1 of [ROADMAP.md](../../ROADMAP.md), complete), frontend JavaScript used to be split into two namespaces below. **This entire `frontend/js/` tree has since been deleted** (`.github/prompts/wgpu-py-migration.prompt.md`) — the equivalent current layout is `client/engine/`/`client/game/` (Python), described in [ARCHITECTURE.md](../../ARCHITECTURE.md). Kept here only as a record of the JS engine/game split this Python one was ported from.

```text
frontend/js/
  engine/               ← reusable engine infrastructure
    renderer.js         ← WebGPU render coordinator
    entityRenderer.js   ← per-entity draw path: 2D sprite / 2.5D billboard / 3D mesh
    mat4.js             ← 4x4 matrix helpers for 3D camera/model transforms
    mesh.js             ← loads and uploads 3D mesh JSON (vertex/index buffers)
    interpolation.js    ← position interpolation (20 TPS → 60 FPS)
    input.js            ← raw input event stream
    network.js          ← SocketIO abstraction
    assetLoader.js      ← asset registry; resolves keys to file paths
    sprites/
      shaderCache.js    ← WGSL pipeline compilation and caching (sprite + mesh variants)
      gpuBuffers.js     ← GPU buffer helpers (uniform, vertex)
      gpuSpriteSheet.js ← WebGPU counterpart to Canvas 2D SpriteSheet
      materialLoader.js ← builds GPUBindGroup objects from material JSON
  game/                 ← game-specific content; calls into engine API only
    characterCreation.js
    playerSelect.js
    ui.js               ← game-specific UI panels
```

Engine modules have no knowledge of game rules. Game modules call into the engine API but must not reach into engine internals.

The backend mirrors this split: `backend/engine/` (ECS, spatial, game loop) versus `backend/game/` (entities, systems, world). See [ROADMAP.md](../../ROADMAP.md) Phase 1 for the full restructure plan and prompt file.

---

## Migration Path: Canvas 2D → WebGPU

1. ✅ **Acquire a GPUDevice** at startup via `navigator.gpu.requestAdapter()` → `requestDevice()`. Gate the entire rendering path on this succeeding; fall back to an error screen if WebGPU is unavailable. *(implemented in `frontend/js/renderer.js` — `initWebGPU()`, `useGPU` flag)*
2. ✅ **Port the sprite blit** to a WebGPU render pipeline: a vertex buffer with positions + UVs, a `GPURenderPipeline` with a minimal WGSL vertex + fragment shader pair, equivalent to the current `drawImage` call. *(implemented across `shaderCache.js`, `gpuBuffers.js`, `gpuSpriteSheet.js`, `entityRenderer.js`, `renderer.js`)*
3. **Introduce the material system**: define bind group layouts for texture bindings and uniform buffers; extend `SpriteSheet` / `EntityRenderer` to create and bind `GPUBindGroup` objects per draw call.
4. **Add parameter map support**: write the Python channel-packing tool, generate param maps for existing assets, upload as `GPUTexture` objects, update material JSON.
5. **Implement the combiner**: parameterise the WGSL fragment shader so the combiner formula is driven by material data rather than being hardcoded.
6. **Add a lighting pass**: a second render pass accumulates additive point-light contributions; the pass reads light-entity positions from a uniform array and outputs a screen-space light buffer multiplied into the base pass. Lights are entities carrying a `light` component (ROADMAP Phase 2.4).
7. **Particle system via compute**: move particle position and velocity integration to a `GPUComputePipeline` so particle state lives entirely on the GPU. The render pass reads the particle storage buffer directly without a CPU round-trip (ROADMAP Phase 2.5).

This migration can be done incrementally — each step is independently testable.

---

## New Systems Required

Paths show the target layout after Phase 1 restructure. Phase 0 systems are ✅ implemented at their original paths pending that move.

| System | Target location | Status |
| --- | --- | --- |
| WebGPU renderer | `frontend/js/engine/renderer.js` | ✅ Phase 0 — device, canvas context, render loop |
| Entity renderer | `frontend/js/engine/entityRenderer.js` | ✅ Phase 0 — per-entity GPU draw path |
| WGSL shader cache | `frontend/js/engine/sprites/shaderCache.js` | ✅ Phase 0 — sprite pipeline, `ShaderCache` class |
| GPU buffer helpers | `frontend/js/engine/sprites/gpuBuffers.js` | ✅ Phase 0 — uniform + quad vertex buffers |
| GPU sprite sheet | `frontend/js/engine/sprites/gpuSpriteSheet.js` | ✅ Phase 0 — texture load, UV rect, bind group |
| Material loader | `frontend/js/engine/sprites/materialLoader.js` | Phase 2 — `GPUBindGroup` from `material/*.json` |
| Asset loader | `frontend/js/engine/assetLoader.js` | Phase 2 — asset registry; resolves keys to paths |
| Lighting pass | `frontend/js/engine/sprites/` | Phase 2 — point-light accumulation render pass |
| Particle compute | `frontend/js/engine/sprites/` | Phase 2 — `GPUComputePipeline` particle simulation |
| Channel-pack tool | `tools/pack_param_map.py` | Phase 2 — Python source-asset pre-processing |
| Parameter map assets | `frontend/assets/images/param_maps/` | Phase 2 — packed RGBA textures as `GPUTexture` |
| Material definitions | `frontend/assets/data/material/` | JSON; one file per material type |
| Overlay animation clips | `frontend/assets/data/animation/` | JSON; same schema as base animation clips |

---

## Further Reading

- [COMBINER.md](COMBINER.md) — Multi-texture combiner, parameter maps, channel packing
- [COORDINATE_MAPPING.md](COORDINATE_MAPPING.md) — UV coordinates, 2D and 3D projection
- [MAT4.md](MAT4.md) — `client/engine/mat4.py`'s matrix layout, function reference, Euler rotation convention, and how callers chain P/V/M into an MVP
- [RENDER_WORKFLOWS.md](RENDER_WORKFLOWS.md) — Practical per-feature shader workflows
- [DATA_STRUCTURES.md](DATA_STRUCTURES.md) — JSON schemas for animation clips, materials, entities
- [ACTION_TRIGGERED_ANIMATIONS.md](ACTION_TRIGGERED_ANIMATIONS.md) — one-shot animations for a discrete server-authoritative action (attack, jump), backend timing + both client draw paths
- [AREA_SYSTEM.md](AREA_SYSTEM.md) — `Scene`, the standalone viewer/builder tool, and the four run modes (Phase 11, `Scene`/`area_viewer.py` done on `engine`; backend Area-file schema pending a game branch)
- [3D_ASSET_AUTHORING.md](3D_ASSET_AUTHORING.md) — Blender → mesh pipeline for 3D content; both the textured-mesh render path and the Blender/glTF authoring side (`tools/convert_mesh.py`) are implemented (Phase 10, steps 1–11 of 14 done)
- [ROADMAP.md](../../ROADMAP.md) — Full engine packaging roadmap; authoritative for current phase status
