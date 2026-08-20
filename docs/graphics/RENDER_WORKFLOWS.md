# Graphics System — Render Workflows

Practical per-feature shader recipes. Each workflow builds on the previous.

Shader pipelines are compiled and cached by `ShaderCache` (`client/engine/shader_cache.py`). Material bind groups — which set up textures and uniforms for a draw call — are created by `MaterialLoader` (`client/engine/material_loader.py`).

> **Historical note:** this document was written for the earlier PyWebView/browser client, whose renderer was JavaScript — `frontend/js/engine/sprites/shaderCache.js`/`materialLoader.js`, `device.queue.writeBuffer(...)`, `class PostProcessState`, etc. That client was deleted entirely during the wgpu-py migration (see `ARCHITECTURE.md`'s Branch model note); the current native client (`client/engine/`, Python) ports the same responsibilities under the file names used above. The WGSL shader code throughout this document is unaffected — WGSL is the same regardless of which language drives the CPU side — but any JavaScript snippets below (buffer-writing helpers, `PostProcessState`, etc.) are illustrative of the *pattern* only and don't correspond to real files anymore; the equivalent CPU-side code today lives in `client/engine/renderer.py`/`entity_renderer.py`/`shader_cache.py`.

---

## Workflow A: Simple Sprite Animation

The baseline — identical visual output to the current `drawImage` blit, rebuilt on the WebGPU pipeline.

**Assets required:**
- One sprite atlas PNG (identical to what exists today).
- No parameter map needed.

**Per-frame CPU work (JS):**

```text
1. Advance animation clip timer by deltaTime.
2. Look up the current frameIndex from the clip's frame list.
3. Compute UV rect from frameIndex:
     u0 = (frameCol * frameW) / atlasW
     v0 = (frameRow * frameH) / atlasH
     u1 = u0 + frameW / atlasW,  v1 = v0 + frameH / atlasH
4. Write quad vertex data (pos + UV) into a mapped GPUBuffer.
5. Update the uniform buffer: MVP matrix, tint = (1,1,1,1), time = 0.
```

**GPU work:**

```wgsl
@fragment
fn fs_main(@location(0) uv: vec2<f32>) -> @location(0) vec4<f32> {
    return textureSample(u_albedo, u_sampler, uv);
}
```

The UV coordinates passed from the vertex shader already select only the current frame's region of the atlas, so the fragment shader is a straight texture read — identical output to `drawImage`.

---

## Workflow B: Primary Animation + Secondary Overlay Animation

Used when a single object needs a **looping base animation** composited with an **independent secondary animation** (e.g. a pulsing glow, a shimmering reflection) whose timing is unrelated to the base.

Both clips advance on independent timers. Both are sampled in the same fragment shader invocation — no extra draw call is needed.

**Assets required:**
- **Atlas A** — base object sprite atlas (e.g. lamp idle frames).
- **Atlas B** — secondary effect atlas (e.g. glow pulse frames, water shimmer frames).
- **Parameter map** — alpha mask channel (A) defining which pixels receive the secondary effect.

**Per-frame CPU work (JS):**

```text
1. Advance base clip timer → frameIndex_A → UV rect_A (in Atlas A).
2. Advance secondary clip timer independently → frameIndex_B → UV rect_B (in Atlas B).
3. Write both UV rects into the uniform buffer.
4. Bind: Atlas A to binding 1, Atlas B to binding 2, param map to binding 3.
```

**GPU work:**

```wgsl
struct Uniforms {
    mvp        : mat4x4<f32>,
    uv_base    : vec4<f32>,   // (u0, v0, u1, v1) for base frame
    uv_overlay : vec4<f32>,   // (u0, v0, u1, v1) for overlay frame
    intensity  : f32,          // overlay blend strength (0–1), driven by game logic
};
@group(0) @binding(0) var<uniform> u      : Uniforms;
@group(0) @binding(1) var u_atlas_base    : texture_2d<f32>;
@group(0) @binding(2) var u_atlas_overlay : texture_2d<f32>;
@group(0) @binding(3) var u_param_map     : texture_2d<f32>;
@group(0) @binding(4) var u_sampler       : sampler;

@fragment
fn fs_main(@location(0) uv: vec2<f32>) -> @location(0) vec4<f32> {
    let base_uv    = u.uv_base.xy    + uv * (u.uv_base.zw    - u.uv_base.xy);
    let overlay_uv = u.uv_overlay.xy + uv * (u.uv_overlay.zw - u.uv_overlay.xy);

    let base    = textureSample(u_atlas_base,    u_sampler, base_uv);
    let overlay = textureSample(u_atlas_overlay, u_sampler, overlay_uv);
    let mask    = textureSample(u_param_map,     u_sampler, uv).a;

    // Additive blend: overlay added on top of base, gated by the mask.
    return base + overlay * mask * u.intensity;
}
```

**Variant — Pulsing light (e.g. a lantern):**
- `Atlas B` contains a few frames of a radial glow at different sizes/opacities.
- The secondary clip loops on a ~1-second cycle, independent of the lamp's idle animation.
- `intensity` is set from game logic (e.g. flicker during low fuel).

**Variant — Water reflection (e.g. a puddle or river tile):**
- `Atlas B` contains a distorted/scrolling copy of the reflected scene (pre-baked or a screen-space capture).
- The secondary clip advances slowly, simulating ripple animation.
- The param map A channel defines the water surface boundary.
- A UV scroll offset in the uniform buffer can move `overlay_uv` over time to fake wave movement without needing many atlas frames.

---

## Workflow C: Colour Range / Palette Remapping

Used when the same sprite needs to be displayed in different colour variants — faction colours, elemental states (fire, ice, poison), status effects — without authoring a separate atlas per variant.

### Option 1: Uniform Tint

The simplest case — multiply every pixel by a flat colour. Useful for team colours, damage/heal flashes, or environmental lighting tint.

**Assets required:** none beyond the base atlas.

```wgsl
@fragment
fn fs_main(@location(0) uv: vec2<f32>) -> @location(0) vec4<f32> {
    return textureSample(u_albedo, u_sampler, uv) * u.tint;
}
```

Set `u.tint = (1.0, 0.4, 0.0, 1.0)` for orange at runtime. No shader recompilation; no extra textures.

### Option 2: HSV Hue Shift

Convert to HSV, rotate the hue by a single float uniform, convert back. One float drives every possible tint of the sprite.

```wgsl
fn rgb_to_hsv(c: vec3<f32>) -> vec3<f32> {
    let K = vec4<f32>(0.0, -1.0/3.0, 2.0/3.0, -1.0);
    let p = mix(vec4<f32>(c.bg, K.wz), vec4<f32>(c.gb, K.xy), step(c.b, c.g));
    let q = mix(vec4<f32>(p.xyw, c.r),  vec4<f32>(c.r, p.yzx), step(p.x, c.r));
    let d = q.x - min(q.w, q.y);
    let e = 1.0e-10;
    return vec3<f32>(abs(q.z + (q.w - q.y) / (6.0 * d + e)), d / (q.x + e), q.x);
}

fn hsv_to_rgb(c: vec3<f32>) -> vec3<f32> {
    let K = vec3<f32>(1.0, 2.0/3.0, 1.0/3.0);
    let p = abs(fract(c.xxx + K) * 6.0 - vec3<f32>(3.0));
    return c.z * mix(vec3<f32>(1.0), clamp(p - vec3<f32>(1.0), vec3<f32>(0.0), vec3<f32>(1.0)), c.y);
}

@fragment
fn fs_main(@location(0) uv: vec2<f32>) -> @location(0) vec4<f32> {
    let base = textureSample(u_albedo, u_sampler, uv);
    var hsv  = rgb_to_hsv(base.rgb);
    hsv.x    = fract(hsv.x + u.hue_shift); // rotate hue; wraps at 1.0
    return vec4<f32>(hsv_to_rgb(hsv), base.a);
}
```

`u.hue_shift = 0.5` flips to the complementary colour. `0.0` = original.

### Option 3: Gradient Map (Colour Ramp)

Remaps the entire colour range using a **256×1 PNG lookup texture**. The sprite's per-pixel luminance indexes into the ramp — dark pixels map to the left end, bright pixels to the right end.

An optional `ramp_steps` uniform **quantises** the luminance into N discrete bands before the lookup. At `0` the ramp is smooth; at `4` you get a cel-shaded look.

```wgsl
struct Uniforms {
    mvp        : mat4x4<f32>,
    ramp_steps : f32,   // 0.0 = smooth, 2+ = number of discrete bands
};
@group(0) @binding(0) var<uniform> u   : Uniforms;
@group(0) @binding(1) var u_albedo     : texture_2d<f32>;
@group(0) @binding(2) var u_color_ramp : texture_2d<f32>; // 256x1 PNG
@group(0) @binding(3) var u_sampler    : sampler;

@fragment
fn fs_main(@location(0) uv: vec2<f32>) -> @location(0) vec4<f32> {
    let base      = textureSample(u_albedo, u_sampler, uv);
    var luminance = dot(base.rgb, vec3<f32>(0.299, 0.587, 0.114));

    if u.ramp_steps >= 2.0 {
        luminance = floor(luminance * u.ramp_steps) / (u.ramp_steps - 1.0);
    }

    let mapped = textureSample(u_color_ramp, u_sampler, vec2<f32>(luminance, 0.5));
    return vec4<f32>(mapped.rgb, base.a);
}
```

Luminance weights `(0.299, 0.587, 0.114)` are the standard Rec. 601 luma coefficients.

**`ramp_steps` reference:**

| Value | Effect |
| --- | --- |
| `0.0` | Smooth gradient |
| `2.0` | Shadow / highlight |
| `3.0` | Shadow / midtone / highlight |
| `4.0` | Classic cel-shading |
| `8.0` | Subtle posterisation |

### Option 4: Cosine Palette (Procedural, No Texture)

Four `vec3` parameters define a smooth colour curve with no texture asset at all:

$$\text{color}(t) = a + b \cdot \cos(2\pi(c \cdot t + d))$$

```wgsl
struct Uniforms {
    mvp   : mat4x4<f32>,
    pal_a : vec3<f32>,
    pal_b : vec3<f32>,
    pal_c : vec3<f32>,
    pal_d : vec3<f32>,
};

fn cosine_palette(t: f32, a: vec3<f32>, b: vec3<f32>, c: vec3<f32>, d: vec3<f32>) -> vec3<f32> {
    return a + b * cos(6.28318 * (c * t + d));
}

@fragment
fn fs_main(@location(0) uv: vec2<f32>) -> @location(0) vec4<f32> {
    let base      = textureSample(u_albedo, u_sampler, uv);
    let luminance = dot(base.rgb, vec3<f32>(0.299, 0.587, 0.114));
    let mapped    = cosine_palette(luminance, u.pal_a, u.pal_b, u.pal_c, u.pal_d);
    return vec4<f32>(mapped, base.a);
}
```

Predefined parameter sets in the material JSON — no PNG assets:

```json
"color_ramp": {
  "type": "cosine",
  "a": [0.5, 0.5, 0.5],
  "b": [0.5, 0.5, 0.5],
  "c": [1.0, 1.0, 1.0],
  "d": [0.0, 0.33, 0.67]
}
```

Useful presets:

| Effect | a | b | c | d |
| --- | --- | --- | --- | --- |
| Rainbow | `(0.5,0.5,0.5)` | `(0.5,0.5,0.5)` | `(1,1,1)` | `(0, 0.33, 0.67)` |
| Fire | `(0.5,0.2,0.1)` | `(0.5,0.3,0.1)` | `(1,1,1)` | `(0, 0.1, 0.2)` |
| Ice | `(0.2,0.4,0.6)` | `(0.2,0.3,0.4)` | `(1,1,1)` | `(0.5, 0.4, 0.3)` |
| Poison | `(0.2,0.5,0.1)` | `(0.2,0.4,0.1)` | `(1,1,2)` | `(0, 0.25, 0)` |

Lerping between two parameter sets over time gives smooth colour transitions (e.g. gradually freezing) with only uniform buffer writes.

### Option 5: Partial Remap via Param Map

Blend between original and ramp-mapped colour using the param map G channel as a per-pixel weight. Useful for recolouring only specific regions (e.g. clothing but not skin).

```wgsl
let base      = textureSample(u_albedo,     u_sampler, uv);
let params    = textureSample(u_param_map,  u_sampler, uv);
let luminance = dot(base.rgb, vec3<f32>(0.299, 0.587, 0.114));
let mapped    = textureSample(u_color_ramp, u_sampler, vec2<f32>(luminance, 0.5));
let weight    = params.g; // 0 = original, 1 = fully remapped
return vec4<f32>(mix(base.rgb, mapped.rgb, weight), base.a);
```

### Choosing an Approach

| Use case | Approach |
| --- | --- |
| Uniform tint (team colour, flash) | Option 1 — `u_tint` uniform, no extra assets |
| Every possible hue variant | Option 2 — HSV hue shift, one float |
| Full palette remap (ice, fire, faction) | Option 3 — colour ramp texture |
| Remap without texture assets | Option 4 — cosine palette, pure math |
| Partial remap (clothing only) | Option 3 or 4 + param map G channel weight |

---

## Workflow D: Full-Screen Post-Process Distortion

Used for screen-space effects that transform the rendered image as a whole — GBA-style scanline warps, screen transitions, ripple effects, and mosaic. These effects operate on the final composed scene image, not on individual sprites.

### Pipeline Architecture

Workflows A–C render sprites directly to the swap chain. Workflow D requires a **two-pass pipeline**:

```text
Pass 1 — Scene Pass
  └── Render target: offscreen GPUTexture (scene_texture)
  └── All sprite draw calls happen here (Workflows A/B/C unchanged)

Pass 2 — Post-Process Pass
  └── Render target: swap chain (canvas)
  └── Input: scene_texture from Pass 1
  └── Geometry: full-screen triangle (no vertex buffer)
  └── Fragment: sample scene_texture with distorted UVs
```

**JS setup — scene render target (create once, resize on canvas resize):**

```js
function createSceneTexture(device, width, height) {
  return device.createTexture({
    size: [width, height],
    format: navigator.gpu.getPreferredCanvasFormat(),
    usage: GPUTextureUsage.RENDER_ATTACHMENT | GPUTextureUsage.TEXTURE_BINDING,
  });
}
```

**JS setup — per-frame render loop:**

```js
// Pass 1: render scene to offscreen texture
const scenePass = encoder.beginRenderPass({
  colorAttachments: [{ view: sceneTexture.createView(), loadOp: 'clear', storeOp: 'store' }],
});
// ... all sprite draw calls ...
scenePass.end();

// Pass 2: post-process to canvas
const postPass = encoder.beginRenderPass({
  colorAttachments: [{ view: context.getCurrentTexture().createView(), loadOp: 'clear', storeOp: 'store' }],
});
postPass.setPipeline(postProcessPipeline);
postPass.setBindGroup(0, postProcessBindGroup); // scene texture + uniforms
postPass.draw(3); // full-screen triangle, no vertex buffer
postPass.end();
```

**WGSL — full-screen triangle vertex shader (no vertex buffer needed):**

```wgsl
@vertex
fn vs_fullscreen(@builtin(vertex_index) vi: u32) -> @builtin(position) vec4<f32> {
    // Single oversized triangle covering NDC [-1,1] on both axes.
    var pos = array<vec2<f32>, 3>(
        vec2<f32>(-1.0, -3.0),
        vec2<f32>(-1.0,  1.0),
        vec2<f32>( 3.0,  1.0),
    );
    return vec4<f32>(pos[vi], 0.0, 1.0);
}

fn ndc_to_uv(pos: vec4<f32>) -> vec2<f32> {
    return pos.xy * vec2<f32>(0.5, -0.5) + vec2<f32>(0.5);
}
```

Use `@builtin(position)` → convert to UV in the fragment shader, or pass UV as a varying from the vertex shader.

---

### Effect A — Scanline Wobble (GBA H-Blank style)

The GBA achieved per-scanline effects by updating hardware registers mid-draw. The equivalent in a shader is applying a per-row horizontal offset using `sin` keyed on the Y UV coordinate.

```wgsl
struct Uniforms {
    time      : f32,
    frequency : f32,  // wave cycles across screen height
    speed     : f32,  // scroll speed of the wave
    amplitude : f32,  // max horizontal shift (in UV space, e.g. 0.005)
};

@fragment
fn fs_main(@builtin(position) pos: vec4<f32>) -> @location(0) vec4<f32> {
    var uv = ndc_to_uv(pos);
    let wobble = sin(uv.y * u.frequency + u.time * u.speed) * u.amplitude;
    uv.x += wobble;
    return textureSample(u_scene, u_sampler, uv);
}
```

Clamp `uv.x` to `[0,1]` or enable repeat addressing to avoid edge artefacts. For a "broken TV" look, add a second slower `sin` term at a different frequency.

**Variant — vertical wobble (horizontal scanlines):** apply offset to `uv.y` keyed on `uv.x` instead.

---

### Effect B — Radial Ripple

Displaces UVs radially from a centre point. Used for impact shockwaves, explosions, stone-in-water transitions.

```wgsl
struct Uniforms {
    time      : f32,
    center    : vec2<f32>,  // in UV space, e.g. (0.5, 0.5) for screen center
    frequency : f32,         // ripple ring density
    speed     : f32,
    amplitude : f32,         // max displacement magnitude
    falloff   : f32,         // how quickly ripple fades with distance (e.g. 3.0)
};

@fragment
fn fs_main(@builtin(position) pos: vec4<f32>) -> @location(0) vec4<f32> {
    let uv    = ndc_to_uv(pos);
    let delta = uv - u.center;
    let dist  = length(delta);
    let ripple = sin(dist * u.frequency - u.time * u.speed)
                 * u.amplitude
                 * exp(-dist * u.falloff);    // fade at distance
    let dir = normalize(delta);
    let distorted_uv = uv + dir * ripple;
    return textureSample(u_scene, u_sampler, distorted_uv);
}
```

Set `amplitude` to `0.0` once the shockwave has passed (controlled from JS game logic). The `exp(-dist * falloff)` term fades the ripple naturally with distance so edges look clean.

---

### Effect C — Mosaic / Pixelate

Blocks adjacent pixels into tiles by snapping UV to a grid. The `mosaic_size` uniform is the number of blocks across the screen — increase it over time to dissolve into/out of scenes.

```wgsl
struct Uniforms {
    mosaic_size : f32,  // e.g. 32.0 = 32×32 grid of tiles
};

@fragment
fn fs_main(@builtin(position) pos: vec4<f32>) -> @location(0) vec4<f32> {
    let uv = ndc_to_uv(pos);
    let snapped = floor(uv * u.mosaic_size) / u.mosaic_size;
    return textureSample(u_scene, u_sampler, snapped);
}
```

Animating `mosaic_size` from a large value (fine grid) down to `1.0` (one tile = entire screen) creates the classic GBA "zoom out to solid colour" transition. Drive it with an easing curve from JS.

---

### Effect D — Iris Wipe (Circle Transition)

Reveals or hides the scene by animating a circular mask. Classic for scene transitions.

```wgsl
struct Uniforms {
    radius       : f32,   // 0.0 = fully closed, ~0.75 = fully open
    edge_soften  : f32,   // smooth the border (e.g. 0.02); 0.0 = hard edge
    color        : vec4<f32>, // fill colour outside the circle (usually black)
    center       : vec2<f32>, // usually (0.5, 0.5)
    aspect       : f32,   // canvas width/height, to keep circle round
};

@fragment
fn fs_main(@builtin(position) pos: vec4<f32>) -> @location(0) vec4<f32> {
    let uv   = ndc_to_uv(pos);
    let d    = vec2<f32>((uv.x - u.center.x) * u.aspect, uv.y - u.center.y);
    let dist = length(d);
    let mask = smoothstep(u.radius, u.radius - u.edge_soften, dist);
    let scene = textureSample(u_scene, u_sampler, uv);
    return mix(u.color, scene, mask);
}
```

Open: animate `radius` from `0.0` → `0.75` (or whatever fully covers the screen diagonal). Close: reverse. The `aspect` correction keeps the shape circular on non-square canvases.

**Variant — off-centre iris:** set `center` to an entity's screen position for a "zoom into character" effect.

---

### Effect E — Warp Map (Predefined Pattern)

For complex non-mathematical distortions (e.g. a specific wobbly transition shape, a lens distortion, a flag wave), pre-author the displacement field as a texture.

**Warp map format:** an RGBA PNG where:
- R channel = X displacement amount (0.5 = no offset, 0 = full negative, 1 = full positive)
- G channel = Y displacement amount (same encoding)
- BA unused (can store a second pass or mask)

```wgsl
struct Uniforms {
    intensity : f32,          // scale factor for how much the warp is applied
    scroll    : vec2<f32>,    // offset into the warp map (animate for flowing effects)
};
@group(0) @binding(0) var<uniform> u        : Uniforms;
@group(0) @binding(1) var u_scene    : texture_2d<f32>;
@group(0) @binding(2) var u_warp_map : texture_2d<f32>;
@group(0) @binding(3) var u_sampler  : sampler;

@fragment
fn fs_main(@builtin(position) pos: vec4<f32>) -> @location(0) vec4<f32> {
    let uv       = ndc_to_uv(pos);
    let warp_uv  = fract(uv + u.scroll);                    // scroll the warp map
    let raw      = textureSample(u_warp_map, u_sampler, warp_uv).rg;
    let offset   = (raw - vec2<f32>(0.5)) * 2.0 * u.intensity; // remap [0,1]→[-1,1]
    let distorted_uv = clamp(uv + offset, vec2<f32>(0.0), vec2<f32>(1.0));
    return textureSample(u_scene, u_sampler, distorted_uv);
}
```

Scroll `u.scroll` over time with JS for animated warp (underwater caustics, heat shimmer). Set `intensity` to `0.0` to disable the effect without switching pipelines.

**Authoring warp maps:** paint grey (0.5, 0.5, 0.5) as the neutral "no offset" value, then push regions toward red or teal to create directional displacement. The `pack_param_map.py` tool can encode separate R and G greyscale images into a single texture (use `-r` and `-g` args, ignore B/A).

---

### Uniform Animation from JS

All post-process uniforms are driven from game logic. A simple approach:

```js
class PostProcessState {
  constructor() {
    this.effects = {};  // keyed by effect name
  }

  setEffect(name, params) {
    this.effects[name] = { ...params, active: true };
  }

  // Call once per frame before encoding Pass 2
  writeUniforms(device, uniformBuffer) {
    const active = Object.values(this.effects).find(e => e.active);
    if (!active) return;
    const data = new Float32Array([
      active.time ?? 0,
      active.intensity ?? 0,
      // ... effect-specific floats packed in order
    ]);
    device.queue.writeBuffer(uniformBuffer, 0, data);
  }
}
```

Blend between effects by lerping their uniform values rather than switching pipelines — a ripple fading out while a mosaic fades in can be a single shader with two sets of parameters and a mix weight.

---

### Choosing an Approach

| Effect | Type | Extra asset needed |
| --- | --- | --- |
| Scanline wobble / heat shimmer | Math | None |
| Radial ripple / shockwave | Math | None |
| Mosaic / pixelate | Math | None |
| Iris wipe (circle transition) | Math | None |
| Complex pre-authored distortion | Warp map | 1 RGBA PNG |
| Flowing animated warp (water, flag) | Warp map + scroll | 1 RGBA PNG |
| Colour grade / vignette | Math / LUT | Optional LUT texture |

---

## Workflow E: Procedural Animated Background (Earthbound / Mother-style)

The Earthbound battle backgrounds combine three concurrent effects running in one fragment shader:

1. **Dual-wave sine distortion** applied to UV coordinates before pattern sampling (the SNES equivalent was HDMA writing per-scanline horizontal scroll offsets from a pre-computed sine table each frame).
2. **A repeating geometric pattern** (stripes, checkerboard, rings, spiral) evaluated at the distorted UV.
3. **Palette colour cycling** — the pattern scalar indexes into a colour palette, and an animated time offset rotates the entire palette each frame (the SNES equivalent was rotating the palette register entries directly).

### How It Differs from Workflow D

Workflow D post-processes an **already-rendered scene image** — pixels are displaced from a source texture. Workflow E has no source texture. Pixel colour is **generated entirely from math**. The background is drawn as the **first draw call in the scene pass** before any sprites:

```text
Pass 1 — Scene Pass
  ├── Draw call 1: Background (Workflow E — full-screen triangle, no texture input)
  └── Draw call 2..N: Sprites (Workflows A/B/C — quads, atlas texture)
```

No extra render target is needed. The background gets painted over by subsequent sprite draw calls.

### Pattern Functions

The pattern is a function `f(uv) → [0, 1]` whose output indexes into a colour palette.

**Diagonal stripes:**

```wgsl
let pattern = fract((uv.x + uv.y) * u.pattern_scale);
```

**Checkerboard:**

```wgsl
let scaled  = uv * u.pattern_scale;
let checker = floor(scaled.x) + floor(scaled.y);
let pattern = fract(checker * 0.5) * 2.0; // snaps to 0.0 or 1.0
```

**Concentric rings (Mother 3):**

```wgsl
let dist    = length(uv - vec2<f32>(0.5, 0.5));
let pattern = fract(dist * u.pattern_scale);
```

**Spiral:**

```wgsl
let delta   = uv - vec2<f32>(0.5, 0.5);
let angle   = atan2(delta.y, delta.x) / 6.28318; // normalise to [−0.5, 0.5]
let dist    = length(delta);
let pattern = fract(dist * u.pattern_scale + angle);
```

**Mixing two patterns** creates more complex shapes without changing the pipeline:

```wgsl
let rings   = fract(length(uv - vec2<f32>(0.5)) * u.pattern_scale);
let stripes = fract((uv.x + uv.y) * u.pattern_scale * 0.5);
let pattern = mix(rings, stripes, 0.5);      // blend
// let pattern = rings * stripes;            // product → moiré-like grid
// let pattern = abs(rings - stripes);       // difference → interference fringes
```

### Dual Sine Distortion

Two waves with different frequencies and speeds warp the UV before the pattern is sampled. Making their frequencies non-integer multiples of each other prevents a repeating lockstep that would look too regular.

```wgsl
uv.x += u.wave1_amp * sin(uv.y * u.wave1_freq + u.time * u.wave1_speed);
uv.x += u.wave2_amp * sin(uv.y * u.wave2_freq + u.time * u.wave2_speed);
// Optional vertical wobble:
uv.y += u.wave1_amp * 0.4 * sin(uv.x * u.wave1_freq * 0.8 + u.time * u.wave1_speed * 1.1);
```

### Colour Cycling

Add `time * cycle_speed` to the pattern scalar before the palette lookup to rotate the entire palette over time.

**Option A — Palette texture (fixed set of colours, SNES-authentic feel):**

```wgsl
let palette_t = fract(pattern + u.time * u.cycle_speed);
return textureSample(u_palette, u_sampler, vec2<f32>(palette_t, 0.5));
```

Author a 256×1 PNG with colours in their desired cycle order. Paint the PNG as a strip from left to right in the sequence the colours should appear at increasing pattern values / over time. This gives direct control over the exact palette (e.g. yellow → orange → red → purple → blue → teal → yellow).

**Option B — Cosine palette (no texture asset):**

```wgsl
let palette_t = fract(pattern + u.time * u.cycle_speed);
return vec4<f32>(cosine_palette(palette_t, u.pal_a, u.pal_b, u.pal_c, u.pal_d), 1.0);
```

See Workflow C Option 4 for the `cosine_palette` function and preset tables. Lerping between two sets of `pal_a/b/c/d` uniforms produces smooth palette transitions (phase change without breaking the cycle).

### Complete Shader

```wgsl
struct Uniforms {
    time          : f32,
    pattern_scale : f32,
    wave1_freq    : f32,
    wave1_speed   : f32,
    wave1_amp     : f32,
    wave2_freq    : f32,
    wave2_speed   : f32,
    wave2_amp     : f32,
    cycle_speed   : f32,
    _pad          : f32,  // align to 16-byte boundary
    pal_a         : vec3<f32>,  _pad1 : f32,
    pal_b         : vec3<f32>,  _pad2 : f32,
    pal_c         : vec3<f32>,  _pad3 : f32,
    pal_d         : vec3<f32>,  _pad4 : f32,
};

@group(0) @binding(0) var<uniform> u : Uniforms;

fn cosine_palette(t: f32, a: vec3<f32>, b: vec3<f32>,
                           c: vec3<f32>, d: vec3<f32>) -> vec3<f32> {
    return a + b * cos(6.28318 * (c * t + d));
}

struct VertexOut {
    @builtin(position) pos : vec4<f32>,
    @location(0)       uv  : vec2<f32>,
};

@vertex
fn vs_main(@builtin(vertex_index) vi: u32) -> VertexOut {
    var tri = array<vec2<f32>, 3>(
        vec2<f32>(-1.0, -3.0),
        vec2<f32>(-1.0,  1.0),
        vec2<f32>( 3.0,  1.0),
    );
    var out: VertexOut;
    out.pos = vec4<f32>(tri[vi], 0.0, 1.0);
    out.uv  = tri[vi] * vec2<f32>(0.5, -0.5) + vec2<f32>(0.5); // NDC → UV (Y flipped)
    return out;
}

@fragment
fn fs_main(in: VertexOut) -> @location(0) vec4<f32> {
    var uv = in.uv;

    // Dual sine distortion
    uv.x += u.wave1_amp * sin(uv.y * u.wave1_freq + u.time * u.wave1_speed);
    uv.x += u.wave2_amp * sin(uv.y * u.wave2_freq + u.time * u.wave2_speed);

    // Pattern (swap this block for any pattern function above)
    let dist    = length(uv - vec2<f32>(0.5, 0.5));
    let pattern = fract(dist * u.pattern_scale);

    // Colour cycling
    let palette_t = fract(pattern + u.time * u.cycle_speed);
    return vec4<f32>(cosine_palette(palette_t, u.pal_a, u.pal_b, u.pal_c, u.pal_d), 1.0);
}
```

> **Struct alignment:** WGSL `vec3<f32>` members in uniform blocks must be 16-byte aligned. The `_pad` fields above satisfy this. When building the `Float32Array` on the JS side, insert matching padding floats at the same offsets, or use `vec4<f32>` and ignore the W component.

### Presets

Suggested starting values pairing pattern type + wave parameters + cosine palette preset (from Workflow C):

| Name | Pattern | `wave1 freq/spd/amp` | `wave2 freq/spd/amp` | `cycle_speed` | Palette |
| --- | --- | --- | --- | --- | --- |
| Classic Earthbound | Concentric rings, scale=8 | `6.0 / 0.8 / 0.03` | `10.0 / 1.3 / 0.02` | `0.15` | Rainbow |
| Mother 3 stripes | Diagonal stripes, scale=12 | `8.0 / 1.0 / 0.04` | `14.0 / 0.7 / 0.025` | `0.20` | Fire |
| Poison caves | Rings+stripes mix, scale=7 | `5.0 / 0.5 / 0.05` | `9.0 / 0.9 / 0.03` | `0.12` | Poison |
| Ice dungeon | Checkerboard, scale=10 | `6.0 / 0.4 / 0.02` | `11.0 / 0.6 / 0.015` | `0.08` | Ice |
| Fast psychedelic | Spiral, scale=10 | `12.0 / 2.0 / 0.02` | `18.0 / 3.1 / 0.015` | `0.40` | Rainbow |

### Transitioning Between Backgrounds

Lerp all uniform values between two preset sets over N frames. Since everything is a float in the uniform buffer, JS only needs to interpolate the structs — no pipeline switch, no texture swap:

```js
function lerpPreset(a, b, t) {
  return {
    patternScale: lerp(a.patternScale, b.patternScale, t),
    wave1Freq:    lerp(a.wave1Freq,    b.wave1Freq,    t),
    // ... all other floats
    cycleSpeed:   lerp(a.cycleSpeed,   b.cycleSpeed,   t),
    palA:         lerpVec3(a.palA, b.palA, t),
    // ...
  };
}
```

A 60-frame linear transition is enough for a smooth morph. Use an ease-in-out curve for a less mechanical feel.
