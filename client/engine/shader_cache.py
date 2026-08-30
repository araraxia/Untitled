"""ShaderCache -- compiles and caches GPURenderPipeline objects.

Direct port of frontend/js/engine/sprites/shaderCache.js -- Step 6 of
.github/prompts/wgpu-py-migration.prompt.md. WGSL source strings are
ported verbatim (JS template literal -> Python triple-quoted string, no
shader-logic changes whatsoever); only the orchestration code
(dict/kwarg construction, pipeline caching) is translated to Python,
using this project's own snake_case convention for the descriptor dict
keys (confirmed against the actual installed wgpu 0.32 API during this
step -- e.g. `entryPoint` -> `entry_point`, `depthWriteEnabled` ->
`depth_write_enabled`, `srcFactor`/`dstFactor` -> `src_factor`/
`dst_factor`).

--- Workflow A (legacy, layout: 'auto') ---
Bind group layout (group 0):
  binding 0 -- uniform buffer: { mvp: mat4x4<f32>, uv_rect: vec4<f32>,
              tint: vec4<f32> }
  binding 1 -- texture_2d<f32>  (albedo atlas)
  binding 2 -- sampler

--- Material pipelines (explicit layout, 4 bindings) ---
Bind group layout (group 0):
  binding 0 -- uniform buffer (192 B base / 256 B mesh, see
              build_mesh_wgsl_common): mvp, uv_rect, uv_overlay, tint,
              intensity, time, ramp_steps, _pad, pal_a..pal_d
  binding 1 -- texture_2d<f32>  (albedo atlas)
  binding 2 -- texture_2d<f32>  (RGBA param map)
  binding 3 -- sampler

Vertex buffer layout (array_stride 16) -- shared by sprite pipelines:
  location 0 -- pos : float32x2  (offset 0)
  location 1 -- uv  : float32x2  (offset 8)
"""

import wgpu

SPRITE_WGSL = """
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
"""

# Depth texture format used by every depth-tested pipeline in this file.
DEPTH_FORMAT = "depth24plus"

# Standard pre-multiplied-alpha blend state, reused by every pipeline
# variant below (matches every blend descriptor in the JS original).
_PREMULTIPLIED_BLEND = {
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
}


def create_sprite_pipeline(device, format, depth_test: bool = False):
    """Compile the sprite pipeline for the given device and swap-chain
    format.

    Args:
        device: GPUDevice.
        format: GPUTextureFormat.
        depth_test: When True, adds depth write/compare state so draws
            using this pipeline correctly occlude each other by world
            depth (needed for 3D billboards -- see
            ShaderCache.get_sprite_pipeline_3d). The existing 2D path
            (ShaderCache.get_sprite_pipeline) always passes False, so 2D
            rendering is completely unaffected by this parameter's
            existence.
    """
    shader_module = device.create_shader_module(code=SPRITE_WGSL)

    kwargs = dict(
        layout="auto",
        vertex={
            "module": shader_module,
            "entry_point": "vs_main",
            "buffers": [
                {
                    "array_stride": 16,
                    "attributes": [
                        {"shader_location": 0, "offset": 0, "format": "float32x2"},
                        {"shader_location": 1, "offset": 8, "format": "float32x2"},
                    ],
                }
            ],
        },
        fragment={
            "module": shader_module,
            "entry_point": "fs_main",
            "targets": [{"format": format, "blend": _PREMULTIPLIED_BLEND}],
        },
        primitive={"topology": "triangle-list"},
    )

    if depth_test:
        kwargs["depth_stencil"] = {
            "format": DEPTH_FORMAT,
            "depth_write_enabled": True,
            "depth_compare": "less",
        }

    return device.create_render_pipeline(**kwargs)


class ShaderCache:
    """Lazy-create-and-cache GPURenderPipeline objects per variant."""

    def __init__(self, device, format):
        """
        Args:
            device: GPUDevice.
            format: GPUTextureFormat -- swap-chain format (from
                context.get_preferred_format(adapter) in this client,
                navigator.gpu.getPreferredCanvasFormat() in the JS one).
        """
        self._device = device
        self._format = format
        self._sprite_pipeline = None
        self._sprite_pipeline_3d = None

        self._material_pipelines: dict[str, object] = {}
        self._material_bgl = None
        self._mesh_pipelines: dict[str, object] = {}
        self._mesh_wireframe_pipeline = None

    def get_sprite_pipeline(self):
        """Return the cached sprite pipeline, creating it on first call."""
        if self._sprite_pipeline is None:
            self._sprite_pipeline = create_sprite_pipeline(self._device, self._format)
        return self._sprite_pipeline

    def get_sprite_pipeline_3d(self):
        """Return the cached depth-tested sprite pipeline used for 3D
        billboards (entity_renderer's draw_entity_3d), creating it on
        first call. Same SPRITE_WGSL shader and bind group layout shape
        as get_sprite_pipeline(), but a distinct GPURenderPipeline
        object (own auto bind group layout) with depth write/compare
        enabled -- kept fully separate from the 2D pipeline so bind
        groups are never accidentally shared across the two.
        """
        if self._sprite_pipeline_3d is None:
            self._sprite_pipeline_3d = create_sprite_pipeline(
                self._device, self._format, True
            )
        return self._sprite_pipeline_3d

    def get_material_bind_group_layout(self):
        """Return (creating lazily) the explicit GPUBindGroupLayout
        shared by all material pipeline variants. Callers may pass this
        layout to MaterialLoader so that bind groups and pipelines share
        the exact same GPUBindGroupLayout object (maximally safe).
        """
        if self._material_bgl is None:
            self._material_bgl = self._device.create_bind_group_layout(
                entries=[
                    {
                        "binding": 0,
                        "visibility": wgpu.ShaderStage.VERTEX | wgpu.ShaderStage.FRAGMENT,
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
                        "texture": {"sample_type": "float"},
                    },
                    {
                        "binding": 3,
                        "visibility": wgpu.ShaderStage.FRAGMENT,
                        "sampler": {"type": "filtering"},
                    },
                ]
            )
        return self._material_bgl

    def get_material_pipeline(self, variant_key: str, bind_group_layout=None):
        """Return the cached material pipeline for the given variant,
        creating it on first call. Falls back to 'base' for unrecognised
        keys.

        Valid variant_keys: 'base' | 'overlay' | 'hue' | 'ramp' | 'cosine'

        Args:
            variant_key: See above.
            bind_group_layout: Pass the layout from MaterialLoader to
                guarantee object-level compatibility. When omitted the
                layout from get_material_bind_group_layout() is used.
        """
        key = variant_key if variant_key in MATERIAL_FRAGMENT_SHADERS else "base"

        if key not in self._material_pipelines:
            bgl = bind_group_layout or self.get_material_bind_group_layout()
            self._material_pipelines[key] = create_material_pipeline(
                self._device, self._format, bgl, key
            )
        return self._material_pipelines[key]

    def get_mesh_pipeline(self, variant_key: str, bind_group_layout=None, affine_uv: bool = False):
        """Return the cached 'mesh' pipeline for the given material
        variant, creating it on first call. Shares the exact same
        MatUniforms struct layout (extended with Step 8's stylization
        fields), bind group layout, and fragment shaders
        (FS_BASE/FS_RAMP/FS_HUE/...) as get_material_pipeline() -- a
        mesh entity's MaterialLoader-built bind group binds to either
        interchangeably. Only the vertex stage differs (mesh attributes
        + a plain mvp transform, vs. a unit quad + an atlas sub-rect
        uniform) -- see build_mesh_wgsl_common() below.

        Always depth-tested (mesh content is inherently 3D), unlike the
        base 2D sprite pipeline -- matches the precedent set by
        get_sprite_pipeline_3d() for billboards.

        Args:
            variant_key: Same variant keys as get_material_pipeline.
            bind_group_layout: Pass MaterialLoader's layout to guarantee
                its bind groups are compatible with this pipeline.
            affine_uv: Step 8's affine (non-perspective-correct) UV
                interpolation toggle. WGSL's @interpolate attribute is
                fixed at shader-compile time, not a runtime uniform
                branch, so affine vs. perspective-correct UVs are
                necessarily two distinct compiled pipelines rather than
                one pipeline with a uniform branch (unlike the other
                Step 8 hooks, which are runtime branches inside a single
                fragment shader -- see build_mesh_style_wgsl_tail()).
                Part of the cache key so a material with affine_uv=True
                and one without don't collide.
        """
        variant = variant_key if variant_key in MATERIAL_FRAGMENT_SHADERS else "base"
        key = f"{variant}:{'affine' if affine_uv else 'persp'}"

        if key not in self._mesh_pipelines:
            bgl = bind_group_layout or self.get_material_bind_group_layout()
            self._mesh_pipelines[key] = create_mesh_pipeline(
                self._device, self._format, bgl, variant, affine_uv
            )
        return self._mesh_pipelines[key]

    def get_mesh_wireframe_pipeline(self, bind_group_layout=None):
        """Return the cached mesh-wireframe pipeline, creating it on
        first call -- the "View > Mesh > Wireframe" toggle's renderer,
        drawn as a line-list over Mesh.wireframe_index_buffer (see that
        property's own docstring: WebGPU has no native polygon
        wireframe fill mode, unlike OpenGL/Vulkan/D3D). One pipeline
        total, unlike get_mesh_pipeline's per-variant/per-affine_uv
        cache -- a flat-color line draw has no material variant or UV
        interpolation mode to key on.
        """
        if self._mesh_wireframe_pipeline is None:
            bgl = bind_group_layout or self.get_material_bind_group_layout()
            self._mesh_wireframe_pipeline = create_mesh_wireframe_pipeline(
                self._device, self._format, bgl
            )
        return self._mesh_wireframe_pipeline


# ======================================================================
# Material pipeline WGSL shaders
# ======================================================================

# Common WGSL declarations included in every material shader module.
# Defines the MatUniforms struct and all four group/binding declarations.
MATERIAL_WGSL_COMMON = """
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
"""

# Fragment shader -- base variant. Samples the albedo atlas at the
# current frame's UV rect and multiplies by the per-draw tint.
FS_BASE = """
@fragment
fn fs_main(@location(0) uv : vec2<f32>) -> @location(0) vec4<f32> {
  let atlas_uv = u.uv_rect.xy + uv * (u.uv_rect.zw - u.uv_rect.xy);
  return textureSample(u_albedo, u_sampler, atlas_uv) * u.tint;
}
"""

# Fragment shader -- overlay / emission variant. The param map's green
# channel drives an additive emission glow scaled by u.intensity.
# Useful for lanterns, fire, and glowing objects whose glow mask is
# baked into the param map.
FS_OVERLAY = """
@fragment
fn fs_main(@location(0) uv : vec2<f32>) -> @location(0) vec4<f32> {
  let atlas_uv = u.uv_rect.xy + uv * (u.uv_rect.zw - u.uv_rect.xy);
  let base     = textureSample(u_albedo,    u_sampler, atlas_uv) * u.tint;
  let emission = textureSample(u_param_map, u_sampler, uv).g;
  let glow     = vec4<f32>(base.rgb * emission * u.intensity, 0.0);
  return base + glow;
}
"""

# Fragment shader -- hue rotation variant. Converts the albedo colour to
# HSV, shifts the hue by u.intensity (0.0-1.0 maps to 0deg-360deg), and
# converts back. Set an entity runtime override 'hue_shift' at runtime.
FS_HUE = """
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
"""

# Fragment shader -- colour ramp (gradient map) variant.
#
# Remaps the sprite's per-pixel luminance through a 256x1 LUT texture
# stored in binding 2 (u_param_map). MaterialLoader puts the colour
# ramp PNG in that slot when color_ramp.type = 'texture'.
#
# ramp_steps >= 2 quantises luminance into discrete cel-shading bands
# before the LUT lookup; ramp_steps = 0 gives a smooth gradient.
#
# Luminance weights follow Rec. 601: (0.299, 0.587, 0.114).
FS_RAMP = """
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
"""

# Fragment shader -- cosine palette variant (Workflow C option 4).
#
# Computes a smooth procedural colour entirely on the GPU:
#   color(t) = pal_a + pal_b * cos(2*pi * (pal_c * t + pal_d))
# where t is the per-pixel Rec. 601 luminance of the albedo sample.
#
# No extra texture asset is required. Palette parameters are written
# into the MatUniforms struct (pal_a .. pal_d) by entity_renderer. Set
# an entity runtime override 'cosine_params' at runtime.
FS_COSINE = """
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
"""

# Fragment shader -- 'orb' variant: a Diablo/PoE-style liquid-filled
# orb for client/engine/ui/panel3d.py-driven UI elements (a health/mana
# orb) -- procedural, no new uniform fields needed. Reuses existing
# MatUniforms slots exactly like FS_COSINE already reuses pal_a..d for
# an unrelated purpose: intensity = fill level (0.0 empty - 1.0 full),
# pal_a.rgb = liquid color, pal_b.rgb = liquid surface highlight color,
# pal_c.rgb = rim/fresnel color, ramp_steps = rim falloff exponent
# (repurposed -- nothing about it is ramp-specific, it's just an unused
# float slot on this draw call), time = elapsed seconds for the liquid
# surface's wobble animation. u_albedo is sampled as a "glass" tint
# layer (a plain white texture is a valid no-op glass); u_param_map is
# unused by this variant but still declared/bound, same as every other
# variant sharing this fixed 4-binding layout.
FS_ORB = """
@fragment
fn fs_main(@location(0) uv : vec2<f32>) -> @location(0) vec4<f32> {
  let atlas_uv = u.uv_rect.xy + uv * (u.uv_rect.zw - u.uv_rect.xy);
  let glass    = textureSample(u_albedo, u_sampler, atlas_uv);

  // Circular mask: uv is assumed to span a square quad the orb circle
  // is inscribed in (center 0.5,0.5, radius 0.5 in uv space). Pixels
  // outside the circle are fully transparent so the orb reads as
  // round regardless of the bound quad's actual geometry.
  let centered = uv - vec2<f32>(0.5, 0.5);
  let dist     = length(centered) * 2.0; // 0 at center, 1 at circle edge
  if dist > 1.0 {
    return vec4<f32>(0.0, 0.0, 0.0, 0.0);
  }

  // Liquid surface: a horizontal fill line at u.intensity, with a small
  // sine wobble driven by u.time so it doesn't read as perfectly static.
  let wobble    = sin(uv.x * 12.566 + u.time * 2.0) * 0.015;
  let fill_line = 1.0 - u.intensity;
  let is_liquid = uv.y > (fill_line + wobble);

  var liquid_color = u.pal_a.rgb;
  if is_liquid && (uv.y - (fill_line + wobble)) < 0.02 {
    liquid_color = u.pal_b.rgb; // bright highlight right at the surface
  }
  let base_color = select(vec3<f32>(0.05, 0.05, 0.08), liquid_color, is_liquid);

  // Fresnel-style rim glow, brighter toward the circle's edge.
  let rim_power = max(u.ramp_steps, 1.0);
  let rim       = pow(dist, rim_power);
  let rim_color = u.pal_c.rgb * rim;

  let final_rgb = base_color * glass.rgb + rim_color;
  return vec4<f32>(final_rgb, 1.0) * u.tint;
}
"""

# Variant key -> fragment shader source mapping.
#
# | Key       | Trigger                     | Description                        |
# | --------- | --------------------------- | ---------------------------------- |
# | 'base'    | no flags                    | albedo x tint                      |
# | 'overlay' | has_overlay                 | base + additive glow via param G   |
# | 'hue'     | hue_shift runtime override  | HSV hue rotation                   |
# | 'ramp'    | color_ramp.type='texture'   | gradient map LUT (256x1 texture)   |
# | 'cosine'  | color_ramp.type='cosine'    | procedural cosine palette          |
# | 'orb'     | client/engine/ui/ callers   | liquid-filled orb w/ fresnel rim   |
MATERIAL_FRAGMENT_SHADERS = {
    "base": FS_BASE,
    "overlay": FS_OVERLAY,
    "hue": FS_HUE,
    "ramp": FS_RAMP,
    "cosine": FS_COSINE,
    "orb": FS_ORB,
}


# ======================================================================
# Material pipeline factory
# ======================================================================


def create_material_pipeline(device, format, bind_group_layout, variant_key: str):
    """Compile a material render pipeline for one fragment shader
    variant.

    Args:
        device: GPUDevice.
        format: GPUTextureFormat.
        bind_group_layout: Explicit layout (from
            ShaderCache.get_material_bind_group_layout or
            MaterialLoader.bind_group_layout).
        variant_key: One of 'base' | 'overlay' | 'hue' | 'ramp' | 'cosine'.
    """
    fs = MATERIAL_FRAGMENT_SHADERS.get(variant_key, FS_BASE)
    wgsl = MATERIAL_WGSL_COMMON + fs
    shader_module = device.create_shader_module(code=wgsl)

    pipeline_layout = device.create_pipeline_layout(bind_group_layouts=[bind_group_layout])

    return device.create_render_pipeline(
        layout=pipeline_layout,
        vertex={
            "module": shader_module,
            "entry_point": "vs_main",
            "buffers": [
                {
                    "array_stride": 16,
                    "attributes": [
                        {"shader_location": 0, "offset": 0, "format": "float32x2"},
                        {"shader_location": 1, "offset": 8, "format": "float32x2"},
                    ],
                }
            ],
        },
        fragment={
            "module": shader_module,
            "entry_point": "fs_main",
            "targets": [{"format": format, "blend": _PREMULTIPLIED_BLEND}],
        },
        primitive={"topology": "triangle-list"},
    )


# ======================================================================
# Mesh pipeline (Step 5 of 3d-coordinate-mapping.prompt.md, JS-side;
# ported here as Step 6 of wgpu-py-migration.prompt.md)
# ======================================================================


def build_mesh_wgsl_common(affine_uv: bool) -> str:
    """Build the common WGSL declarations for the 'mesh' pipeline
    family. The MatUniforms struct is the *same* 192-byte layout as
    MATERIAL_WGSL_COMMON for the first 192 bytes (byte-for-byte), so a
    mesh entity's MaterialLoader-built bind group -- the exact same kind
    a 2D sprite entity already uses -- binds to a mesh pipeline
    unchanged; Step 8 (JS-side) then appends 64 more bytes of
    stylization fields (mesh_params/fog_range/fog_color/ambient_color)
    that only this struct declares -- MATERIAL_WGSL_COMMON's copy of
    the struct is untouched, so the 2D sprite path neither reads nor
    needs to write them. Total 256 bytes, exactly MATERIAL_UNIFORM_ALIGNED
    (material_loader.py, Step 7). No waste, no buffer resize needed.

    `normal` is accepted as a vertex attribute (matching Mesh's buffer
    layout) but unused in this shader -- there is no lighting pass in
    the mesh vertex stage; it's present so the buffer layout doesn't
    need to change when one is added.

    uv_rect defaults to [0,0,1,1] (identity) for mesh draws -- a mesh's
    vertex UVs are already final texture-space coordinates, not a
    sprite atlas sub-rect, so the existing fragment shaders' remap
    (atlas_uv = uv_rect.xy + uv * (uv_rect.zw - uv_rect.xy)) degenerates
    into a no-op rather than needing mesh-specific fragment shaders.

    Args:
        affine_uv: When True, the `uv` varying is declared
            `@interpolate(linear)` -- WGSL's native non-perspective-
            correct interpolation mode, exactly the classic N64
            texture-warp artifact -- instead of the default
            `@interpolate(perspective)`. This has to be a compile-time
            choice (WGSL interpolation sampling is fixed per shader
            module, not a uniform you can branch on at runtime), which
            is why this is a function parameter baked into the
            generated source rather than a MatUniforms field like the
            other Step 8 hooks.
    """
    uv_attr = (
        "@location(0) @interpolate(linear) uv" if affine_uv else "@location(0) uv"
    )

    return f"""
struct MatUniforms {{
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
  // --- Step 8 (JS-side): mesh stylization hooks (mesh pipeline only) ---
  // mesh_params.x = vertex_color flag (>0.5 = on), .y = color_levels
  // (>0 = quantise into this many bands/channel, 0 = off). .zw = this
  // draw's camera near/far -- needed to linearize frag_pos.z (NDC depth)
  // back into a world-unit distance for the fog calculation below; not
  // itself a stylization flag, just riding along in otherwise-unused
  // padding rather than growing the buffer past the existing 256-byte
  // allocation (see MATERIAL_UNIFORM_ALIGNED, material_loader.py).
  mesh_params   : vec4<f32>,     // offset 192, 16 bytes
  // fog_range.x = fog_near, .y = fog_far (<=0 = fog fully disabled), .zw unused.
  fog_range     : vec4<f32>,     // offset 208, 16 bytes
  fog_color     : vec4<f32>,     // offset 224, 16 bytes (.a unused)
  ambient_color : vec4<f32>,     // offset 240, 16 bytes (.a unused; [1,1,1] = no-op)
}};                                // total: 256 bytes

@group(0) @binding(0) var<uniform> u           : MatUniforms;
@group(0) @binding(1) var          u_albedo    : texture_2d<f32>;
@group(0) @binding(2) var          u_param_map : texture_2d<f32>;
@group(0) @binding(3) var          u_sampler   : sampler;

struct VertexOut {{
  @builtin(position) position : vec4<f32>,
  {uv_attr}                   : vec2<f32>,
  @location(1)       color    : vec4<f32>,
}};

@vertex
fn vs_main(
  @location(0) pos    : vec3<f32>,
  @location(1) normal : vec3<f32>,
  @location(2) uv     : vec2<f32>,
  @location(3) color  : vec4<f32>,
) -> VertexOut {{
  var out : VertexOut;
  out.position = u.mvp * vec4<f32>(pos, 1.0);
  out.uv = uv;
  out.color = color;
  return out;
}}
"""


def build_mesh_style_wgsl_tail(affine_uv: bool) -> str:
    """Build the Step 8 (JS-side) stylization wrapper -- the mesh
    pipeline's actual fragment *entry point*. Calls `fs_main` (a
    strip_fragment_entry_point()-transformed copy of whichever
    MATERIAL_FRAGMENT_SHADERS variant is in play -- same combiner logic
    the 2D sprite path uses, just no longer its own entry point in this
    module) to get the base colour, then layers independently opt-in
    effects on top. Kept entirely separate from the FS_BASE/FS_RAMP/
    FS_HUE/... constants themselves -- those are never edited --
    specifically so the 2D sprite pipeline, which compiles those exact
    strings unchanged, is never at risk of reading these mesh-only
    uniform fields.

    Every branch here is a true no-op at its documented default:
      - vertex_color off (mesh_params.x <= 0.5): multiplies by vec4(1)
        -- see `select` below, not an `if`, since this one runs
        unconditionally cheaply either way and a runtime branch buys
        nothing.
      - color_levels <= 0: `if` skips quantisation entirely.
      - ambient_color [1,1,1] (the documented default/omitted value):
        multiplying by 1 is a genuine no-op; always applied
        unconditionally since, unlike fog, there's no "cost of the
        branch" to avoid -- a single vec3 multiply.
      - fog_range.y (fog_far) <= 0: `if` skips the mix() entirely, per
        the Step 8 spec's explicit requirement that disabled fog cost
        nothing, not just blend at zero strength.

    Args:
        affine_uv: Must match the value passed to
            build_mesh_wgsl_common() for the same pipeline. WGSL
            requires a vertex output and the fragment input it feeds at
            the same @location to declare the *same* @interpolate type
            -- mismatching them fails pipeline creation with "The
            interpolation type ... is different ...", producing an
            invalid GPURenderPipeline that poisons every command buffer
            it's used in (this exact bug was hit and fixed on the JS
            side during 3d-coordinate-mapping.prompt.md's Step 8 -- the
            port preserves the fix, not just the shader text).
    """
    uv_attr = (
        "@location(0) @interpolate(linear) uv" if affine_uv else "@location(0) uv"
    )

    return f"""
@fragment
fn fs_mesh_stylized(
  @builtin(position) frag_pos : vec4<f32>,
  {uv_attr}    : vec2<f32>,
  @location(1) color : vec4<f32>,
) -> @location(0) vec4<f32> {{
  var out_color = fs_main(uv);

  // Vertex-color tint (opt-in via material.vertex_color).
  let vc_tint = select(vec4<f32>(1.0, 1.0, 1.0, 1.0), color, u.mesh_params.x > 0.5);
  out_color = out_color * vc_tint;

  // Colour quantisation (opt-in via material.color_levels > 0).
  if (u.mesh_params.y > 0.0) {{
    let levels = u.mesh_params.y;
    out_color = vec4<f32>(floor(out_color.rgb * levels) / levels, out_color.a);
  }}

  // Ambient tint -- default [1,1,1] is a genuine no-op multiply.
  out_color = vec4<f32>(out_color.rgb * u.ambient_color.rgb, out_color.a);

  // Distance fog (opt-in via camera.fogFar > 0). frag_pos.z is the
  // fragment's NDC depth in [0,1] (WebGPU's documented depth range --
  // see mat4.py's perspective() header comment). Linearize it back to
  // a world-unit forward distance by inverting this project's exact
  // perspective() matrix (mat4.py): for near/far clip planes proj_near/
  // proj_far, d = (proj_near * proj_far) / (proj_far - ndc_z * (proj_far
  // - proj_near)) recovers the same linear distance used to build
  // fog_near/fog_far against. Deliberately not the cheaper
  // 1.0 / frag_pos.w trick seen in some WGSL samples -- that relies on
  // exactly what builtin(position).w means in the fragment stage,
  // which isn't worth staking correctness on when frag_pos.z's [0,1]
  // meaning is unambiguous and already documented elsewhere in this
  // project.
  if (u.fog_range.y > 0.0) {{
    let proj_near = u.mesh_params.z;
    let proj_far  = u.mesh_params.w;
    let ndc_z     = frag_pos.z;
    let view_dist = (proj_near * proj_far) / (proj_far - ndc_z * (proj_far - proj_near));
    let fog_amount = clamp(
      (view_dist - u.fog_range.x) / max(u.fog_range.y - u.fog_range.x, 0.001),
      0.0, 1.0,
    );
    out_color = vec4<f32>(mix(out_color.rgb, u.fog_color.rgb, fog_amount), out_color.a);
  }}

  return out_color;
}}
"""


def strip_fragment_entry_point(fs_source: str) -> str:
    """Turn a MATERIAL_FRAGMENT_SHADERS entry's `fs_main` into a plain
    callable helper function for use inside build_mesh_style_wgsl_tail()'s
    `fs_mesh_stylized`.

    Two WGSL rules make this necessary rather than calling `fs_main`
    as-is: (1) a function attributed `@fragment` is an entry point, and
    entry points must not be the target of a function call; (2)
    `@location(n)` attributes are only valid on entry-point IO
    (parameters/return values, or struct members used as such), not on
    an arbitrary function signature. So both attributes have to come
    off before `fs_main` can be called as a regular helper.

    This never touches the FS_BASE/FS_OVERLAY/FS_HUE/FS_RAMP/FS_COSINE
    constants themselves -- it returns a transformed *copy* of whichever
    string is passed in, used only when composing the mesh pipeline's
    WGSL source. The 2D material pipeline (create_material_pipeline)
    still concatenates the original, fully unmodified string, where
    `fs_main` genuinely is the entry point.

    Exact-string match rather than a general regex: every current
    variant declares the identical signature `fn fs_main(@location(0)
    uv : vec2<f32>) -> @location(0) vec4<f32>` (verified against the
    current FS_BASE/FS_OVERLAY/FS_HUE/FS_RAMP/FS_COSINE source), so this
    is exact and won't silently no-op if a future variant's signature
    drifts -- safer than a regex that could partially match and produce
    invalid WGSL.

    Args:
        fs_source: One of the MATERIAL_FRAGMENT_SHADERS values.
    """
    signature = "fn fs_main(@location(0) uv : vec2<f32>) -> @location(0) vec4<f32>"
    if signature not in fs_source:
        raise ValueError(
            "[shader_cache] strip_fragment_entry_point: fs_main signature "
            "did not match the expected exact text -- a "
            "MATERIAL_FRAGMENT_SHADERS variant changed without updating "
            "this helper."
        )
    return fs_source.replace("@fragment", "").replace(
        signature, "fn fs_main(uv : vec2<f32>) -> vec4<f32>"
    )


def create_mesh_pipeline(device, format, bind_group_layout, variant_key: str, affine_uv: bool = False):
    """Compile a 'mesh' render pipeline for one fragment shader variant.
    Pairs the mesh vertex stage (build_mesh_wgsl_common) with a
    strip_fragment_entry_point()-transformed copy of the relevant
    MATERIAL_FRAGMENT_SHADERS entry -- the *original* string is
    untouched and still used as-is by the 2D material pipeline. The
    transformed copy is called (as a plain helper, no longer an entry
    point) from build_mesh_style_wgsl_tail()'s `fs_mesh_stylized`, which
    is the mesh pipeline's actual fragment entry point.

    Args:
        device: GPUDevice.
        format: GPUTextureFormat.
        bind_group_layout: Explicit layout (from
            ShaderCache.get_material_bind_group_layout or
            MaterialLoader.bind_group_layout).
        variant_key: One of 'base' | 'overlay' | 'hue' | 'ramp' | 'cosine'.
        affine_uv: See build_mesh_wgsl_common's docstring. Passed to
            *both* build_mesh_wgsl_common() and
            build_mesh_style_wgsl_tail() -- they must agree, since one
            declares the vertex-output interpolation type and the other
            the fragment-input type at the same location.
    """
    fs = strip_fragment_entry_point(MATERIAL_FRAGMENT_SHADERS.get(variant_key, FS_BASE))
    wgsl = build_mesh_wgsl_common(affine_uv) + fs + build_mesh_style_wgsl_tail(affine_uv)
    shader_module = device.create_shader_module(code=wgsl)

    pipeline_layout = device.create_pipeline_layout(bind_group_layouts=[bind_group_layout])

    return device.create_render_pipeline(
        layout=pipeline_layout,
        vertex={
            "module": shader_module,
            "entry_point": "vs_main",
            "buffers": [
                {
                    # pos(12) + normal(12) + uv(8) + color(16) = 48
                    # bytes/vertex -- matches mesh.py's
                    # MESH_VERTEX_ATTRIBUTES/MESH_VERTEX_STRIDE (Step 8).
                    "array_stride": 48,
                    "attributes": [
                        {"shader_location": 0, "offset": 0, "format": "float32x3"},  # pos
                        {"shader_location": 1, "offset": 12, "format": "float32x3"},  # normal
                        {"shader_location": 2, "offset": 24, "format": "float32x2"},  # uv
                        {"shader_location": 3, "offset": 32, "format": "float32x4"},  # color
                    ],
                }
            ],
        },
        fragment={
            # Step 8 (JS-side): the pipeline's actual entry point is the
            # stylization wrapper, not the shared fs_main it calls
            # internally -- see build_mesh_style_wgsl_tail()'s docstring
            # for why this can't just be a branch inside fs_main itself.
            "module": shader_module,
            "entry_point": "fs_mesh_stylized",
            "targets": [{"format": format, "blend": _PREMULTIPLIED_BLEND}],
        },
        primitive={"topology": "triangle-list"},
        # Always depth-tested -- mesh content is inherently 3D. Unlike
        # the base 2D sprite pipeline (never depth-tested, see
        # get_sprite_pipeline), there's no "existing 2D behaviour" to
        # preserve here.
        depth_stencil={
            "format": DEPTH_FORMAT,
            "depth_write_enabled": True,
            "depth_compare": "less",
        },
    )


def create_mesh_wireframe_pipeline(device, format, bind_group_layout):
    """Compile the mesh pipeline's wireframe variant: the exact same
    vertex stage as the solid mesh pipeline (build_mesh_wgsl_common's
    vs_main -- an unmodified mvp transform, no reason to duplicate it),
    but a trivial flat-white fragment shader and `line-list` topology
    in place of the solid pipeline's textured fragment shader and
    `triangle-list`. Paired at draw time with
    Mesh.wireframe_index_buffer (see that property's docstring: WebGPU
    has no native polygon/wireframe fill mode, so an actual line-list
    over the mesh's triangle edges is the standard workaround).

    Reuses the real material bind group layout (and, at draw time, a
    part's real material bind group) purely so the same MatUniforms.mvp
    field is available at binding 0 -- the fragment shader never reads
    the albedo/param_map/sampler bindings it's paired with, no second,
    smaller bind group layout needed just for this.
    """
    wgsl = (
        build_mesh_wgsl_common(affine_uv=False)
        + """
@fragment
fn fs_wireframe() -> @location(0) vec4<f32> {
  return vec4<f32>(1.0, 1.0, 1.0, 1.0);
}
"""
    )
    shader_module = device.create_shader_module(code=wgsl)

    pipeline_layout = device.create_pipeline_layout(bind_group_layouts=[bind_group_layout])

    return device.create_render_pipeline(
        layout=pipeline_layout,
        vertex={
            "module": shader_module,
            "entry_point": "vs_main",
            "buffers": [
                {
                    "array_stride": 48,
                    "attributes": [
                        {"shader_location": 0, "offset": 0, "format": "float32x3"},  # pos
                        {"shader_location": 1, "offset": 12, "format": "float32x3"},  # normal
                        {"shader_location": 2, "offset": 24, "format": "float32x2"},  # uv
                        {"shader_location": 3, "offset": 32, "format": "float32x4"},  # color
                    ],
                }
            ],
        },
        fragment={
            "module": shader_module,
            "entry_point": "fs_wireframe",
            "targets": [{"format": format}],
        },
        primitive={"topology": "line-list"},
        depth_stencil={
            "format": DEPTH_FORMAT,
            "depth_write_enabled": True,
            "depth_compare": "less",
        },
    )
