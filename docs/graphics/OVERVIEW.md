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

## Migration Path: Canvas 2D → WebGPU

1. **Acquire a GPUDevice** at startup via `navigator.gpu.requestAdapter()` → `requestDevice()`. Gate the entire rendering path on this succeeding; fall back to an error screen if WebGPU is unavailable.
2. **Port the sprite blit** to a WebGPU render pipeline: a vertex buffer with positions + UVs, a `GPURenderPipeline` with a minimal WGSL vertex + fragment shader pair, equivalent to the current `drawImage` call.
3. **Introduce the material system**: define bind group layouts for texture bindings and uniform buffers; extend `SpriteSheet` / `EntityRenderer` to create and bind `GPUBindGroup` objects per draw call.
4. **Add parameter map support**: write the Python channel-packing tool, generate param maps for existing assets, upload as `GPUTexture` objects, update material JSON.
5. **Implement the combiner**: parameterise the WGSL fragment shader so the combiner formula is driven by material data rather than being hardcoded.
6. **Exploit compute shaders** (later): move particle simulation, spatial queries, or animation bone blending to `GPUComputePipeline` to offload the CPU game loop.

This migration can be done incrementally — the Canvas 2D path can remain active while the WebGPU pipeline is built alongside it.

---

## New Systems Required

| System | Location | Notes |
| --- | --- | --- |
| WebGPU renderer | `frontend/js/renderer.js` | Replace Canvas 2D context; acquire `GPUDevice` |
| WGSL shader cache | `frontend/js/sprites/` | Compile + cache `GPURenderPipeline` objects |
| Material loader | `frontend/js/sprites/` | Create bind group layouts and `GPUBindGroup` per material |
| Channel-pack tool | `tools/pack_param_map.py` | Python pre-processing script |
| Parameter map assets | `frontend/assets/images/param_maps/` | GPU-ready packed textures uploaded as `GPUTexture` |
| Material definitions | `frontend/assets/data/material/` | JSON; one file per material type |
| Overlay animation clips | `frontend/assets/data/animation/` | JSON; same schema as base animation clips |

---

## Further Reading

- [COMBINER.md](COMBINER.md) — Multi-texture combiner, parameter maps, channel packing
- [COORDINATE_MAPPING.md](COORDINATE_MAPPING.md) — UV coordinates, 2D and 3D projection
- [RENDER_WORKFLOWS.md](RENDER_WORKFLOWS.md) — Practical per-feature shader workflows
- [DATA_STRUCTURES.md](DATA_STRUCTURES.md) — JSON schemas for animation clips, materials, entities
