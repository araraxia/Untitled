---
agent: agent
description: Migrate the renderer from Canvas 2D to WebGPU following the design in docs/graphics/.
tools:
  - read_file
  - create_file
  - replace_string_in_file
  - multi_replace_string_in_file
  - grep_search
  - file_search
  - get_errors
---

# Task: Migrate Renderer — Canvas 2D → WebGPU

You are migrating the rendering system from the Canvas 2D API to WebGPU. Follow the design documents in `docs/graphics/` exactly. Do not add features beyond what is specified in those documents. Work through the steps below in order; complete and verify each step before moving to the next.

## Required Reading

Read these files before writing any code:

- `docs/graphics/OVERVIEW.md` — migration path, platform notes, new systems table
- `docs/graphics/COORDINATE_MAPPING.md` — UV computation, MVP matrix
- `docs/graphics/COMBINER.md` — bind group layout, material system, WGSL shader sketch
- `docs/graphics/RENDER_WORKFLOWS.md` — Workflow A (the target for this migration step)
- `docs/graphics/DATA_STRUCTURES.md` — animation clip and entity JSON schemas
- `frontend/js/renderer.js` — current Canvas 2D renderer (understand before replacing)
- `frontend/js/sprites/spritesheet.js` — current SpriteSheet class
- `frontend/js/entityRenderer.js` — current EntityRenderer class

## Constraints

- All shaders must be written in **WGSL**. Do not use GLSL.
- Do not use `getContext('2d')` anywhere in new code.
- The Canvas 2D render path (`ctx.drawImage`, `ctx.fillRect`, etc.) must remain intact until Step 5 confirms the WebGPU path produces correct output. Gate on a feature flag rather than deleting the old code immediately.
- Keep `console.log` calls consistent with the existing style in the file being edited.
- Follow the JavaScript Airbnb style guide (2-space indent, single quotes).
- Follow PEP 8 for any Python files touched.
- Do not exceed 79 characters per line in Python files.

---

## Step 1 — WebGPU Device Initialisation

**File:** `frontend/js/renderer.js`

Add a WebGPU initialisation path alongside the existing Canvas 2D init. The existing `initRenderer` function must continue to work unchanged.

Tasks:

1. Add a module-level `let gpuDevice = null;` variable.
2. Create an `async function initWebGPU()` that:
   - Calls `navigator.gpu?.requestAdapter()`. If the result is `null` or `navigator.gpu` is absent, logs a clear warning and returns `false`.
   - Calls `adapter.requestDevice()`.
   - Stores the device in `gpuDevice`.
   - Configures the WebGPU canvas context: call `canvas.getContext('webgpu')` and `gpuContext.configure(...)` with `device`, `format: navigator.gpu.getPreferredCanvasFormat()`, and `alphaMode: 'premultiplied'`.
   - Returns `true` on success.
3. Call `initWebGPU()` at the end of `initRenderer`, after the Canvas 2D setup.
4. Export or expose `gpuDevice` so other modules can access it.

Verify: no existing tests break, the Canvas 2D path still renders, and `gpuDevice` is non-null in a WebGPU-capable browser (check via console).

---

## Step 2 — WGSL Shader Module

**New file:** `frontend/js/sprites/shaderCache.js`

Create a shader cache module responsible for compiling and caching `GPURenderPipeline` objects.

Tasks:

1. Define the WGSL source for the **sprite pipeline** (Workflow A from `RENDER_WORKFLOWS.md`):
   - Vertex shader: takes `@location(0) pos: vec2<f32>` and `@location(1) uv: vec2<f32>`, applies `mvp` mat4 uniform, outputs position + UV varying.
   - Fragment shader: samples `u_albedo` texture at the interpolated UV (see Workflow A).
   - Uniform buffer layout: `mvp: mat4x4<f32>`, `uv_rect: vec4<f32>` (u0, v0, u1, v1), `tint: vec4<f32>`.
2. Create `function createSpritePipeline(device, format)` that compiles the shader module and returns a `GPURenderPipeline`.
3. Create a `ShaderCache` class with:
   - `constructor(device, format)` — stores device and format.
   - `getSpritePipeline()` — lazily creates and caches the pipeline, returns it.
4. Export `ShaderCache`.

---

## Step 3 — GPUBuffer Helpers

**New file:** `frontend/js/sprites/gpuBuffers.js`

Tasks:

1. `function createUniformBuffer(device, byteSize)` — wraps `device.createBuffer` with `UNIFORM | COPY_DST` usage.
2. `function writeUniformBuffer(device, buffer, data)` — wraps `device.queue.writeBuffer`.
3. `function createQuadVertexBuffer(device)` — creates a static `VERTEX` buffer from 6 vertices (two triangles, CCW winding) forming a unit quad with UVs `[0,0]→[1,1]`. Vertex layout: `[x, y, u, v]` as `f32` — 4 floats × 6 vertices = 256 bytes.
4. Export all three functions.

---

## Step 4 — WebGPU SpriteSheet

**New file:** `frontend/js/sprites/gpuSpriteSheet.js`

This replaces `SpriteSheet` for the WebGPU path. The Canvas 2D `SpriteSheet` class must not be modified.

Tasks:

1. Create `class GPUSpriteSheet` with:
   - `constructor(device, imagePath, frameWidth, frameHeight, columns, rows)` — mirrors the Canvas 2D `SpriteSheet` constructor signature.
   - `async load()` — fetches the image via `fetch` + `createImageBitmap`, uploads to a `GPUTexture` via `device.queue.copyExternalImageToTexture`, creates a `GPUSampler` with `minFilter: 'linear'`, `magFilter: 'nearest'` (pixel art).
   - `getUVRect(frameIndex)` — returns a `Float32Array([u0, v0, u1, v1])` for the given frame index. Uses the same column/row arithmetic as `SpriteSheet.drawFrame`.
   - `createBindGroup(device, pipeline, uniformBuffer)` — creates and returns a `GPUBindGroup` binding the loaded texture, sampler, and provided uniform buffer to bind group index 0.
2. `get loaded()` — returns `true` once `load()` has completed.
3. Export `GPUSpriteSheet`.

---

## Step 5 — WebGPU Render Path in EntityRenderer

**File:** `frontend/js/entityRenderer.js`

Read the existing `EntityRenderer` class fully before editing.

Tasks:

1. Add an optional `useGPU` flag to `EntityRenderer` (default `false`). When `true`, use the GPU path; when `false`, retain the existing Canvas 2D path unmodified.
2. When `useGPU` is `true`:
   - In the constructor, create a `GPUSpriteSheet` instead of `SpriteSheet`.
   - Change the `drawEntity` signature to `drawEntity(entity, camera, passEncoder = null)`. The `passEncoder` argument is a `GPURenderPassEncoder` provided by the caller; it is only used when `useGPU` is `true` and must not be `null` in that path.
   - In `drawEntity`, instead of calling `spriteSheet.drawFrame`:
     a. Compute the MVP matrix from the entity's world position and the camera (2D orthographic — see `COORDINATE_MAPPING.md`).
     b. Write MVP, UV rect (from `GPUSpriteSheet.getUVRect`), and tint `(1,1,1,1)` into the uniform buffer.
     c. Record draw commands onto `passEncoder`: call `passEncoder.setPipeline`, `passEncoder.setBindGroup`, `passEncoder.setVertexBuffer`, then `passEncoder.draw(6)`. Do **not** begin or end a render pass here — the encoder is owned by `renderer.js`.
3. The existing Canvas 2D `drawEntity(entity, camera)` path must remain fully functional (the extra `passEncoder` parameter is ignored when `useGPU` is `false`).

---

## Step 6 — Wire Up in renderer.js

**File:** `frontend/js/renderer.js`

Tasks:

1. After `initWebGPU()` succeeds, set a module-level `let useGPU = true;` flag.
2. Pass `useGPU` when constructing `EntityRenderer` instances in `getEntityRenderer`.
3. Update `renderEntities(gameState, deltaTime)` to accept an optional third parameter: `renderEntities(gameState, deltaTime, passEncoder = null)`. Thread `passEncoder` through to each `renderer.drawEntity(entity, camera, passEncoder)` call. When `useGPU` is `false`, `passEncoder` is `null` and `drawEntity` ignores it.
4. In `render()`, when `useGPU` is true:
   - Begin a `GPUCommandEncoder`.
   - Begin a render pass targeting `gpuContext.getCurrentTexture().createView()` with `loadOp: 'clear'` (clear colour `#2a2a2a`, matching the existing `ctx.fillStyle`) and `storeOp: 'store'`.
   - Call `renderEntities(gameState, deltaTime, passEncoder)`, passing the active `GPURenderPassEncoder`.
   - Call `passEncoder.end()` after `renderEntities` returns.
   - Submit the finished command buffer via `gpuDevice.queue.submit([commandEncoder.finish()])`.
   - Skip the Canvas 2D `ctx.fillRect` / `ctx.drawImage` calls.
5. Keep the Canvas 2D path active when `useGPU` is false.

---

## Step 7 — Verify & Clean Up

Tasks:

1. Run the application (`main.py` or `run_browser.py`). Confirm sprites render at correct positions with correct frame selection — output should be visually identical to the Canvas 2D path.
2. Confirm the debug grid still draws (it uses Canvas 2D directly — it can remain as a Canvas 2D overlay for now, drawn to a second `<canvas>` element layered on top, or simply disabled).
3. Run `get_errors` on all modified files and fix any reported issues.
4. Remove the `useGPU = false` fallback code paths only after confirming Step 7.1.

---

## Success Criteria

- [x] `gpuDevice` is acquired without errors in Chrome/Edge on Windows.
- [x] Sprites render at the correct screen position with the correct animation frame.
- [x] Horizontal flip (`flipX`) works correctly (negate X scale in the MVP matrix).
- [x] No Canvas 2D `drawImage` calls remain in the active render path.
- [x] No GLSL shader source exists anywhere in the codebase.
- [x] `get_errors` reports zero errors on all modified files.
- [x] `docs/graphics/OVERVIEW.md` migration step 1 and 2 are done; update the migration path section to reflect current status if steps are completed.
