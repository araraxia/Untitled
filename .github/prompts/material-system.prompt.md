---
agent: agent
description: Complete the material system, parameter maps, combiner shader, lighting pass, and particle system (Phase 2 of ROADMAP.md).
tools:
  - read_file
  - create_file
  - replace_string_in_file
  - multi_replace_string_in_file
  - grep_search
  - file_search
  - get_errors
  - run_in_terminal
---

# Task: Graphics Pipeline Completion (Phase 2)

You are extending the WebGPU rendering pipeline from a simple sprite blit (Workflow A) to the full material system described in `docs/graphics/`. This is Phase 2 of `ROADMAP.md`. Complete all steps in order; verify each step produces correct visual output before proceeding to the next.

## Required Reading

Read these files before writing any code:

- `ROADMAP.md` — Phase 2 specification
- `docs/graphics/OVERVIEW.md` — migration path steps 3–7; new systems table
- `docs/graphics/COMBINER.md` — bind group layout, parameter maps, WGSL shader sketch, material JSON
- `docs/graphics/RENDER_WORKFLOWS.md` — Workflow A (existing), B (overlay), C (colour ramp, hue shift, cosine)
- `docs/graphics/DATA_STRUCTURES.md` — full material and entity JSON schemas
- `frontend/js/sprites/shaderCache.js` — existing pipeline (Workflow A only)
- `frontend/js/sprites/gpuSpriteSheet.js` — existing albedo-only bind group
- `frontend/js/entityRenderer.js` — existing draw path; understands how `ShaderCache` and `GPUSpriteSheet` are used
- `frontend/js/renderer.js` — render loop entry point
- `frontend/assets/data/material/material-example-lantern.json` — example material
- `frontend/assets/data/entity/entity-example-lantern.json` — example entity referencing that material
- `tools/pack_param_map.py` — existing Python channel-packing tool

## Constraints

- All shaders must be written in **WGSL**. Do not use GLSL.
- Follow the JavaScript Airbnb style guide: 2-space indent, single quotes.
- Follow PEP 8 for any Python files touched; max 79 characters per line.
- Do not break the existing Workflow A render path at any point. Gate new functionality on material flags so entities without a material definition continue to render exactly as before.
- Do not move or rename existing JS files. The frontend restructure into `engine/` and `game/` directories is a separate task deferred until after Phase 2.
- Do not alter any Python backend files in this task.
- Do not add features beyond what is scoped in each step.

---

## Step 1 — Audit Current State

Before writing any code, read the four key JS files (`shaderCache.js`, `gpuSpriteSheet.js`, `entityRenderer.js`, `renderer.js`) and the example material/entity JSON files. Produce a short summary covering:

1. What bind group slots are currently defined in `shaderCache.js` (bindings 0–2 for Workflow A).
2. How `EntityRenderer` selects which `GPUSpriteSheet` to use per entity.
3. How animation frame UV rects are currently written into the uniform buffer.
4. What fields are present and absent in the example material JSON compared to `DATA_STRUCTURES.md`.

Do not create or edit any files in this step. Output your findings and then proceed.

---

## Step 2 — `MaterialLoader` Class

**New file:** `frontend/js/sprites/materialLoader.js`

Create a `MaterialLoader` class that reads material JSON files and builds `GPUBindGroup` objects.

### Bind group layout (expand the existing layout from 3 bindings to 4):

| Binding | Resource | Description |
| ------- | -------- | ----------- |
| 0 | `GPUBuffer` (uniform) | `mvp`, `uv_rect`, `uv_overlay`, `tint`, `intensity`, `time`, `ramp_steps` |
| 1 | `GPUTexture` (albedo) | Sprite atlas — the base animation frames |
| 2 | `GPUTexture` (param map) | RGBA parameter map (`null` → 1×1 black fallback) |
| 3 | `GPUSampler` | Shared sampler for all texture slots |

### `MaterialLoader` API:

```js
class MaterialLoader {
  constructor(device) { ... }

  // Fetch and parse a material JSON file, upload textures, build bind group.
  // Returns a Promise<MaterialHandle>.
  async load(materialJsonPath) { ... }

  // Return a previously loaded handle by material id.
  get(materialId) { ... }
}
```

### `MaterialHandle` object shape:

```js
{
  id: string,
  bindGroup: GPUBindGroup,       // ready to pass to setBindGroup(0, ...)
  uniformBuffer: GPUBuffer,      // caller writes per-frame uniforms here
  flags: {
    hasParamMap: boolean,
    hasOverlay: boolean,
    hasColorRamp: boolean,
  },
  overlays: [                    // one entry per overlay in material JSON
    { animationId: string, blendMode: string, intensity: number }
  ]
}
```

### Tasks:

1. `async _loadTexture(key)` — fetches the image at the given asset key path, uploads it to a `GPUTexture` with `usage: TEXTURE_BINDING | COPY_DST | RENDER_ATTACHMENT`, returns the texture.
2. For `param_map: null` in the material JSON, create a 1×1 black RGBA fallback texture so the bind group slot is always populated.
3. Create the uniform buffer with `usage: UNIFORM | COPY_DST`; size it to hold the struct defined in Step 3.
4. Store the bind group layout explicitly (do not use `layout: 'auto'`) so `ShaderCache` can share it.

Verify: `python -m http.server` or the Flask dev server. Import `MaterialLoader` in the browser console and call `load()` with the lantern material path — it should resolve without errors and log the bind group.

---

## Step 3 — Update `ShaderCache` for Material Pipelines

**File:** `frontend/js/sprites/shaderCache.js`

Extend `ShaderCache` to support multiple pipeline variants driven by material flags.

### Updated uniform buffer struct (WGSL):

```wgsl
struct Uniforms {
  mvp        : mat4x4<f32>,
  uv_rect    : vec4<f32>,   // (u0,v0,u1,v1) base frame in atlas
  uv_overlay : vec4<f32>,   // (u0,v0,u1,v1) overlay frame (Workflow B)
  tint       : vec4<f32>,   // flat tint colour (r,g,b,a)
  intensity  : f32,         // overlay blend strength
  time       : f32,         // game time in seconds (for animated effects)
  ramp_steps : f32,         // colour ramp quantisation (0 = smooth)
  _pad       : f32,         // align to 16 bytes
};
```

### Pipeline variants:

| Variant key | Material flags | Fragment shader behaviour |
| ----------- | -------------- | ------------------------- |
| `'base'` | none | Workflow A — straight albedo sample × tint |
| `'overlay'` | `hasOverlay: true` | Workflow B — base + additive overlay gated by param map A channel |
| `'ramp'` | `hasColorRamp: true` | Workflow C option 3 — gradient map remap |
| `'hue'` | `hue_shift` runtime key present | Workflow C option 2 — HSV hue rotation |

### Tasks:

1. Write four WGSL fragment shader strings (`FS_BASE`, `FS_OVERLAY`, `FS_RAMP`, `FS_HUE`). Use the code from `RENDER_WORKFLOWS.md` as the source of truth.
2. `createMaterialPipeline(device, format, bindGroupLayout, variantKey)` — creates a pipeline for the given variant using the explicit bind group layout from `MaterialLoader`.
3. `getMaterialPipeline(variantKey)` — lazily creates and caches; returns the pipeline. Falls back to `'base'` for unknown keys.
4. Keep the existing `getSpritePipeline()` method working for entities that do not have a material (`layout: 'auto'`). This preserves full backward compatibility.

Verify: call `shaderCache.getMaterialPipeline('base')` in the browser console — it should return a `GPURenderPipeline` without errors.

---

## Step 4 — Extend `GPUSpriteSheet` for Param Maps

**File:** `frontend/js/sprites/gpuSpriteSheet.js`

Add an optional second texture slot for param maps, matching the new 4-binding layout.

### Tasks:

1. Add an optional `paramMapPath` parameter to the constructor (default `null`).
2. In `load()`: if `paramMapPath` is non-null, fetch and upload it as a second `GPUTexture`. If null, use the 1×1 black fallback from `MaterialLoader`.
3. Add `createMaterialBindGroup(pipeline, uniformBuffer, paramTexture, sampler)` method that builds a bind group using the explicit layout (binding 0=uniform, 1=albedo, 2=param, 3=sampler).
4. Keep the existing `createBindGroup(pipeline, uniformBuffer)` method intact (3-binding layout) for the backward-compatible Workflow A path.

Verify: instantiate a `GPUSpriteSheet` with the lantern atlas path. Call `createMaterialBindGroup(...)` — it should return a `GPUBindGroup` without errors.

---

## Step 5 — Wire `EntityRenderer` to Use Materials

**File:** `frontend/js/entityRenderer.js`

Connect `MaterialLoader` into the entity draw path so entities that reference a `material_id` in their data use the material pipeline, and entities without one continue using the existing Workflow A path.

### Tasks:

1. Add a `MaterialLoader` instance as a property of `EntityRenderer`. Lazy-initialise it on first use.
2. In the entity load/init path: if an entity's data contains `material_id`, call `materialLoader.load(materialJsonPath)` and store the resulting `MaterialHandle` keyed by `entity_id`.
3. In the draw path (`drawEntity` or equivalent):
   - If a `MaterialHandle` exists for the entity: use `getMaterialPipeline(variantKey)` (choosing the variant from `handle.flags`), bind `handle.bindGroup`, and write the expanded uniform struct (including `uv_overlay`, `intensity`, `time`, `ramp_steps`).
   - Otherwise: use the existing `getSpritePipeline()` and the 3-binding bind group (old path unchanged).
4. For overlay entities: advance the overlay animation clip independently from the base clip, compute `uv_overlay`, and write it into the uniform buffer before the draw call.
5. Expose a `setEntityRuntime(entityId, key, value)` method that writes named runtime values (`glow_intensity`, `hue_shift`, `tint`, `ramp_steps`) into the entity's uniform buffer slot.

Verify: place the lantern entity in the scene. It should render with its glow overlay pulsing. Non-lantern entities must render identically to before.

---

## Step 6 — Lighting Pass (Phase 2.4)

**New file:** `frontend/js/sprites/lightingPass.js`

Add a second render pass that accumulates additive point-light contributions and multiplies the result into the base pass output.

### Design:

- Lights are entities carrying a `light` component; the Python backend includes light entity state in the normal `state_update` SocketIO event.
- The lighting pass reads up to 32 lights from a uniform array (sufficient for indoor areas). This avoids a storage buffer and keeps the implementation forward-compatible with the deferred approach.
- The pass renders a full-screen quad; per-pixel contribution is the sum of `intensity × falloff(distance)` for all active lights.

### Uniform buffer struct (WGSL):

```wgsl
struct Light {
  pos    : vec2<f32>,   // world position
  color  : vec4<f32>,   // (r, g, b, radius)
  // radius encoded in color.a to avoid alignment padding
};

struct LightUniforms {
  view_proj  : mat4x4<f32>,
  count      : u32,
  _pad       : array<u32, 3>,
  lights     : array<Light, 32>,
};
```

### Tasks:

1. Create `LightingPass` class with:
   - `constructor(device, format, basePassTexture)` — stores refs; creates the full-screen quad vertex buffer.
   - `updateLights(lightsArray)` — writes a `LightUniforms` buffer from `[{ x, y, color, radius }]`.
   - `render(commandEncoder, outputTextureView)` — encodes the lighting pass into the command encoder.
2. Write a WGSL fragment shader that loops over `u.count` lights, computes `1.0 / (1.0 + dist² / radius²)` falloff, accumulates contributions, and outputs the accumulated light colour multiplied by the base pass colour sample.
3. In `renderer.js`: after the base sprite pass, if `LightingPass` is active, encode the lighting pass into the same `GPUCommandEncoder` before submit.
4. Add a `registerLight(entityId, color, radius)` / `unregisterLight(entityId)` API on `EntityRenderer` that `LightingPass` queries each frame.

Verify: add a light entity in the scene data. The area around it should be brightened with a soft falloff. Remove the entity — the light should disappear.

---

## Step 7 — Particle System via Compute (Phase 2.5)

**New file:** `frontend/js/sprites/particleSystem.js`

Move particle simulation to a `GPUComputePipeline` so particle state lives entirely on the GPU.

### Particle struct (WGSL / JS layout must match):

```wgsl
struct Particle {
  pos      : vec2<f32>,
  vel      : vec2<f32>,
  color    : vec4<f32>,
  lifetime : f32,   // remaining seconds; < 0 = dead
  size     : f32,
  _pad     : vec2<f32>,
};
```

### Tasks:

1. `ParticleSystem` class:
   - `constructor(device, maxParticles)` — allocates a `GPUBuffer` with `STORAGE | VERTEX` usage for the particle array; allocates a simulation uniform buffer (`delta_time`, `time`, emitter `pos`, `emit_rate`, `initial_vel`, `spread`).
   - `emit(emitterState)` — CPU writes initial particle state for newly spawned particles into a staging buffer, copies to the GPU particle buffer.
   - `simulate(commandEncoder, deltaTime)` — encodes a compute dispatch (`workgroupSize(64)`; `ceil(maxParticles / 64)` groups) that updates positions, applies velocity damping, decrements lifetime.
   - `render(renderPassEncoder, pipeline)` — binds the particle buffer as a vertex buffer and issues a draw call (one quad per particle via instancing or point sprites).
2. WGSL compute shader: integrate `pos += vel * delta_time`, apply a gravity constant (`0.0, -9.8 * 0.01`), decrement `lifetime`. Dead particles (`lifetime < 0`) are left in place (no compaction needed — they are skipped by alpha = 0).
3. WGSL render shader: use `@builtin(instance_index)` to index into the particle storage buffer; output a billboard quad scaled by `size`, coloured by `color`, faded by `lifetime`.
4. Hook emitter components into `EntityRenderer`: entities with `emitter` in their data get a `ParticleSystem` instance. The entity's world position drives the emitter position each tick.

Verify: attach an emitter to the lantern entity. Particles should stream upward from it, fade out, and restart — with no CPU-side position array at runtime.

---

## Step 8 — Smoke Test

Run the application and confirm:

```text
python main.py
```

Or headlessly:

```cmd
python -c "from backend.app import app; print('app ok')"
```

Visual checks (in browser via `run_browser.py`):

- [ ] Non-material entities render identically to before (Workflow A path unchanged).
- [ ] Lantern entity renders with pulsing glow overlay (Workflow B).
- [ ] A light entity produces a visible soft light contribution on surrounding sprites.
- [ ] Particle emitter on lantern entity streams particles upward.
- [ ] No WebGPU validation errors in the browser console (`GPUValidationError`).
- [ ] No JS errors in the console.

---

## Success Criteria

- [ ] `frontend/js/sprites/materialLoader.js` — `MaterialLoader` class with `load()` and `get()`
- [ ] `frontend/js/sprites/shaderCache.js` — four pipeline variants (`base`, `overlay`, `ramp`, `hue`); existing `getSpritePipeline()` intact
- [ ] `frontend/js/sprites/gpuSpriteSheet.js` — `createMaterialBindGroup()` added; `createBindGroup()` intact
- [ ] `frontend/js/entityRenderer.js` — material path wired in; `setEntityRuntime()` exposed
- [ ] `frontend/js/sprites/lightingPass.js` — `LightingPass` class; GPU-side additive light accumulation
- [ ] `frontend/js/sprites/particleSystem.js` — `ParticleSystem` class; compute + render shaders
- [ ] `tools/pack_param_map.py` — works correctly (already implemented; verify with a test invocation)
- [ ] All entities without a `material_id` continue to render without changes
- [ ] No new Python backend files modified
