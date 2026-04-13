/**
 * ParticleSystem — GPU compute-based particle simulation (Phase 2.5).
 *
 * Architecture:
 *   • A GPUBuffer (STORAGE | COPY_DST) holds up to maxParticles Particle
 *     structs.  The CPU writes initial state for newly spawned particles via
 *     device.queue.writeBuffer() using a ring-buffer slot counter.
 *   • simulate(commandEncoder, dtSeconds) — encodes a GPUComputePass that
 *     integrates velocities, applies gravity, and decrements lifetimes.
 *     Must be called BEFORE the sprite render pass in the same command
 *     encoder so the GPU sees the updated positions.
 *   • render(passEncoder, camera, cW, cH) — draws maxParticles instanced
 *     billboard quads.  Dead particles (lifetime < 0) produce alpha = 0
 *     and are discarded; no compaction is needed.
 *
 * Particle struct layout (48 bytes, matches WGSL alignment):
 *   pos      : vec2<f32>   offset  0   (8 bytes)
 *   vel      : vec2<f32>   offset  8   (8 bytes)
 *   color    : vec4<f32>   offset 16  (16 bytes)
 *   lifetime : f32         offset 32   (4 bytes)
 *   size     : f32         offset 36   (4 bytes)
 *   _pad     : vec2<f32>   offset 40   (8 bytes)
 *                          total : 48 bytes
 *
 * Emitter config (entity.emitter JSON field):
 *   max_particles : number   initial allocation; not hot-reloadable
 *   emit_rate     : number   particles/second          (default 20)
 *   initial_vel   : [vx,vy] pixels/second             (default [0, -30])
 *   spread        : number   ± random spread per axis  (default 10)
 *   lifetime      : number   seconds per particle      (default 2.0)
 *   color         : [r,g,b,a]                          (default fire orange)
 *   size          : number   particle radius in pixels (default 4.0)
 */

/** Bytes per Particle struct — must match the WGSL layout above. */
const PARTICLE_SIZE_BYTES = 48;

/** Floats per Particle (PARTICLE_SIZE_BYTES / 4). */
const PARTICLE_FLOATS = 12;

/** Compute workgroup size — must match @workgroup_size in the shader. */
const PARTICLE_COMPUTE_WG = 64;

/** Default maximum live particles when the emitter config omits max_particles. */
const DEFAULT_MAX_PARTICLES = 512;

// ------------------------------------------------------------------
// WGSL — compute simulation shader
// ------------------------------------------------------------------

const PARTICLE_COMPUTE_WGSL = `
struct Particle {
  pos      : vec2<f32>,
  vel      : vec2<f32>,
  color    : vec4<f32>,
  lifetime : f32,
  size     : f32,
  _pad     : vec2<f32>,
};

struct SimUniforms {
  delta_time : f32,
  time       : f32,
  _pad0      : f32,
  _pad1      : f32,
};

@group(0) @binding(0) var<storage, read_write> particles : array<Particle>;
@group(0) @binding(1) var<uniform>             u         : SimUniforms;

// Gentle downward drift in world units (pixels/sec²).
const GRAVITY = vec2<f32>(0.0, -9.8 * 0.01);

@compute @workgroup_size(${PARTICLE_COMPUTE_WG})
fn cs_main(@builtin(global_invocation_id) gid : vec3<u32>) {
  let i = gid.x;
  if i >= arrayLength(&particles) { return; }
  var p = particles[i];
  if p.lifetime < 0.0 { return; }
  p.vel      += GRAVITY * u.delta_time;
  p.pos      += p.vel   * u.delta_time;
  p.lifetime -= u.delta_time;
  particles[i] = p;
}
`;

// ------------------------------------------------------------------
// WGSL — billboard render shader
// ------------------------------------------------------------------

const PARTICLE_RENDER_WGSL = `
struct Particle {
  pos      : vec2<f32>,
  vel      : vec2<f32>,
  color    : vec4<f32>,
  lifetime : f32,
  size     : f32,
  _pad     : vec2<f32>,
};

struct RenderUniforms {
  canvas_width  : f32,
  canvas_height : f32,
  camera_x      : f32,
  camera_y      : f32,
};

@group(0) @binding(0) var<storage, read> particles : array<Particle>;
@group(0) @binding(1) var<uniform>       u         : RenderUniforms;

struct VertexOut {
  @builtin(position) position : vec4<f32>,
  @location(0)       color    : vec4<f32>,
};

@vertex
fn vs_particle(
  @builtin(vertex_index)   vi : u32,
  @builtin(instance_index) ii : u32,
) -> VertexOut {
  // Unit quad offsets for two triangles (CCW winding).
  var quad = array<vec2<f32>, 6>(
    vec2<f32>(-0.5, -0.5), vec2<f32>( 0.5, -0.5), vec2<f32>( 0.5,  0.5),
    vec2<f32>(-0.5, -0.5), vec2<f32>( 0.5,  0.5), vec2<f32>(-0.5,  0.5),
  );
  let p      = particles[ii];
  let offset = quad[vi] * p.size;

  // World → screen pixel space, then → NDC.
  let sx   = p.pos.x - u.camera_x + offset.x;
  let sy   = p.pos.y - u.camera_y + offset.y;
  let ndcX =  2.0 * sx / u.canvas_width  - 1.0;
  let ndcY =  1.0 - 2.0 * sy / u.canvas_height;

  // Fade alpha toward 0 as lifetime → 0 (or < 0 → fully dead).
  let alpha = clamp(p.lifetime, 0.0, 1.0) * p.color.a;

  var out : VertexOut;
  out.position = vec4<f32>(ndcX, ndcY, 0.0, 1.0);
  // Pre-multiplied alpha to match the swap-chain alphaMode.
  out.color    = vec4<f32>(p.color.rgb * alpha, alpha);
  return out;
}

@fragment
fn fs_particle(@location(0) color : vec4<f32>) -> @location(0) vec4<f32> {
  // Discard fully transparent fragments (dead particles, rounding errors).
  if color.a < 0.004 { discard; }
  return color;
}
`;

// ------------------------------------------------------------------
// ParticleSystem class
// ------------------------------------------------------------------

class ParticleSystem {
  /**
   * @param {GPUDevice} device
   * @param {GPUTextureFormat} format - Swap-chain surface format; used for
   *   the render pipeline's color target.
   * @param {number} [maxParticles=DEFAULT_MAX_PARTICLES]
   */
  constructor(device, format, maxParticles = DEFAULT_MAX_PARTICLES) {
    this._device = device;
    this._format = format;
    this._maxParticles = maxParticles;

    /** Ring-buffer write head — next slot to overwrite on emission. */
    this._nextSlot = 0;
    /** Fractional emission accumulator; tracks sub-particle remainders. */
    this._emitAccum = 0;

    // Particle storage buffer.
    // STORAGE  — compute (read_write) and render (read-only) bindings.
    // COPY_DST — CPU emission writes via device.queue.writeBuffer().
    this._particleBuffer = device.createBuffer({
      size: maxParticles * PARTICLE_SIZE_BYTES,
      usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST,
    });

    // Simulation uniform buffer: delta_time, time, _pad, _pad (16 bytes).
    this._simUniformBuffer = device.createBuffer({
      size: 16,
      usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST,
    });

    // Render uniform buffer: canvas_width, canvas_height, camera_x, camera_y.
    this._renderUniformBuffer = device.createBuffer({
      size: 16,
      usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST,
    });

    this._computePipeline = this._createComputePipeline();
    this._computeBindGroup = this._createComputeBindGroup();
    this._renderPipeline = this._createRenderPipeline();
    this._renderBindGroup = this._createRenderBindGroup();

    console.log(
      "[ParticleSystem] Created — maxParticles:",
      maxParticles,
      "bufferSize:",
      maxParticles * PARTICLE_SIZE_BYTES,
      "bytes",
    );
  }

  // ------------------------------------------------------------------
  // Public API
  // ------------------------------------------------------------------

  /**
   * Spawn new particles into ring-buffer slots and upload their initial
   * state to the GPU via device.queue.writeBuffer().
   *
   * @param {number} emitterX - World X of the emitter (interpolated pos).
   * @param {number} emitterY - World Y of the emitter.
   * @param {Object} config   - Emitter config (see file-level JSDoc).
   * @param {number} dtSeconds - Time elapsed since the last frame, seconds.
   */
  emit(emitterX, emitterY, config, dtSeconds) {
    this._emitAccum += (config.emit_rate || 20) * dtSeconds;
    const toEmit = Math.min(Math.floor(this._emitAccum), this._maxParticles);
    this._emitAccum -= toEmit;
    if (toEmit === 0) return;

    const col = config.color || [1.0, 0.5, 0.0, 1.0];
    const initVel = config.initial_vel || [0, -30];
    const spread = typeof config.spread === "number" ? config.spread : 10;
    const lifetime =
      typeof config.lifetime === "number" ? config.lifetime : 2.0;
    const size = typeof config.size === "number" ? config.size : 4.0;

    const raw = new Float32Array(toEmit * PARTICLE_FLOATS);
    for (let i = 0; i < toEmit; i++) {
      const vx = initVel[0] + (Math.random() - 0.5) * spread;
      const vy = initVel[1] + (Math.random() - 0.5) * spread;
      const base = i * PARTICLE_FLOATS;
      raw[base] = emitterX;
      raw[base + 1] = emitterY;
      raw[base + 2] = vx;
      raw[base + 3] = vy;
      raw[base + 4] = col[0] !== undefined ? col[0] : 1.0;
      raw[base + 5] = col[1] !== undefined ? col[1] : 0.5;
      raw[base + 6] = col[2] !== undefined ? col[2] : 0.0;
      raw[base + 7] = col[3] !== undefined ? col[3] : 1.0;
      raw[base + 8] = lifetime;
      raw[base + 9] = size;
      raw[base + 10] = 0; // _pad.x
      raw[base + 11] = 0; // _pad.y
    }

    // Write into the ring buffer.  Split into two writes if the range wraps.
    const start = this._nextSlot;
    const end = start + toEmit;

    if (end <= this._maxParticles) {
      this._device.queue.writeBuffer(
        this._particleBuffer,
        start * PARTICLE_SIZE_BYTES,
        raw,
      );
    } else {
      const firstCount = this._maxParticles - start;
      this._device.queue.writeBuffer(
        this._particleBuffer,
        start * PARTICLE_SIZE_BYTES,
        raw.subarray(0, firstCount * PARTICLE_FLOATS),
      );
      this._device.queue.writeBuffer(
        this._particleBuffer,
        0,
        raw.subarray(firstCount * PARTICLE_FLOATS),
      );
    }

    this._nextSlot = end % this._maxParticles;
  }

  /**
   * Encode a compute dispatch that simulates all live particles.
   * MUST be called on the commandEncoder BEFORE the render pass begins.
   *
   * @param {GPUCommandEncoder} commandEncoder
   * @param {number} dtSeconds
   */
  simulate(commandEncoder, dtSeconds) {
    const simData = new Float32Array([
      dtSeconds,
      performance.now() / 1000.0,
      0,
      0,
    ]);
    this._device.queue.writeBuffer(this._simUniformBuffer, 0, simData);

    const computePass = commandEncoder.beginComputePass();
    computePass.setPipeline(this._computePipeline);
    computePass.setBindGroup(0, this._computeBindGroup);
    computePass.dispatchWorkgroups(
      Math.ceil(this._maxParticles / PARTICLE_COMPUTE_WG),
    );
    computePass.end();
  }

  /**
   * Issue an instanced draw call for all particle billboard quads.
   * Must be called inside an active GPURenderPassEncoder, after simulate().
   *
   * @param {GPURenderPassEncoder} passEncoder
   * @param {{x:number, y:number}} camera
   * @param {number} canvasWidth
   * @param {number} canvasHeight
   */
  render(passEncoder, camera, canvasWidth, canvasHeight) {
    const renderData = new Float32Array([
      canvasWidth,
      canvasHeight,
      camera.x,
      camera.y,
    ]);
    this._device.queue.writeBuffer(this._renderUniformBuffer, 0, renderData);

    passEncoder.setPipeline(this._renderPipeline);
    passEncoder.setBindGroup(0, this._renderBindGroup);
    // 6 vertices × maxParticles instances; no vertex buffer needed.
    passEncoder.draw(6, this._maxParticles);
  }

  // ------------------------------------------------------------------
  // Private helpers
  // ------------------------------------------------------------------

  _createComputePipeline() {
    const bgl = this._device.createBindGroupLayout({
      entries: [
        {
          binding: 0,
          visibility: GPUShaderStage.COMPUTE,
          buffer: { type: "storage" },
        },
        {
          binding: 1,
          visibility: GPUShaderStage.COMPUTE,
          buffer: { type: "uniform" },
        },
      ],
    });
    const module = this._device.createShaderModule({
      code: PARTICLE_COMPUTE_WGSL,
    });
    return this._device.createComputePipeline({
      layout: this._device.createPipelineLayout({ bindGroupLayouts: [bgl] }),
      compute: { module, entryPoint: "cs_main" },
    });
  }

  _createComputeBindGroup() {
    const bgl = this._computePipeline.getBindGroupLayout(0);
    return this._device.createBindGroup({
      layout: bgl,
      entries: [
        { binding: 0, resource: { buffer: this._particleBuffer } },
        { binding: 1, resource: { buffer: this._simUniformBuffer } },
      ],
    });
  }

  _createRenderPipeline() {
    const bgl = this._device.createBindGroupLayout({
      entries: [
        {
          // Particle data — read-only in vertex stage.
          binding: 0,
          visibility: GPUShaderStage.VERTEX,
          buffer: { type: "read-only-storage" },
        },
        {
          binding: 1,
          visibility: GPUShaderStage.VERTEX,
          buffer: { type: "uniform" },
        },
      ],
    });
    const module = this._device.createShaderModule({
      code: PARTICLE_RENDER_WGSL,
    });
    return this._device.createRenderPipeline({
      layout: this._device.createPipelineLayout({ bindGroupLayouts: [bgl] }),
      vertex: {
        module,
        entryPoint: "vs_particle",
        // No vertex buffer — positions are computed from instance + vertex index.
      },
      fragment: {
        module,
        entryPoint: "fs_particle",
        targets: [
          {
            format: this._format,
            // Pre-multiplied alpha blending (matches canvas alphaMode).
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

  _createRenderBindGroup() {
    const bgl = this._renderPipeline.getBindGroupLayout(0);
    return this._device.createBindGroup({
      layout: bgl,
      entries: [
        { binding: 0, resource: { buffer: this._particleBuffer } },
        { binding: 1, resource: { buffer: this._renderUniformBuffer } },
      ],
    });
  }
}
