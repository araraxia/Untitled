"""GPUSpriteSheet -- wgpu counterpart to a Canvas-2D sprite sheet.

Port of frontend/js/engine/sprites/gpuSpriteSheet.js -- Step 7 of
.github/prompts/wgpu-py-migration.prompt.md.

Deliberate adaptation, not a straight translation, and called out
explicitly per this task's "flag it instead of improvising a new
design" rule: `load()` is a plain synchronous method here, not `async`.
The JS version is async because it does `fetch()` + `createImageBitmap()`
over the network/browser cache; this client reads the same files
directly off disk (Pillow's `Image.open()`), which has no comparable
I/O-wait reason to be async, and nothing else in this port commits to
an asyncio-first design (network.py, Step 11, is expected to use
`socketio.Client()`'s synchronous API per Step 1's audit). Keeping this
synchronous matches "the same abstraction level" the JS version
actually needed, not the abstraction level `async`/`await` implies once
translated verbatim.

Bind group layout produced by create_bind_group() matches the sprite
pipeline defined in shader_cache.py (group 0):
  binding 0 -- uniform buffer  (mvp / uv_rect / tint)
  binding 1 -- texture_2d<f32> (albedo atlas)
  binding 2 -- sampler

Bind group layout produced by create_material_bind_group() matches the
material pipelines (group 0):
  binding 0 -- uniform buffer  (MatUniforms)
  binding 1 -- texture_2d<f32> (albedo atlas)
  binding 2 -- texture_2d<f32> (RGBA param map)
  binding 3 -- sampler

Correction (found while porting entity_renderer.py, Step 9, whose sprite
paths are FRONTEND_DIR-relative strings built the same way the JS
version builds them): this module originally resolved image_path/
param_map_path directly, with no FRONTEND_DIR prefix, inconsistent with
material_loader.py/mesh.py's established convention -- it only "worked"
in Step 7's own test because that test happened to pass a path that
already included a literal 'frontend/' prefix while running from the
repo root as CWD, which isn't a safe general assumption (e.g. once
client/main.py, Step 15, might run from a different working directory).
Fixed to resolve against FRONTEND_DIR like every other loader in this
port.
"""

import array
from pathlib import Path

import wgpu
from PIL import Image

# client/engine/gpu_sprite_sheet.py -> client/engine -> client -> repo
# root -> frontend. Matches material_loader.py's/mesh.py's/
# asset_loader.py's FRONTEND_DIR convention.
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


class GPUSpriteSheet:
    """
    Args:
        device: GPUDevice.
        image_path: Path to the sprite atlas image, relative to
            FRONTEND_DIR (already resolved -- asset-key resolution
            happens in asset_loader.py, Step 10, not here, mirroring
            the JS division of responsibility).
        frame_width: Width of one frame in pixels.
        frame_height: Height of one frame in pixels.
        columns: Number of columns in the atlas grid.
        rows: Number of rows in the atlas grid.
        param_map_path: Optional path to an RGBA parameter map image.
            When provided, the image is uploaded as a second GPUTexture
            available via the param_texture property.
    """

    def __init__(
        self,
        device,
        image_path: str,
        frame_width: int,
        frame_height: int,
        columns: int,
        rows: int,
        param_map_path: "str | None" = None,
    ):
        self._device = device
        self._image_path = image_path
        self._param_map_path = param_map_path
        self._frame_width = frame_width
        self._frame_height = frame_height
        self._columns = columns
        self._rows = rows

        self._texture = None
        self._albedo_view = None
        self._param_texture = None
        self._sampler = None
        self._loaded = False

    @property
    def loaded(self) -> bool:
        """True once load() has completed successfully."""
        return self._loaded

    def load(self) -> None:
        """Read the atlas image, upload it to a GPUTexture, and create
        the sampler. Must be called before get_uv_rect or
        create_bind_group.
        """
        self._texture = self._load_texture(self._image_path)
        self._albedo_view = self._texture.create_view()

        self._sampler = self._device.create_sampler(
            min_filter="linear", mag_filter="nearest"
        )

        if self._param_map_path:
            self._param_texture = self._load_texture(self._param_map_path)

        self._loaded = True

    def _load_texture(self, path: str):
        """Read an image at *path* (relative to FRONTEND_DIR) off disk
        and upload it as an rgba8unorm GPUTexture. Shared by the albedo
        atlas and the optional param map -- both need identical upload
        logic.
        """
        full_path = FRONTEND_DIR / path
        if not full_path.exists():
            raise FileNotFoundError(f"[gpu_sprite_sheet] Texture not found: {full_path}")
        image = Image.open(full_path).convert("RGBA")
        width, height = image.size
        pixels = image.tobytes()

        texture = self._device.create_texture(
            size=(width, height, 1),
            format="rgba8unorm",
            usage=(
                wgpu.TextureUsage.TEXTURE_BINDING
                | wgpu.TextureUsage.COPY_DST
                | wgpu.TextureUsage.RENDER_ATTACHMENT
            ),
        )
        self._device.queue.write_texture(
            {"texture": texture},
            pixels,
            {"bytes_per_row": width * 4, "rows_per_image": height},
            (width, height, 1),
        )
        return texture

    @property
    def albedo_texture_view(self):
        """A stable GPUTextureView of the atlas texture -- the *same*
        object every call, not recreated, so consumers that key on view
        identity (client/engine/ui/draw.py's texture-registration cache)
        don't re-register a "new" texture every frame. None until
        load() has run.
        """
        return self._albedo_view

    @property
    def param_texture(self):
        """The uploaded RGBA param map texture, or None if no
        param_map_path was provided (or load() hasn't completed).
        Pass this to create_material_bind_group as the param_texture
        argument, or use the MaterialLoader fallback texture when None.
        """
        return self._param_texture

    def get_uv_rect(self, frame_index: int) -> "array.array":
        """Compute the UV sub-rect for a given frame index.

        Uses the same column/row arithmetic as the Canvas-2D sprite
        sheet's drawFrame.

        Args:
            frame_index: 0-based, left-to-right, top-to-bottom.

        Returns:
            array.array('f', [u0, v0, u1, v1])
        """
        column = frame_index % self._columns
        row = frame_index // self._columns

        u0 = column / self._columns
        v0 = row / self._rows
        u1 = u0 + 1 / self._columns
        v1 = v0 + 1 / self._rows

        return array.array("f", [u0, v0, u1, v1])

    def create_bind_group(self, device, pipeline, uniform_buffer):
        """Create a GPUBindGroup for one draw call.

        The bind group is inexpensive to create and is intended to be
        created once per sprite sheet (reusing the same uniform_buffer
        every frame) -- call this after load(), store the result, and
        reuse it.

        Args:
            device: GPUDevice.
            pipeline: The sprite pipeline from ShaderCache.
            uniform_buffer: Pre-allocated uniform buffer (binding 0).
        """
        return device.create_bind_group(
            layout=pipeline.get_bind_group_layout(0),
            entries=[
                {"binding": 0, "resource": {"buffer": uniform_buffer}},
                {"binding": 1, "resource": self._texture.create_view()},
                {"binding": 2, "resource": self._sampler},
            ],
        )

    def destroy(self) -> None:
        """Release the GPU texture(s) held by this sprite sheet. Call
        when the sheet is no longer needed to free GPU memory.
        """
        if self._texture:
            self._texture.destroy()
            self._texture = None
            self._albedo_view = None
        if self._param_texture:
            self._param_texture.destroy()
            self._param_texture = None
        self._sampler = None
        self._loaded = False

    def create_material_bind_group(
        self, bind_group_layout, uniform_buffer, param_texture, sampler
    ):
        """Create a GPUBindGroup for the material pipeline (4-binding
        layout).

        Use this when the entity has a material JSON and you need to
        bind the albedo atlas from this sheet alongside a separate
        param map and sampler from MaterialLoader.

        Args:
            bind_group_layout: The explicit layout from
                MaterialLoader.bind_group_layout (or
                ShaderCache.get_material_bind_group_layout()).
            uniform_buffer: MatUniforms buffer.
            param_texture: RGBA param map texture (use the
                MaterialLoader fallback when no param map is defined).
            sampler: Shared sampler for both texture slots.
        """
        return self._device.create_bind_group(
            layout=bind_group_layout,
            entries=[
                {"binding": 0, "resource": {"buffer": uniform_buffer}},
                {"binding": 1, "resource": self._texture.create_view()},
                {"binding": 2, "resource": param_texture.create_view()},
                {"binding": 3, "resource": sampler},
            ],
        )
