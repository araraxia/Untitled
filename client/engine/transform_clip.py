"""Transform animation clips -- authored, repeating motion for a mesh
part (a spinning coin, a bobbing crate lid), reusing the existing
clip-JSON pattern already used for sprite overlay animations, but
interpolating a position/rotation/scale transform instead of a frame
index. Step 11 of .github/prompts/3d-coordinate-mapping.prompt.md.

Hand-rolled, no-library linear interpolation -- matches
client/engine/mat4.py's explicit, dependency-free style (and the same
style docs/graphics/RENDER_WORKFLOWS.md's Workflow E `lerpPreset`
established on the JS side; this is the same *style*, not a port of
that function, which stays JS).

Clip JSON schema (frontend/assets/data/animation/animation-transform-
<name>.json)::

    {
      "id": "anim-coin-spin",
      "type": "transform",
      "loop": true,
      "keyframes": [
        {"time_ms": 0,    "rotation": [0, 0, 0]},
        {"time_ms": 1000, "rotation": [0, 6.283, 0]}
      ]
    }

Each keyframe may define any subset of position/rotation/scale. A
field entirely absent from every keyframe in the clip is omitted from
sample_transform_clip()'s return value -- the caller (entity_renderer.py)
falls back to the part's own authored localOffset for that field,
matching "omitted fields hold the part's rest value".

Multi-part rig clips (client/engine/entity_builder.py's Animation
Editor, per direct request) extend the same file with an optional
per-keyframe `"parts"` map instead of top-level position/rotation/
scale, so one clip can drive several parts on one shared timeline,
each with its own independent transform::

    {
      "id": "anim-transform-bird-flap",
      "type": "transform",
      "loop": true,
      "keyframes": [
        {"time_ms": 0,   "parts": {"wing_l": {"rotation": [0,0,0]},
                                    "wing_r": {"rotation": [0,0,0]}}},
        {"time_ms": 300, "parts": {"wing_l": {"rotation": [0,0,1.2]}}}
      ]
    }

A part need not appear in every keyframe -- see sample_transform_clip's
`part_id` argument, which interpolates only across the keyframes that
actually name that part, holding at the nearest one outside that span
(same "hold at the bracketing keyframe" rule the flat, single-part
schema above already uses). A clip with no `"parts"` map anywhere is
the original flat, single-part schema, sampled identically to before
regardless of `part_id` -- existing clips need no migration.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _interpolate(keyframes: List[Dict[str, Any]], time_ms: float) -> Dict[str, List[float]]:
    """Shared bracket-and-lerp core for both the flat, single-part
    schema and (per keyframe) one part's own filtered sub-list from a
    multi-part rig clip -- see sample_transform_clip.
    """
    if time_ms <= keyframes[0]["time_ms"]:
        lo = hi = keyframes[0]
        t = 0.0
    elif time_ms >= keyframes[-1]["time_ms"]:
        lo = hi = keyframes[-1]
        t = 0.0
    else:
        lo, hi = keyframes[0], keyframes[-1]
        for i in range(len(keyframes) - 1):
            if keyframes[i]["time_ms"] <= time_ms <= keyframes[i + 1]["time_ms"]:
                lo, hi = keyframes[i], keyframes[i + 1]
                break
        span = hi["time_ms"] - lo["time_ms"]
        t = (time_ms - lo["time_ms"]) / span if span > 0 else 0.0

    result: Dict[str, List[float]] = {}
    for field in ("position", "rotation", "scale"):
        if field not in lo and field not in hi:
            continue
        # A keyframe missing this field falls back to the other
        # bracketing keyframe's value (holds steady across that span)
        # rather than a hard schema requirement that every keyframe
        # define every animated field.
        lo_val = lo.get(field, hi.get(field))
        hi_val = hi.get(field, lo.get(field))
        result[field] = [a + (b - a) * t for a, b in zip(lo_val, hi_val)]
    return result


def sample_transform_clip(
    clip: Dict[str, Any], time_ms: float, part_id: Optional[str] = None
) -> Dict[str, List[float]]:
    """Sample a transform clip at time_ms.

    Args:
        clip: Parsed clip JSON (see module docstring for schema).
        time_ms: Elapsed time since this part's clip started, in
            milliseconds. Wrapped modulo the clip's total duration
            when `clip.get("loop", True)` -- the *full* clip's own
            last keyframe, even for a multi-part clip whose per-part
            filtered sub-list (see below) ends earlier, so every part
            in a shared rig clip stays on one common clock.
        part_id: If given and any keyframe in the clip defines a
            `"parts"` map, sample only that part's own entries (this
            clip's flat, top-level fields are ignored in that case).
            Ignored -- falls back to the flat schema below -- for a
            clip with no `"parts"` map anywhere, so existing single-
            part clips behave exactly as before regardless of whether
            a caller now passes `part_id`.

    Returns:
        A dict with whichever of "position"/"rotation"/"scale" the
        relevant keyframes define, each a 3-element [x, y, z] list
        linearly interpolated between the two bracketing keyframes.
        Empty dict if the clip has no keyframes (or, for a multi-part
        clip, no keyframe names this part_id).
    """
    keyframes = clip.get("keyframes", [])
    if not keyframes:
        return {}

    duration = keyframes[-1]["time_ms"]
    if clip.get("loop", True) and duration > 0:
        time_ms = time_ms % duration

    if part_id is not None and any("parts" in kf for kf in keyframes):
        part_keyframes = [
            {"time_ms": kf["time_ms"], **kf["parts"][part_id]}
            for kf in keyframes
            if part_id in kf.get("parts", {})
        ]
        if not part_keyframes:
            return {}
        return _interpolate(part_keyframes, time_ms)

    return _interpolate(keyframes, time_ms)
