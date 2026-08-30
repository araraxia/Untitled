# Graphics System — 3D Asset Authoring (Blender → Mesh Pipeline)

> **Status: implemented.** This document describes the asset pipeline
> specified in
> [`.github/prompts/3d-coordinate-mapping.prompt.md`](../../.github/prompts/3d-coordinate-mapping.prompt.md).
> `client/engine/mat4.py`, `client/engine/mesh.py`, and `tools/convert_mesh.py`
> all exist and are in use — per [ROADMAP.md](../../ROADMAP.md) Phase 10,
> steps 1–11 (including the mesh authoring pipeline, step 10.4) are done.
> `tools/convert_animation.py` (importing Blender keyframe animation as
> transform clips), `tools/split_glb.py` (multi-mesh export splitting),
> and `client/engine/entity_builder.py` (a GUI wrapping this entire
> pipeline, per [ROADMAP.md](../../ROADMAP.md) Phase 15 and
> [`.github/prompts/entity-builder.prompt.md`](../../.github/prompts/entity-builder.prompt.md))
> are also implemented and referenced throughout this document — it is
> no longer accurate to say animation keyframes can't be imported from
> Blender (see §7) or that only single-mesh files are supported (see §1a).
> If you're looking for the *2D sprite atlas* pipeline instead, see
> [DATA_STRUCTURES.md](DATA_STRUCTURES.md) — this document is its 3D-mesh
> counterpart.

## Scope — what this pipeline is and isn't

This is **not** a general 3D engine integration. It supports exactly:

- Static (non-skinned) triangle meshes — position, normal, UV, optional vertex colour.
- Multi-part assets built from several meshes attached at named sockets.
- Authored transform animation (position/rotation/scale keyframes) — not skeletal animation.
- A cosmetic, client-side-only secondary-motion spring for dangling parts.
- Server-timed one-shot action animations (attack, jump).

There is **no skinning, no bone weights, no shape keys, no imported
*skeletal* animation, no rigid-body or collision physics**. If an asset
needs any of those, it belongs on the existing 2D sprite-sheet pipeline
instead (covered in [DATA_STRUCTURES.md](DATA_STRUCTURES.md)) — characters
in particular should generally stay there until this pipeline grows
skinning support, which is not currently planned. **Rigid transform
keyframes (position/rotation/scale on a whole part — a wing flap, a
door swing) *can* be imported directly from Blender's own keyframe
timeline** (§7) — this used to require hand-authoring every keyframe
value by hand; it no longer does.

---

## Two ways to build an asset

Everything below can be done either as a sequence of CLI scripts, or
through **`client/engine/entity_builder.py`** — a GUI tool reachable
from the launcher ("New Entity", or "Edit" next to any existing entity
in the Entities tab) that wraps every script this document covers:
Import Mesh (`convert_mesh.py`, plus a "Split Multi-Mesh GLB" button
for `split_glb.py`), Import Animation (`convert_animation.py`), part
assembly with `attachTo`/socket pickers constrained to a mesh's real,
loaded sockets, "Scaffold Parts from Sockets" (§6), a Materials panel
(`pack_param_map.py`), and Save. The GUI doesn't change any file format
or authoring rule described here — it's the same pipeline, one click
per step instead of one terminal command per step. This document
describes the underlying steps either path ultimately performs; use
whichever you prefer.

---

## 1. Modeling in Blender

- **Low-poly.** This renders at small on-screen sizes alongside 2D sprites — a few hundred to low-thousands of tris per asset is the target, not tens of thousands.
- **One mesh, one primitive, triangles only.** The converter only reads `meshes[0].primitives[0]` with `mode 4` (`TRIANGLES`). Join multi-object models into a single mesh (`Ctrl+J`) and apply any modifiers (`Ctrl+A` → Visual Geometry to Mesh, or Apply on each modifier) before export. Triangulate n-gons/quads (`Ctrl+T`, or enable "Triangulate Faces" in export options).
- **UV unwrap normally** (`U` → Unwrap, per-seam or Smart UV Project) — see [DATA_STRUCTURES.md](DATA_STRUCTURES.md) and the texturing section below for how UVs are used.
- **No armature.** Don't rig the mesh — skinned meshes are rejected by the converter (see §4).
- **Attachment points = Empties.** For a part that needs a socket other meshes attach to (e.g. where a charm hangs off a staff), add a plain Empty (`Shift+A` → Empty) at that point and name it descriptively (`charm_socket`). The converter picks up any glTF node with a name but no mesh reference as a socket, using that Empty's local translation/rotation. Don't parent geometry to the Empty — it's a marker, not a rig.
- **Vertex colour (optional).** If this asset should use the `vertex_color` stylization hook (§7), paint it in Vertex Paint mode before export. Skip this entirely if you don't need it — the default is a no-op white.

### 1a. Multi-part rigs (several meshes in one file)

`tools/convert_mesh.py` still only ever reads one mesh per file (§4) —
that hasn't changed. But a rigid-part hierarchy (a bird made of a body,
two legs, two wings, a beak — see §6) is naturally modeled as several
separate objects in *one* Blender scene, not five separate `.blend`
files. `tools/split_glb.py` bridges this: export the whole rig as one
glTF, and it splits it into one single-mesh `.glb` per mesh-bearing
node, each ready for the normal `convert_mesh.py` step.

This has its own, more specific authoring rules than the single-mesh
case above:

1. **Model each part as its own object.** One Blender object per
   rigid part (body, each leg, each wing, the beak) — not one object
   with multiple material slots or loose geometry islands.
2. **Set each attaching part's origin to its pivot joint.** Rotation
   happens around a part's own object origin once split and placed at
   runtime — a wing's origin needs to be at the shoulder, not its
   bounding-box center, or it'll flap around the wrong point. Move the
   3D cursor to the joint (`Shift+S` → Cursor to Selected on a vertex),
   then `Object > Set Origin > Origin to 3D Cursor` on that part.
3. **Socket Empties must be parented directly to the mesh object they
   belong to — not to another Empty, not left unparented.** Add a
   plain-axes Empty on the *parent* part (e.g. the body) at the exact
   joint location, named for what attaches there (`wing_l_socket`,
   `beak_socket`), and parent it to that mesh object (`Ctrl+P` →
   Object, keep transform). `split_glb.py` walks each mesh-bearing
   node's direct children for socket Empties — a socket nested under
   the wrong node, or under another Empty instead of a mesh, won't be
   found.
4. **Apply Transform on every mesh object (not the Empties)** —
   `Ctrl+A` → All Transforms — before export, so each part's exported
   local coordinates are clean relative to its own origin. Do **not**
   apply transforms on the socket Empties themselves; their position
   relative to their parent mesh is exactly what's being captured.
5. **Export the whole rig as one glTF 2.0** (`.glb`), armatures/shape
   keys/animations disabled — identical export settings to the
   single-mesh case (§3).
6. **Run the splitter, then convert each part normally:**
   ```text
   python tools/split_glb.py bird.glb
   ```
   Split parts land in `frontend/assets/pending/models/<source
   stem>/` by default (one `.glb` per mesh-bearing node) and print a
   socket count per part; run `tools/convert_mesh.py` on each as usual
   (§4a covers the flag that does both in one step). The Entity
   Builder's "Split Multi-Mesh GLB" button does exactly this, then
   lets you pick and name each resulting part through the normal
   Import Mesh flow.

A node that is itself mesh-bearing is never swept into a sibling
part's subtree even if it's nested underneath it in Blender's outliner
— it always becomes its own independent split output. Materials and
textures are dropped entirely during the split (this pipeline's
texturing is a separate step, §2) — carrying glTF materials through
would add real complexity for zero consumers, since nothing here ever
reads them.

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

The converter (§4) **refuses** files containing skins, morph targets, or more than one mesh/primitive — it raises a clear error rather than silently dropping data, so an accidental armature or shape key will surface immediately at conversion time, not as a mystery render bug later. A multi-mesh file isn't an error to fix in the export settings, though — split it first (§1a, §4a).

### 3a. Export settings for animation clips (§7)

A **separate export**, not an addition to the settings above — animating a part means exporting it a second time with different settings:

| Setting | Value |
| --- | --- |
| Format | `.glb` (single file) or `.gltf` + `.bin` |
| Object animated | **Exactly one** — the part's own object, or a proxy pivot, whichever this clip should move |
| Keyframe interpolation | **Linear**, on every keyframe (Dope Sheet/Graph Editor: select all, `T` → Linear). Bezier — Blender's default — exports as `CUBICSPLINE`, which the converter (§4b) refuses. |
| Animations | **Enabled** — the opposite of the geometry export above |
| Armatures | **Disabled** — do not include |
| Shape keys | **Disabled** — do not include |

If the file has more than one Blender Action, the converter needs `--animation <name>` to pick one (§4b) — otherwise it lists the available names and stops rather than guessing.

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

### 4a. Splitting multi-mesh exports: `tools/split_glb.py`

For the multi-part rigs described in §1a — a companion pre-processing
step for the converter above, never a replacement for it:

```text
python tools/split_glb.py bird.glb
```

Walks the source file's node graph and, for every mesh-bearing node,
writes a self-contained single-mesh `.glb` (that mesh's geometry,
re-packed into a fresh binary buffer, plus any socket Empties parented
directly under it — see §1a's rule 3) into `frontend/assets/pending/models/<input
stem>/` by default (`-o` to choose another directory). By default it
also immediately runs each split part through `convert_mesh.convert()`
in-process, writing `frontend/assets/data/mesh/mesh-<part name>.json`
for each — pass `--no-convert` to only split and leave conversion to a
later manual `convert_mesh.py` run (this is what the Entity Builder's
"Split Multi-Mesh GLB" button does, so each part can still be named
deliberately through the normal Import Mesh flow rather than
inheriting raw Blender object names). Materials/textures are dropped
entirely (§1a) and sparse accessors are refused, same as §4's
converter.

### 4b. Converting animation: `tools/convert_animation.py`

```text
python tools/convert_animation.py wing_flap.glb \
  -o frontend/assets/data/animation/animation-transform-wing-flap.json \
  [--id anim-transform-wing-flap] [--animation <name>] [--no-loop]
```

Converts one glTF animation (exported per §3a) into the transform-clip
JSON format §7 describes — the same file format as a hand-authored
clip, just produced from Blender's own timeline instead of typed by
hand. Also stdlib-only, and equally narrow by design:

1. Picks exactly one animation from the file — the only one present,
   or whichever `--animation <name>` names; otherwise lists the
   available names and refuses to guess.
2. Requires exactly one animated node — a transform clip animates one
   part's local transform; refuses (rather than merging or picking
   one) if more than one object has keyframes in the export.
3. Reads translation/rotation/scale channels (refuses morph-target
   `weights` channels) and merges them onto one shared time grid, even
   if you keyed position on different frames than rotation.
4. Refuses non-`LINEAR` sampler interpolation outright (§3a) — the
   error message tells you exactly which Blender setting to fix.
5. **Resolves rotation-decomposition ambiguity across keyframes** (an
   "Euler continuity" pass, the same class of fix Blender/Maya's own
   Graph Editor calls an "Euler Filter"): converting a quaternion
   keyframe to Euler angles independently per keyframe can land on a
   different, numerically-discontinuous-but-visually-identical
   representation once a rotation crosses roughly 180° on one axis —
   without correcting for it, a plain 90°-per-keyframe spin can come
   out as a jarring flip instead of a smooth turn once this project's
   own runtime linearly interpolates between the raw keyframes. This
   step exists so you don't have to work around it by hand (extra
   in-between keyframes, avoiding large single-axis turns) — animate
   normally in Blender and export.

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

Hand-writing the `parts` array below for a multi-part rig (one entry per part, `attachTo`/`socket` kept internally consistent) is exactly the kind of mechanical, error-prone step the Entity Builder's "Scaffold Parts from Sockets" button automates: point it at a root part whose mesh has sockets (§1a), and it suggests one part per socket — matched to an already-imported mesh by name where possible, always editable, never auto-written until you confirm.

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

For continuous authored motion (a spinning coin, a bobbing lid, a wing
flap). Two ways to produce the file below — pick whichever fits the
motion:

- **Hand-author the keyframe values** — still the simplest choice for
  a handful of keyframes with round numbers (a full-turn spin like the
  example below is genuinely easier to type than to key in Blender:
  just write the end angle as a multiple of `2π`).
- **Export from Blender's own keyframe timeline** and run
  `tools/convert_animation.py` (§4b) — the better choice for anything
  with real, hand-posed motion (a flap, a swing, a walk cycle). Animate
  the one object this clip should move, keep interpolation Linear
  (§3a), export, convert. This used to be unsupported ("don't try to
  export them from Blender's timeline" — no longer true); §4b covers
  the exact workflow and the one real gotcha (large single-axis turns)
  the converter now handles for you.

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

Reference it from a part via `animation_id`. Any subset of `position`/`rotation`/`scale` may be keyframed; omitted fields hold the part's rest value. **For a looping clip, make the last keyframe's pose match the first exactly** — playback wraps via `time % duration`, so a mismatched loop point produces a visible pop every cycle; this matters equally whether the clip was hand-typed or converted from Blender.

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

**Single-mesh asset:**

1. Model in Blender: single mesh, triangulated, low-poly, UV-unwrapped, modifiers applied.
2. (Optional) Vertex-paint if using `vertex_color`.
3. (Optional) Add named Empties for attachment sockets.
4. Export glTF 2.0 (`.glb` recommended) with armatures/shape keys/animations disabled.
5. `python tools/convert_mesh.py model.glb -o frontend/assets/data/mesh/mesh-<name>.json`
6. Paint/export albedo + the 4 param-map masks; pack with `tools/pack_param_map.py`.
7. Write a `material-<name>.json` pointing at the albedo + param map (per [DATA_STRUCTURES.md](DATA_STRUCTURES.md)).
8. Write an `entity-<name>.json` definition referencing the mesh (and material, and any `parts`/`dangle`/`animation_id`/`action_animations`) — or use the Entity Builder's "Scaffold Parts from Sockets" (§6).
9. Run the manifest tool so the mesh and entity-definition files resolve through `assetLoader`:
   ```text
   python tools/build_manifest.py
   ```
10. Set `render_template` (and, if needed, `transform3d`) on the networked entity instance that should use this asset.

**Multi-part rig, add before step 5:**

4a. `python tools/split_glb.py model.glb` (§1a, §4a) — splits into one single-mesh `.glb` per part; run step 5 once per resulting file (or let `split_glb.py`/the Entity Builder auto-chain it).

**Animated part, add wherever a part needs motion:**

- Hand-author the clip JSON directly (§7), **or** animate the part in Blender (§3a) and run `python tools/convert_animation.py part.glb -o frontend/assets/data/animation/animation-transform-<name>.json` (§4b) — either way, reference the resulting clip id from that part's `animation_id`/`action_animations`.

**Or, skip the CLI entirely:** open the Entity Builder (launcher → "New Entity", or "Edit" on an existing one) and do all of the above — import/split/convert, part assembly, materials, save — through one window. See "Two ways to build an asset," above.

---

## Further reading

- [DATA_STRUCTURES.md](DATA_STRUCTURES.md) — animation clip / material / entity JSON schemas (2D pipeline; this document's `mesh`/`parts`/`sockets`/`render_template`/`transform3d` fields extend the same schemas)
- [COMBINER.md](COMBINER.md) — parameter map channel layout and packing, shared by both pipelines
- [COORDINATE_MAPPING.md](COORDINATE_MAPPING.md) — "2.5D / 3D (Future)" section this pipeline implements
- [OVERVIEW.md](OVERVIEW.md) — overall rendering architecture and migration status
- [`.github/prompts/3d-coordinate-mapping.prompt.md`](../../.github/prompts/3d-coordinate-mapping.prompt.md) — full implementation spec for the engine work this document assumes
- [`.github/prompts/entity-builder.prompt.md`](../../.github/prompts/entity-builder.prompt.md) — the Entity Builder GUI (§ "Two ways to build an asset"), `tools/convert_animation.py`, and `tools/split_glb.py`'s implementation spec
