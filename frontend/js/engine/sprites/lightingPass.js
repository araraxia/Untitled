/**
 * LightingPass — second render pass that accumulates additive point-light
 * contributions and multiplies the result into the base scene texture.
 *
 * Architecture (two-pass):
 *   Pass 1 — Sprite draw calls render into an offscreen scene GPUTexture
 *            (allocated and owned by renderer.js).
 *   Pass 2 — This class reads the scene texture and a uniform array of
 *            up to MAX_LIGHTS lights, accumulates per-pixel attenuation,
 *            and outputs  scene × (ambient + Σ lightContrib)  to the
 *            swap chain.
 *
 * Lighting model:
 *   For each light: falloff = 1 / (1 + dist² / radius²)
 *   output = sceneColor × clamp(ambient + Σ(lightColor × falloff), 0, ∞)
 *
 * Uniform buffer layout (LIGHT_UNIFORM_BYTES = 1120):
 *   view_proj   : mat4x4<f32>     bytes   0–63  world → NDC
 *   canvas_size : vec2<f32>       bytes  64–71
 *   count       : u32             bytes  72–75
 *   _pad_a      : u32             bytes  76–79
 *   ambient     : vec4<f32>       bytes  80–95  .rgb used; .a unused
 *   lights[32]  : struct Light    bytes  96–1119 (32 × 32 bytes each)
 *     .pos   : vec2<f32>   offset  +0  (8 bytes)
 *     ._pad  : vec2<f32>   offset  +8  (8 bytes, alignment padding)
 *     .color : vec4<f32>   offset +16  (16 bytes; .rgb = colour, .a = radius)
 */

const MAX_LIGHTS = 32;

/**
 * Byte size of the full LightUniforms struct.
 * 64 (view_proj) + 8 (canvas_size) + 4 (count) + 4 (_pad) + 16 (ambient)
 * + 32 (MAX_LIGHTS) * 32 (Light size) = 1120
 */
const LIGHT_UNIFORM_BYTES = 1120;

// ------------------------------------------------------------------
// WGSL source
// ------------------------------------------------------------------

const LIGHTING_WGSL = `
struct Light {
  pos   : vec2<f32>,
  _pad  : vec2<f32>,
  color : vec4<f32>, // .rgb = light colour, .a = radius in world pixels
};

struct LightUniforms {
  view_proj   : mat4x4<f32>,
  canvas_size : vec2<f32>,
  count       : u32,
  _pad_a      : u32,
  ambient     : vec4<f32>,
  lights      : array<Light, ${MAX_LIGHTS}>,
};

@group(0) @binding(0) var<uniform> u         : LightUniforms;
@group(0) @binding(1) var          u_scene   : texture_2d<f32>;
@group(0) @binding(2) var          u_sampler : sampler;

// Full-screen triangle — no vertex buffer required.
@vertex
fn vs_main(@builtin(vertex_index) vi : u32) -> @builtin(position) vec4<f32> {
  var pos = array<vec2<f32>, 3>(
    vec2<f32>(-1.0, -3.0),
    vec2<f32>(-1.0,  1.0),
    vec2<f32>( 3.0,  1.0),
  );
  return vec4<f32>(pos[vi], 0.0, 1.0);
}

@fragment
fn fs_main(@builtin(position) fragPos : vec4<f32>) -> @location(0) vec4<f32> {
  // Sample the base scene texture at the current fragment's UV.
  let uv    = fragPos.xy / u.canvas_size;
  let scene = textureSample(u_scene, u_sampler, uv);

  // Accumulate light contributions in screen-pixel space.
  var accum = u.ambient.rgb;
  for (var i : u32 = 0u; i < u.count; i++) {
    let light = u.lights[i];

    // Transform light world position → NDC → screen pixels.
    let ndc      = (u.view_proj * vec4<f32>(light.pos, 0.0, 1.0)).xy;
    let light_px = vec2<f32>(
      (ndc.x * 0.5 + 0.5)  * u.canvas_size.x,
      (0.5   - ndc.y * 0.5) * u.canvas_size.y,
    );

    let dist_sq = dot(fragPos.xy - light_px, fragPos.xy - light_px);
    let r       = max(light.color.a, 1.0);
    let falloff = 1.0 / (1.0 + dist_sq / (r * r));
    accum      += light.color.rgb * falloff;
  }

  // Multiply accumulated light map into the scene colour.
  return vec4<f32>(scene.rgb * accum, scene.a);
}
`;

// ------------------------------------------------------------------
// LightingPass class
// ------------------------------------------------------------------

class LightingPass {
  /**
   * @param {GPUDevice} device
   * @param {GPUTextureFormat} format - Swap-chain surface format.
   */
  constructor(device, format) {
    this._device = device;
    this._format = format;

    /** @type {[number, number, number]} */
    this._ambient = [1.0, 1.0, 1.0];

    this._uniformBuffer = device.createBuffer({
      size: LIGHT_UNIFORM_BYTES,
      usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST,
    });

    this._sampler = device.createSampler({
      minFilter: "nearest",
      magFilter: "nearest",
    });

    this._bindGroupLayout = device.createBindGroupLayout({
      entries: [
        {
          binding: 0,
          visibility: GPUShaderStage.FRAGMENT,
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
          sampler: { type: "filtering" },
        },
      ],
    });

    /** @type {GPUBindGroup|null} */
    this._bindGroup = null;

    this._pipeline = this._createPipeline();
  }

  // ------------------------------------------------------------------
  // Public API
  // ------------------------------------------------------------------

  /**
   * Provide (or replace) the scene texture that the lighting pass reads.
   * Must be called once after construction and again whenever the canvas
   * is resized (which requires a new scene texture to be allocated).
   *
   * @param {GPUTexture} sceneTexture
   */
  setSceneTexture(sceneTexture) {
    this._bindGroup = this._device.createBindGroup({
      layout: this._bindGroupLayout,
      entries: [
        { binding: 0, resource: { buffer: this._uniformBuffer } },
        { binding: 1, resource: sceneTexture.createView() },
        { binding: 2, resource: this._sampler },
      ],
    });
  }

  /**
   * Set the ambient light colour that illuminates the scene when no
   * point lights are active.  Default is (1, 1, 1) — full brightness.
   * Lower values darken unlit areas to create a night-time feel.
   *
   * @param {number} r
   * @param {number} g
   * @param {number} b
   */
  setAmbient(r, g, b) {
    this._ambient = [r, g, b];
  }

  /**
   * Write the current light state into the GPU uniform buffer.
   * Call this once per frame, before render(), with the aggregated
   * list of active lights from the current game state.
   *
   * @param {Array<{x:number, y:number, color:number[], radius:number}>} lightsArray
   *   Up to MAX_LIGHTS entries; extras are ignored.
   * @param {{x:number, y:number}} camera - Current camera world position.
   * @param {number} canvasWidth
   * @param {number} canvasHeight
   */
  updateLights(lightsArray, camera, canvasWidth, canvasHeight) {
    const data = new ArrayBuffer(LIGHT_UNIFORM_BYTES);
    const f32 = new Float32Array(data);
    const u32 = new Uint32Array(data);

    const cW = canvasWidth;
    const cH = canvasHeight;
    const cx = camera.x;
    const cy = camera.y;

    // Column-major mat4x4: world → NDC
    //   ndcX = 2*(wx - cx) / cW - 1  =  (2/cW)*wx + (-2*cx/cW - 1)
    //   ndcY = 1 - 2*(wy - cy) / cH  = -(2/cH)*wy + ( 1 + 2*cy/cH)
    // col 0
    f32[0] = 2 / cW;
    f32[1] = 0;
    f32[2] = 0;
    f32[3] = 0;
    // col 1
    f32[4] = 0;
    f32[5] = -2 / cH;
    f32[6] = 0;
    f32[7] = 0;
    // col 2
    f32[8] = 0;
    f32[9] = 0;
    f32[10] = 1;
    f32[11] = 0;
    // col 3  (translation)
    f32[12] = (-2 * cx) / cW - 1;
    f32[13] = (2 * cy) / cH + 1;
    f32[14] = 0;
    f32[15] = 1;

    // canvas_size at byte offset 64 = float index 16
    f32[16] = cW;
    f32[17] = cH;

    // count at byte offset 72 = uint32 index 18
    const count = Math.min(lightsArray.length, MAX_LIGHTS);
    u32[18] = count;
    // _pad_a at uint32 index 19 — leave as 0

    // ambient at byte offset 80 = float index 20
    f32[20] = this._ambient[0];
    f32[21] = this._ambient[1];
    f32[22] = this._ambient[2];
    f32[23] = 0; // .w unused

    // lights at byte offset 96 = float index 24
    // Each Light is 32 bytes = 8 floats: pos(2) + _pad(2) + color(4)
    for (let i = 0; i < count; i++) {
      const light = lightsArray[i];
      const base = 24 + i * 8;
      const col = light.color || [1.0, 1.0, 0.9];
      f32[base + 0] = light.x;
      f32[base + 1] = light.y;
      f32[base + 2] = 0; // _pad.x
      f32[base + 3] = 0; // _pad.y
      f32[base + 4] = col[0] !== undefined ? col[0] : 1.0;
      f32[base + 5] = col[1] !== undefined ? col[1] : 1.0;
      f32[base + 6] = col[2] !== undefined ? col[2] : 0.9;
      f32[base + 7] = light.radius || 150.0;
    }

    this._device.queue.writeBuffer(this._uniformBuffer, 0, data);
  }

  /**
   * Encode the lighting pass into the given command encoder.
   * The pass reads the scene texture set by setSceneTexture() and
   * writes the lit result to outputTextureView (the swap-chain surface).
   *
   * @param {GPUCommandEncoder} commandEncoder
   * @param {GPUTextureView} outputTextureView - Swap-chain texture view.
   */
  render(commandEncoder, outputTextureView) {
    if (!this._bindGroup) {
      console.warn("[LightingPass] render() called before setSceneTexture()");
      return;
    }

    const pass = commandEncoder.beginRenderPass({
      colorAttachments: [
        {
          view: outputTextureView,
          loadOp: "clear",
          storeOp: "store",
          clearValue: { r: 0, g: 0, b: 0, a: 1 },
        },
      ],
    });
    pass.setPipeline(this._pipeline);
    pass.setBindGroup(0, this._bindGroup);
    pass.draw(3); // full-screen triangle; no vertex buffer
    pass.end();
  }

  // ------------------------------------------------------------------
  // Private helpers
  // ------------------------------------------------------------------

  _createPipeline() {
    const shaderModule = this._device.createShaderModule({
      code: LIGHTING_WGSL,
    });
    const pipelineLayout = this._device.createPipelineLayout({
      bindGroupLayouts: [this._bindGroupLayout],
    });
    return this._device.createRenderPipeline({
      layout: pipelineLayout,
      vertex: {
        module: shaderModule,
        entryPoint: "vs_main",
      },
      fragment: {
        module: shaderModule,
        entryPoint: "fs_main",
        targets: [
          {
            format: this._format,
            // Opaque replace — we write the fully composited value.
            blend: {
              color: {
                srcFactor: "one",
                dstFactor: "zero",
                operation: "add",
              },
              alpha: {
                srcFactor: "one",
                dstFactor: "zero",
                operation: "add",
              },
            },
          },
        ],
      },
      primitive: { topology: "triangle-list" },
    });
  }
}
