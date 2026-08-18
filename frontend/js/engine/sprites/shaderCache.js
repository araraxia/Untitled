/**
 * ShaderCache — compiles and caches GPURenderPipeline objects.
 *
 * --- Workflow A (legacy, layout: 'auto') ---
 * Bind group layout (group 0):
 *   binding 0 — uniform buffer: { mvp: mat4x4<f32>, uv_rect: vec4<f32>,
 *               tint: vec4<f32> }
 *   binding 1 — texture_2d<f32>  (albedo atlas)
 *   binding 2 — sampler
 *
 * --- Material pipelines (explicit layout, 4 bindings) ---
 * Bind group layout (group 0):
 *   binding 0 — uniform buffer (128 B): mvp, uv_rect, uv_overlay, tint,
 *               intensity, time, ramp_steps, _pad
 *   binding 1 — texture_2d<f32>  (albedo atlas)
 *   binding 2 — texture_2d<f32>  (RGBA param map)
 *   binding 3 — sampler
 *
 * Vertex buffer layout (arrayStride 16) — shared by all pipelines:
 *   location 0 — pos : float32x2  (offset 0)
 *   location 1 — uv  : float32x2  (offset 8)
 */

const SPRITE_WGSL = `
struct Uniforms {
  mvp     : mat4x4<f32>,
  uv_rect : vec4<f32>,
  tint    : vec4<f32>,
};

@group(0) @binding(0) var<uniform> u         : Uniforms;
@group(0) @binding(1) var          u_albedo  : texture_2d<f32>;
@group(0) @binding(2) var          u_sampler : sampler;

struct VertexOut {
  @builtin(position) position : vec4<f32>,
  @location(0)       uv       : vec2<f32>,
};

@vertex
fn vs_main(
  @location(0) pos : vec2<f32>,
  @location(1) uv  : vec2<f32>,
) -> VertexOut {
  var out : VertexOut;
  out.position = u.mvp * vec4<f32>(pos, 0.0, 1.0);
  out.uv       = uv;
  return out;
}

@fragment
fn fs_main(@location(0) uv : vec2<f32>) -> @location(0) vec4<f32> {
  // Remap unit-quad UV [0,1] into the atlas sub-region for the current frame.
  let atlas_uv = u.uv_rect.xy + uv * (u.uv_rect.zw - u.uv_rect.xy);
  return textureSample(u_albedo, u_sampler, atlas_uv) * u.tint;
}
`;

/** Depth texture format used by every depth-tested pipeline in this file. */
const DEPTH_FORMAT = "depth24plus";

/**
 * Compile the sprite pipeline for the given device and swap-chain format.
 *
 * @param {GPUDevice} device
 * @param {GPUTextureFormat} format
 * @param {boolean} [depthTest=false] - When true, adds depth write/compare
 *   state so draws using this pipeline correctly occlude each other by
 *   world depth (needed for 3D billboards — see ShaderCache.getSpritePipeline3D).
 *   The existing 2D path (ShaderCache.getSpritePipeline) always passes
 *   false, so 2D rendering is completely unaffected by this parameter's
 *   existence — 2D sprites never wrote or read a depth buffer before this
 *   flag was added, and still don't.
 * @returns {GPURenderPipeline}
 */
function createSpritePipeline(device, format, depthTest = false) {
  const shaderModule = device.createShaderModule({ code: SPRITE_WGSL });

  const descriptor = {
    layout: "auto",
    vertex: {
      module: shaderModule,
      entryPoint: "vs_main",
      buffers: [
        {
          arrayStride: 16,
          attributes: [
            { shaderLocation: 0, offset: 0, format: "float32x2" },
            { shaderLocation: 1, offset: 8, format: "float32x2" },
          ],
        },
      ],
    },
    fragment: {
      module: shaderModule,
      entryPoint: "fs_main",
      targets: [
        {
          format,
          // Pre-multiplied alpha blending — matches alphaMode: 'premultiplied'.
          blend: {
            color: {
              srcFactor: "one",
              dstFactor: "one-minus-src-alpha",
              operation: "add",
            },
            alpha: {
              srcFactor: "one",
              dstFactor: "one-minus-src-alpha",
              operation: "add",
            },
          },
        },
      ],
    },
    primitive: {
      topology: "triangle-list",
    },
  };

  if (depthTest) {
    descriptor.depthStencil = {
      format: DEPTH_FORMAT,
      depthWriteEnabled: true,
      depthCompare: "less",
    };
  }

  return device.createRenderPipeline(descriptor);
}

class ShaderCache {
  /**
   * @param {GPUDevice} device
   * @param {GPUTextureFormat} format — swap-chain format from
   *   navigator.gpu.getPreferredCanvasFormat()
   */
  constructor(device, format) {
    this._device = device;
    this._format = format;
    this._spritePipeline = null;
    this._spritePipeline3D = null;

    /** @type {Map<string, GPURenderPipeline>} */
    this._materialPipelines = new Map();

    /** @type {GPUBindGroupLayout|null} */
    this._materialBGL = null;

    /** @type {Map<string, GPURenderPipeline>} */
    this._meshPipelines = new Map();
  }

  /**
   * Return the cached sprite pipeline, creating it on first call.
   * @returns {GPURenderPipeline}
   */
  getSpritePipeline() {
    if (!this._spritePipeline) {
      this._spritePipeline = createSpritePipeline(this._device, this._format);
      console.log("[ShaderCache] Sprite pipeline created");
    }
    return this._spritePipeline;
  }

  /**
   * Return the cached depth-tested sprite pipeline used for 3D billboards
   * (`EntityRenderer.drawEntity3D`), creating it on first call. Same
   * SPRITE_WGSL shader and bind group layout shape as `getSpritePipeline()`,
   * but a distinct GPURenderPipeline object (own auto bind group layout)
   * with depth write/compare enabled — kept fully separate from the 2D
   * pipeline so bind groups are never accidentally shared across the two
   * (see gpuSpriteSheet.js's `createBindGroup`, which binds to whichever
   * pipeline object it's given).
   * @returns {GPURenderPipeline}
   */
  getSpritePipeline3D() {
    if (!this._spritePipeline3D) {
      this._spritePipeline3D = createSpritePipeline(
        this._device,
        this._format,
        true,
      );
      console.log("[ShaderCache] 3D (depth-tested) sprite pipeline created");
    }
    return this._spritePipeline3D;
  }

  /**
   * Return (creating lazily) the explicit GPUBindGroupLayout shared by
   * all material pipeline variants.  Callers may pass this layout to
   * MaterialLoader so that bind groups and pipelines share the exact
   * same GPUBindGroupLayout object (maximally safe).
   *
   * @returns {GPUBindGroupLayout}
   */
  getMaterialBindGroupLayout() {
    if (!this._materialBGL) {
      this._materialBGL = this._device.createBindGroupLayout({
        entries: [
          {
            binding: 0,
            visibility: GPUShaderStage.VERTEX | GPUShaderStage.FRAGMENT,
            buffer: { type: "uniform" },
          },
          {
            binding: 1,
            visibility: GPUShaderStage.FRAGMENT,
            texture: { sampleType: "float" },
          },
          {
            binding: 2,
            visibility: GPUShaderStage.FRAGMENT,
            texture: { sampleType: "float" },
          },
          {
            binding: 3,
            visibility: GPUShaderStage.FRAGMENT,
            sampler: { type: "filtering" },
          },
        ],
      });
    }
    return this._materialBGL;
  }

  /**
   * Return the cached material pipeline for the given variant, creating
   * it on first call.  Falls back to 'base' for unrecognised keys.
   *
   * Valid variantKeys: 'base' | 'overlay' | 'hue' | 'ramp' | 'cosine'
   *
   * @param {string} variantKey
   * @param {GPUBindGroupLayout} [bindGroupLayout] - Pass the layout from
   *   MaterialLoader to guarantee object-level compatibility.  When omitted
   *   the layout from getMaterialBindGroupLayout() is used.
   * @returns {GPURenderPipeline}
   */
  getMaterialPipeline(variantKey, bindGroupLayout) {
    const key = MATERIAL_FRAGMENT_SHADERS[variantKey] ? variantKey : "base";

    if (!this._materialPipelines.has(key)) {
      const bgl = bindGroupLayout || this.getMaterialBindGroupLayout();
      const pipeline = createMaterialPipeline(
        this._device,
        this._format,
        bgl,
        key,
      );
      this._materialPipelines.set(key, pipeline);
      console.log("[ShaderCache] Material pipeline created:", key);
    }
    return this._materialPipelines.get(key);
  }

  /**
   * Return the cached 'mesh' pipeline for the given material variant,
   * creating it on first call. Shares the exact same MatUniforms struct
   * layout (extended with Step 8's stylization fields), bind group
   * layout, and fragment shaders (FS_BASE/FS_RAMP/FS_HUE/...) as
   * getMaterialPipeline() — a mesh entity's MaterialLoader-built bind
   * group binds to either interchangeably. Only the vertex stage differs
   * (mesh attributes + a plain mvp transform, vs. a unit quad + an atlas
   * sub-rect uniform) — see buildMeshWgslCommon() below.
   *
   * Always depth-tested (mesh content is inherently 3D), unlike the base
   * 2D sprite pipeline — matches the precedent set by
   * getSpritePipeline3D() for billboards.
   *
   * @param {string} variantKey - Same variant keys as getMaterialPipeline.
   * @param {GPUBindGroupLayout} [bindGroupLayout] - Pass MaterialLoader's
   *   layout to guarantee its bind groups are compatible with this pipeline.
   * @param {boolean} [affineUv=false] - Step 8's affine (non-perspective-
   *   correct) UV interpolation toggle. WGSL's `@interpolate` attribute is
   *   fixed at shader-compile time, not a runtime uniform branch, so
   *   affine vs. perspective-correct UVs are necessarily two distinct
   *   compiled pipelines rather than one pipeline with a uniform branch
   *   (unlike the other Step 8 hooks, which are runtime branches inside
   *   a single fragment shader — see buildMeshStyleWgslTail()). Part of the
   *   cache key so a material with `affine_uv: true` and one without
   *   don't collide.
   * @returns {GPURenderPipeline}
   */
  getMeshPipeline(variantKey, bindGroupLayout, affineUv = false) {
    const variant = MATERIAL_FRAGMENT_SHADERS[variantKey] ? variantKey : "base";
    const key = `${variant}:${affineUv ? "affine" : "persp"}`;

    if (!this._meshPipelines.has(key)) {
      const bgl = bindGroupLayout || this.getMaterialBindGroupLayout();
      const pipeline = createMeshPipeline(
        this._device,
        this._format,
        bgl,
        variant,
        affineUv,
      );
      this._meshPipelines.set(key, pipeline);
      console.log("[ShaderCache] Mesh pipeline created:", key);
    }
    return this._meshPipelines.get(key);
  }
}

// ==================================================================
// Material pipeline WGSL shaders
// ==================================================================

/**
 * Common WGSL declarations included in every material shader module.
 * Defines the MatUniforms struct and all four group/binding declarations.
 */
const MATERIAL_WGSL_COMMON = `
struct MatUniforms {
  mvp        : mat4x4<f32>,   // offset   0, 64 bytes
  uv_rect    : vec4<f32>,     // offset  64, 16 bytes
  uv_overlay : vec4<f32>,     // offset  80, 16 bytes
  tint       : vec4<f32>,     // offset  96, 16 bytes
  intensity  : f32,           // offset 112,  4 bytes
  time       : f32,           // offset 116,  4 bytes
  ramp_steps : f32,           // offset 120,  4 bytes
  _pad       : f32,           // offset 124,  4 bytes
  // Cosine palette parameters (Workflow C option 4).
  // Each stores a vec3 value; .w is always 0.
  pal_a      : vec4<f32>,     // offset 128, 16 bytes
  pal_b      : vec4<f32>,     // offset 144, 16 bytes
  pal_c      : vec4<f32>,     // offset 160, 16 bytes
  pal_d      : vec4<f32>,     // offset 176, 16 bytes
};                            // total: 192 bytes

@group(0) @binding(0) var<uniform> u           : MatUniforms;
@group(0) @binding(1) var          u_albedo    : texture_2d<f32>;
@group(0) @binding(2) var          u_param_map : texture_2d<f32>;
@group(0) @binding(3) var          u_sampler   : sampler;

struct VertexOut {
  @builtin(position) position : vec4<f32>,
  @location(0)       uv       : vec2<f32>,
};

@vertex
fn vs_main(
  @location(0) pos : vec2<f32>,
  @location(1) uv  : vec2<f32>,
) -> VertexOut {
  var out : VertexOut;
  out.position = u.mvp * vec4<f32>(pos, 0.0, 1.0);
  out.uv       = uv;
  return out;
}
`;

/**
 * Fragment shader — base variant.
 * Samples the albedo atlas at the current frame's UV rect and
 * multiplies by the per-draw tint.
 */
const FS_BASE = `
@fragment
fn fs_main(@location(0) uv : vec2<f32>) -> @location(0) vec4<f32> {
  let atlas_uv = u.uv_rect.xy + uv * (u.uv_rect.zw - u.uv_rect.xy);
  return textureSample(u_albedo, u_sampler, atlas_uv) * u.tint;
}
`;

/**
 * Fragment shader — overlay / emission variant.
 * The param map's green channel drives an additive emission glow
 * scaled by u.intensity.  Useful for lanterns, fire, and glowing
 * objects whose glow mask is baked into the param map.
 */
const FS_OVERLAY = `
@fragment
fn fs_main(@location(0) uv : vec2<f32>) -> @location(0) vec4<f32> {
  let atlas_uv = u.uv_rect.xy + uv * (u.uv_rect.zw - u.uv_rect.xy);
  let base     = textureSample(u_albedo,    u_sampler, atlas_uv) * u.tint;
  let emission = textureSample(u_param_map, u_sampler, uv).g;
  let glow     = vec4<f32>(base.rgb * emission * u.intensity, 0.0);
  return base + glow;
}
`;

/**
 * Fragment shader — hue rotation variant.
 * Converts the albedo colour to HSV, shifts the hue by u.intensity
 * (0.0–1.0 maps to 0°–360°), and converts back.  Set
 * setEntityRuntime(id, 'hue_shift', value) at runtime.
 */
const FS_HUE = `
fn rgb_to_hsv(c : vec3<f32>) -> vec3<f32> {
  let K = vec4<f32>(0.0, -1.0 / 3.0, 2.0 / 3.0, -1.0);
  let p = mix(
    vec4<f32>(c.bg, K.wz),
    vec4<f32>(c.gb, K.xy),
    step(c.b, c.g),
  );
  let q = mix(
    vec4<f32>(p.xyw, c.r),
    vec4<f32>(c.r, p.yzx),
    step(p.x, c.r),
  );
  let d = q.x - min(q.w, q.y);
  let e = 1.0e-10;
  return vec3<f32>(
    abs(q.z + (q.w - q.y) / (6.0 * d + e)),
    d / (q.x + e),
    q.x,
  );
}

fn hsv_to_rgb(c : vec3<f32>) -> vec3<f32> {
  let K = vec3<f32>(1.0, 2.0 / 3.0, 1.0 / 3.0);
  let p = abs(fract(c.xxx + K) * 6.0 - vec3<f32>(3.0));
  return c.z * mix(
    vec3<f32>(1.0),
    clamp(p - vec3<f32>(1.0), vec3<f32>(0.0), vec3<f32>(1.0)),
    c.y,
  );
}

@fragment
fn fs_main(@location(0) uv : vec2<f32>) -> @location(0) vec4<f32> {
  let atlas_uv = u.uv_rect.xy + uv * (u.uv_rect.zw - u.uv_rect.xy);
  let base     = textureSample(u_albedo, u_sampler, atlas_uv);
  var hsv      = rgb_to_hsv(base.rgb);
  hsv.x        = fract(hsv.x + u.intensity);
  return vec4<f32>(hsv_to_rgb(hsv), base.a) * u.tint;
}
`;

/**
 * Fragment shader — colour ramp (gradient map) variant.
 *
 * Remaps the sprite's per-pixel luminance through a 256×1 LUT texture
 * stored in binding 2 (u_param_map).  MaterialLoader puts the colour
 * ramp PNG in that slot when color_ramp.type = 'texture'.
 *
 * ramp_steps ≥ 2 quantises luminance into discrete cel-shading bands
 * before the LUT lookup; ramp_steps = 0 gives a smooth gradient.
 *
 * Luminance weights follow Rec. 601: (0.299, 0.587, 0.114).
 */
const FS_RAMP = `
@fragment
fn fs_main(@location(0) uv : vec2<f32>) -> @location(0) vec4<f32> {
  let atlas_uv  = u.uv_rect.xy + uv * (u.uv_rect.zw - u.uv_rect.xy);
  let base      = textureSample(u_albedo, u_sampler, atlas_uv);
  var luminance = dot(base.rgb, vec3<f32>(0.299, 0.587, 0.114));

  if u.ramp_steps >= 2.0 {
    luminance = floor(luminance * u.ramp_steps) / (u.ramp_steps - 1.0);
  }

  // u_param_map holds the 256x1 colour ramp LUT for this variant.
  let mapped = textureSample(
    u_param_map, u_sampler, vec2<f32>(luminance, 0.5)
  );
  return vec4<f32>(mapped.rgb, base.a) * u.tint;
}
`;

/**
 * Fragment shader — cosine palette variant (Workflow C option 4).
 *
 * Computes a smooth procedural colour entirely on the GPU:
 *   color(t) = pal_a + pal_b * cos(2π * (pal_c * t + pal_d))
 * where t is the per-pixel Rec. 601 luminance of the albedo sample.
 *
 * No extra texture asset is required.  Palette parameters are written
 * into the MatUniforms struct (pal_a … pal_d) by EntityRenderer.
 * Use setEntityRuntime(id, 'cosine_params', {a,b,c,d}) at runtime.
 */
const FS_COSINE = `
fn cosine_palette(
  t : f32,
  a : vec4<f32>,
  b : vec4<f32>,
  c : vec4<f32>,
  d : vec4<f32>,
) -> vec3<f32> {
  return (a + b * cos(6.28318 * (c * t + d))).rgb;
}

@fragment
fn fs_main(@location(0) uv : vec2<f32>) -> @location(0) vec4<f32> {
  let atlas_uv  = u.uv_rect.xy + uv * (u.uv_rect.zw - u.uv_rect.xy);
  let base      = textureSample(u_albedo, u_sampler, atlas_uv);
  let luminance = dot(base.rgb, vec3<f32>(0.299, 0.587, 0.114));
  let mapped    = cosine_palette(
    luminance, u.pal_a, u.pal_b, u.pal_c, u.pal_d
  );
  return vec4<f32>(mapped, base.a) * u.tint;
}
`;

/**
 * Variant key → fragment shader source mapping.
 *
 * | Key       | Trigger                     | Description                        |
 * | --------- | --------------------------- | ---------------------------------- |
 * | 'base'    | no flags                    | albedo × tint                      |
 * | 'overlay' | hasOverlay                  | base + additive glow via param G   |
 * | 'hue'     | hue_shift runtime override  | HSV hue rotation                   |
 * | 'ramp'    | color_ramp.type='texture'   | gradient map LUT (256×1 texture)   |
 * | 'cosine'  | color_ramp.type='cosine'    | procedural cosine palette          |
 *
 * @type {Record<string, string>}
 */
const MATERIAL_FRAGMENT_SHADERS = {
  base: FS_BASE,
  overlay: FS_OVERLAY,
  hue: FS_HUE,
  ramp: FS_RAMP,
  cosine: FS_COSINE,
};

// ==================================================================
// Material pipeline factory
// ==================================================================

/**
 * Compile a material render pipeline for one fragment shader variant.
 *
 * @param {GPUDevice} device
 * @param {GPUTextureFormat} format
 * @param {GPUBindGroupLayout} bindGroupLayout - Explicit layout (from
 *   ShaderCache.getMaterialBindGroupLayout or MaterialLoader.bindGroupLayout).
 * @param {string} variantKey
 *   One of 'base' | 'overlay' | 'hue' | 'ramp' | 'cosine'.
 * @returns {GPURenderPipeline}
 */
function createMaterialPipeline(device, format, bindGroupLayout, variantKey) {
  const fs = MATERIAL_FRAGMENT_SHADERS[variantKey] || FS_BASE;
  const wgsl = MATERIAL_WGSL_COMMON + fs;
  const shaderModule = device.createShaderModule({ code: wgsl });

  const pipelineLayout = device.createPipelineLayout({
    bindGroupLayouts: [bindGroupLayout],
  });

  return device.createRenderPipeline({
    layout: pipelineLayout,
    vertex: {
      module: shaderModule,
      entryPoint: "vs_main",
      buffers: [
        {
          arrayStride: 16,
          attributes: [
            { shaderLocation: 0, offset: 0, format: "float32x2" },
            { shaderLocation: 1, offset: 8, format: "float32x2" },
          ],
        },
      ],
    },
    fragment: {
      module: shaderModule,
      entryPoint: "fs_main",
      targets: [
        {
          format,
          blend: {
            color: {
              srcFactor: "one",
              dstFactor: "one-minus-src-alpha",
              operation: "add",
            },
            alpha: {
              srcFactor: "one",
              dstFactor: "one-minus-src-alpha",
              operation: "add",
            },
          },
        },
      ],
    },
    primitive: { topology: "triangle-list" },
  });
}

// ==================================================================
// Mesh pipeline (Step 5 of 3d-coordinate-mapping.prompt.md)
// ==================================================================

/**
 * Build the common WGSL declarations for the 'mesh' pipeline family. The
 * MatUniforms struct is the *same* 192-byte layout as MATERIAL_WGSL_COMMON
 * for the first 192 bytes (byte-for-byte), so a mesh entity's
 * MaterialLoader-built bind group — the exact same kind a 2D sprite
 * entity already uses — binds to a mesh pipeline unchanged; Step 8 then
 * appends 64 more bytes of stylization fields (mesh_params/fog_range/
 * fog_color/ambient_color) that only this struct declares —
 * MATERIAL_WGSL_COMMON's copy of the struct is untouched, so the 2D
 * sprite path neither reads nor needs to write them. Total 256 bytes,
 * exactly MATERIAL_UNIFORM_ALIGNED (materialLoader.js) — no waste, no
 * buffer resize needed.
 *
 * `normal` is accepted as a vertex attribute (matching Mesh's buffer
 * layout) but unused in this shader — Step 5 has no lighting pass; it's
 * present so the buffer layout doesn't need to change when one is added.
 *
 * uv_rect defaults to [0,0,1,1] (identity) for mesh draws — a mesh's
 * vertex UVs are already final texture-space coordinates, not a sprite
 * atlas sub-rect, so the existing fragment shaders' remap
 * (`atlas_uv = uv_rect.xy + uv * (uv_rect.zw - uv_rect.xy)`) degenerates
 * into a no-op rather than needing mesh-specific fragment shaders.
 *
 * @param {boolean} affineUv - When true, the `uv` varying is declared
 *   `@interpolate(linear)` — WGSL's native non-perspective-correct
 *   interpolation mode, exactly the classic N64 texture-warp artifact —
 *   instead of the default `@interpolate(perspective)`. This has to be a
 *   compile-time choice (WGSL interpolation sampling is fixed per shader
 *   module, not a uniform you can branch on at runtime), which is why
 *   this is a function parameter baked into the generated source rather
 *   than a MatUniforms field like the other Step 8 hooks.
 * @returns {string}
 */
function buildMeshWgslCommon(affineUv) {
  const uvAttr = affineUv
    ? "@location(0) @interpolate(linear) uv"
    : "@location(0) uv";

  return `
struct MatUniforms {
  mvp           : mat4x4<f32>,   // offset   0, 64 bytes
  uv_rect       : vec4<f32>,     // offset  64, 16 bytes
  uv_overlay    : vec4<f32>,     // offset  80, 16 bytes
  tint          : vec4<f32>,     // offset  96, 16 bytes
  intensity     : f32,           // offset 112,  4 bytes
  time          : f32,           // offset 116,  4 bytes
  ramp_steps    : f32,           // offset 120,  4 bytes
  _pad          : f32,           // offset 124,  4 bytes
  pal_a         : vec4<f32>,     // offset 128, 16 bytes
  pal_b         : vec4<f32>,     // offset 144, 16 bytes
  pal_c         : vec4<f32>,     // offset 160, 16 bytes
  pal_d         : vec4<f32>,     // offset 176, 16 bytes
  // --- Step 8: mesh stylization hooks (mesh pipeline only) ---
  // mesh_params.x = vertex_color flag (>0.5 = on), .y = color_levels
  // (>0 = quantise into this many bands/channel, 0 = off). .zw = this
  // draw's camera near/far — needed to linearize frag_pos.z (NDC depth)
  // back into a world-unit distance for the fog calculation below; not
  // itself a stylization flag, just riding along in otherwise-unused
  // padding rather than growing the buffer past the existing 256-byte
  // allocation (see MATERIAL_UNIFORM_ALIGNED, materialLoader.js).
  mesh_params   : vec4<f32>,     // offset 192, 16 bytes
  // fog_range.x = fog_near, .y = fog_far (<=0 = fog fully disabled), .zw unused.
  fog_range     : vec4<f32>,     // offset 208, 16 bytes
  fog_color     : vec4<f32>,     // offset 224, 16 bytes (.a unused)
  ambient_color : vec4<f32>,     // offset 240, 16 bytes (.a unused; [1,1,1] = no-op)
};                                // total: 256 bytes

@group(0) @binding(0) var<uniform> u           : MatUniforms;
@group(0) @binding(1) var          u_albedo    : texture_2d<f32>;
@group(0) @binding(2) var          u_param_map : texture_2d<f32>;
@group(0) @binding(3) var          u_sampler   : sampler;

struct VertexOut {
  @builtin(position) position : vec4<f32>,
  ${uvAttr}                   : vec2<f32>,
  @location(1)       color    : vec4<f32>,
};

@vertex
fn vs_main(
  @location(0) pos    : vec3<f32>,
  @location(1) normal : vec3<f32>,
  @location(2) uv     : vec2<f32>,
  @location(3) color  : vec4<f32>,
) -> VertexOut {
  var out : VertexOut;
  out.position = u.mvp * vec4<f32>(pos, 1.0);
  out.uv = uv;
  out.color = color;
  return out;
}
`;
}

/**
 * Build the Step 8 stylization wrapper — the mesh pipeline's actual
 * fragment *entry point*. Calls `fs_main` (a stripFragmentEntryPoint()-
 * transformed copy of whichever MATERIAL_FRAGMENT_SHADERS variant is in
 * play — same combiner logic the 2D sprite path uses, just no longer its
 * own entry point in this module) to get the base colour, then layers
 * independently opt-in effects on top. Kept entirely separate from the
 * FS_BASE/FS_RAMP/FS_HUE/... constants themselves — those are never
 * edited — specifically so the 2D sprite pipeline, which compiles those
 * exact strings unchanged, is never at risk of reading these mesh-only
 * uniform fields.
 *
 * Every branch here is a true no-op at its documented default:
 *   - vertex_color off (mesh_params.x <= 0.5): multiplies by vec4(1) — see
 *     `select` below, not an `if`, since this one runs unconditionally
 *     cheaply either way and a runtime branch buys nothing.
 *   - color_levels <= 0: `if` skips quantisation entirely.
 *   - ambient_color [1,1,1] (the documented default/omitted value):
 *     multiplying by 1 is a genuine no-op; always applied unconditionally
 *     since, unlike fog, there's no "cost of the branch" to avoid — a
 *     single vec3 multiply.
 *   - fog_range.y (fog_far) <= 0: `if` skips the mix() entirely, per the
 *     Step 8 spec's explicit requirement that disabled fog cost nothing,
 *     not just blend at zero strength.
 *
 * @param {boolean} affineUv - Must match the value passed to
 *   buildMeshWgslCommon() for the same pipeline. WGSL requires a vertex
 *   output and the fragment input it feeds at the same @location to
 *   declare the *same* @interpolate type — mismatching them (e.g. a
 *   `@interpolate(linear)` vertex output paired with the fragment's
 *   default `@interpolate(perspective)` input, which is exactly what an
 *   earlier version of this function did) fails pipeline creation with
 *   "The interpolation type ... is different ...", producing an invalid
 *   GPURenderPipeline that poisons every command buffer it's used in —
 *   not just a bad draw, an entire frame silently failing to submit.
 * @returns {string}
 */
function buildMeshStyleWgslTail(affineUv) {
  const uvAttr = affineUv
    ? "@location(0) @interpolate(linear) uv"
    : "@location(0) uv";

  return `
@fragment
fn fs_mesh_stylized(
  @builtin(position) frag_pos : vec4<f32>,
  ${uvAttr}    : vec2<f32>,
  @location(1) color : vec4<f32>,
) -> @location(0) vec4<f32> {
  var out_color = fs_main(uv);

  // Vertex-color tint (opt-in via material.vertex_color).
  let vc_tint = select(vec4<f32>(1.0, 1.0, 1.0, 1.0), color, u.mesh_params.x > 0.5);
  out_color = out_color * vc_tint;

  // Colour quantisation (opt-in via material.color_levels > 0).
  if (u.mesh_params.y > 0.0) {
    let levels = u.mesh_params.y;
    out_color = vec4<f32>(floor(out_color.rgb * levels) / levels, out_color.a);
  }

  // Ambient tint — default [1,1,1] is a genuine no-op multiply.
  out_color = vec4<f32>(out_color.rgb * u.ambient_color.rgb, out_color.a);

  // Distance fog (opt-in via camera.fogFar > 0). frag_pos.z is the
  // fragment's NDC depth in [0,1] (WebGPU's documented depth range — see
  // mat4.js's perspective() header comment). Linearize it back to a
  // world-unit forward distance by inverting this project's exact
  // perspective() matrix (mat4.js): for near/far clip planes proj_near/
  // proj_far, d = (proj_near * proj_far) / (proj_far - ndc_z * (proj_far
  // - proj_near)) recovers the same linear distance used to build fog_near/
  // fog_far against. Deliberately not the cheaper 1.0 / frag_pos.w trick
  // seen in some WGSL samples — that relies on exactly what
  // builtin(position).w means in the fragment stage, which isn't worth
  // staking correctness on when frag_pos.z's [0,1] meaning is
  // unambiguous and already documented elsewhere in this project.
  if (u.fog_range.y > 0.0) {
    let proj_near = u.mesh_params.z;
    let proj_far  = u.mesh_params.w;
    let ndc_z     = frag_pos.z;
    let view_dist = (proj_near * proj_far) / (proj_far - ndc_z * (proj_far - proj_near));
    let fog_amount = clamp(
      (view_dist - u.fog_range.x) / max(u.fog_range.y - u.fog_range.x, 0.001),
      0.0, 1.0,
    );
    out_color = vec4<f32>(mix(out_color.rgb, u.fog_color.rgb, fog_amount), out_color.a);
  }

  return out_color;
}
`;
}

/**
 * Turn a MATERIAL_FRAGMENT_SHADERS entry's `fs_main` into a plain callable
 * helper function for use inside buildMeshStyleWgslTail()'s `fs_mesh_stylized`.
 *
 * Two WGSL rules make this necessary rather than calling `fs_main`
 * as-is: (1) a function attributed `@fragment` is an entry point, and
 * entry points must not be the target of a function call; (2)
 * `@location(n)` attributes are only valid on entry-point IO (parameters/
 * return values, or struct members used as such), not on an arbitrary
 * function signature. So both attributes have to come off before
 * `fs_main` can be called as a regular helper.
 *
 * This never touches the FS_BASE/FS_OVERLAY/FS_HUE/FS_RAMP/FS_COSINE
 * constants themselves — it returns a transformed *copy* of whichever
 * string is passed in, used only when composing the mesh pipeline's WGSL
 * source. The 2D material pipeline (createMaterialPipeline) still
 * concatenates the original, fully unmodified string, where `fs_main`
 * genuinely is the entry point.
 *
 * Exact-string match rather than a general regex: every current variant
 * declares the identical signature `fn fs_main(@location(0) uv :
 * vec2<f32>) -> @location(0) vec4<f32>` (verified against the current
 * FS_BASE/FS_OVERLAY/FS_HUE/FS_RAMP/FS_COSINE source), so this is exact
 * and won't silently no-op if a future variant's signature drifts —
 * safer than a regex that could partially match and produce invalid WGSL.
 *
 * @param {string} fsSource - One of the MATERIAL_FRAGMENT_SHADERS values.
 * @returns {string}
 */
function stripFragmentEntryPoint(fsSource) {
  const signature =
    "fn fs_main(@location(0) uv : vec2<f32>) -> @location(0) vec4<f32>";
  if (!fsSource.includes(signature)) {
    throw new Error(
      "[ShaderCache] stripFragmentEntryPoint: fs_main signature did not " +
        "match the expected exact text — a MATERIAL_FRAGMENT_SHADERS " +
        "variant changed without updating this helper.",
    );
  }
  return fsSource
    .replace("@fragment", "")
    .replace(signature, "fn fs_main(uv : vec2<f32>) -> vec4<f32>");
}

/**
 * Compile a 'mesh' render pipeline for one fragment shader variant.
 * Pairs the mesh vertex stage (buildMeshWgslCommon) with a
 * stripFragmentEntryPoint()-transformed copy of the relevant
 * MATERIAL_FRAGMENT_SHADERS entry — the *original* string is untouched
 * and still used as-is by the 2D material pipeline. The transformed copy
 * is called (as a plain helper, no longer an entry point) from
 * buildMeshStyleWgslTail()'s `fs_mesh_stylized`, which is the mesh pipeline's
 * actual fragment entry point.
 *
 * @param {GPUDevice} device
 * @param {GPUTextureFormat} format
 * @param {GPUBindGroupLayout} bindGroupLayout - Explicit layout (from
 *   ShaderCache.getMaterialBindGroupLayout or MaterialLoader.bindGroupLayout).
 * @param {string} variantKey
 *   One of 'base' | 'overlay' | 'hue' | 'ramp' | 'cosine'.
 * @param {boolean} [affineUv=false] - See buildMeshWgslCommon's jsdoc.
 *   Passed to *both* buildMeshWgslCommon() and buildMeshStyleWgslTail() —
 *   they must agree, since one declares the vertex-output interpolation
 *   type and the other the fragment-input type at the same location.
 * @returns {GPURenderPipeline}
 */
function createMeshPipeline(device, format, bindGroupLayout, variantKey, affineUv = false) {
  const fs = stripFragmentEntryPoint(MATERIAL_FRAGMENT_SHADERS[variantKey] || FS_BASE);
  const wgsl = buildMeshWgslCommon(affineUv) + fs + buildMeshStyleWgslTail(affineUv);
  const shaderModule = device.createShaderModule({ code: wgsl });

  const pipelineLayout = device.createPipelineLayout({
    bindGroupLayouts: [bindGroupLayout],
  });

  return device.createRenderPipeline({
    layout: pipelineLayout,
    vertex: {
      module: shaderModule,
      entryPoint: "vs_main",
      buffers: [
        {
          // pos(12) + normal(12) + uv(8) + color(16) = 48 bytes/vertex —
          // matches mesh.js's MESH_VERTEX_ATTRIBUTES/MESH_VERTEX_STRIDE.
          arrayStride: 48,
          attributes: [
            { shaderLocation: 0, offset: 0, format: "float32x3" }, // pos
            { shaderLocation: 1, offset: 12, format: "float32x3" }, // normal
            { shaderLocation: 2, offset: 24, format: "float32x2" }, // uv
            { shaderLocation: 3, offset: 32, format: "float32x4" }, // color
          ],
        },
      ],
    },
    fragment: {
      module: shaderModule,
      // Step 8: the pipeline's actual entry point is the stylization
      // wrapper, not the shared fs_main it calls internally — see
      // buildMeshStyleWgslTail()'s jsdoc for why this can't just be a branch
      // inside fs_main itself.
      entryPoint: "fs_mesh_stylized",
      targets: [
        {
          format,
          blend: {
            color: {
              srcFactor: "one",
              dstFactor: "one-minus-src-alpha",
              operation: "add",
            },
            alpha: {
              srcFactor: "one",
              dstFactor: "one-minus-src-alpha",
              operation: "add",
            },
          },
        },
      ],
    },
    primitive: { topology: "triangle-list" },
    // Always depth-tested — mesh content is inherently 3D. Unlike the
    // base 2D sprite pipeline (never depth-tested, see getSpritePipeline),
    // there's no "existing 2D behaviour" to preserve here.
    depthStencil: {
      format: DEPTH_FORMAT,
      depthWriteEnabled: true,
      depthCompare: "less",
    },
  });
}
