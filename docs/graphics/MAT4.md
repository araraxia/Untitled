# Graphics System — `mat4` Matrix Helpers

> **Keep this file in sync.** `client/engine/mat4.py` carries a header
> comment pointing here — any change to that file's function set,
> matrix layout, or Euler rotation convention must be reflected in this
> doc in the same change.

## What It Is

[`client/engine/mat4.py`](../../client/engine/mat4.py) is a small,
dependency-free 4x4 matrix library — plain Python, no numpy/pyglm.
Every matrix is a flat, **column-major** list of 16 floats, matching
WGSL's `mat4x4<f32>` layout exactly, so a matrix built here can be
packed straight into a uniform buffer with no transpose step:

```text
[ m0  m4  m8  m12 ]
[ m1  m5  m9  m13 ]
[ m2  m6  m10 m14 ]
[ m3  m7  m11 m15 ]
```

It was originally a line-for-line port of a `frontend/js/engine/mat4.js`
counterpart (same math, same layout), written that way so the old
PyWebView/JS client and this one would agree bit-for-bit on transform
math. That JS tree was deleted outright during the `client/` migration
(see `.github/prompts/wgpu-py-migration.prompt.md`) — `mat4.py` is now
the only implementation and has no twin to stay in sync with; the
provenance is kept in its header comment as history, not as a live
sync obligation.

---

## Function Reference

| Function | Returns | Purpose |
| --- | --- | --- |
| `identity()` | `Mat4` | 4x4 identity matrix |
| `perspective(fov_y_radians, aspect, near, far)` | `Mat4` | **P**rojection matrix — WebGPU's 0..1 depth-range convention (not OpenGL's -1..1) |
| `look_at(eye, target, up)` | `Mat4` | **V**iew matrix for a camera at `eye` facing `target` |
| `translation_scale(tx, ty, tz, sx, sy, sz)` | `Mat4` | Translate + non-uniform scale, no rotation — only for callers that genuinely never rotate |
| `rotation_xyz(rx, ry, rz)` | `Mat4` | Rotation matrix from Euler angles, radians — see convention note below |
| `compose(position, rotation_euler, scale)` | `Mat4` | Full TRS **M**odel matrix — what most 3D entities/sockets/keyframes actually use |
| `compose_with_pivot(position, rotation_euler, scale, pivot)` | `Mat4` | Same TRS composition, but rotation/scale pivot around `pivot` (local-space point) instead of the origin — `pivot = [0,0,0]` is identical to `compose()`. Used by animated parts whose desired rotation origin doesn't match their mesh's own local (0,0,0), e.g. a wing hinging at its socket rather than its mesh center |
| `multiply(a, b)` | `Mat4` | `a * b`, both column-major — used to chain P, V, M into an MVP |

`Vec3` is any 3-element `Sequence[float]`; `Mat4` is a plain
`list[float]` of length 16.

---

## Euler Rotation Convention (critical invariant)

`rotation_xyz(rx, ry, rz)` composes as intrinsic **Z, then Y, then X**
— the returned matrix is `Rx * Ry * Rz` applied to a column vector
(roll, then pitch, then yaw). `compose()` uses the same convention
internally.

**Every** consumer of a `transform3d`/socket/keyframe rotation in this
project — mesh entities, action-clip animation, socket-relative parts —
must agree on this exact order. There is no second implementation left
to drift from (see above), but a future rewrite of `rotation_xyz`/
`compose` that silently changes axis order would desync every already
-authored rotation value in `frontend/assets/data/`. Change the
convention only with a matching data-migration plan, never as a quiet
refactor.

---

## MVP Composition — How Callers Actually Chain These

`multiply(a, b)` computes `a * b`; there's no dedicated "build MVP"
helper; callers chain `perspective`/`look_at`/`compose` themselves.
Two real call sites, both using the same `multiply(multiply(P, V), M)`
order:

**View-projection** — [`renderer.get_view_projection_matrix(camera, aspect)`](../../client/engine/renderer.py):
```python
projection = mat4.perspective(fov, aspect, near, far)
view = mat4.look_at(camera["position"], camera["target"], up)
view_projection = mat4.multiply(projection, view)   # P * V
```

**Per-entity MVP** — [`entity_renderer.py`](../../client/engine/entity_renderer.py),
mesh draw path:
```python
model = mat4.compose(position, rotation, scale)      # M
mvp = mat4.multiply(view_projection, model)          # (P * V) * M
```

The 2.5D billboard draw path (same file) skips `compose()` and builds
its model matrix's basis columns directly from the view matrix's
right/up rows (`view[0], view[4], view[8]` / `view[1], view[5],
view[9]`, per `look_at`'s column-major layout), so camera-facing quads
never need a rotation matrix at all — worth knowing before assuming
every model matrix in this codebase goes through `compose()`.

Socket/part-relative world transforms (mesh entities with attachment
points, action-clip-driven animation) chain an extra `compose()` +
`multiply()` per level of nesting: `world = multiply(parent_world,
compose(local_position, local_rotation, local_scale))`. When a part
(or the currently-sampled animation clip) defines a rotation/scale
origin (`localOffset.origin`, or a transform clip's per-part `origins`
map — see `transform_clip.py`'s own docstring), `entity_renderer.py`
calls `compose_with_pivot(local_position, local_rotation, local_scale,
local_origin)` instead of plain `compose()` for that one part; every
other part in the same entity is unaffected.

The 2D (non-`mode: "3d"`) camera path never touches this file at all —
`renderer.get_view_projection_matrix` returns `None` for it, and 2D
draws build their own inline orthographic MVP. See
[COORDINATE_MAPPING.md](COORDINATE_MAPPING.md) for that path.

---

## Consumers

| File | Uses |
| --- | --- |
| `client/engine/renderer.py` | `get_view_projection_matrix()` — builds P and V once per frame for the active 3D camera |
| `client/engine/entity_renderer.py` | Builds model matrices (`compose`, or the billboard's inline basis-column construction) and the final per-entity MVP (`multiply`) for both the mesh and 2.5D billboard draw paths, including socket/part-relative nesting |

Editor-only screen-space projection (the transform gizmo, the grid
overlay, zone-box outlines in `client/engine/area_viewer.py` /
`client/engine/gizmo.py`) does **not** go through this file — it
projects world points to screen pixels for imgui draw-list overlays,
a separate, CPU-only concern from the GPU MVP uniform this file feeds.

---

## Further Reading

- [COORDINATE_MAPPING.md](COORDINATE_MAPPING.md) — UV coordinates, 2D and 3D projection, billboarding
- [DATA_STRUCTURES.md](DATA_STRUCTURES.md) — JSON schemas for the `transform3d`/socket/keyframe data that ultimately becomes a `compose()` call
- [OVERVIEW.md](OVERVIEW.md) — graphics system overview and current status
