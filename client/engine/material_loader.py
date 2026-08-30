"""MaterialLoader -- builds GPUBindGroup objects from material JSON files.

Port of frontend/js/engine/sprites/materialLoader.js -- Step 7 of
.github/prompts/wgpu-py-migration.prompt.md.

Deliberate adaptation: `load()` is synchronous, reading material JSON
and texture files directly off disk (json.load()/Pillow) instead of
`fetch()` -- same reasoning as gpu_sprite_sheet.py's docstring (no
network round-trip to be async about, and nothing else in this port
commits to an asyncio-first design). Material JSON paths use the exact
same string convention as the JS version (e.g.
'assets/data/material/material-example-lantern.json', relative to
frontend/, matching what asset_loader.py -- Step 10 -- will also use)
so the two clients' asset references stay interchangeable; they're
resolved to real files by joining with FRONTEND_DIR below.

Bind group layout (slots 0-3, shared structurally with material
pipelines compiled by shader_cache.py):
  binding 0 -- GPUBuffer (uniform)       per-draw uniforms
  binding 1 -- texture_2d<f32>           albedo sprite atlas
  binding 2 -- texture_2d<f32>           param map OR 256x1 color ramp
                                         (fallback: 1x1 black)
                                         slot is mutually exclusive:
                                           overlay/base -> param map
                                           ramp variant -> color ramp LUT
  binding 3 -- GPUSampler                shared sampler

Uniform buffer layout (MATERIAL_UNIFORM_BYTES = 192):
  mvp(64) + uv_rect(16) + uv_overlay(16) + tint(16)
  + intensity(4) + time(4) + ramp_steps(4) + _pad(4)
  + pal_a(16) + pal_b(16) + pal_c(16) + pal_d(16)
"""

import json
from pathlib import Path
from typing import Any, Optional

import wgpu
from PIL import Image

# Logical size of the material uniform struct, in bytes.
MATERIAL_UNIFORM_BYTES = 192

# Aligned to WebGPU minUniformBufferOffsetAlignment (256 bytes).
MATERIAL_UNIFORM_ALIGNED = -(-MATERIAL_UNIFORM_BYTES // 256) * 256

# client/engine/material_loader.py -> client/engine -> client -> repo
# root -> frontend. Material JSON paths are relative to this directory,
# matching the string convention the JS client's fetch() calls use.
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


class MaterialLoader:
    """
    Args:
        device: GPUDevice.
        loader: Optional asset registry (an object with `.has(key)`/
            `.resolve(key)` methods, matching asset_loader.py's
            AssetLoader -- Step 10) for key-based path resolution. When
            provided, material JSON fields that look like asset keys (no
            '/' in the value) are resolved through it. Falls back to
            prepending 'assets/' when a key can't be resolved. May be
            None (e.g. before Step 10 lands, or in a standalone test) --
            matching the JS version's "global instance, or none" fallback,
            adapted to explicit injection since Python has no equivalent
            of a module-scope browser global.
    """

    def __init__(self, device, loader: Optional[Any] = None):
        self._device = device
        self._asset_loader = loader

        self._handles: dict[str, dict] = {}

        self._bind_group_layout = self._create_bind_group_layout()
        self._sampler = self._create_sampler()
        self._fallback_param_texture = self._create_1x1_black_texture()
        self._fallback_material_handle: "dict | None" = None

    @property
    def bind_group_layout(self):
        """Explicit GPUBindGroupLayout used for all material bind groups.
        Pass to ShaderCache when creating material pipelines to
        guarantee object-level layout compatibility.
        """
        return self._bind_group_layout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, material_json_path: str) -> dict:
        """Read and parse a material JSON file, upload textures, and
        build a GPUBindGroup. Returns the cached handle on subsequent
        calls for the same material id.

        Args:
            material_json_path: Path relative to FRONTEND_DIR, e.g.
                'assets/data/material/material-example-lantern.json'.

        Returns:
            A MaterialHandle dict: id, bind_group, uniform_buffer,
            flags ({has_param_map, has_overlay, has_color_ramp}),
            overlays, color_ramp_type, cosine_params, vertex_color,
            affine_uv, color_levels.
        """
        full_path = FRONTEND_DIR / material_json_path
        if not full_path.exists():
            raise FileNotFoundError(
                f"[material_loader] Material JSON not found: {full_path}"
            )
        data = json.loads(full_path.read_text(encoding="utf-8"))

        if data["id"] in self._handles:
            return self._handles[data["id"]]

        # Resolve atlas path -- material JSON may use 'atlas' or 'base_atlas'.
        atlas_path = self._resolve_path(data.get("atlas") or data.get("base_atlas"))
        albedo_tex = self._load_texture(atlas_path)

        has_param_map = bool(data.get("param_map"))
        param_tex = (
            self._load_texture(self._resolve_path(data["param_map"]))
            if has_param_map
            else self._fallback_param_texture
        )

        # --- color_ramp ---
        # Binding 2 is dual-purpose: param map for overlay/base variants,
        # or 256x1 colour ramp LUT for the ramp variant. They are
        # mutually exclusive per material.
        color_ramp = data.get("color_ramp")
        has_color_ramp = bool(color_ramp)
        color_ramp_type = None
        cosine_params = None
        ramp_tex = None

        if color_ramp:
            color_ramp_type = color_ramp.get("type", "texture")
            if color_ramp_type == "cosine":
                cosine_params = {
                    "a": color_ramp.get("a", [0.5, 0.5, 0.5]),
                    "b": color_ramp.get("b", [0.5, 0.5, 0.5]),
                    "c": color_ramp.get("c", [1.0, 1.0, 1.0]),
                    "d": color_ramp.get("d", [0.0, 0.33, 0.67]),
                }
            elif color_ramp_type == "texture" and color_ramp.get("texture"):
                ramp_tex = self._load_texture(self._resolve_path(color_ramp["texture"]))

        # Slot 2: colour ramp LUT when loaded, otherwise the param map
        # (or 1x1 black fallback when neither is present).
        binding2_tex = ramp_tex or param_tex

        uniform_buffer = self._device.create_buffer(
            size=MATERIAL_UNIFORM_ALIGNED,
            usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
        )

        bind_group = self._device.create_bind_group(
            layout=self._bind_group_layout,
            entries=[
                {"binding": 0, "resource": {"buffer": uniform_buffer}},
                {"binding": 1, "resource": albedo_tex.create_view()},
                {"binding": 2, "resource": binding2_tex.create_view()},
                {"binding": 3, "resource": self._sampler},
            ],
        )

        overlays_data = data.get("overlays") or []
        has_overlay = len(overlays_data) > 0
        overlays = [
            {
                "type": o.get("type", "animation"),
                "atlas": o.get("atlas"),
                "animation_id": o.get("animation_id") or o.get("animation_clip"),
                "blend_mode": o.get("blend_mode", "additive"),
                "intensity": o["intensity"] if isinstance(o.get("intensity"), (int, float)) else 1.0,
            }
            for o in overlays_data
        ]

        # Step 8 (JS-side) mesh stylization hooks -- material-level,
        # opt-in, each independently defaulting to a no-op. Parsed here
        # regardless of whether this material is ever used by a mesh
        # entity; 2D sprite draws simply never read these handle fields.
        vertex_color = data.get("vertex_color") is True
        affine_uv = data.get("affine_uv") is True
        color_levels = data["color_levels"] if isinstance(data.get("color_levels"), (int, float)) else 0

        handle = {
            "id": data["id"],
            "bind_group": bind_group,
            "uniform_buffer": uniform_buffer,
            "flags": {
                "has_param_map": has_param_map,
                "has_overlay": has_overlay,
                "has_color_ramp": has_color_ramp,
            },
            "overlays": overlays,
            "color_ramp_type": color_ramp_type,
            "cosine_params": cosine_params,
            "vertex_color": vertex_color,
            "affine_uv": affine_uv,
            "color_levels": color_levels,
        }

        self._handles[data["id"]] = handle
        return handle

    def get(self, material_id: str) -> "dict | None":
        """Return a previously loaded handle by material id, or None."""
        return self._handles.get(material_id)

    def get_fallback_handle(self) -> dict:
        """Shared placeholder material -- a solid magenta albedo, the
        conventional "missing texture" signal games use -- for a mesh
        part with no `material_id` at all, or one whose material file
        failed to load.

        Real bug this fixes: `entity_renderer.py`'s `_draw_mesh_part`
        used to skip the draw call entirely whenever no material
        handle was available, so any part with an unassigned
        `material_id` (every part `entity_builder.py`'s "+ Add Part"/
        "Scaffold Parts from Sockets" create, which never set one)
        rendered as nothing -- no error, no placeholder, just an empty
        viewport, indistinguishable from "the mesh itself failed to
        load." Built once, lazily, and reused for every part that
        needs it -- cheap, since it's a single 1x1 texture + one bind
        group shared across the whole session.
        """
        if self._fallback_material_handle is not None:
            return self._fallback_material_handle

        magenta_tex = self._create_1x1_texture((255, 0, 255, 255))
        uniform_buffer = self._device.create_buffer(
            size=MATERIAL_UNIFORM_ALIGNED,
            usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
        )
        bind_group = self._device.create_bind_group(
            layout=self._bind_group_layout,
            entries=[
                {"binding": 0, "resource": {"buffer": uniform_buffer}},
                {"binding": 1, "resource": magenta_tex.create_view()},
                {"binding": 2, "resource": self._fallback_param_texture.create_view()},
                {"binding": 3, "resource": self._sampler},
            ],
        )
        self._fallback_material_handle = {
            "id": "__fallback_missing_material__",
            "bind_group": bind_group,
            "uniform_buffer": uniform_buffer,
            "flags": {"has_param_map": False, "has_overlay": False, "has_color_ramp": False},
            "overlays": [],
            "color_ramp_type": None,
            "cosine_params": None,
            "vertex_color": False,
            "affine_uv": False,
            "color_levels": 0,
        }
        return self._fallback_material_handle

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _create_bind_group_layout(self):
        """Create the explicit bind group layout for all material shaders."""
        return self._device.create_bind_group_layout(
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

    def _create_sampler(self):
        """Shared sampler used across all material bind groups.

        `address_mode_u`/`address_mode_v` explicitly set to `"repeat"`
        -- wgpu's own default is `"clamp-to-edge"` (confirmed via
        `inspect.signature(wgpu.GPUDevice.create_sampler)`), which
        would smear the edge pixel outward instead of tiling for any
        UV authored outside `[0,1]` (e.g. a large terrain chunk's
        repeating ground texture). Safe for every material authored so
        far: repeat and clamp-to-edge are identical for any UV that
        never leaves `[0,1]`, which is everything existing so far --
        this only changes behavior for the first mesh that actually
        uses tiled UVs.
        """
        return self._device.create_sampler(
            address_mode_u="repeat",
            address_mode_v="repeat",
            min_filter="linear",
            mag_filter="nearest",
        )

    def _create_1x1_texture(self, color: "tuple[int, int, int, int]"):
        """1x1 opaque RGBA texture of *color* -- shared by the missing-
        param-map fallback (black) and the missing-material fallback
        (magenta, see get_fallback_handle()).
        """
        tex = self._device.create_texture(
            size=(1, 1, 1),
            format="rgba8unorm",
            usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST,
        )
        self._device.queue.write_texture(
            {"texture": tex},
            bytes(color),
            {"bytes_per_row": 4},
            (1, 1, 1),
        )
        return tex

    def _create_1x1_black_texture(self):
        """1x1 opaque black RGBA texture -- placeholder when no param
        map is defined, ensuring the bind group slot is always
        populated.
        """
        return self._create_1x1_texture((0, 0, 0, 255))

    def _load_texture(self, path: str):
        """Read an image at *path* (relative to FRONTEND_DIR) and
        upload it as a GPUTexture.
        """
        full_path = FRONTEND_DIR / path
        if not full_path.exists():
            raise FileNotFoundError(f"[material_loader] Texture not found: {full_path}")

        image = Image.open(full_path).convert("RGBA")
        width, height = image.size
        pixels = image.tobytes()

        tex = self._device.create_texture(
            size=(width, height, 1),
            format="rgba8unorm",
            usage=(
                wgpu.TextureUsage.TEXTURE_BINDING
                | wgpu.TextureUsage.COPY_DST
                | wgpu.TextureUsage.RENDER_ATTACHMENT
            ),
        )
        self._device.queue.write_texture(
            {"texture": tex},
            pixels,
            {"bytes_per_row": width * 4, "rows_per_image": height},
            (width, height, 1),
        )
        return tex

    def _resolve_path(self, value: "str | None") -> str:
        """Resolve a material-JSON field value to a FRONTEND_DIR-relative
        path.

        Resolution order:
            1. Already a path/URL (contains '/') -- returned unchanged.
            2. Looks like an asset key (no '/') and an asset loader is
               available -> resolved via loader.resolve().
            3. Fallback -- prepend 'assets/'.
        """
        if not value:
            return ""

        if "/" in value or value.startswith("http"):
            return value

        if self._asset_loader:
            if self._asset_loader.has(value):
                return self._asset_loader.resolve(value)

        return "assets/" + value
