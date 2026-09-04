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

A clip may also define a top-level `"origins"` map
(client/engine/entity_builder.py's Animation Editor, per direct
request: "allow setting an origin point to apply the animation
transformation from"), keyed the same way as a keyframe's own `"parts"`
map but living once per clip, not per keyframe -- a rotation/scale
pivot point is a property of *how a part is rigged* (a wing's hinge, a
door's hitch), not something that would sensibly change keyframe to
keyframe within one clip::

    {
      "id": "anim-transform-bird-flap",
      "type": "transform",
      "loop": true,
      "origins": {"wing_l": [0.02, 0.0, 0.0]},
      "keyframes": [ ... ]
    }

When `sample_transform_clip` is called with the same `part_id` this map
names, its returned dict also carries `"origin"` (unmodified -- not
interpolated, since it's constant for the whole clip). The caller
(`entity_renderer.py`) composes with `mat4.compose_with_pivot()`
instead of plain `mat4.compose()` whenever an origin is present,
rotating/scaling around that point instead of the part's own mesh-space
(0, 0, 0). A clip with no `"origins"` entry for a part is unaffected --
`"origin"` is simply absent from the result, exactly like an
unanimated position/rotation/scale field.

A keyframe entry (a top-level keyframe in the flat schema, or a part's
own entry inside a multi-part keyframe's `"parts"` map) may also carry
an optional `"easing": [x1, y1, x2, y2]` -- a cubic-bezier control-point
pair, the same `cubic-bezier(x1, y1, x2, y2)` convention CSS/After
Effects use (`P0=(0,0)`, `P1=(x1,y1)`, `P2=(x2,y2)`, `P3=(1,1)`), per
direct request ("I'd rather expose a more flexible curve" than a fixed
named-easing set). It governs the transition *into* that keyframe (the
segment from the previous keyframe up to this one) -- see
`cubic_bezier_ease`/`resolve_easing`, used by `_interpolate` in place of
the raw linear `t` before lerping. Absent (every clip authored before
this feature existed) defaults to `[0, 0, 1, 1]`, a straight line --
identical to the old, uneased linear behavior, so no migration is
needed. `x1`/`x2` should stay within `[0, 1]` (a bezier curve is only a
valid function of time otherwise); `y1`/`y2` are intentionally
unclamped, so an overshoot/"back" style curve (`y` briefly outside
`[0, 1]`) is possible, same as CSS/AE allow.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# A straight line, P1=(0,0) P2=(1,1) -- cubic_bezier_ease reduces to
# plain linear interpolation with these control points, so this is
# also the correct "no easing authored" default (see resolve_easing).
DEFAULT_EASING: Tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)


def resolve_easing(entry: Dict[str, Any]) -> Tuple[float, float, float, float]:
    """*entry*'s own `"easing"` control points (see the module
    docstring), or DEFAULT_EASING (a straight line) when absent or
    malformed -- shared by `_interpolate` and by
    `entity_builder.py`'s Animation Editor UI, so both always agree on
    what "no curve authored yet" means.
    """
    easing = entry.get("easing")
    if not isinstance(easing, (list, tuple)) or len(easing) != 4:
        return DEFAULT_EASING
    try:
        return (float(easing[0]), float(easing[1]), float(easing[2]), float(easing[3]))
    except (TypeError, ValueError):
        return DEFAULT_EASING


def _bezier_coefficients(p1: float, p2: float) -> Tuple[float, float, float]:
    """Cubic-bezier-along-one-axis coefficients for a curve pinned to
    P0=0/P3=1 -- standard form (same as WebKit's UnitBezier/the CSS
    Easing Functions spec's own reference algorithm): the curve is
    `((a*u + b)*u + c) * u` for `u` in [0, 1].
    """
    c = 3.0 * p1
    b = 3.0 * (p2 - p1) - c
    a = 1.0 - c - b
    return a, b, c


def cubic_bezier_ease(t: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """Sample the cubic-bezier easing curve `cubic-bezier(x1, y1, x2,
    y2)` at time *t* (0..1), returning the eased 0..1 progress to lerp
    with instead of *t* itself -- per direct request for a fully
    flexible transition curve (not a fixed named set).

    The curve is defined parametrically (`x(u)`, `y(u)` for `u` in
    [0, 1]), so unlike a simple 1D easing formula, sampling it at a
    given *t* first requires solving `x(u) = t` for `u` -- done here via
    a few Newton-Raphson iterations (same approach as WebKit's own
    `cubic-bezier()` implementation and the CSS Easing Functions spec's
    reference algorithm), then evaluating `y(u)`.

    *t* <=0/>=1 short-circuit to exactly 0.0/1.0 (every valid bezier
    curve here is pinned to pass through (0,0) and (1,1) by
    construction) rather than running Newton-Raphson at the boundary,
    where its derivative can be degenerate.
    """
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0

    ax, bx, cx = _bezier_coefficients(x1, x2)
    ay, by, cy = _bezier_coefficients(y1, y2)

    u = t
    for _ in range(8):
        x = ((ax * u + bx) * u + cx) * u - t
        if abs(x) < 1e-6:
            break
        derivative = (3.0 * ax * u + 2.0 * bx) * u + cx
        if abs(derivative) < 1e-6:
            break
        u -= x / derivative
    u = min(1.0, max(0.0, u))

    return ((ay * u + by) * u + cy) * u


def _interpolate(keyframes: List[Dict[str, Any]], time_ms: float) -> Dict[str, List[float]]:
    """Shared bracket-and-lerp core for both the flat, single-part
    schema and (per keyframe) one part's own filtered sub-list from a
    multi-part rig clip -- see sample_transform_clip.

    *hi* (the destination keyframe of whichever segment *time_ms* falls
    in) is where the segment's `"easing"` control points are read from
    (see resolve_easing/cubic_bezier_ease/the module docstring) -- "ease
    into this pose" reads naturally as a property of the keyframe being
    eased into, and keeps `"easing"` colocated with the pose it shapes,
    right alongside that same part's position/rotation/scale for this
    keyframe. `t`'s already exactly 0.0 in both hold-at-the-boundary
    branches below, and cubic_bezier_ease(0, ...) is always 0.0
    regardless of curve, so easing has no effect outside the clip's
    time range -- only ever reshapes an actual transition between two
    real keyframes.
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

    eased_t = cubic_bezier_ease(t, *resolve_easing(hi))

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
        result[field] = [a + (b - a) * eased_t for a, b in zip(lo_val, hi_val)]
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
            a caller now passes `part_id`. Also selects which entry of
            the clip's top-level `"origins"` map (if any) gets attached
            to the result as `"origin"`.

    Returns:
        A dict with whichever of "position"/"rotation"/"scale" the
        relevant keyframes define, each a 3-element [x, y, z] list
        linearly interpolated between the two bracketing keyframes,
        plus "origin" (unmodified, not interpolated) when *part_id*
        names an entry in the clip's own `"origins"` map. Empty dict if
        the clip has no keyframes, or (for a multi-part clip) no
        keyframe names this part_id at all -- in that case "origin" is
        never attached either, since this part_id has no track in the
        clip to begin with.
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
        result = _interpolate(part_keyframes, time_ms)
    else:
        result = _interpolate(keyframes, time_ms)

    if part_id is not None:
        origin = (clip.get("origins") or {}).get(part_id)
        if origin is not None:
            result["origin"] = origin
    return result
