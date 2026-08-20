"""Mesh -- a static (non-animated) textured 3D mesh: an interleaved
vertex buffer (pos.xyz, normal.xyz, uv.xy, color.rgba = 12 floats/vertex)
plus an index buffer, loaded from this project's own JSON format (not a
glTF subset -- see tools/convert_mesh.py for the Blender authoring
pipeline, and docs/graphics/DATA_STRUCTURES.md for the schema).

Port of frontend/js/engine/mesh.js -- Step 8 of
.github/prompts/wgpu-py-migration.prompt.md. Reuses the existing
material combiner fragment shaders (shader_cache.py's 'mesh' pipeline
variant) -- this class only owns the GPU vertex/index buffers, nothing
shader- or material-specific.

Deliberate adaptation: `load()` is synchronous (reads JSON off disk),
same reasoning as gpu_sprite_sheet.py/material_loader.py in Step 7.
Mesh JSON paths use the same FRONTEND_DIR-relative convention as
material_loader.py.
"""

import array
import json
from pathlib import Path

import wgpu

# Floats per vertex: pos(3) + normal(3) + uv(2) + color(4).
MESH_FLOATS_PER_VERTEX = 12

# Bytes per vertex (12 floats x 4 bytes).
MESH_VERTEX_STRIDE = MESH_FLOATS_PER_VERTEX * 4

# Vertex buffer attribute layout for the 'mesh' pipeline variant
# (ShaderCache.get_mesh_pipeline). Exported so shader_cache.py doesn't
# need to hand-duplicate these offsets.
MESH_VERTEX_ATTRIBUTES = [
    {"shader_location": 0, "offset": 0, "format": "float32x3"},  # pos
    {"shader_location": 1, "offset": 12, "format": "float32x3"},  # normal
    {"shader_location": 2, "offset": 24, "format": "float32x2"},  # uv
    {"shader_location": 3, "offset": 32, "format": "float32x4"},  # color
]

# client/engine/mesh.py -> client/engine -> client -> repo root -> frontend.
# Mesh JSON paths are relative to this directory, matching
# material_loader.py's FRONTEND_DIR convention.
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


class Mesh:
    """
    Args:
        device: GPUDevice.
    """

    def __init__(self, device):
        self._device = device
        self._vertex_buffer = None
        self._index_buffer = None
        self._index_format = "uint16"
        self._vertex_count = 0
        self._index_count = 0
        # name -> {"position": [x,y,z], "rotation": [x,y,z]} (radians,
        # rotation_xyz convention). Step 9 of 3d-coordinate-mapping
        # .prompt.md -- named local-space attachment points, empty dict
        # for meshes with no `sockets` key (the common case).
        self._sockets: dict = {}

    @property
    def vertex_count(self) -> int:
        return self._vertex_count

    @property
    def index_count(self) -> int:
        return self._index_count

    @property
    def index_format(self) -> str:
        """'uint16' or 'uint32', matching index_buffer's contents."""
        return self._index_format

    @property
    def vertex_buffer(self):
        return self._vertex_buffer

    @property
    def index_buffer(self):
        return self._index_buffer

    def get_socket(self, name: str) -> "dict | None":
        """Return the named socket's {"position", "rotation"} dict, or
        None if this mesh has no socket by that name (or no sockets at
        all). Used by entity_renderer.py's attachment-chain composition
        (Step 9)."""
        return self._sockets.get(name)

    def load(self, mesh_json_path: str) -> None:
        """Read the mesh JSON, pack vertices into an interleaved
        array.array('f', ...), and upload both vertex and index buffers
        to the GPU. Must be called before drawing.

        Args:
            mesh_json_path: Path relative to FRONTEND_DIR, e.g.
                'assets/data/mesh/mesh-example-crate.json'.
        """
        full_path = FRONTEND_DIR / mesh_json_path
        if not full_path.exists():
            raise FileNotFoundError(f"[mesh] Mesh JSON not found: {full_path}")
        data = json.loads(full_path.read_text(encoding="utf-8"))

        self._sockets = {
            s["name"]: {
                "position": s.get("position", [0.0, 0.0, 0.0]),
                "rotation": s.get("rotation", [0.0, 0.0, 0.0]),
            }
            for s in data.get("sockets", [])
        }

        vertices = data.get("vertices", [])
        self._vertex_count = len(vertices)

        vertex_data = array.array("f", [0.0] * (self._vertex_count * MESH_FLOATS_PER_VERTEX))
        for i, v in enumerate(vertices):
            base = i * MESH_FLOATS_PER_VERTEX
            pos = v.get("pos", [0, 0, 0])
            normal = v.get("normal", [0, 1, 0])
            uv = v.get("uv", [0, 0])
            # Missing color defaults to [1,1,1,1] (a no-op multiply) --
            # the field is purely opt-in per DATA_STRUCTURES.md, not
            # required.
            color = v.get("color", [1, 1, 1, 1])

            vertex_data[base + 0] = pos[0]
            vertex_data[base + 1] = pos[1]
            vertex_data[base + 2] = pos[2]
            vertex_data[base + 3] = normal[0]
            vertex_data[base + 4] = normal[1]
            vertex_data[base + 5] = normal[2]
            vertex_data[base + 6] = uv[0]
            vertex_data[base + 7] = uv[1]
            vertex_data[base + 8] = color[0]
            vertex_data[base + 9] = color[1]
            vertex_data[base + 10] = color[2]
            vertex_data[base + 11] = color[3]

        self._vertex_buffer = self._device.create_buffer(
            size=vertex_data.itemsize * len(vertex_data),
            usage=wgpu.BufferUsage.VERTEX | wgpu.BufferUsage.COPY_DST,
            mapped_at_creation=True,
        )
        self._vertex_buffer.write_mapped(vertex_data)
        self._vertex_buffer.unmap()

        indices = data.get("indices", [])
        self._index_count = len(indices)

        # Uint16 covers up to 65535 distinct vertex indices -- plenty
        # for the low-poly assets this task targets; fall back to
        # Uint32 otherwise.
        use_u16 = self._vertex_count <= 65535
        self._index_format = "uint16" if use_u16 else "uint32"
        typecode = "H" if use_u16 else "I"

        # array module typecode sizes are only *guaranteed minimums* by
        # the language spec, even though 'H'/'I' are 2/4 bytes on every
        # platform this project targets in practice -- assert rather
        # than silently upload a wrong-width index buffer if that ever
        # stops being true.
        expected_size = 2 if use_u16 else 4
        actual_size = array.array(typecode).itemsize
        if actual_size != expected_size:
            raise RuntimeError(
                f"[mesh] Platform's array.array('{typecode}') is "
                f"{actual_size} bytes, expected {expected_size} -- "
                "cannot safely build a GPU index buffer this way on "
                "this platform."
            )

        index_array = array.array(typecode, indices)
        # GPUBuffer sizes must be a multiple of 4 bytes. Uint32 index
        # arrays are always aligned; a Uint16 array with an odd index
        # count needs one extra (unused) padding index to reach a
        # 4-byte-aligned byte length.
        if use_u16 and (index_array.itemsize * len(index_array)) % 4 != 0:
            index_array = array.array(typecode, list(index_array) + [0])

        self._index_buffer = self._device.create_buffer(
            size=index_array.itemsize * len(index_array),
            usage=wgpu.BufferUsage.INDEX | wgpu.BufferUsage.COPY_DST,
            mapped_at_creation=True,
        )
        self._index_buffer.write_mapped(index_array)
        self._index_buffer.unmap()

    def destroy(self) -> None:
        """Release the GPU buffers held by this mesh. Call when no
        longer needed.
        """
        if self._vertex_buffer:
            self._vertex_buffer.destroy()
            self._vertex_buffer = None
        if self._index_buffer:
            self._index_buffer.destroy()
            self._index_buffer = None
        self._vertex_count = 0
        self._index_count = 0
        self._sockets = {}
