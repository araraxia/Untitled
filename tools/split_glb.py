"""Split a multi-mesh glTF 2.0 export into one single-mesh .glb per part.

Companion pre-processing step for ``tools/convert_mesh.py``, which
refuses (by design) any glTF file containing more than one mesh — see
that module's own docstring. Rather than loosening that refusal, this
script walks the source file's node graph and, for every mesh-bearing
node, emits its own minimal, self-contained ``.glb``: just that mesh's
geometry accessors (re-packed into a fresh binary buffer) plus any
empty (mesh-less) descendant nodes — socket markers parented directly
under that mesh in Blender, per
``docs/graphics/3D_ASSET_AUTHORING.md`` §1 — so each output file is
exactly the shape ``convert_mesh.py`` already expects. A node that is
itself mesh-bearing is never swept into a sibling part's subtree, even
if nested under it — it becomes its own independent split output.

Materials/textures/images are dropped entirely: this project's mesh
pipeline doesn't read glTF materials at all (texturing goes through
the separate atlas + param-map system, see ``docs/graphics/COMBINER.md``),
so carrying them through would add real complexity for no consumer.

Sparse accessors are refused outright (raises, doesn't warn), matching
``convert_mesh.py``'s own refusal philosophy — this script can't safely
repack sparse-encoded data without fully decoding it, and doing so
would blur the line with the general-purpose importer this project
deliberately doesn't build.

Uses only the Python standard library (``json``, ``struct``, ``re``) —
no new ``pip`` dependency, matching every other ``tools/`` script.

Usage:
    python tools/split_glb.py bird.glb
    python tools/split_glb.py bird.glb -o some/other/dir --no-convert

By default, split parts land in
``frontend/assets/pending/models/<input filename stem>/`` and are then
immediately run through ``convert_mesh.convert()`` in-process, writing
``frontend/assets/data/mesh/mesh-<part name>.json`` for each — pass
``--no-convert`` to only split, leaving conversion to a later manual
``convert_mesh.py`` run.

Authoring workflow:
    1. Model each part as its own object in Blender; parent each
       socket Empty directly under the mesh object it belongs to
       (not under another Empty, not un-parented).
    2. Apply Transform on every mesh object (not the Empties) —
       see docs/graphics/3D_ASSET_AUTHORING.md §1.
    3. Export the whole rig as one glTF 2.0 (.glb), armatures/shape
       keys/animations disabled, same as a single-part export.
    4. Run this script on the exported file.
"""

import argparse
import json
import re
import struct
import sys
from pathlib import Path
from typing import Any, Optional

from convert_mesh import ConvertError, convert, load_glb, load_gltf


def collect_part_roots(gltf: dict[str, Any]) -> list[int]:
    """Return the index of every node that references a mesh."""
    return [i for i, n in enumerate(gltf.get("nodes", [])) if "mesh" in n]


def build_part_subtree(
    gltf: dict[str, Any],
    node_idx: int,
    new_nodes: list[dict[str, Any]],
    is_root: bool,
) -> int:
    """Copy ``node_idx`` and its non-mesh descendants into ``new_nodes``.

    A descendant that itself has a ``mesh`` key belongs to a different
    part and is excluded here — it gets its own top-level call from
    ``split_glb``'s main loop instead. Returns the new index of the
    copied node within ``new_nodes``.
    """
    node = gltf["nodes"][node_idx]
    new_node: dict[str, Any] = {}
    if "name" in node:
        new_node["name"] = node["name"]
    for key in ("translation", "rotation", "scale"):
        if key in node:
            new_node[key] = node[key]
    if is_root:
        new_node["mesh"] = 0

    new_index = len(new_nodes)
    new_nodes.append(new_node)

    children_out = []
    for child_idx in node.get("children", []):
        if "mesh" in gltf["nodes"][child_idx]:
            continue
        children_out.append(
            build_part_subtree(gltf, child_idx, new_nodes, is_root=False)
        )
    if children_out:
        new_node["children"] = children_out

    return new_index


def collect_mesh_accessor_indices(mesh_def: dict[str, Any]) -> set[int]:
    """Every accessor index a mesh's primitives reference, in any of
    attributes/indices/morph targets."""
    indices: set[int] = set()
    for prim in mesh_def.get("primitives", []):
        indices.update(prim.get("attributes", {}).values())
        if "indices" in prim:
            indices.add(prim["indices"])
        for target in prim.get("targets", []):
            indices.update(target.values())
    return indices


def remap_mesh(
    mesh_def: dict[str, Any], accessor_remap: dict[int, int]
) -> dict[str, Any]:
    """Rebuild a mesh dict with accessor indices remapped and any
    ``material`` reference dropped (materials aren't carried through)."""
    new_mesh: dict[str, Any] = {}
    if "name" in mesh_def:
        new_mesh["name"] = mesh_def["name"]

    new_primitives = []
    for prim in mesh_def.get("primitives", []):
        new_prim: dict[str, Any] = {
            "attributes": {
                k: accessor_remap[v]
                for k, v in prim.get("attributes", {}).items()
            }
        }
        if "indices" in prim:
            new_prim["indices"] = accessor_remap[prim["indices"]]
        if "mode" in prim:
            new_prim["mode"] = prim["mode"]
        if "targets" in prim:
            new_prim["targets"] = [
                {k: accessor_remap[v] for k, v in target.items()}
                for target in prim["targets"]
            ]
        new_primitives.append(new_prim)
    new_mesh["primitives"] = new_primitives
    return new_mesh


def write_glb(path: Path, gltf_json: dict[str, Any], bin_data: bytes) -> None:
    """Write a minimal, valid .glb: 12-byte header + JSON chunk + BIN
    chunk, both padded to 4-byte alignment per the glTF 2.0 spec."""
    json_bytes = json.dumps(gltf_json, separators=(",", ":")).encode("utf-8")
    json_bytes += b" " * ((-len(json_bytes)) % 4)

    bin_padded = bin_data + b"\x00" * ((-len(bin_data)) % 4)

    total_length = 12 + 8 + len(json_bytes) + 8 + len(bin_padded)

    with open(path, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, total_length))
        f.write(struct.pack("<I4s", len(json_bytes), b"JSON"))
        f.write(json_bytes)
        f.write(struct.pack("<I4s", len(bin_padded), b"BIN\x00"))
        f.write(bin_padded)


def split_glb(
    input_path: str,
    output_dir: Optional[str],
    mesh_dir: str,
    do_convert: bool,
) -> list[Path]:
    """Split one multi-mesh glTF/GLB into one single-mesh .glb per
    mesh-bearing node, optionally chaining each into
    ``convert_mesh.convert()``. Returns the list of split .glb paths
    written."""
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

    root_indices = collect_part_roots(gltf)
    if not root_indices:
        raise ConvertError(f"'{in_path}' has no mesh-bearing nodes to split")

    out_dir = (
        Path(output_dir)
        if output_dir
        else Path("frontend/assets/pending/models") / in_path.stem
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    used_names: set[str] = set()

    for node_idx in root_indices:
        node = gltf["nodes"][node_idx]
        mesh_index = node["mesh"]
        mesh_def = gltf["meshes"][mesh_index]

        accessor_indices = collect_mesh_accessor_indices(mesh_def)
        for acc_idx in accessor_indices:
            if "sparse" in gltf["accessors"][acc_idx]:
                raise ConvertError(
                    f"node '{node.get('name', node_idx)}': accessor "
                    f"{acc_idx} uses sparse storage — not supported"
                )

        bufferview_indices = sorted(
            {
                gltf["accessors"][i]["bufferView"]
                for i in accessor_indices
                if "bufferView" in gltf["accessors"][i]
            }
        )

        new_bin = bytearray()
        bufferview_remap: dict[int, int] = {}
        new_bufferviews: list[dict[str, Any]] = []
        for old_bv_idx in bufferview_indices:
            bv = gltf["bufferViews"][old_bv_idx]
            src = buffers.get(bv["buffer"])
            if src is None:
                raise ConvertError(
                    f"bufferViews[{old_bv_idx}] references buffer "
                    f"{bv['buffer']}, which has no data loaded"
                )
            start = bv.get("byteOffset", 0)
            length = bv["byteLength"]
            new_offset = len(new_bin)
            new_bin += src[start : start + length]
            new_bin += b"\x00" * ((-len(new_bin)) % 4)

            new_bv: dict[str, Any] = {
                "buffer": 0,
                "byteOffset": new_offset,
                "byteLength": length,
            }
            if "byteStride" in bv:
                new_bv["byteStride"] = bv["byteStride"]
            bufferview_remap[old_bv_idx] = len(new_bufferviews)
            new_bufferviews.append(new_bv)

        accessor_remap: dict[int, int] = {}
        new_accessors: list[dict[str, Any]] = []
        for old_acc_idx in sorted(accessor_indices):
            acc = dict(gltf["accessors"][old_acc_idx])
            if "bufferView" in acc:
                acc["bufferView"] = bufferview_remap[acc["bufferView"]]
            accessor_remap[old_acc_idx] = len(new_accessors)
            new_accessors.append(acc)

        new_mesh = remap_mesh(mesh_def, accessor_remap)

        new_nodes: list[dict[str, Any]] = []
        build_part_subtree(gltf, node_idx, new_nodes, is_root=True)

        out_gltf = {
            "asset": gltf.get("asset", {"version": "2.0"}),
            "scene": 0,
            "scenes": [{"nodes": [0]}],
            "nodes": new_nodes,
            "meshes": [new_mesh],
            "accessors": new_accessors,
            "bufferViews": new_bufferviews,
            "buffers": [{"byteLength": len(new_bin)}],
        }

        raw_name = node.get("name") or f"part{mesh_index}"
        name = re.sub(r"[^A-Za-z0-9_-]", "_", raw_name)
        base_name = name
        suffix_n = 1
        while name in used_names:
            suffix_n += 1
            name = f"{base_name}_{suffix_n}"
        used_names.add(name)

        out_path = out_dir / f"{name}.glb"
        write_glb(out_path, out_gltf, bytes(new_bin))
        written.append(out_path)
        socket_count = sum(len(n.get("children", [])) for n in [new_nodes[0]])
        print(
            f"[split_glb] Wrote {out_path} "
            f"({len(new_mesh['primitives'])} primitive(s), "
            f"{socket_count} socket(s))"
        )

        if do_convert:
            mesh_json_path = Path(mesh_dir) / f"mesh-{name}.json"
            try:
                convert(str(out_path), str(mesh_json_path))
            except ConvertError as err:
                print(
                    f"[split_glb] Error converting {out_path}: {err}",
                    file=sys.stderr,
                )

    return written


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Split a multi-mesh glTF 2.0 export into one single-mesh "
            ".glb per mesh-bearing node, ready for tools/convert_mesh.py."
        )
    )
    parser.add_argument("input", help="Path to a multi-mesh .gltf or .glb file")
    parser.add_argument(
        "-o",
        "--output-dir",
        help=(
            "Directory to write split .glb files into. Default: "
            "frontend/assets/pending/models/<input filename stem>/"
        ),
    )
    parser.add_argument(
        "--mesh-dir",
        default="frontend/assets/data/mesh",
        help=(
            "Directory for auto-converted mesh JSON "
            "(default: frontend/assets/data/mesh)"
        ),
    )
    parser.add_argument(
        "--no-convert",
        action="store_true",
        help=(
            "Only split into per-part .glb files; skip auto-running "
            "convert_mesh.py on each"
        ),
    )
    args = parser.parse_args()

    try:
        split_glb(
            args.input,
            args.output_dir,
            args.mesh_dir,
            do_convert=not args.no_convert,
        )
    except ConvertError as err:
        print(f"[split_glb] Error: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
