"""Convert a glTF 2.0 export into this project's mesh JSON format.

Build-time-only authoring bridge (Step 6 of
.github/prompts/3d-coordinate-mapping.prompt.md): takes a single-mesh,
single-primitive glTF export from Blender (or any glTF-exporting tool)
and emits the small project-specific mesh JSON format consumed by
``frontend/js/engine/mesh.js``. This is deliberately narrow — geometry
attributes only, one mesh, one primitive — not a general-purpose glTF
importer. It refuses (raises, never silently drops data) anything outside
that scope: multiple meshes/primitives, non-triangle topology, skins,
morph targets, and sparse accessors.

Uses only the Python standard library (``json``, ``struct``) — no new
``pip`` dependency, matching ``tools/pack_param_map.py`` and
``tools/build_manifest.py``.

Usage:
    python tools/convert_mesh.py <input.gltf|input.glb> \\
        -o frontend/assets/data/mesh/mesh-<name>.json

Authoring workflow:
    1. Model in Blender, low-poly.
    2. Optionally paint vertex colours (Vertex Paint mode) to use the
       ``vertex_color`` stylization hook.
    3. Export glTF 2.0 (.gltf+.bin or .glb), with skinning/armatures/
       shape keys/animations disabled in the export options.
    4. Run this script.
"""

import argparse
import base64
import json
import struct
import sys
from pathlib import Path
from typing import Any, Optional, Union

# componentType -> (struct format char, byte size)
COMPONENT_TYPE_FORMATS: dict[int, tuple[str, int]] = {
    5120: ("b", 1),  # BYTE
    5121: ("B", 1),  # UNSIGNED_BYTE
    5122: ("h", 2),  # SHORT
    5123: ("H", 2),  # UNSIGNED_SHORT
    5125: ("I", 4),  # UNSIGNED_INT
    5126: ("f", 4),  # FLOAT
}

# accessor "type" -> component count
TYPE_COMPONENT_COUNTS: dict[str, int] = {
    "SCALAR": 1,
    "VEC2": 2,
    "VEC3": 3,
    "VEC4": 4,
}


class ConvertError(Exception):
    """Raised for anything outside this converter's narrow scope."""


def load_glb(path: Path) -> tuple[dict[str, Any], dict[int, bytes]]:
    """Parse a .glb file's 12-byte header and JSON/BIN chunks.

    Returns the parsed glTF JSON dict and a ``{buffer_index: bytes}`` map
    — glb always uses buffer index 0 for its embedded BIN chunk.
    """
    data = path.read_bytes()
    if len(data) < 12:
        raise ConvertError(f"'{path}' is too small to be a valid .glb file")

    magic, _version, total_length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF":
        raise ConvertError(f"'{path}' is not a valid .glb file (bad magic)")

    offset = 12
    json_chunk: Optional[bytes] = None
    bin_chunk: Optional[bytes] = None
    while offset < total_length:
        chunk_length, chunk_type = struct.unpack_from("<I4s", data, offset)
        offset += 8
        chunk_data = data[offset : offset + chunk_length]
        offset += chunk_length
        if chunk_type == b"JSON":
            json_chunk = chunk_data
        elif chunk_type == b"BIN\x00":
            bin_chunk = chunk_data

    if json_chunk is None:
        raise ConvertError(f"'{path}' has no JSON chunk")

    gltf = json.loads(json_chunk)
    buffers = {0: bin_chunk} if bin_chunk is not None else {}
    return gltf, buffers


def load_gltf(path: Path) -> tuple[dict[str, Any], dict[int, bytes]]:
    """Parse a .gltf file and load its referenced/embedded buffers."""
    gltf = json.loads(path.read_text(encoding="utf-8"))

    buffers: dict[int, bytes] = {}
    for i, buf in enumerate(gltf.get("buffers", [])):
        uri = buf.get("uri")
        if uri is None:
            raise ConvertError(
                f"buffers[{i}] has no 'uri' — bufferless buffers are only "
                "valid in .glb (embedded BIN chunk)"
            )
        if uri.startswith("data:"):
            _header, _, b64data = uri.partition(",")
            buffers[i] = base64.b64decode(b64data)
        else:
            bin_path = path.parent / uri
            if not bin_path.exists():
                raise ConvertError(
                    f"buffers[{i}] references missing file: {bin_path}"
                )
            buffers[i] = bin_path.read_bytes()
    return gltf, buffers


def normalize_component(value: Union[int, float], fmt_char: str) -> float:
    """Normalize an integer component to [0, 1] (or [-1, 1] if signed)."""
    if fmt_char == "B":
        return value / 255.0
    if fmt_char == "b":
        return max(value / 127.0, -1.0)
    if fmt_char == "H":
        return value / 65535.0
    if fmt_char == "h":
        return max(value / 32767.0, -1.0)
    return float(value)


def read_accessor(
    gltf: dict[str, Any],
    buffers: dict[int, bytes],
    accessor_index: int,
) -> list[tuple[float, ...]]:
    """Resolve accessor -> bufferView -> buffer and unpack every element.

    Returns one tuple per element (length = the accessor's component
    count, e.g. 3-tuples for VEC3). Refuses sparse accessors outright.
    """
    accessor = gltf["accessors"][accessor_index]
    if "sparse" in accessor:
        raise ConvertError(
            f"accessors[{accessor_index}] uses sparse storage — not "
            "supported by this converter"
        )

    component_type = accessor["componentType"]
    accessor_type = accessor["type"]
    count = accessor["count"]
    normalized = accessor.get("normalized", False)

    if component_type not in COMPONENT_TYPE_FORMATS:
        raise ConvertError(
            f"accessors[{accessor_index}]: unsupported componentType "
            f"{component_type}"
        )
    if accessor_type not in TYPE_COMPONENT_COUNTS:
        raise ConvertError(
            f"accessors[{accessor_index}]: unsupported type "
            f"'{accessor_type}'"
        )

    fmt_char, comp_size = COMPONENT_TYPE_FORMATS[component_type]
    num_components = TYPE_COMPONENT_COUNTS[accessor_type]

    buffer_view_index = accessor.get("bufferView")
    if buffer_view_index is None:
        # No bufferView = accessor defined as all-zero. Not needed by any
        # attribute this converter reads, but valid per the glTF spec.
        return [tuple(0.0 for _ in range(num_components))] * count

    buffer_view = gltf["bufferViews"][buffer_view_index]
    buffer_data = buffers.get(buffer_view["buffer"])
    if buffer_data is None:
        raise ConvertError(
            f"bufferViews[{buffer_view_index}] references buffer "
            f"{buffer_view['buffer']}, which has no data loaded"
        )

    base_offset = buffer_view.get("byteOffset", 0) + accessor.get(
        "byteOffset", 0
    )
    element_size = comp_size * num_components
    stride = buffer_view.get("byteStride", element_size)

    fmt = "<" + fmt_char * num_components
    values: list[tuple[float, ...]] = []
    for i in range(count):
        elem_offset = base_offset + i * stride
        raw = struct.unpack_from(fmt, buffer_data, elem_offset)
        if normalized:
            raw = tuple(normalize_component(v, fmt_char) for v in raw)
        values.append(raw)
    return values


def convert(input_path: str, output_path: str) -> None:
    """Convert one glTF/GLB file to the project's mesh JSON format."""
    in_path = Path(input_path)
    suffix = in_path.suffix.lower()
    if suffix == ".glb":
        gltf, buffers = load_glb(in_path)
    elif suffix == ".gltf":
        gltf, buffers = load_gltf(in_path)
    else:
        raise ConvertError(
            f"Unsupported extension '{suffix}' — expected .gltf or .glb"
        )

    meshes = gltf.get("meshes", [])
    if len(meshes) == 0:
        raise ConvertError("glTF file has no meshes")
    if len(meshes) > 1:
        raise ConvertError(
            f"glTF file has {len(meshes)} meshes — this converter only "
            "supports a single mesh (meshes[0])"
        )
    mesh = meshes[0]

    primitives = mesh.get("primitives", [])
    if len(primitives) == 0:
        raise ConvertError("meshes[0] has no primitives")
    if len(primitives) > 1:
        raise ConvertError(
            f"meshes[0] has {len(primitives)} primitives — this "
            "converter only supports a single primitive (primitives[0])"
        )
    primitive = primitives[0]

    mode = primitive.get("mode", 4)
    if mode != 4:
        raise ConvertError(
            f"primitives[0].mode = {mode} — only TRIANGLES (mode 4) is "
            "supported"
        )

    if "targets" in primitive:
        raise ConvertError("morph targets are not supported")

    attributes = primitive.get("attributes", {})
    for required in ("POSITION", "NORMAL", "TEXCOORD_0"):
        if required not in attributes:
            raise ConvertError(f"primitives[0] has no {required} attribute")
    if "JOINTS_0" in attributes or "WEIGHTS_0" in attributes:
        raise ConvertError(
            "skinned meshes (JOINTS_0/WEIGHTS_0 attributes) are not "
            "supported"
        )

    positions = read_accessor(gltf, buffers, attributes["POSITION"])
    normals = read_accessor(gltf, buffers, attributes["NORMAL"])
    uvs = read_accessor(gltf, buffers, attributes["TEXCOORD_0"])

    colors: Optional[list[tuple[float, ...]]] = None
    if "COLOR_0" in attributes:
        colors = read_accessor(gltf, buffers, attributes["COLOR_0"])

    vertex_count = len(positions)
    if len(normals) != vertex_count or len(uvs) != vertex_count:
        raise ConvertError(
            "POSITION/NORMAL/TEXCOORD_0 accessor counts do not match"
        )
    if colors is not None and len(colors) != vertex_count:
        raise ConvertError("COLOR_0 accessor count does not match POSITION")

    vertices = []
    for i in range(vertex_count):
        vertex: dict[str, Any] = {
            "pos": list(positions[i]),
            "normal": list(normals[i]),
            "uv": list(uvs[i]),
        }
        if colors is not None:
            color = list(colors[i])
            if len(color) == 3:
                color = color + [1.0]
            vertex["color"] = color
        vertices.append(vertex)

    if "indices" not in primitive:
        raise ConvertError(
            "primitives[0] has no 'indices' — non-indexed primitives are "
            "not supported"
        )
    index_tuples = read_accessor(gltf, buffers, primitive["indices"])
    indices = [int(v[0]) for v in index_tuples]

    name = in_path.stem
    mesh_json = {
        "id": f"mesh-{name}",
        "name": name,
        "vertices": vertices,
        "indices": indices,
    }

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(mesh_json, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"[convert_mesh] Wrote {out_path} "
        f"({vertex_count} vertices, {len(indices)} indices)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a single-mesh, single-primitive glTF 2.0 export "
            "into this project's mesh JSON format."
        )
    )
    parser.add_argument("input", help="Path to a .gltf or .glb file")
    parser.add_argument(
        "-o", "--output", required=True, help="Output mesh JSON path"
    )
    args = parser.parse_args()

    try:
        convert(args.input, args.output)
    except ConvertError as err:
        print(f"[convert_mesh] Error: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
