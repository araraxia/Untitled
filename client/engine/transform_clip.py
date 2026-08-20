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
"""

from __future__ import annotations

from typing import Any, Dict, List


def sample_transform_clip(clip: Dict[str, Any], time_ms: float) -> Dict[str, List[float]]:
    """Sample a transform clip at time_ms.

    Args:
        clip: Parsed clip JSON (see module docstring for schema).
        time_ms: Elapsed time since this part's clip started, in
            milliseconds. Wrapped modulo the clip's total duration
            when `clip.get("loop", True)`.

    Returns:
        A dict with whichever of "position"/"rotation"/"scale" the
        clip's keyframes define, each a 3-element [x, y, z] list
        linearly interpolated between the two bracketing keyframes.
        Empty dict if the clip has no keyframes.
    """
    keyframes = clip.get("keyframes", [])
    if not keyframes:
        return {}

    duration = keyframes[-1]["time_ms"]
    if clip.get("loop", True) and duration > 0:
        time_ms = time_ms % duration

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
