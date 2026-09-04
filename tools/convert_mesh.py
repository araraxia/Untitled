"""Convert a glTF 2.0 export into this project's mesh JSON format.

Build-time-only authoring bridge (Step 6 of
.github/prompts/3d-coordinate-mapping.prompt.md): takes a single-mesh,
single-primitive glTF export from Blender (or any glTF-exporting tool)
and emits the small project-specific mesh JSON format consumed by
``client/engine/mesh.py``. This is deliberately narrow — geometry
attributes only, one mesh, one primitive — not a general-purpose glTF
importer. It refuses (raises, never silently drops data) anything outside
that scope: multiple meshes/primitives, non-triangle topology, skins,
morph targets, and sparse accessors.

Step 9 of the same prompt file extends this converter with **socket**
extraction: glTF ``nodes`` that have a ``name`` but no ``mesh`` reference
(a Blender "Empty" placed at an attachment point) become named local-space
anchor points in the output JSON's ``sockets`` array. This is metadata
(a name + a transform) read straight off the node, not geometry/material/
skin data, so it doesn't broaden the converter's scope — skins/morph
targets/extra primitives are still refused exactly as before.

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
import math
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


def quaternion_to_euler_xyz(x: float, y: float, z: float, w: float) -> list[float]:
    """Convert a glTF node's rotation quaternion to Euler radians matching
    ``client/engine/mat4.py``'s ``rotation_xyz`` convention exactly
    (composition order Rx * Ry * Rz applied to a column vector) — every
    consumer of a mesh's ``sockets`` rotation (Step 9's attachment-chain
    composition) assumes that same convention, so a mismatch here would
    silently misalign every socket.

    Standard quaternion -> rotation-matrix -> XYZ-Euler extraction; the
    matrix element names below (m00..m22) match ``rotation_xyz``'s own
    internal derivation for direct comparison.
    """
    m00 = 1 - 2 * (y * y + z * z)
    m01 = 2 * (x * y - w * z)
    m02 = 2 * (x * z + w * y)
    m11 = 1 - 2 * (x * x + z * z)
    m12 = 2 * (y * z - w * x)
    m21 = 2 * (y * z + w * x)
    m22 = 1 - 2 * (x * x + y * y)

    ry = math.asin(max(-1.0, min(1.0, -m02)))
    if abs(math.cos(ry)) > 1e-6:
        rx = math.atan2(m12, m22)
        rz = math.atan2(m01, m00)
    else:
        # Gimbal lock (ry at +/-90deg) -- rx/rz aren't independently
        # recoverable; fold everything into rx, matching the standard
        # convention for this degenerate case.
        rx = math.atan2(-m21, m11)
        rz = 0.0

    return [rx, ry, rz]


def extract_sockets(gltf: dict[str, Any]) -> list[dict[str, Any]]:
    """Scan glTF ``nodes`` for named, mesh-less nodes (Blender "Empty"
    objects placed at attachment points) and emit each as a socket.

    Returns an empty list if there are no such nodes -- callers omit
    the ``sockets`` key entirely in that case (see convert()), matching
    Step 9's "omit entirely for meshes with no attachment points, no
    change to existing behaviour" rule.
    """
    sockets = []
    for node in gltf.get("nodes", []):
        name = node.get("name")
        if not name or "mesh" in node:
            continue
        position = list(node.get("translation", [0.0, 0.0, 0.0]))
        qx, qy, qz, qw = node.get("rotation", [0.0, 0.0, 0.0, 1.0])
        rotation = quaternion_to_euler_xyz(qx, qy, qz, qw)
        sockets.append({"name": name, "position": position, "rotation": rotation})
    return sockets


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

    # Real bug fixed here: id/name used to derive from in_path (the
    # *source* .glb's filename) instead of output_path (what the
    # caller actually asked this mesh to be named) -- entity_builder
    # .py's "Convert Mesh" button lets the user type an independent
    # output id, but that choice was silently ignored for the JSON's
    # own id/name fields, which were stamped from whatever the source
    # file happened to be called. Confirmed as the exact cause of a
    # real, live duplicate-id collision already in the asset tree
    # (mesh-bird.json and mesh-body.json both converted from a source
    # file literally named body.glb, at different times, into two
    # different output filenames, but both stamped "id": "mesh-body").
    out_path = Path(output_path)
    out_stem = out_path.stem
    name = out_stem[len("mesh-") :] if out_stem.startswith("mesh-") else out_stem
    mesh_json = {
        "id": out_stem,
        "name": name,
        "vertices": vertices,
        "indices": indices,
    }

    sockets = extract_sockets(gltf)
    if sockets:
        mesh_json["sockets"] = sockets

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(mesh_json, indent=2) + "\n", encoding="utf-8"
    )
    socket_note = f", {len(sockets)} sockets" if sockets else ""
    print(
        f"[convert_mesh] Wrote {out_path} "
        f"({vertex_count} vertices, {len(indices)} indices{socket_note})"
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
