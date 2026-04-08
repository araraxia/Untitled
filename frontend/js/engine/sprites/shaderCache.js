/**
 * ShaderCache — compiles and caches GPURenderPipeline objects.
 *
 * Bind group layout (group 0):
 *   binding 0 — uniform buffer: { mvp: mat4x4<f32>, uv_rect: vec4<f32>, tint: vec4<f32> }
 *   binding 1 — texture_2d<f32>  (albedo atlas)
 *   binding 2 — sampler
 *
 * Vertex buffer layout (arrayStride 16):
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
    layout: 'auto',
    vertex: {
      module: shaderModule,
      entryPoint: 'vs_main',
      buffers: [{
        arrayStride: 16,
        attributes: [
          { shaderLocation: 0, offset: 0, format: 'float32x2' },
          { shaderLocation: 1, offset: 8, format: 'float32x2' },
        ],
      }],
    },
    fragment: {
      module: shaderModule,
      entryPoint: 'fs_main',
      targets: [{
        format,
        // Pre-multiplied alpha blending — matches alphaMode: 'premultiplied'.
        blend: {
          color: {
            srcFactor: 'one',
            dstFactor: 'one-minus-src-alpha',
            operation: 'add',
          },
          alpha: {
            srcFactor: 'one',
            dstFactor: 'one-minus-src-alpha',
            operation: 'add',
          },
        },
      }],
    },
    primitive: {
      topology: 'triangle-list',
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
  }

  /**
   * Return the cached sprite pipeline, creating it on first call.
   * @returns {GPURenderPipeline}
   */
  getSpritePipeline() {
    if (!this._spritePipeline) {
      this._spritePipeline = createSpritePipeline(this._device, this._format);
      console.log('[ShaderCache] Sprite pipeline created');
    }
    return this._spritePipeline;
  }
}
