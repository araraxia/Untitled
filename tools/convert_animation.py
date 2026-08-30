"""Convert a glTF 2.0 animation export into this project's transform-clip
JSON format (client/engine/transform_clip.py).

Companion to tools/convert_mesh.py, covering the other half of the same
Blender authoring pipeline: that script exports geometry+sockets with
animation explicitly *disabled*; this one exports a single animated
node's keyframes with animation explicitly *enabled*. Reuses
convert_mesh.py's glTF/accessor plumbing (load_glb/load_gltf/
read_accessor/quaternion_to_euler_xyz) directly rather than duplicating
it.

Deliberately narrow, matching convert_mesh.py's own "refuse anything
outside scope" philosophy:
  - exactly one glTF animation per file (ambiguous otherwise -- pick
    with --animation if a file has more than one)
  - exactly one animated node per animation (a transform clip animates
    one rigid part's local offset -- see entity_renderer.py's
    draw_entity_mesh_parts/_sample_part_animation)
  - only translation/rotation/scale channels (morph-target "weights"
    channels are refused, matching convert_mesh.py's skin/morph refusal)
  - only LINEAR interpolation (Blender's default Bezier keyframe
    interpolation exports as CUBICSPLINE, which this tool refuses --
    see the authoring workflow below)

Usage:
    python tools/convert_animation.py <input.gltf|input.glb> \\
        -o frontend/assets/data/animation/animation-transform-<name>.json \\
        [--id anim-transform-<name>] [--animation <name>] [--no-loop]

Authoring workflow:
    1. In Blender, animate ONLY the one object representing the part's
       local pivot (the same object/Empty whose rest transform is that
       part's localOffset in the entity-definition JSON) -- translation/
       rotation/scale keyframes, nothing else in the scene.
    2. Select every keyframe you set (Dope Sheet or Graph Editor,
       select all) and set interpolation to Linear: Key > Interpolation
       Mode > Linear (or press T > Linear). Bezier (Blender's default)
       exports as CUBICSPLINE and this tool refuses it.
    3. Export glTF 2.0 (.gltf+.bin or .glb) with Animation EXPORT
       ENABLED this time (the opposite of convert_mesh.py's workflow,
       which disables it) -- skinning/armatures/shape keys still
       disabled; this tool has no use for them either.
    4. Run this script.
"""

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Optional

from convert_mesh import (
    ConvertError,
    load_gltf,
    load_glb,
    quaternion_to_euler_xyz,
    read_accessor,
)

# glTF animation channel target path -> transform_clip.py field name.
PATH_TO_FIELD = {
    "translation": "position",
    "rotation": "rotation",
    "scale": "scale",
}


def _select_animation(gltf: dict[str, Any], animation_name: Optional[str]) -> dict[str, Any]:
    """Pick exactly one glTF animation, erroring with the available
    names/indices if the choice is ambiguous -- mirrors convert_mesh.py's
    "refuse rather than guess" handling of multiple meshes/primitives.
    """
    animations = gltf.get("animations", [])
    if not animations:
        raise ConvertError(
            "glTF file has no animations -- enable Animation export in "
            "Blender's glTF exporter (see this script's module docstring)"
        )

    if animation_name is not None:
        for anim in animations:
            if anim.get("name") == animation_name:
                return anim
        available = ", ".join(a.get("name", "<unnamed>") for a in animations)
        raise ConvertError(
            f"no animation named '{animation_name}' -- available: {available}"
        )

    if len(animations) > 1:
        available = ", ".join(
            f"'{a.get('name', f'animation_{i}')}'" for i, a in enumerate(animations)
        )
        raise ConvertError(
            f"glTF file has {len(animations)} animations ({available}) -- "
            "pass --animation <name> to pick one"
        )

    return animations[0]


def _select_target_node(gltf: dict[str, Any], animation: dict[str, Any]) -> int:
    """Return the single node index targeted by every channel in
    *animation*, erroring if more than one distinct node is animated --
    a transform clip animates exactly one part's local transform.
    """
    node_indices = {
        channel["target"]["node"]
        for channel in animation.get("channels", [])
        if "node" in channel.get("target", {})
    }
    if not node_indices:
        raise ConvertError("animation has no channels with a target node")
    if len(node_indices) > 1:
        nodes = gltf.get("nodes", [])
        names = ", ".join(
            f"'{nodes[i].get('name', f'node_{i}')}'" for i in sorted(node_indices)
        )
        raise ConvertError(
            f"animation targets {len(node_indices)} different objects "
            f"({names}) -- a transform clip animates exactly one part; "
            "animate only that one object in this export"
        )
    return next(iter(node_indices))


def _make_rotation_continuous(values: "list[list[float]]") -> "list[list[float]]":
    """Resolve Euler-angle decomposition ambiguity across a rotation
    channel's own keyframe sequence -- an "Euler continuity"/"un-flip"
    filter, the same class of fix Blender/Maya's graph editors call an
    Euler Filter.

    quaternion_to_euler_xyz() extracts each keyframe's Euler triple
    independently via atan2/asin, with no notion of the previous
    keyframe. Any rotation matrix reachable by two distinct XYZ-Euler
    triples (which includes the common case of a near-180-degree
    single-axis turn) can have successive keyframes land on different
    branches and/or wrap by +-2*pi -- turning a smooth intended spin
    into a discontinuous jump once transform_clip.py lerps between them
    componentwise at playback. Found via this converter's own test
    fixtures, not a hypothetical: a plain quarter-turn-per-keyframe Y
    spin extracted as ry = 0, -pi/2, +pi, +pi/2, ~0 (branch-flipped at
    the third keyframe) until this filter resolves it to the
    monotonic 0, -pi/2, -pi, -3pi/2, -2pi sequence the lerp actually
    needs to reproduce the intended motion.

    The two XYZ-Euler solutions for a given rotation matrix are
    (rx, ry, rz) and (rx+pi, pi-ry, rz+pi) (each component then free to
    also wrap by any multiple of 2*pi) -- this picks whichever branch,
    after unwrapping each component to the closest representative near
    the previous (already-fixed) keyframe, lands closest overall.
    """
    if len(values) < 2:
        return values

    def unwrap(prev: float, val: float) -> float:
        return val - round((val - prev) / (2 * math.pi)) * 2 * math.pi

    def candidate(prev: "list[float]", branch: "list[float]") -> "tuple[list[float], float]":
        unwrapped = [unwrap(p, v) for p, v in zip(prev, branch)]
        dist = sum((u - p) ** 2 for u, p in zip(unwrapped, prev))
        return unwrapped, dist

    fixed = [list(values[0])]
    for raw in values[1:]:
        prev = fixed[-1]
        flipped = [raw[0] + math.pi, math.pi - raw[1], raw[2] + math.pi]
        raw_unwrapped, raw_dist = candidate(prev, raw)
        flip_unwrapped, flip_dist = candidate(prev, flipped)
        fixed.append(raw_unwrapped if raw_dist <= flip_dist else flip_unwrapped)
    return fixed


def _read_channel(
    gltf: dict[str, Any],
    buffers: dict[int, bytes],
    animation: dict[str, Any],
    channel: dict[str, Any],
) -> tuple[list[float], list[list[float]]]:
    """Read one channel's (times_seconds, values) pair, sorted by time
    and values already converted to plain float lists (quaternions
    converted to Euler XYZ immediately, matching client/engine/mat4.py's
    rotation_xyz convention -- see quaternion_to_euler_xyz's own
    docstring -- then passed through _make_rotation_continuous()).
    """
    sampler = animation["samplers"][channel["sampler"]]
    interpolation = sampler.get("interpolation", "LINEAR")
    if interpolation != "LINEAR":
        raise ConvertError(
            f"channel uses {interpolation} interpolation -- only LINEAR "
            "is supported. In Blender, select all keyframes and set "
            "interpolation to Linear (Key > Interpolation Mode > Linear) "
            "before exporting -- Bezier (the default) exports as "
            "CUBICSPLINE"
        )

    times = [t[0] for t in read_accessor(gltf, buffers, sampler["input"])]
    raw_values = read_accessor(gltf, buffers, sampler["output"])

    # glTF doesn't guarantee sampler.input is pre-sorted; both the
    # continuity filter below and _sample_channel's bracket search
    # assume ascending time order.
    order = sorted(range(len(times)), key=lambda i: times[i])
    times = [times[i] for i in order]
    raw_values = [raw_values[i] for i in order]

    path = channel["target"]["path"]
    if path == "rotation":
        values = _make_rotation_continuous(
            [list(quaternion_to_euler_xyz(*q)) for q in raw_values]
        )
    elif path in ("translation", "scale"):
        values = [list(v) for v in raw_values]
    else:
        raise ConvertError(
            f"channel targets unsupported path '{path}' -- only "
            "translation/rotation/scale are supported (morph-target "
            "weight animation is not)"
        )

    return times, values


def _sample_channel(times: list[float], values: list[list[float]], t: float) -> list[float]:
    """Linearly interpolate *values* at time *t*, holding the first/last
    value outside the channel's own time range. Same bracket-and-lerp
    shape as transform_clip.sample_transform_clip's runtime sampling --
    used here to resample multiple channels (which may carry different
    native keyframe times, e.g. position keyed on different frames than
    rotation) onto one shared, merged time grid.
    """
    if t <= times[0]:
        return list(values[0])
    if t >= times[-1]:
        return list(values[-1])
    for i in range(len(times) - 1):
        if times[i] <= t <= times[i + 1]:
            span = times[i + 1] - times[i]
            frac = (t - times[i]) / span if span > 0 else 0.0
            return [a + (b - a) * frac for a, b in zip(values[i], values[i + 1])]
    return list(values[-1])  # unreachable given the bounds checks above


def convert(
    input_path: str,
    output_path: str,
    clip_id: Optional[str] = None,
    animation_name: Optional[str] = None,
    loop: bool = True,
) -> None:
    """Convert one glTF/GLB animation to the project's transform-clip
    JSON format."""
    in_path = Path(input_path)
    suffix = in_path.suffix.lower()
    if suffix == ".glb":
        gltf, buffers = load_glb(in_path)
    elif suffix == ".gltf":
        gltf, buffers = load_gltf(in_path)
    else:
        raise ConvertError(
            f"Unsupported extension '{suffix}' -- expected .gltf or .glb"
        )

    animation = _select_animation(gltf, animation_name)
    node_index = _select_target_node(gltf, animation)
    node_name = gltf.get("nodes", [])[node_index].get("name", f"node_{node_index}")

    channels_by_path: dict[str, tuple[list[float], list[list[float]]]] = {}
    for channel in animation.get("channels", []):
        target = channel.get("target", {})
        if target.get("node") != node_index:
            continue
        path = target["path"]
        if path in channels_by_path:
            raise ConvertError(
                f"multiple channels target the same path '{path}' on "
                f"node '{node_name}' -- exactly one channel per path is "
                "supported"
            )
        channels_by_path[path] = _read_channel(gltf, buffers, animation, channel)

    if not channels_by_path:
        raise ConvertError(f"node '{node_name}' has no animated channels")

    merged_times = sorted({t for times, _ in channels_by_path.values() for t in times})

    keyframes = []
    last_time_ms: Optional[int] = None
    for t in merged_times:
        time_ms = round(t * 1000)
        if time_ms == last_time_ms:
            continue  # two source times rounded to the same ms -- keep the first
        last_time_ms = time_ms

        keyframe: dict[str, Any] = {"time_ms": time_ms}
        for path, field in PATH_TO_FIELD.items():
            if path not in channels_by_path:
                continue
            times, values = channels_by_path[path]
            keyframe[field] = _sample_channel(times, values, t)
        keyframes.append(keyframe)

    name = in_path.stem
    clip_json = {
        "id": clip_id or f"anim-transform-{name}",
        "type": "transform",
        "loop": loop,
        "keyframes": keyframes,
        "_source": f"{in_path.name} (node: '{node_name}')",
    }

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(clip_json, indent=2) + "\n", encoding="utf-8")
    print(
        f"[convert_animation] Wrote {out_path} "
        f"({len(keyframes)} keyframes, fields: "
        f"{', '.join(PATH_TO_FIELD[p] for p in channels_by_path)})"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a single-node glTF 2.0 animation export into this "
            "project's transform-clip JSON format."
        )
    )
    parser.add_argument("input", help="Path to a .gltf or .glb file")
    parser.add_argument(
        "-o", "--output", required=True, help="Output transform-clip JSON path"
    )
    parser.add_argument(
        "--id", dest="clip_id", default=None,
        help="Clip id (default: anim-transform-<input filename stem>)",
    )
    parser.add_argument(
        "--animation", default=None,
        help="Animation name to convert, if the file has more than one",
    )
    parser.add_argument(
        "--no-loop", action="store_true",
        help="Mark the clip non-looping (default: looping)",
    )
    args = parser.parse_args()

    try:
        convert(
            args.input, args.output,
            clip_id=args.clip_id,
            animation_name=args.animation,
            loop=not args.no_loop,
        )
    except ConvertError as err:
        print(f"[convert_animation] Error: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
