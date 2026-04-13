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

/**
 * Compile the sprite pipeline for the given device and swap-chain format.
 * @param {GPUDevice} device
 * @param {GPUTextureFormat} format
 * @returns {GPURenderPipeline}
 */
function createSpritePipeline(device, format) {
  const shaderModule = device.createShaderModule({ code: SPRITE_WGSL });

  return device.createRenderPipeline({
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
  });
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

    /** @type {Map<string, GPURenderPipeline>} */
    this._materialPipelines = new Map();

    /** @type {GPUBindGroupLayout|null} */
    this._materialBGL = null;
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
