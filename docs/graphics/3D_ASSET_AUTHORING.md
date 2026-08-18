# Graphics System — 3D Asset Authoring (Blender → Mesh Pipeline)

> **Status: planned, not yet implemented.** This document describes the asset
> pipeline specified in
> [`.github/prompts/3d-coordinate-mapping.prompt.md`](../../.github/prompts/3d-coordinate-mapping.prompt.md).
> None of `frontend/js/engine/mat4.js`, `frontend/js/engine/mesh.js`, or
> `tools/convert_mesh.py` exist yet. Written so asset creation can start
> ahead of the engine work landing — the moment the pipeline ships, assets
> built to this spec should convert and load without rework. If you're
> looking for the *current, working* asset pipeline (2D sprite atlases),
> see [DATA_STRUCTURES.md](DATA_STRUCTURES.md) instead — this document is
> its 3D-mesh counterpart.

## Scope — what this pipeline is and isn't

This is **not** a general 3D engine integration. It supports exactly:

- Static (non-skinned) triangle meshes — position, normal, UV, optional vertex colour.
- Multi-part assets built from several meshes attached at named sockets.
- Authored transform animation (position/rotation/scale keyframes) — not skeletal animation.
- A cosmetic, client-side-only secondary-motion spring for dangling parts.
- Server-timed one-shot action animations (attack, jump).

There is **no skinning, no bone weights, no shape keys, no imported keyframe
animation, no rigid-body or collision physics**. If an asset needs any of
those, it belongs on the existing 2D sprite-sheet pipeline instead (covered
in [DATA_STRUCTURES.md](DATA_STRUCTURES.md)) — characters in particular
should generally stay there until this pipeline grows skinning support,
which is not currently planned.

---

## 1. Modeling in Blender

- **Low-poly.** This renders at small on-screen sizes alongside 2D sprites — a few hundred to low-thousands of tris per asset is the target, not tens of thousands.
- **One mesh, one primitive, triangles only.** The converter only reads `meshes[0].primitives[0]` with `mode 4` (`TRIANGLES`). Join multi-object models into a single mesh (`Ctrl+J`) and apply any modifiers (`Ctrl+A` → Visual Geometry to Mesh, or Apply on each modifier) before export. Triangulate n-gons/quads (`Ctrl+T`, or enable "Triangulate Faces" in export options).
- **UV unwrap normally** (`U` → Unwrap, per-seam or Smart UV Project) — see [DATA_STRUCTURES.md](DATA_STRUCTURES.md) and the texturing section below for how UVs are used.
- **No armature.** Don't rig the mesh — skinned meshes are rejected by the converter (see §4).
- **Attachment points = Empties.** For a part that needs a socket other meshes attach to (e.g. where a charm hangs off a staff), add a plain Empty (`Shift+A` → Empty) at that point and name it descriptively (`charm_socket`). The converter picks up any glTF node with a name but no mesh reference as a socket, using that Empty's local translation/rotation. Don't parent geometry to the Empty — it's a marker, not a rig.
- **Vertex colour (optional).** If this asset should use the `vertex_color` stylization hook (§7), paint it in Vertex Paint mode before export. Skip this entirely if you don't need it — the default is a no-op white.

---

## 2. Texturing

Meshes **do not get a new material format** — they reuse the same 2D albedo atlas + RGBA parameter map system the sprite pipeline uses (see [COMBINER.md](COMBINER.md)). A mesh's UVs just need to land somewhere sensible on those existing textures; nothing about texture painting changes from the sprite workflow already documented in this project.

Practical approach:

- Author (or reuse) a flat texture sheet — it can be a single "unwrapped" texture for this one mesh, or a shared atlas if several small props share a sheet.
- Paint albedo normally (Texture Paint workspace, per the sprite-pipeline texturing guide).
- Paint the four param-map masks (roughness, emission, palette index, alpha) as separate greyscale images against the *same UV layout*, then pack them:
  ```text
  python tools/pack_param_map.py \
    -r roughness.png -g emission.png -b palette.png -a alpha.png \
    -o frontend/assets/images/param_maps/<name>_params.png
  ```
- Register both PNGs (albedo + param map) with `assetLoader` the same way any other texture is registered, and reference the albedo key from the mesh's material JSON (`atlas` field) — a mesh entity still points at a `material-<name>.json`, exactly like a sprite entity.

---

## 3. Export settings

Export **glTF 2.0**, not OBJ or FBX — glTF carries the standard `COLOR_0` vertex attribute the converter reads, and its node graph is what supplies socket data.

| Setting | Value |
| --- | --- |
| Format | `.glb` (single file) or `.gltf` + `.bin` |
| Mesh | Single object, single material slot, triangulated |
| Armatures | **Disabled** — do not include |
| Shape keys | **Disabled** — do not include |
| Animations | **Disabled** — do not include |
| Vertex colours | Included, if painted |
| Apply modifiers | Yes |

The converter (§4) **refuses** files containing skins, morph targets, or more than one mesh/primitive — it raises a clear error rather than silently dropping data, so an accidental armature or shape key will surface immediately at conversion time, not as a mystery render bug later.

---

## 4. Converting: `tools/convert_mesh.py`

```text
python tools/convert_mesh.py <input.glb> -o frontend/assets/data/mesh/mesh-<name>.json
```

The converter is a small, stdlib-only script (`json`/`struct`, no `pip` dependencies) — it is deliberately narrow and will not grow into a general glTF importer. It:

1. Parses `meshes[0].primitives[0]` only.
2. Reads `POSITION`, `NORMAL`, `TEXCOORD_0`, and optional `COLOR_0` (normalized to `[0,1]` floats; defaults to `[1,1,1,1]` per vertex if absent).
3. Reads the index accessor.
4. Emits any named, mesh-less node as a `sockets` entry.
5. Writes the result as project-format mesh JSON (§5).
6. Refuses (raises, doesn't warn) on skins, morph targets, sparse accessors, or extra primitives/meshes.

---

## 5. Mesh JSON format

**File path:** `frontend/assets/data/mesh/mesh-<name>.json`

```json
{
  "id": "mesh-crate-001",
  "name": "wooden_crate",
  "vertices": [
    { "pos": [0.0, 0.0, 0.0], "normal": [0.0, 1.0, 0.0], "uv": [0.0, 0.0], "color": [1.0, 1.0, 1.0, 1.0] }
  ],
  "indices": [0, 1, 2, 2, 1, 3],
  "sockets": [
    { "name": "charm_socket", "position": [0.0, 0.5, 0.0], "rotation": [0.0, 0.0, 0.0] }
  ]
}
```

| Field | Type | Description |
| --- | --- | --- |
| `id` | `string` | Unique identifier |
| `name` | `string` | Human-readable name |
| `vertices[].pos` | `[x,y,z]` | Local-space position |
| `vertices[].normal` | `[x,y,z]` | Local-space normal |
| `vertices[].uv` | `[u,v]` | Texture coordinate into the material's albedo/param map |
| `vertices[].color` | `[r,g,b,a]` (optional) | Per-vertex tint; omit entirely if unused — defaults to `[1,1,1,1]` (no-op) |
| `indices` | `array<int>` | Triangle list |
| `sockets` | `array` (optional) | Named local-space attachment points — omit if this mesh has none |
| `sockets[].name` | `string` | Referenced by another part's `attachTo.socket` |
| `sockets[].position` / `.rotation` | `[x,y,z]` | Local transform of the socket |

This is a project-specific format, not a glTF subset — nothing loads `.gltf`/`.glb` at runtime, only the JSON the converter produces.

---

## 6. Placing a mesh: entity definitions

A mesh alone isn't placeable — it's referenced from an **entity definition**, which is what a networked entity's `render_template` field resolves to. This mirrors the existing entity/material split documented in [DATA_STRUCTURES.md](DATA_STRUCTURES.md).

**Single-mesh entity** (`frontend/assets/data/entity/entity-<uuid>.json`):

```json
{
  "id": "crate-def-001",
  "name": "wooden_crate",
  "material_id": "mat-crate-001",
  "mesh": "mesh-crate-001"
}
```

**Multi-part entity** (staff + socket-attached charm):

```json
{
  "id": "staff-def-001",
  "name": "hollow_staff",
  "parts": [
    { "id": "shaft", "mesh": "mesh-staff-shaft", "material_id": "mat-staff-shaft" },
    {
      "id": "charm",
      "mesh": "mesh-staff-charm",
      "material_id": "mat-staff-charm",
      "attachTo": { "part": "shaft", "socket": "charm_socket" },
      "localOffset": { "position": [0, 0, 0], "rotation": [0, 0, 0], "scale": [1, 1, 1] },
      "dangle": { "stiffness": 40, "damping": 0.15, "gravity": [0, -9.8, 0], "maxOffset": 0.2 },
      "animation_id": "anim-charm-idle-spin",
      "action_animations": { "attacking": "anim-charm-swing" }
    }
  ]
}
```

Key rules:

- A part with no `attachTo` composes directly off the entity's own placement (its networked `x`/`y`/`z` plus per-instance `transform3d`).
- `attachTo.part` may only reference an **earlier** part in the array — no forward references, no cycles.
- `localOffset` is the fixed, definition-level relationship between two meshes of the *same* asset (e.g. "the charm hangs 0.3 units below this socket") — it is **not** the same thing as `transform3d`.

### Placement is per-instance, not baked into the definition

The definition file above describes what the object *looks like* — never where it is. Placement lives entirely on the networked `Entity` (`backend/engine/ecs/entity.py`):

- `x` / `y` / `z` — existing position fields, unchanged.
- `render_template` — key resolving to the entity-definition JSON above.
- `transform3d: { rotation: [x,y,z], scale: [x,y,z] }` — per-instance rotation/scale (no `position` key — don't duplicate `x`/`y`/`z` here).

Two entities can share one `render_template` and render as fully independent, independently-rotated copies.

---

## 7. Animation

There is **no skeletal animation support** — a Blender armature/action never survives export (per §3, and the converter refuses skins outright). Motion is authored directly as project JSON in one of three ways, all of which compose additively on the same part:

### Looping transform clips

For continuous authored motion (a spinning coin, a bobbing lid). Hand-author the keyframe values — don't try to export them from Blender's timeline.

**File:** `frontend/assets/data/animation/animation-transform-<name>.json`

```json
{
  "id": "anim-coin-spin",
  "type": "transform",
  "loop": true,
  "keyframes": [
    { "time_ms": 0, "rotation": [0, 0, 0] },
    { "time_ms": 1000, "rotation": [0, 6.283, 0] }
  ]
}
```

Reference it from a part via `animation_id`. Any subset of `position`/`rotation`/`scale` may be keyframed; omitted fields hold the part's rest value.

### Dangle (cosmetic secondary motion)

A hand-rolled spring-damper for parts that should lag/sway with movement (a cloak fringe, a hanging charm) — **not** physics, purely a client-side rendering offset. Configure via the `dangle` block on a part (see example in §6): `stiffness`, `damping`, `gravity`, `maxOffset`. No authoring in Blender is involved — it reacts to the entity's own movement at runtime.

### Action-triggered one-shots

Server-timed clips that play once when `entity.state` transitions into a matching key (e.g. `attacking`, `jumping`), then automatically revert — the client never sends an explicit "stop" message. Configure via a part's `action_animations` map, pointing at transform-clip ids (same schema as the looping clips above, but played once regardless of their own `loop` field).

---

## 8. Optional stylization hooks

Independent, opt-in flags on the mesh's material/scene — each defaults to off/neutral, and a mesh using none of them renders as a plain textured mesh:

| Flag | Where | Default | Effect |
| --- | --- | --- | --- |
| `vertex_color` | material | `false` | Multiply albedo by the mesh's per-vertex `color` |
| `affine_uv` | material | `false` | Disable perspective-correct UV interpolation (N64-style texture warp) |
| `color_levels` | material | `0` (off) | Quantise final colour into N bands |
| `fogColor` / `fogNear` / `fogFar` | scene/camera | `fogFar: 0` (off) | Distance fog |
| `ambientColor` | scene/camera | `[1,1,1]` (off) | Flat ambient tint |

Don't enable these speculatively — they exist for a deliberate low-poly/N64 look and each should be a conscious per-asset or per-scene choice.

---

## 9. End-to-end checklist

1. Model in Blender: single mesh, triangulated, low-poly, UV-unwrapped, modifiers applied.
2. (Optional) Vertex-paint if using `vertex_color`.
3. (Optional) Add named Empties for attachment sockets.
4. Export glTF 2.0 (`.glb` recommended) with armatures/shape keys/animations disabled.
5. `python tools/convert_mesh.py model.glb -o frontend/assets/data/mesh/mesh-<name>.json`
6. Paint/export albedo + the 4 param-map masks; pack with `tools/pack_param_map.py`.
7. Write a `material-<name>.json` pointing at the albedo + param map (per [DATA_STRUCTURES.md](DATA_STRUCTURES.md)).
8. Write an `entity-<name>.json` definition referencing the mesh (and material, and any `parts`/`dangle`/`animation_id`/`action_animations`).
9. Run the manifest tool so the mesh and entity-definition files resolve through `assetLoader`:
   ```text
   python tools/build_manifest.py
   ```
10. Set `render_template` (and, if needed, `transform3d`) on the networked entity instance that should use this asset.

---

## Further reading

- [DATA_STRUCTURES.md](DATA_STRUCTURES.md) — animation clip / material / entity JSON schemas (2D pipeline; this document's `mesh`/`parts`/`sockets`/`render_template`/`transform3d` fields extend the same schemas)
- [COMBINER.md](COMBINER.md) — parameter map channel layout and packing, shared by both pipelines
- [COORDINATE_MAPPING.md](COORDINATE_MAPPING.md) — "2.5D / 3D (Future)" section this pipeline implements
- [OVERVIEW.md](OVERVIEW.md) — overall rendering architecture and migration status
- [`.github/prompts/3d-coordinate-mapping.prompt.md`](../../.github/prompts/3d-coordinate-mapping.prompt.md) — full implementation spec for the engine work this document assumes
