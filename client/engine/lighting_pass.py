"""LightingPass -- second render pass that accumulates additive
point-light contributions and multiplies the result into the base
scene texture.

Port of frontend/js/engine/sprites/lightingPass.js -- Step 7 of
.github/prompts/wgpu-py-migration.prompt.md. WGSL ported verbatim;
the manually-laid-out uniform buffer packing (view_proj/canvas_size/
count/ambient/lights[32]) is ported using the stdlib `array`/`struct`
modules instead of JS's ArrayBuffer + Float32Array/Uint32Array dual
views over the same memory -- Python's `array.array` doesn't support
that kind of type-punned aliasing cleanly, so this uses `struct.pack`
to build the exact same byte layout directly, which is more explicit
about the layout anyway (matching this project's stated preference for
explicit over implicit).

Architecture (two-pass):
    Pass 1 -- Sprite draw calls render into an offscreen scene
              GPUTexture (allocated and owned by renderer.py).
    Pass 2 -- This class reads the scene texture and a uniform array of
              up to MAX_LIGHTS lights, accumulates per-pixel
              attenuation, and outputs
              scene * (ambient + sum(light_contrib)) to the swap chain.

Lighting model:
    For each light: falloff = 1 / (1 + dist^2 / radius^2)
    output = scene_color * clamp(ambient + sum(light_color * falloff), 0, inf)

Uniform buffer layout (LIGHT_UNIFORM_BYTES = 1120):
    view_proj   : mat4x4<f32>     bytes   0-63  world -> NDC
    canvas_size : vec2<f32>       bytes  64-71
    count       : u32             bytes  72-75
    _pad_a      : u32             bytes  76-79
    ambient     : vec4<f32>       bytes  80-95  .rgb used; .a unused
    lights[32]  : struct Light    bytes  96-1119 (32 x 32 bytes each)
        .pos   : vec2<f32>   offset  +0  (8 bytes)
        ._pad  : vec2<f32>   offset  +8  (8 bytes, alignment padding)
        .color : vec4<f32>   offset +16  (16 bytes; .rgb = colour, .a = radius)
"""

import struct

import wgpu

MAX_LIGHTS = 32

# Byte size of the full LightUniforms struct.
# 64 (view_proj) + 8 (canvas_size) + 4 (count) + 4 (_pad) + 16 (ambient)
# + 32 (MAX_LIGHTS) * 32 (Light size) = 1120
LIGHT_UNIFORM_BYTES = 1120

# ----------------------------------------------------------------------
# WGSL source
# ----------------------------------------------------------------------

LIGHTING_WGSL = f"""
struct Light {{
  pos   : vec2<f32>,
  _pad  : vec2<f32>,
  color : vec4<f32>, // .rgb = light colour, .a = radius in world pixels
}};

struct LightUniforms {{
  view_proj   : mat4x4<f32>,
  canvas_size : vec2<f32>,
  count       : u32,
  _pad_a      : u32,
  ambient     : vec4<f32>,
  lights      : array<Light, {MAX_LIGHTS}>,
}};

@group(0) @binding(0) var<uniform> u         : LightUniforms;
@group(0) @binding(1) var          u_scene   : texture_2d<f32>;
@group(0) @binding(2) var          u_sampler : sampler;

// Full-screen triangle -- no vertex buffer required.
@vertex
fn vs_main(@builtin(vertex_index) vi : u32) -> @builtin(position) vec4<f32> {{
  var pos = array<vec2<f32>, 3>(
    vec2<f32>(-1.0, -3.0),
    vec2<f32>(-1.0,  1.0),
    vec2<f32>( 3.0,  1.0),
  );
  return vec4<f32>(pos[vi], 0.0, 1.0);
}}

@fragment
fn fs_main(@builtin(position) fragPos : vec4<f32>) -> @location(0) vec4<f32> {{
  // Sample the base scene texture at the current fragment's UV.
  let uv    = fragPos.xy / u.canvas_size;
  let scene = textureSample(u_scene, u_sampler, uv);

  // Accumulate light contributions in screen-pixel space.
  var accum = u.ambient.rgb;
  for (var i : u32 = 0u; i < u.count; i++) {{
    let light = u.lights[i];

    // Transform light world position -> NDC -> screen pixels.
    let ndc      = (u.view_proj * vec4<f32>(light.pos, 0.0, 1.0)).xy;
    let light_px = vec2<f32>(
      (ndc.x * 0.5 + 0.5)  * u.canvas_size.x,
      (0.5   - ndc.y * 0.5) * u.canvas_size.y,
    );

    let dist_sq = dot(fragPos.xy - light_px, fragPos.xy - light_px);
    let r       = max(light.color.a, 1.0);
    let falloff = 1.0 / (1.0 + dist_sq / (r * r));
    accum      += light.color.rgb * falloff;
  }}

  // Multiply accumulated light map into the scene colour.
  return vec4<f32>(scene.rgb * accum, scene.a);
}}
"""


class LightingPass:
    """
    Args:
        device: GPUDevice.
        format: GPUTextureFormat -- swap-chain surface format.
    """

    def __init__(self, device, format):
        self._device = device
        self._format = format

        self._ambient = [1.0, 1.0, 1.0]

        self._uniform_buffer = device.create_buffer(
            size=LIGHT_UNIFORM_BYTES,
            usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
        )

        self._sampler = device.create_sampler(min_filter="nearest", mag_filter="nearest")

        self._bind_group_layout = device.create_bind_group_layout(
            entries=[
                {
                    "binding": 0,
                    "visibility": wgpu.ShaderStage.FRAGMENT,
                    "buffer": {"type": "uniform"},
                },
                {
                    "binding": 1,
                    "visibility": wgpu.ShaderStage.FRAGMENT,
                    "texture": {"sample_type": "float"},
                },
                {
                    "binding": 2,
                    "visibility": wgpu.ShaderStage.FRAGMENT,
                    "sampler": {"type": "filtering"},
                },
            ]
        )

        self._bind_group = None

        self._pipeline = self._create_pipeline()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_scene_texture(self, scene_texture) -> None:
        """Provide (or replace) the scene texture that the lighting pass
        reads. Must be called once after construction and again
        whenever the canvas is resized (which requires a new scene
        texture to be allocated).
        """
        self._bind_group = self._device.create_bind_group(
            layout=self._bind_group_layout,
            entries=[
                {"binding": 0, "resource": {"buffer": self._uniform_buffer}},
                {"binding": 1, "resource": scene_texture.create_view()},
                {"binding": 2, "resource": self._sampler},
            ],
        )

    def set_ambient(self, r: float, g: float, b: float) -> None:
        """Set the ambient light colour that illuminates the scene when
        no point lights are active. Default is (1, 1, 1) -- full
        brightness. Lower values darken unlit areas to create a
        night-time feel.
        """
        self._ambient = [r, g, b]

    def update_lights(self, lights: list, camera: dict, canvas_width: int, canvas_height: int) -> None:
        """Write the current light state into the GPU uniform buffer.
        Call this once per frame, before render(), with the aggregated
        list of active lights from the current game state.

        Args:
            lights: Up to MAX_LIGHTS entries (each a dict with x, y,
                color=[r,g,b], radius); extras are ignored.
            camera: Current camera world position ({x, y}).
            canvas_width: int
            canvas_height: int
        """
        c_w = canvas_width
        c_h = canvas_height
        # Real bug, found via Step 18's smoke test: this whole method
        # builds a 2D screen-space orthographic transform (world -> NDC
        # via a simple camera-pan offset) -- a fundamentally 2D-camera
        # concept, same as the JS original (renderer.js calls
        # updateLights(lights, gameState.camera, ...) unconditionally,
        # regardless of camera.mode). Neither client's lighting pass has
        # ever been extended to a real 3D-camera design. JS's camera['x']
        # on a 3D-mode camera (which has position/target, not x/y) is
        # just `undefined`, NaN-poisoning the matrix silently rather than
        # crashing; direct dict bracket access here raised a real
        # KeyError instead the first time a 3D-mode frame actually ran
        # this code path for real (never exercised before this task's
        # own smoke test). Defaulting to 0 avoids both the crash and
        # uploading NaN into a GPU uniform buffer (worse than JS's silent
        # NaN -- undefined behavior on some drivers) -- harmless since
        # lighting has no defined meaning for 3D-mode scenes yet in
        # either client.
        cx = camera.get("x", 0)
        cy = camera.get("y", 0)

        # Column-major mat4x4: world -> NDC
        #   ndcX = 2*(wx - cx) / cW - 1  =  (2/cW)*wx + (-2*cx/cW - 1)
        #   ndcY = 1 - 2*(wy - cy) / cH  = -(2/cH)*wy + ( 1 + 2*cy/cH)
        view_proj = [
            2 / c_w, 0.0, 0.0, 0.0,  # col 0
            0.0, -2 / c_h, 0.0, 0.0,  # col 1
            0.0, 0.0, 1.0, 0.0,  # col 2
            (-2 * cx) / c_w - 1, (2 * cy) / c_h + 1, 0.0, 1.0,  # col 3 (translation)
        ]

        count = min(len(lights), MAX_LIGHTS)

        # Build the exact byte layout by hand with struct.pack, since
        # Python's array module (unlike JS's ArrayBuffer + multiple
        # typed-array views) doesn't cleanly support mixing f32/u32
        # views over the same buffer -- struct.pack is the explicit,
        # stdlib-only equivalent.
        buf = bytearray(LIGHT_UNIFORM_BYTES)
        struct.pack_into("<16f", buf, 0, *view_proj)  # offset 0, 64 bytes
        struct.pack_into("<2f", buf, 64, c_w, c_h)  # offset 64, 8 bytes
        struct.pack_into("<I", buf, 72, count)  # offset 72, 4 bytes
        # offset 76 (_pad_a) left as zero
        struct.pack_into(
            "<4f", buf, 80, self._ambient[0], self._ambient[1], self._ambient[2], 0.0
        )  # offset 80, 16 bytes

        for i in range(count):
            light = lights[i]
            base = 96 + i * 32
            col = light.get("color", [1.0, 1.0, 0.9])
            struct.pack_into("<2f", buf, base, light["x"], light["y"])  # pos
            # base + 8 : _pad, left as zero
            struct.pack_into(
                "<4f",
                buf,
                base + 16,
                col[0] if len(col) > 0 else 1.0,
                col[1] if len(col) > 1 else 1.0,
                col[2] if len(col) > 2 else 0.9,
                light.get("radius", 150.0),
            )  # color (.a = radius)

        self._device.queue.write_buffer(self._uniform_buffer, 0, bytes(buf))

    def render(self, command_encoder, output_texture_view) -> None:
        """Encode the lighting pass into the given command encoder. The
        pass reads the scene texture set by set_scene_texture() and
        writes the lit result to output_texture_view (the swap-chain
        surface).
        """
        if self._bind_group is None:
            return

        pass_encoder = command_encoder.begin_render_pass(
            color_attachments=[
                {
                    "view": output_texture_view,
                    "load_op": "clear",
                    "store_op": "store",
                    "clear_value": (0, 0, 0, 1),
                }
            ],
        )
        pass_encoder.set_pipeline(self._pipeline)
        pass_encoder.set_bind_group(0, self._bind_group)
        pass_encoder.draw(3)  # full-screen triangle; no vertex buffer
        pass_encoder.end()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _create_pipeline(self):
        shader_module = self._device.create_shader_module(code=LIGHTING_WGSL)
        pipeline_layout = self._device.create_pipeline_layout(
            bind_group_layouts=[self._bind_group_layout]
        )
        return self._device.create_render_pipeline(
            layout=pipeline_layout,
            vertex={"module": shader_module, "entry_point": "vs_main"},
            fragment={
                "module": shader_module,
                "entry_point": "fs_main",
                "targets": [
                    {
                        "format": self._format,
                        # Opaque replace -- we write the fully composited value.
                        "blend": {
                            "color": {
                                "src_factor": "one",
                                "dst_factor": "zero",
                                "operation": "add",
                            },
                            "alpha": {
                                "src_factor": "one",
                                "dst_factor": "zero",
                                "operation": "add",
                            },
                        },
                    }
                ],
            },
            primitive={"topology": "triangle-list"},
        )
