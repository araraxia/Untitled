"""ParticleSystem -- GPU compute-based particle simulation.

Port of frontend/js/engine/sprites/particleSystem.js -- Step 7 of
.github/prompts/wgpu-py-migration.prompt.md. WGSL source ported
verbatim; orchestration translated to snake_case with `array.array`
(stdlib, no numpy) for CPU-side particle data packing, matching every
other module in this port.

Architecture:
    - A GPUBuffer (STORAGE | COPY_DST) holds up to max_particles
      Particle structs. The CPU writes initial state for newly spawned
      particles via device.queue.write_buffer() using a ring-buffer
      slot counter.
    - simulate(command_encoder, dt_seconds) -- encodes a
      GPUComputePassEncoder that integrates velocities, applies
      gravity, and decrements lifetimes. Must be called BEFORE the
      sprite render pass in the same command encoder so the GPU sees
      the updated positions.
    - render(pass_encoder, camera, canvas_width, canvas_height) --
      draws max_particles instanced billboard quads. Dead particles
      (lifetime < 0) produce alpha = 0 and are discarded; no compaction
      is needed.

Particle struct layout (48 bytes, matches WGSL alignment):
    pos      : vec2<f32>   offset  0   (8 bytes)
    vel      : vec2<f32>   offset  8   (8 bytes)
    color    : vec4<f32>   offset 16  (16 bytes)
    lifetime : f32         offset 32   (4 bytes)
    size     : f32         offset 36   (4 bytes)
    _pad     : vec2<f32>   offset 40   (8 bytes)
                           total : 48 bytes

Emitter config (entity.emitter JSON field):
    max_particles : number   initial allocation; not hot-reloadable
    emit_rate     : number   particles/second          (default 20)
    initial_vel   : [vx,vy] pixels/second             (default [0, -30])
    spread        : number   +/- random spread per axis  (default 10)
    lifetime      : number   seconds per particle      (default 2.0)
    color         : [r,g,b,a]                          (default fire orange)
    size          : number   particle radius in pixels (default 4.0)
"""

import array
import random
import time

import wgpu

# Bytes per Particle struct -- must match the WGSL layout above.
PARTICLE_SIZE_BYTES = 48

# Floats per Particle (PARTICLE_SIZE_BYTES / 4).
PARTICLE_FLOATS = 12

# Compute workgroup size -- must match @workgroup_size in the shader.
PARTICLE_COMPUTE_WG = 64

# Default maximum live particles when the emitter config omits max_particles.
DEFAULT_MAX_PARTICLES = 512

# ----------------------------------------------------------------------
# WGSL -- compute simulation shader
# ----------------------------------------------------------------------

PARTICLE_COMPUTE_WGSL = f"""
struct Particle {{
  pos      : vec2<f32>,
  vel      : vec2<f32>,
  color    : vec4<f32>,
  lifetime : f32,
  size     : f32,
  _pad     : vec2<f32>,
}};

struct SimUniforms {{
  delta_time : f32,
  time       : f32,
  _pad0      : f32,
  _pad1      : f32,
}};

@group(0) @binding(0) var<storage, read_write> particles : array<Particle>;
@group(0) @binding(1) var<uniform>             u         : SimUniforms;

// Gentle downward drift in world units (pixels/sec^2).
const GRAVITY = vec2<f32>(0.0, -9.8 * 0.01);

@compute @workgroup_size({PARTICLE_COMPUTE_WG})
fn cs_main(@builtin(global_invocation_id) gid : vec3<u32>) {{
  let i = gid.x;
  if i >= arrayLength(&particles) {{ return; }}
  var p = particles[i];
  if p.lifetime < 0.0 {{ return; }}
  p.vel      += GRAVITY * u.delta_time;
  p.pos      += p.vel   * u.delta_time;
  p.lifetime -= u.delta_time;
  particles[i] = p;
}}
"""

# ----------------------------------------------------------------------
# WGSL -- billboard render shader
# ----------------------------------------------------------------------

PARTICLE_RENDER_WGSL = """
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

  // World -> screen pixel space, then -> NDC.
  let sx   = p.pos.x - u.camera_x + offset.x;
  let sy   = p.pos.y - u.camera_y + offset.y;
  let ndcX =  2.0 * sx / u.canvas_width  - 1.0;
  let ndcY =  1.0 - 2.0 * sy / u.canvas_height;

  // Fade alpha toward 0 as lifetime -> 0 (or < 0 -> fully dead).
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
"""


class ParticleSystem:
    """
    Args:
        device: GPUDevice.
        format: GPUTextureFormat -- swap-chain surface format; used for
            the render pipeline's color target.
        max_particles: Defaults to DEFAULT_MAX_PARTICLES.
    """

    def __init__(self, device, format, max_particles: int = DEFAULT_MAX_PARTICLES):
        self._device = device
        self._format = format
        self._max_particles = max_particles

        # Ring-buffer write head -- next slot to overwrite on emission.
        self._next_slot = 0
        # Fractional emission accumulator; tracks sub-particle remainders.
        self._emit_accum = 0.0

        # Particle storage buffer.
        # STORAGE  -- compute (read_write) and render (read-only) bindings.
        # COPY_DST -- CPU emission writes via device.queue.write_buffer().
        self._particle_buffer = device.create_buffer(
            size=max_particles * PARTICLE_SIZE_BYTES,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
        )

        # Simulation uniform buffer: delta_time, time, _pad, _pad (16 bytes).
        self._sim_uniform_buffer = device.create_buffer(
            size=16,
            usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
        )

        # Render uniform buffer: canvas_width, canvas_height, camera_x, camera_y.
        self._render_uniform_buffer = device.create_buffer(
            size=16,
            usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
        )

        self._compute_pipeline = self._create_compute_pipeline()
        self._compute_bind_group = self._create_compute_bind_group()
        self._render_pipeline = self._create_render_pipeline()
        self._render_bind_group = self._create_render_bind_group()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def emit(self, emitter_x: float, emitter_y: float, config: dict, dt_seconds: float) -> None:
        """Spawn new particles into ring-buffer slots and upload their
        initial state to the GPU via device.queue.write_buffer().

        Args:
            emitter_x: World X of the emitter (interpolated pos).
            emitter_y: World Y of the emitter.
            config: Emitter config (see module docstring).
            dt_seconds: Time elapsed since the last frame, seconds.
        """
        self._emit_accum += config.get("emit_rate", 20) * dt_seconds
        to_emit = min(int(self._emit_accum), self._max_particles)
        self._emit_accum -= to_emit
        if to_emit == 0:
            return

        col = config.get("color", [1.0, 0.5, 0.0, 1.0])
        init_vel = config.get("initial_vel", [0, -30])
        spread = config.get("spread", 10)
        lifetime = config.get("lifetime", 2.0)
        size = config.get("size", 4.0)

        raw = array.array("f", [0.0] * (to_emit * PARTICLE_FLOATS))
        for i in range(to_emit):
            vx = init_vel[0] + (random.random() - 0.5) * spread
            vy = init_vel[1] + (random.random() - 0.5) * spread
            base = i * PARTICLE_FLOATS
            raw[base] = emitter_x
            raw[base + 1] = emitter_y
            raw[base + 2] = vx
            raw[base + 3] = vy
            raw[base + 4] = col[0] if len(col) > 0 else 1.0
            raw[base + 5] = col[1] if len(col) > 1 else 0.5
            raw[base + 6] = col[2] if len(col) > 2 else 0.0
            raw[base + 7] = col[3] if len(col) > 3 else 1.0
            raw[base + 8] = lifetime
            raw[base + 9] = size
            raw[base + 10] = 0  # _pad.x
            raw[base + 11] = 0  # _pad.y

        # Write into the ring buffer. Split into two writes if the range wraps.
        start = self._next_slot
        end = start + to_emit

        if end <= self._max_particles:
            self._device.queue.write_buffer(
                self._particle_buffer, start * PARTICLE_SIZE_BYTES, raw
            )
        else:
            first_count = self._max_particles - start
            self._device.queue.write_buffer(
                self._particle_buffer,
                start * PARTICLE_SIZE_BYTES,
                raw[: first_count * PARTICLE_FLOATS],
            )
            self._device.queue.write_buffer(
                self._particle_buffer, 0, raw[first_count * PARTICLE_FLOATS :]
            )

        self._next_slot = end % self._max_particles

    def simulate(self, command_encoder, dt_seconds: float) -> None:
        """Encode a compute dispatch that simulates all live particles.
        MUST be called on the command_encoder BEFORE the render pass
        begins.
        """
        sim_data = array.array("f", [dt_seconds, time.perf_counter(), 0.0, 0.0])
        self._device.queue.write_buffer(self._sim_uniform_buffer, 0, sim_data)

        compute_pass = command_encoder.begin_compute_pass()
        compute_pass.set_pipeline(self._compute_pipeline)
        compute_pass.set_bind_group(0, self._compute_bind_group)
        compute_pass.dispatch_workgroups(
            -(-self._max_particles // PARTICLE_COMPUTE_WG)
        )
        compute_pass.end()

    def render(self, pass_encoder, camera: dict, canvas_width: int, canvas_height: int) -> None:
        """Issue an instanced draw call for all particle billboard quads.
        Must be called inside an active GPURenderPassEncoder, after
        simulate().
        """
        render_data = array.array(
            "f", [canvas_width, canvas_height, camera["x"], camera["y"]]
        )
        self._device.queue.write_buffer(self._render_uniform_buffer, 0, render_data)

        pass_encoder.set_pipeline(self._render_pipeline)
        pass_encoder.set_bind_group(0, self._render_bind_group)
        # 6 vertices x max_particles instances; no vertex buffer needed.
        pass_encoder.draw(6, self._max_particles)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _create_compute_pipeline(self):
        bgl = self._device.create_bind_group_layout(
            entries=[
                {
                    "binding": 0,
                    "visibility": wgpu.ShaderStage.COMPUTE,
                    "buffer": {"type": "storage"},
                },
                {
                    "binding": 1,
                    "visibility": wgpu.ShaderStage.COMPUTE,
                    "buffer": {"type": "uniform"},
                },
            ]
        )
        module = self._device.create_shader_module(code=PARTICLE_COMPUTE_WGSL)
        return self._device.create_compute_pipeline(
            layout=self._device.create_pipeline_layout(bind_group_layouts=[bgl]),
            compute={"module": module, "entry_point": "cs_main"},
        )

    def _create_compute_bind_group(self):
        bgl = self._compute_pipeline.get_bind_group_layout(0)
        return self._device.create_bind_group(
            layout=bgl,
            entries=[
                {"binding": 0, "resource": {"buffer": self._particle_buffer}},
                {"binding": 1, "resource": {"buffer": self._sim_uniform_buffer}},
            ],
        )

    def _create_render_pipeline(self):
        bgl = self._device.create_bind_group_layout(
            entries=[
                {
                    # Particle data -- read-only in vertex stage.
                    "binding": 0,
                    "visibility": wgpu.ShaderStage.VERTEX,
                    "buffer": {"type": "read-only-storage"},
                },
                {
                    "binding": 1,
                    "visibility": wgpu.ShaderStage.VERTEX,
                    "buffer": {"type": "uniform"},
                },
            ]
        )
        module = self._device.create_shader_module(code=PARTICLE_RENDER_WGSL)
        return self._device.create_render_pipeline(
            layout=self._device.create_pipeline_layout(bind_group_layouts=[bgl]),
            vertex={
                "module": module,
                "entry_point": "vs_particle",
                # No vertex buffer -- positions are computed from instance + vertex index.
            },
            fragment={
                "module": module,
                "entry_point": "fs_particle",
                "targets": [
                    {
                        "format": self._format,
                        # Pre-multiplied alpha blending (matches canvas alphaMode).
                        "blend": {
                            "color": {
                                "src_factor": "one",
                                "dst_factor": "one-minus-src-alpha",
                                "operation": "add",
                            },
                            "alpha": {
                                "src_factor": "one",
                                "dst_factor": "one-minus-src-alpha",
                                "operation": "add",
                            },
                        },
                    }
                ],
            },
            primitive={"topology": "triangle-list"},
        )

    def _create_render_bind_group(self):
        bgl = self._render_pipeline.get_bind_group_layout(0)
        return self._device.create_bind_group(
            layout=bgl,
            entries=[
                {"binding": 0, "resource": {"buffer": self._particle_buffer}},
                {"binding": 1, "resource": {"buffer": self._render_uniform_buffer}},
            ],
        )
