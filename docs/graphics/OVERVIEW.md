# Graphics System — Overview

## Goals

Prefer explicit control and mathematical clarity over convenience abstractions. Prioritise efficiency in the rendering path — minimise draw calls, GPU state changes, and CPU-GPU data transfers.

---

## Current System: Sprite Atlas + Animation Clips

The renderer uses a **sprite atlas** (sprite sheet): a single image containing all animation frames packed into a grid. Each rendered frame is a **sub-region blit** — the source rectangle (frame column × width, frame row × height) is drawn to a destination rectangle on the canvas via `drawImage`.

Animation sequences are defined as **animation clips** in JSON: ordered lists of frame indices with per-frame durations. This data-driven approach is good — it separates art data from engine code. The JSON can be compiled to a tighter binary format (e.g. a flat `Uint16Array` of `[frameIndex, durationMs]` pairs) before deployment if parse time or payload size becomes a concern.

**Limitation of the current approach:** The Canvas 2D API (`getContext('2d')`) provides no programmable shader stage. All per-pixel operations are fixed. Moving to WebGPU is required to implement the planned rendering features.

---

## Platform Targets & WebGPU Status

| Platform | PyWebView engine | WebGPU | Notes |
| --- | --- | --- | --- |
| Windows | Edge WebView2 (Chromium) | **Yes** | Fully supported |
| macOS | WKWebView (WebKit) | **Yes** | Safari 17+ / macOS Sonoma |
| Linux (browser) | Chrome 121+ | **Yes** | Use via `run_browser.py` |
| Linux (PyWebView) | WebKitGTK | **No** | Not yet in stable releases |

**Current decision:** Commit to **WebGPU** as the primary rendering API. The Linux PyWebView packaged build is deferred until WebKitGTK ships stable WebGPU support.

**Linux development workflow:** Use Chrome via `run_browser.py` for all development and testing on Linux. The packaged app on Linux will be unshippable during this period — this is accepted.

> **TRACK:** Monitor WebKitGTK WebGPU progress. Check the [WebKit Feature Status](https://webkit.org/status/) page for `WebGPU` and follow WebKitGTK release notes. Once WebGPU ships in a stable WebKitGTK release that is widely available in major Linux distributions, the Linux PyWebView build is unblocked.

---

## Frontend Engine Directory Structure

Following the engine–game separation (Phase 1 of [ROADMAP.md](../../ROADMAP.md)), frontend JavaScript is split into two namespaces. The layout below shows the **target state** after Phase 1 completes; Phase 0 systems currently live under `frontend/js/` and `frontend/js/sprites/` pending the restructure.

```text
frontend/js/
  engine/               ← reusable engine infrastructure
    renderer.js         ← WebGPU render coordinator
    entityRenderer.js   ← per-entity animation and GPU draw
    interpolation.js    ← position interpolation (10 TPS → 60 FPS)
    input.js            ← raw input event stream
    network.js          ← SocketIO abstraction
    assetLoader.js      ← asset registry; resolves keys to file paths
    sprites/
      shaderCache.js    ← WGSL pipeline compilation and caching
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
- [RENDER_WORKFLOWS.md](RENDER_WORKFLOWS.md) — Practical per-feature shader workflows
- [DATA_STRUCTURES.md](DATA_STRUCTURES.md) — JSON schemas for animation clips, materials, entities
- [ROADMAP.md](../../ROADMAP.md) — Full engine packaging roadmap; graphics work is Phase 0 (complete) and Phase 2
