---
agent: agent
description: Implement 3D coordinate mapping — perspective camera, mat4 helpers, billboarded sprites, a minimal textured mesh path, a Blender/glTF mesh authoring pipeline, opt-in stylization hooks, multi-part meshes with attachment sockets, a secondary-motion dangle spring, transform animation clips, and action-triggered (attack/jump) one-shot playback — per the "2.5D / 3D (Future)" section of docs/graphics/COORDINATE_MAPPING.md.
tools:
  - read_file
  - create_file
  - replace_string_in_file
  - multi_replace_string_in_file
  - grep_search
  - file_search
  - get_errors
---

# Task: 3D Coordinate Mapping — Camera, Billboards, Minimal Mesh Path

You are extending the WebGPU renderer with a 3D coordinate mapping path: a real perspective camera (position + look-at + FOV), the matrix math to support it, camera-facing billboarded sprites in a 3D world, a minimal textured-mesh draw path for actual 3D assets, a build-time pipeline so those meshes can actually be authored rather than hand-typed, multi-part meshes with named attachment points, a small secondary-motion system for parts that should hang and sway, authored transform animation clips, and one-shot animation playback triggered by discrete actions (attacking, jumping). This turns the placeholder described in `docs/graphics/COORDINATE_MAPPING.md` ("2.5D / 3D (Future)") into working code.

This is **not** a full 3D engine. No skeletal animation, no skinning, no runtime glTF loading (glTF is used only as an offline authoring interchange format — see Step 6 — it is never loaded by the browser/engine itself), no rigid-body or collision physics, no shadow mapping. Scope is: perspective projection, a 3D camera, billboards, static textured meshes (position/normal/UV), a narrow build-time mesh conversion tool, a handful of **optional, opt-in stylization hooks** (vertex-color tinting, distance fog, an affine/perspective-correct UV toggle, colour quantization), multi-part meshes attached via named sockets (Step 9), a hand-rolled spring-damper for small dangling parts (Step 10 — this is a client-side cosmetic effect, not the "no physics" rule being broken; nothing here touches collision, rigid bodies, or the backend ECS), authored per-part transform animation clips (Step 11), and server-timed one-shot action animations (Step 12, the one step that legitimately touches backend Python — see Constraints). The stylization hooks happen to be the ingredients of a low-poly N64 look, but each one defaults to off/neutral so the mesh path is a plain perspective-correct textured-mesh renderer unless a material or scene explicitly opts in. This is a deliberate choice: the goal is a foundation other rendering techniques (PBR, toon shading, whatever comes next) can build on later without inheriting N64-specific assumptions baked into the base path. Anything beyond that is out of scope — flag it in the audit step instead of building it.

## Required Reading

Read these files before writing any code:

- `docs/graphics/COORDINATE_MAPPING.md` — current 2D MVP approach; the 2.5D/3D section this task implements
- `docs/graphics/OVERVIEW.md` — rendering goals ("explicit control and mathematical clarity over convenience abstractions"); do not introduce a general-purpose linear algebra dependency
- `docs/graphics/RENDER_WORKFLOWS.md` — Workflow A (baseline sprite draw) — the mesh path's fragment shader reuses this combiner logic
- `docs/graphics/DATA_STRUCTURES.md` — entity JSON schema (`size`, `pivot`, `runtime`) — this task adds an optional 3D transform block
- `frontend/js/engine/entityRenderer.js` — read the full file; note how the 2D orthographic MVP is built inline (around the `Workflow A (legacy sprite path)` comment) and how material vs. non-material entities branch
- `frontend/js/engine/renderer.js` — render loop, command encoder/pass lifecycle, `camera` object shape
- `frontend/js/engine/sprites/shaderCache.js` — pipeline variant pattern (`base`, `overlay`, `ramp`, `hue`) to follow for the new `mesh` variant
- `frontend/js/engine/sprites/gpuBuffers.js` — existing buffer helpers to extend, not duplicate
- `frontend/js/engine/assetLoader.js` — manifest category registration pattern (`loadManifest()`'s `categories` array) that Step 7 extends for meshes
- `tools/pack_param_map.py` and `tools/build_manifest.py` — the existing "small, explicit, stdlib-only preprocessing script" pattern that Step 6's mesh converter and Step 7's manifest changes should follow
- `docs/graphics/RENDER_WORKFLOWS.md` — Workflow E's `lerpPreset` — the hand-rolled linear-interpolation style Step 11's `sampleTransformClip` should match
- `backend/engine/ecs/component.py` — `StateComponent` (`state`, `facing`) is the existing field that already drives `"moving"`/`"idle"` animation selection; Step 12 adds new values to it rather than inventing a parallel mechanism
- `backend/game/entities/player.py` and `backend/game/systems/actions.py` — both currently set `entity.state = "attacking"`/`"using_item"`/`"interacting"` on action execution with no code path that ever reverts it; read both before touching either, since they're two parallel (and not fully consistent) action-handling paths
- `backend/game/tick.py` — where the per-tick system list runs; Step 12's auto-revert check is added here
- `.github/copilot-instructions.md` — "Physics & Simulation Boundary" section; governs how Step 10's dangle spring must be named, scoped, and kept separate from `backend/engine/physics.py`'s authoritative system
- `backend/engine/ecs/entity.py` — `serialize()`/`to_dict()`/`from_dict()`; confirms Step 1 task 4's finding and shows the exact pattern (`race`/`model_version`) Step 5's `render_template` field follows

## Constraints

**Read this before assuming every constraint below still applies to the step you're on**: partway through this task (between Steps 8 and 9) the client implementation target switches from the JS/WebGPU browser frontend to the native Python `client/` (wgpu-py), per this repository's migration decision — see the full banner between Steps 8 and 9 for the details (file-path mapping, naming-convention change, style-guide change, the `wgpu-py-migration.prompt.md` prerequisite). The JS-specific bullets below (WGSL-in-JS-template-literals wording aside — WGSL itself is unaffected — and the Airbnb style-guide bullet specifically) describe Steps 1–8, which are already done in JS and stay that way; they do not retroactively apply to Steps 9–14.

- All shaders in **WGSL**. No GLSL. (Unaffected by the JS→Python client switch — WGSL is the shader language regardless of host language.)
- No third-party matrix/vector math library (no `gl-matrix`/npm dependency for Steps 1–8's JS; no `numpy`/`pyglm` for Steps 9–14's Python, per `wgpu-py-migration.prompt.md`'s own constraint). Write explicit `mat4` helper functions matching the project's existing "flat array, column-major, hand-built" style — see `mat4.js` (Steps 1–8) / `client/engine/mat4.py` (Steps 9–14) for the convention to follow.
- The existing 2D orthographic path (`Workflow A`, and the material path in `entityRenderer.js`) must keep working byte-for-byte unchanged when `camera.mode === '2d'` (or the field is absent — default to 2D). Gate all new behaviour behind an explicit 3D camera mode; never make it the implicit default. This constraint is JS-specific by construction (it's protecting the existing browser client's 2D path) — the Python client has no equivalent legacy 2D path to protect.
- Steps 1–8: follow the JavaScript Airbnb style guide, 2-space indent, single quotes. Steps 9–14: follow PEP 8, 4-space indent, 79-column lines (per `.github/copilot-instructions.md` and `wgpu-py-migration.prompt.md`).
- Do not touch Python backend files in this task, **except** two narrowly-scoped additions: Step 5's `render_template` field on `Entity` (three lines following the existing `race`/`model_version` pattern — `entity.py` only, nothing else) and Step 12's action-duration auto-revert (`player.py`, `actions.py`, `tick.py`). Those are the only backend changes in scope. `render_template` is in scope because without it there is no field connecting a networked entity to any 3D render definition at all — every other step in this task would be unreachable from real gameplay. Keep both additions small: `render_template` is a plain optional attribute, nothing more; the action-duration fix is an `ACTION_DURATIONS` constant plus a per-tick revert check, not a rewrite of the action/state system.
- Step 10's dangle spring must comply with `.github/copilot-instructions.md`'s "Physics & Simulation Boundary" section: it is client-side-only cosmetic motion, not the backend's authoritative physics, and must never be named or structured in a way that blurs that line. Concretely: no file/class/function name containing "physics"; no collider; no interaction with the backend ECS or `state_update`; it only offsets what's drawn, never anything simulated or networked; it must not require backend changes or a physics-engine dependency.
- The mesh format itself is a small project-defined JSON format, not a glTF subset. Step 6 adds a narrow build-time glTF-to-project-JSON converter for authoring purposes only — it must stay narrow (single mesh, single primitive, geometry attributes only) and must not grow into a general asset importer that also parses materials, skinning, animations, or multiple meshes/scenes.
- `tools/convert_mesh.py` (Step 6) must use only the Python standard library (`json`, `struct`) — no new `pip` dependency (no `pygltflib`, no `trimesh`), consistent with `requirements.txt`'s bloat-avoidance policy in `.github/copilot-instructions.md` and the project's existing preference for hand-rolled parsing (`pack_param_map.py`, `mat4.js`) over pulling in libraries for narrowly-scoped tasks.
- Stylization hooks added in Step 8 (vertex-color tint, fog, affine UV, colour quantization) must each be an independent opt-in flag defaulting to off/neutral. Do not make any of them the implicit default, and do not couple them to each other or bundle them behind a single "style" switch — a future rendering technique should be able to reuse the mesh/camera plumbing from this task without inheriting any of these behaviours.

---

## Step 1 — Audit Current State ✅

Before writing code, read `entityRenderer.js`, `renderer.js`, and `shaderCache.js` fully and summarize:

1. Where the 2D orthographic MVP is constructed and what `camera` object fields currently exist (likely just 2D position/zoom).
2. How `ShaderCache` currently selects pipeline variants, so the new `mesh` variant follows the same lazy-create-and-cache pattern.
3. What the quad vertex buffer layout is (`gpuBuffers.js` — `createQuadVertexBuffer`), since the mesh path needs a distinct vertex layout (position + normal + UV) rather than the 2D quad's (pos + UV).
4. **Confirm this finding before Step 5 relies on it**: `backend/engine/ecs/entity.py`'s `serialize()` (network wire format for `state_update`/`initial_state`) and `to_dict()`/`from_dict()` (save-file/persistence format) carry gameplay fields (position, velocity, state, facing, `race`, `model_version`, stats, equipment) but **no** `mesh`, `material_id`, `parts`, or any other rendering-definition reference — those fields only exist in the separate `frontend/assets/data/entity/entity-<uuid>.json` schema documented in `DATA_STRUCTURES.md`. Nothing today links a networked ECS entity to which of those definition files renders it. Re-verify this against the current code (it may have changed) before proceeding — Step 5 adds the missing link (`render_template`) on the assumption this gap is real.
5. Read `backend/game/entities/player.py`, `backend/game/systems/actions.py`, and `backend/game/tick.py` and summarize the current action-handling flow (needed for Step 12) — specifically confirm the "sets `entity.state` but never reverts it" finding still holds.
6. Read `.github/copilot-instructions.md`'s "Physics & Simulation Boundary" section (needed for Step 10).

Do not create or edit files in this step.

---

## Step 2 — `mat4` Helper Module ✅

**New file:** `frontend/js/engine/mat4.js`

Small, explicit, dependency-free matrix helpers — flat `Float32Array(16)`, column-major, matching WGSL's `mat4x4<f32>` layout.

Tasks:

1. `identity()` → `Float32Array(16)` identity matrix.
2. `perspective(fovYRadians, aspect, near, far)` → standard WebGPU-convention (0–1 depth range) perspective projection matrix.
3. `lookAt(eye, target, up)` → view matrix from three `[x,y,z]` triples.
4. `multiply(a, b)` → `a * b` (both column-major `Float32Array(16)`), returns a new `Float32Array(16)`.
5. `translationScale(tx, ty, tz, sx, sy, sz)` → model matrix combining translation and non-uniform scale, **no rotation** (mirrors the existing 2D `scaleX/scaleY/tx/ty` inline construction, extended to 3 axes). Kept only for callers that genuinely never rotate — most 3D callers need task 7's `compose` instead.
6. `rotationXYZ(rx, ry, rz)` → rotation matrix from Euler angles in radians. **Fix the composition order and document it in a code comment**: intrinsic rotation about Z, then Y, then X (the returned matrix is `Rx · Ry · Rz` applied to a column vector — roll, then pitch, then yaw). Every consumer of Euler rotation in this task — Step 9 sockets, Step 11 keyframes, Step 12 action clips — must use this exact convention; do not let any later step invent its own order.
7. `compose(position, rotationEuler, scale)` → the general-purpose TRS (translate · rotate · scale) model matrix, combining a translation, `rotationXYZ(...)`, and a scale matrix in that order. This is what actually gets used wherever a `transform3d`/socket/keyframe with position **and** rotation needs to become a matrix — `translationScale` alone cannot represent a rotated socket or an animated spin, and no later step should hand-roll a substitute.
8. Export all seven as named functions (no default export, no class wrapper — match the functional style of `gpuBuffers.js`).

Verify: no visual change yet — this module has no callers.

---

## Step 3 — 3D Camera on the `camera` Object ✅

**File:** `frontend/js/engine/renderer.js`

Tasks:

1. Extend the `camera` object with optional 3D fields, all defaulting so existing 2D behaviour is untouched:
   - `mode`: `'2d'` (default) or `'3d'`
   - `position`: `[x, y, z]` (world-space eye position, 3D mode only)
   - `target`: `[x, y, z]` (look-at point, 3D mode only)
   - `up`: `[x, y, z]` (default `[0, 1, 0]`)
   - `fov`: vertical FOV in radians (default e.g. `Math.PI / 4`)
   - `near`, `far`: clip planes
2. Add a `getViewProjectionMatrix(camera, aspect)` function: when `camera.mode === '3d'`, returns `multiply(perspective(...), lookAt(...))` from `mat4.js`; when `'2d'`, return `null` (callers keep using the existing inline 2D MVP construction — do not reroute the 2D path through this function).
3. Do not change the render loop's pass/encoder structure — this step only adds camera data and a matrix helper, no new draw calls yet.

Verify: log `getViewProjectionMatrix` output in the browser console for a manually-set 3D camera; confirm it's a plausible `Float32Array(16)` (identity-ish when eye is far down +z looking at origin).

---

## Step 4 — Billboarded Sprites in 3D Space ✅

**File:** `frontend/js/engine/entityRenderer.js`

Implement the billboard technique described in `COORDINATE_MAPPING.md`: a sprite quad whose model matrix is built from the camera's right/up vectors rather than a fixed 2D orientation, so 2.5D sprites can exist in a 3D world without needing per-entity meshes.

Tasks:

1. Add a `drawEntity3D(entity, camera, passEncoder)` path, used when `camera.mode === '3d'` and the entity's resolved render definition (via `render_template`, see Step 5) has no `mesh` field — i.e., it's a billboarded sprite. An entity with no `render_template` at all also falls here, unaffected by this task's mesh work.
2. Derive camera right/up vectors from the view matrix (right = view matrix row 0, up = row 1, transposed appropriately — verify against `lookAt`'s output convention from Step 2).
3. Build the model matrix so the quad's plane is spanned by `right * entity.size[0]` and `up * entity.size[1]`, centered/pivoted per the entity's existing `pivot` field, positioned at the entity's 3D world position.
4. Compute `mvp = viewProjection * model` and write it into the same 64-byte `mvp` slot in the uniform struct already used by Workflow A / the material path — the fragment shader and UV-rect logic are unchanged; only the vertex-side matrix differs.
5. Reuse the existing `getSpritePipeline()` / material pipeline and bind groups unchanged — billboards are still textured quads, just with a 3D model matrix instead of the 2D one.

Verify: place a sprite entity with a 3D `position` in a scene using a 3D camera. It should render as a flat sprite that always faces the camera as the camera orbits, at the correct world depth relative to other billboards (nearer billboards render in front — depth testing may need enabling on the pipeline if not already on).

---

## Step 5 — Minimal Textured Mesh Path ✅

**New file:** `frontend/js/engine/mesh.js`

A static (non-animated) textured mesh path for actual 3D assets, reusing the existing material combiner fragment shaders.

### Mesh data format

**New directory:** `frontend/assets/data/mesh/`
**File path:** `frontend/assets/data/mesh/mesh-<name>.json`

```json
{
  "id": "mesh-crate-001",
  "name": "wooden_crate",
  "vertices": [
    { "pos": [x, y, z], "normal": [x, y, z], "uv": [u, v], "color": [r, g, b, a] }
  ],
  "indices": [0, 1, 2, 2, 1, 3]
}
```

`color` is optional per vertex — omit it entirely for a mesh that never uses vertex-color tinting (Step 8). Loaded vertices missing `color` default to `[1, 1, 1, 1]` (a no-op multiply), so the field's presence is purely opt-in and doesn't affect meshes that don't use it.

Keep this format minimal and project-specific — it is not a glTF subset and does not need to become one. Step 6 adds a narrow build-time tool that converts glTF exports into this format; nothing else authors it directly.

### Tasks:

1. `class Mesh` in `mesh.js`:
   - `constructor(device)`
   - `async load(meshJsonPath)` — fetches the JSON, packs `vertices` into an interleaved `Float32Array` (`pos.xyz, normal.xyz, uv.xy, color.rgba` = 12 floats/vertex; fill `color` with `[1,1,1,1]` for any vertex that omits it), uploads as a `GPUBuffer` (`VERTEX | COPY_DST`), uploads `indices` as a `GPUBuffer` (`INDEX | COPY_DST`, `Uint16Array` if index count allows, else `Uint32Array`).
   - `get vertexCount()` / `get indexCount()`.
2. Add a vertex buffer layout constant (`attributes`: position `@location(0)`, normal `@location(1)`, uv `@location(2)`, color `@location(3)`) exported alongside `Mesh` for `ShaderCache` to reference. The `'mesh'` pipeline variant (Step 5) reads `color` unconditionally as an attribute; whether the fragment shader *uses* it is gated by the `vertex_color` material flag added in Step 8 — an unset flag means the attribute is present but ignored, not absent.

**File:** `frontend/js/engine/sprites/shaderCache.js`

3. Add a `'mesh'` pipeline variant:
   - Vertex shader: takes `pos: vec3<f32>`, `normal: vec3<f32>`, `uv: vec2<f32>`, **and `color: vec4<f32>`** (the Step 5 task 2 attribute at `@location(3)` — declare it as an input even though nothing reads it until Step 8); applies `mvp` (from Step 4's matrix path); passes `uv` **and `color`** through as varyings for the fragment stage, unchanged, for the existing Workflow A/C fragment shaders to sample. Skipping `color` here would leave Step 8's vertex-color tint with no varying to read.
   - Reuse `FS_BASE` (or `FS_RAMP`/`FS_HUE` if the entity's material requests it) unchanged — the combiner doesn't care whether UVs came from a sprite atlas rect or a mesh's authored UVs.
   - Uses indexed draws: `passEncoder.setIndexBuffer(...)` + `passEncoder.drawIndexed(indexCount)` instead of `passEncoder.draw(6)`.

**File:** `frontend/js/engine/entityRenderer.js`

4. Entities whose resolved render definition has a `mesh` field (mesh JSON path, resolved via `assetLoader`; the definition itself is reached via `render_template`, task 8 below) route to a `drawEntityMesh(entity, camera, passEncoder)` path: build `mvp` via `mat4.compose([entity.x, entity.y, entity.z], entity.transform3d.rotation, entity.transform3d.scale)` (Step 2) combined with the camera's view-projection — **position comes from the entity's own existing `x`/`y`/`z` (already per-instance, already networked via `PositionComponent`), never from the definition file; only rotation/scale come from `transform3d` (task 7 below)** — bind the mesh's vertex/index buffers, bind the entity's existing material bind group (albedo/param map/sampler are still 2D textures — a mesh just needs UVs that land somewhere sensible on them), and issue `drawIndexed`. Task 8 resolves `render_template` before this routing decision is made, even though it's described later in this step for narrative flow — implement the resolution first.
5. Entities with no `render_template`, or whose resolved definition has no `mesh`, continue through the existing 2D path or the Step 4 billboard path, unchanged.

**File:** `docs/graphics/DATA_STRUCTURES.md`

6. Document the new optional entity-**definition** field (on the `frontend/assets/data/entity/entity-<uuid>.json` schema — this is a template, not what's sent over the network, and it carries **no placement data** — a template describes what something looks like, never where it is):
   - `mesh`: `string | null` — asset key for a mesh JSON file

### Resolving which definition a networked entity uses, and where it's placed (`render_template` + `transform3d`)

Per Step 1 task 4, a networked ECS entity carries no reference to its `entity-<uuid>.json` definition at all today — nor any rotation/scale (only `x`/`y`/`z` position exists, via `PositionComponent`). This step adds both missing links as per-**instance** fields — additive, and scoped narrowly (following an existing pattern), which is why it's the one Constraints exception besides Step 12.

**Get this distinction right, it matters:** `render_template` says *what a placed entity looks like* (shared across every instance using the same template). `transform3d` says *how this one instance is rotated/scaled* (never shared — two placed copies of the same crate template must be independently rotatable). Neither belongs on the other's file. A definition file with a baked-in `transform3d` would mean every copy of that template renders identically rotated, which defeats the purpose of placing more than one.

**File:** `backend/engine/ecs/entity.py`

7. Add two plain attributes to `Entity`, following the exact same pattern as the existing `race`/`model_version` attributes — included in the constructor, `serialize()`, `to_dict()`, and `from_dict()`:
   - `render_template: Optional[str] = None` — `None` means "no 3D render definition" (2D/legacy resolution, whatever that currently is, is untouched). Deliberately a new, generic field rather than overloading `race`/`model_version` — those are character-appearance-specific; `render_template` needs to work for non-character props (a placed crate, a staff) too.
   - `transform3d: Optional[dict] = None` — `{ "rotation": [x,y,z], "scale": [x,y,z] }`, `None` meaning identity rotation and `[1,1,1]` scale. **No `position` key** — position is already `x`/`y`/`z`, don't duplicate it here.

**File:** `frontend/js/engine/entityRenderer.js`

8. Before routing to `drawEntityMesh`/`drawEntity3D`/2D drawing, resolve `entity.render_template` (if set) via `assetLoader.resolve()` — this key resolves against the `"entities"` manifest category added in Step 7 — fetch the referenced `entity-<uuid>.json` once and cache it, and use *its* `mesh`/`parts`/`material_id` fields to decide the render path — the networked entity supplies position (`x`/`y`/`z`), rotation/scale (`transform3d`), state, and `render_template`; the definition file supplies everything about how it looks, nothing about where. An entity with no `render_template` falls back to whatever resolution already exists today (out of scope to change here).

Verify: author one example mesh (a textured cube or plane is enough — see whether `frontend/assets/data/mesh/mesh-example-crate.json` makes sense as the example, mirroring the existing `entity-example-lantern.json` convention) and one entity-definition JSON referencing it via `mesh` only. Place **two** networked entities with the same `render_template` at different `x`/`y`/`z` and different `transform3d.rotation` — confirm both render as independently positioned and rotated copies of the same mesh, proving placement genuinely is per-instance. (The `"entities"` manifest category this depends on lands in Step 7 — this step's manual verify can register the one test file by hand if run before Step 7 is implemented.)

---

## Step 6 — Mesh Authoring Pipeline: Blender/glTF → Project JSON ✅

**New file:** `tools/convert_mesh.py`

Bridges an artist working in a real DCC tool to the Step 5 mesh JSON format, following the same "small, explicit, stdlib-only preprocessing script" pattern as `tools/pack_param_map.py` and `tools/build_manifest.py` — not a general-purpose 3D asset importer.

### Authoring workflow (for whoever is modeling)

1. Model in Blender (or any glTF-exporting tool), keeping to low-poly triangle budgets.
2. To use the `vertex_color` stylization hook (Step 8), paint vertex colours in Blender's Vertex Paint mode before export.
3. Export **glTF 2.0** (`.gltf` + `.bin`, or single-file `.glb`) — not OBJ. glTF has a standard `COLOR_0` vertex attribute; OBJ doesn't reliably carry vertex colour across tools. In Blender's glTF export options, disable skinning/armatures/shape keys/animations — this converter refuses meshes that use them (task 6 below).
4. Run `python tools/convert_mesh.py <input.gltf|.glb> -o frontend/assets/data/mesh/mesh-<name>.json`.

### `convert_mesh.py` tasks

1. Parse the input with the standard library only (`json`, `struct` — no new `pip` dependency, per the Constraints section):
   - `.glb`: a 12-byte binary header followed by a JSON chunk and an optional binary buffer chunk, per the glTF binary container spec.
   - `.gltf` + `.bin`: parse the JSON directly; load the referenced `.bin` file (or decode a base64 data-URI buffer) as raw bytes.
2. Only support `meshes[0].primitives[0]`. If the file contains more than one mesh, more than one primitive, or a primitive whose `mode` isn't `4` (`TRIANGLES`), raise a clear error naming the unsupported feature — never guess or silently drop geometry.
3. For `POSITION`, `NORMAL`, `TEXCOORD_0`, and optional `COLOR_0` in `primitives[0].attributes`, resolve the accessor → bufferView → buffer chain and unpack with `struct` per the accessor's `componentType`/`type` (e.g. `FLOAT` `VEC3`). `COLOR_0` may be `VEC3`/`VEC4` and normalized `UNSIGNED_BYTE`/`UNSIGNED_SHORT` — normalize to `[0,1]` floats per the glTF spec; a mesh with no `COLOR_0` gets `color: [1,1,1,1]` on every vertex, matching Step 5's default.
4. Resolve the `indices` accessor the same way (`UNSIGNED_BYTE`/`UNSIGNED_SHORT`/`UNSIGNED_INT`).
5. Assemble the Step 5 mesh JSON shape (`id`, `name` from the input filename stem, `vertices` zipping position/normal/uv/color per index, `indices`) and write it to the `-o` path.
6. Refuse — raise, don't warn — on skins, morph targets, sparse accessors, or extra primitives/meshes. These are unsupported, not silently mishandled.

Verify: export a vertex-painted textured cube from Blender as glTF, run the converter, and confirm the output JSON loads via Step 5's `Mesh.load()` without errors, with vertex/index counts matching what Blender reports for the mesh.

---

## Step 7 — Manifest Registration for Meshes and Entity Definitions ✅

**File:** `tools/build_manifest.py`

Meshes and entity-definition files (`frontend/assets/data/entity/*.json`, whose new `render_template`-resolved role Step 5 depends on) currently have no place in the asset manifest — `build_manifest()` only scans `images/`, `data/animation/`, `data/material/`, and `audio/`. Extend it so both asset types resolve through `AssetLoader` like every other asset type instead of needing hardcoded paths.

Tasks:

1. Add a `mesh_dir = ASSETS_DIR / "data" / "mesh"` scan mirroring the existing `anim_dir`/`mat_dir` blocks: walk `*.json` files, skip `example_*` files, extract the id via the existing `json_asset_id()` helper, and populate a new top-level `"meshes"` dict (`{path, hash}` per entry, same shape as `"animations"`/`"materials"`).
2. Add an `entity_dir = ASSETS_DIR / "data" / "entity"` scan, identical in structure, populating a new top-level `"entities"` dict — this is what Step 5's `render_template` field resolves against.
3. Include `"meshes"` and `"entities"` in the summary line printed by `main()`.

**File:** `frontend/js/engine/assetLoader.js`

4. Add `"meshes"` and `"entities"` to the `categories` array in `loadManifest()` (currently `["images", "animations", "materials", "audio"]`) so mesh and entity-definition asset keys resolve through `assetLoader.resolve()` the same way as everything else.

**File:** `tools/build_assets.py`

5. Optional: add a `_validate_meshes()` step mirroring `_validate_animations()` (checks for `id`/`vertices`/`indices` keys, warns without aborting the build) and wire it into `main()`'s numbered step sequence. Not required if manifest registration alone meets the current need.

Verify: after adding a mesh JSON under `frontend/assets/data/mesh/` (e.g. the output of Step 6, or the Step 5 example) and an entity-definition JSON under `frontend/assets/data/entity/`, run `python tools/build_assets.py` (or `build_manifest.py` directly) and confirm `manifest.json` gains both a `"meshes"` and an `"entities"` entry; in the browser console, confirm `assetLoader.resolve('<mesh-id>')` and `assetLoader.resolve('<entity-definition-id>')` both return the correct paths.

---

## Step 8 — Optional Stylization Hooks (opt-in, not the default) ✅

These are additive knobs layered on top of the Step 5 mesh path, each gated by an explicit flag so a mesh/material/scene that sets none of them renders exactly as Step 5 left it. They happen to be the ingredients of a low-poly N64 look (affine texture warp, vertex-lit Gouraud shading, distance fog, banded colour), but are named generically — `vertex_color`, `affine_uv`, `color_levels`, scene `fog*` — rather than bundled as an `"n64_mode"` switch, so any future style can pick individual ones à la carte or ignore all of them.

**File:** `frontend/js/engine/sprites/shaderCache.js`

1. Extend the `'mesh'` fragment shader with independent, uniform-gated branches (prefer runtime uniform checks over separate pipeline permutations unless profiling later shows a need):
   - **Vertex-color tint** — multiply albedo by the interpolated per-vertex `color` attribute (now correctly threaded through as a varying per Step 5's fix) when `material.vertex_color === true`; otherwise multiply by `vec4(1,1,1,1)` (no-op, same output as no `color` data at all).
   - **Distance fog** — mix the fragment colour toward a `fog_color` uniform by a factor derived from view-space depth, only when `fog_far > 0`. Default `fog_far: 0` disables the branch's effect entirely — verify it's a true no-op, not just a zero-strength blend that still costs a lerp.
   - **Colour quantisation** — `floor(color * levels) / levels` per channel when `material.color_levels > 0`; `0` (default) leaves colour continuous/unquantized.
   - **Ambient tint** — multiply the final colour by an `ambient_color` uniform, default `vec3(1,1,1)` (no-op). This is the consumer for the `lighting.ambientColor` field the Area/Scene system authors — see `.github/prompts/area-system.prompt.md` Step 3, which merges its `lighting.ambientColor`/fog fields onto this same runtime object at load time. Without this task, that field would be authored data with nothing reading it.

**File:** `frontend/js/engine/mesh.js` or `entityRenderer.js` (wherever the mesh draw path's UVs/varyings are set up)

2. **Affine UV toggle** — when `material.affine_uv === true`, interpolate UVs without perspective correction (the classic N64 texture-warp artifact from cheap linear interpolation across a triangle in screen space). Default `false` keeps standard perspective-correct interpolation, which is what WGSL gives you by default — implementing the affine path means deliberately working around that default (e.g. passing clip-space `w` through as a varying and doing a manual, non-corrected interpolation), not the other way around.

**File:** `frontend/js/engine/renderer.js`

3. Add optional `fogColor: [r,g,b]`, `fogNear: float`, `fogFar: float`, **and `ambientColor: [r,g,b]`** fields to the `camera`/scene object from Step 3, defaulting so `fogFar: 0` means fog is fully disabled and `ambientColor: [1,1,1]` means no tint. All four live on the same object (the `camera` object) specifically because that's the one runtime object the renderer already reads every frame — do not introduce a second per-frame uniform source.

**File:** `docs/graphics/DATA_STRUCTURES.md`

4. Document the new optional fields:
   - Material: `vertex_color: bool` (default `false`), `affine_uv: bool` (default `false`), `color_levels: int` (default `0` = off)
   - Camera/scene: `fogColor: [r,g,b]`, `fogNear: float`, `fogFar: float` (default `fogFar: 0` = off), `ambientColor: [r,g,b]` (default `[1,1,1]` = off)

Verify: with all flags left at their defaults, a Step 5 mesh entity must render identically to before this step. Then enable each flag individually, one at a time, on a copy of the test mesh/material and confirm only that one effect appears — vertex-color tint, distance fade-to-fog-color, texture warp under camera movement, colour banding, or ambient tint, respectively — with no interaction bugs when two are enabled together.

---

# ⚠️ SYSTEM CHANGE — Steps 9–14 target a different runtime than Steps 1–8

**Steps 1–8 above were built in the JS/WebGPU browser frontend** (`frontend/js/engine/*.js`, WGSL as JS template-literal strings, tested via `run_browser.py`/`run_desktop_test.py`+PyWebView) and that work is real, committed, and done — nothing above this banner should be reinterpreted or re-implemented in Python. It stands as-is, permanently, as the historical record of what was actually built.

**Steps 9–14 below target the native Python client instead** (`client/engine/*.py`, WGSL as Python triple-quoted strings, built on `wgpu-py` + GLFW), per this repository's decision to migrate off the PyWebView/browser client — see `.github/prompts/wgpu-py-migration.prompt.md` for the full rationale (WebKitGTK's incomplete Linux WebGPU support) and porting plan. This is a genuine runtime/language switch mid-task, not a renaming exercise:

- **File paths change**: `frontend/js/engine/entityRenderer.js` → `client/engine/entity_renderer.py`, `frontend/js/engine/dangle.js` → `client/engine/dangle.py`, `frontend/js/engine/transformClip.js` → `client/engine/transform_clip.py`, `frontend/js/engine/mesh.js`/`mat4.js`/`shaderCache.js` → `client/engine/mesh.py`/`mat4.py`/`shader_cache.py`.
- **Naming convention changes**: JS `camelCase` → Python `snake_case` for functions/methods (`drawEntityMesh` → `draw_entity_mesh`, `sampleTransformClip` → `sample_transform_clip`, `updateDangle` → `update_dangle`); class names stay `PascalCase` in both (`DangleState` is `DangleState` either way).
- **Style guide changes**: Steps 1–8's "JavaScript Airbnb style guide, 2-space indent, single quotes" constraint no longer applies to Steps 9–14 — they follow PEP 8 (4-space indent, 79-column lines), per `.github/prompts/wgpu-py-migration.prompt.md`'s own constraints.
- **A real prerequisite, not just a path change**: Steps 9–14 assume `client/engine/entity_renderer.py`, `mesh.py`, `shader_cache.py`, and `mat4.py` already exist and already cover the Step 1–8 JS feature set (billboards, the mesh path, stylization hooks) — i.e., that `wgpu-py-migration.prompt.md`'s Steps 4, 6, 8, and 9 have landed. If they haven't yet, that porting is a blocking dependency for Steps 9–14 here, not something to improvise inline. Check `wgpu-py-migration.prompt.md`'s own step checkmarks before starting Step 9 below.
- **WGSL shader text itself is unaffected** — WGSL doesn't change between a JS host and a Python host; only the string type wrapping it does (JS template literal → Python triple-quoted string). Do not re-derive or "improve" shader logic while crossing this boundary.
- **The backend (`backend/`) is unaffected by this switch** — it was already Python and stays exactly as Steps 1–8 left it. Step 12 below still edits `backend/game/entities/player.py`/`actions.py`/`tick.py` exactly as originally scoped; this banner only concerns the *client*.

---

## Step 9 — Multi-Part Meshes & Attachment Sockets

Lets one entity be built from more than one mesh, each positioned relative to a named anchor point on another part rather than the world. This is the foundation Step 10 (dangle) and Step 11 (transform clips) build on, and what a "staff with a separately-modeled hanging charm" actually needs — not a single rigid mesh, but a small parent/child chain.

**File:** `docs/graphics/DATA_STRUCTURES.md` (mesh schema)

1. Mesh JSON gains an optional top-level `sockets` array: `{ "name": string, "position": [x,y,z], "rotation": [x,y,z] }` — named local-space anchor points on that mesh. Omit entirely for meshes with no attachment points; no change to Step 5 behaviour.

**File:** `tools/convert_mesh.py`

2. Extend the converter, still within Step 6's "geometry attributes only, no general importer" constraint: alongside `meshes[0].primitives[0]`, scan the glTF `nodes` array for nodes that have a `name` but **no** `mesh` reference (a Blender "Empty" placed at an attachment point) and emit each as a socket using that node's local `translation`/`rotation`. This is metadata (names + transforms), not geometry/material/skin data, so it doesn't broaden the converter's scope — still refuse skins/morph targets/extra primitives exactly as Step 6 already does.

**File:** `docs/graphics/DATA_STRUCTURES.md` (entity-**definition** schema — same `entity-<uuid>.json` file Step 5's `mesh` field lives on, not the networked/Area-file entity; `render_template` is what a placed instance uses to reach this file)

3. Entity-definition JSON gains an optional `parts` array usable instead of the single `mesh` field:
   ```json
   "parts": [
     { "id": "shaft", "mesh": "mesh-staff-shaft" },
     { "id": "charm", "mesh": "mesh-staff-charm", "attachTo": { "part": "shaft", "socket": "charm_socket" }, "localOffset": { "position": [x,y,z], "rotation": [x,y,z], "scale": [x,y,z] } }
   ]
   ```
   Each part's world transform = the part named in `attachTo.part`'s world transform × that socket's local transform × the part's own `localOffset` (default identity, if present at all). A part with no `attachTo` composes directly off the **entity's** per-instance placement (`x`/`y`/`z` + `transform3d.rotation`/`transform3d.scale`, Step 5) — identical to a Step 5 single-mesh entity.

   **Naming note, deliberately not `transform3d`:** a part's `localOffset` is definition-level (the fixed relationship between two meshes of the same asset — "the charm hangs 0.3 units below this socket," true for every placed instance) and is a different concept from the per-instance `transform3d` Step 5 added to `Entity` (how *this one placement* is rotated/scaled). Reusing the same field name for both would make it easy to confuse "adjust this asset's internal composition" with "adjust where this copy is placed" — keep them visibly distinct.

**File:** `client/engine/entity_renderer.py` (the wgpu-py port of `entityRenderer.js` — see the system-change banner above; this must already exist, covering at least the Step 1–8 JS feature set, before this task proceeds)

4. Generalise `draw_entity_mesh` into `draw_entity_mesh_parts`: resolve `parts` in array order (a part may only reference an *earlier* part's `id` in `attachTo.part` — reject cycles and forward references at load time with a clear error, don't silently mis-render), compose each part's world matrix through its attachment chain via `mat4.multiply` (`client/engine/mat4.py`) — starting from the entity's own per-instance placement as the chain's root, per task 3 — and issue one indexed draw per part using its own mesh/material.
5. Entities with a plain `mesh` field (no `parts`) continue to render exactly as Step 5 left them — `parts` is additive, not a replacement.

Verify: a two-mesh staff (shaft + separately-modeled charm, charm's part attached to a socket exported from a Blender Empty on the shaft) renders with the charm correctly offset and oriented, and stays rigidly attached as the entity's position or `transform3d` (rotation/scale) changes. Place two staff instances at different positions with different rotations and confirm both render correctly and independently — not the same bug Step 5's fix just corrected, one level up the composition chain.

---

## Step 10 — Secondary-Motion "Dangle" Spring (cosmetic-only, not physics)

This is the client-side-only cosmetic simulation behind "a part that hangs and moves slightly as you move" — a hand-rolled spring-damper per dangling part. It is **not** rigid-body physics and does **not** touch the backend ECS/AABB collision system, which stays exactly as it is today, unaware this exists. This step exists specifically on the "frontend / cosmetic motion" side of `.github/copilot-instructions.md`'s "Physics & Simulation Boundary" — read that section before writing this file, and follow its naming rule: nothing here may be named or framed as "physics." That rule is language-agnostic — it applies just as much to `client/` Python as it did to `frontend/js/`.

**New file:** `client/engine/dangle.py`

0. At the top of the file, add a one-line comment (`#`, not `//` — this file is Python) pointing back to the "Physics & Simulation Boundary" section in `.github/copilot-instructions.md`, per that section's own rule for new cosmetic-motion systems.
1. `class DangleState`: per dangling part, holds `offset: [x,y,z]` and `velocity: [x,y,z]`, both starting at `[0,0,0]`.
2. `update_dangle(state, parent_delta_position, params, delta_time)` — explicit, hand-rolled, no physics library (matches `mat4.py`'s convention):
   - inertial kick: `velocity -= parent_delta_position * params.inertia` — the child resists the parent's sudden movement, which is what reads as "weight" swinging on the end of the staff.
   - optional gravity: `velocity += params.gravity * delta_time` if `params.gravity` is set.
   - spring back to rest: `velocity += -offset * params.stiffness * delta_time`.
   - damping: `velocity *= (1 - params.damping)`.
   - integrate: `offset += velocity * delta_time`.
   - clamp `offset`'s magnitude to `params.max_offset` (small default, e.g. `0.2` world units) so a teleport or network hiccup can't fling the part off-screen.

**File:** `docs/graphics/DATA_STRUCTURES.md` (extends Step 9's `parts[]` entry)

3. A `parts[]` entry gains an optional `dangle: { stiffness, damping, gravity: [x,y,z] | null, maxOffset }` block. Absent = perfectly rigid attachment, exactly Step 9's behaviour. This is a JSON schema field, unaffected by which client reads it — keep the JSON key names as documented (`camelCase`, matching every other field in this schema), even though the Python code that reads them uses `snake_case` locals.

**File:** `client/engine/entity_renderer.py`

4. In `draw_entity_mesh_parts`, a part with `dangle` set gets a cached `DangleState` (keyed by entity id + part id, alongside where material handles are already cached), updated once per render frame from that part's attachment point's frame-to-frame world position delta, with its `offset` added to the part's local translation before composing into the attachment chain.

Verify: attach a dangle-enabled charm to a moving/turning entity's staff — it should visibly lag and swing rather than snapping rigidly, and settle back toward rest within a couple of seconds of the entity going idle. A dangle part on a stationary entity should sit at zero steady-state offset, not drift.

---

## Step 11 — Transform Animation Clips for Mesh Parts

Generalises "model animation" to authored, repeating motion — a spinning coin, a bobbing crate lid — reusing the existing clip-JSON pattern already used for sprite overlay animations, but interpolating a transform instead of a frame index.

**New file:** `frontend/assets/data/animation/animation-transform-<name>.json` (schema, documented in `DATA_STRUCTURES.md`)

```json
{
  "id": "anim-coin-spin",
  "type": "transform",
  "loop": true,
  "keyframes": [
    { "time_ms": 0,    "rotation": [0, 0, 0] },
    { "time_ms": 1000, "rotation": [0, 6.283, 0] }
  ]
}
```

1. Extend the animation clip schema with `"type": "transform"` alongside the existing frame-based clips; `keyframes` interpolate any subset of `position`/`rotation`/`scale` linearly between entries (omitted fields hold the part's rest value), looping per `loop`.

**New file:** `client/engine/transform_clip.py`

2. `sample_transform_clip(clip, time_ms)` → `{ position, rotation, scale }`, linearly interpolating between the two bracketing keyframes — matching the same hand-rolled, no-library interpolation style `RENDER_WORKFLOWS.md` Workflow E's `lerpPreset` established for the JS side (that function itself is JS and stays JS — this is about matching its *style*, explicit and dependency-free, in the Python port, not porting `lerpPreset` literally).

**File:** `client/engine/entity_renderer.py`

3. A `parts[]` entry gains an optional `animation_id` (a transform clip id). `draw_entity_mesh_parts` advances a per-part clock, samples the clip, and applies the result as an additional local transform layered **before** the Step 10 dangle offset — a part can play an authored spin and wobble from motion at the same time; they compose rather than conflict.
4. A part with neither `dangle` nor `animation_id` renders exactly as Step 9 left it.

Verify: a coin-shaped part with the spin clip rotates continuously regardless of entity movement; adding a `dangle` config to the same part makes it both spin and sway.

---

## Step 12 — Action-Triggered Animation Playback (attack, jump, etc.)

One-shot animations fired by a discrete player/AI action — "swing the weapon," "jump" — rather than the continuous state-driven walk/idle animation or Step 11's looping transform clips. This is the one step in this task that legitimately touches backend Python (see Constraints): *who* is attacking and *when* is a server-authoritative fact, so how long the swing "lasts" has to be too, or clients desync. The backend was already Python before the system-change banner above and stays exactly as originally scoped — this step's backend tasks (1–4) are unaffected by the client's JS→Python switch; only tasks 5–6 (client-side) target `client/engine/` now instead of `frontend/js/engine/`.

**File:** `backend/game/entities/player.py` and `backend/game/systems/actions.py`

Read both fully first — they are two parallel, not-fully-consistent action-handling paths, and both currently set `entity.state = "attacking"`/`"using_item"`/`"interacting"` on action execution with **no** existing mechanism that ever reverts it back to `"idle"`/`"moving"`.

1. Add a small `ACTION_DURATIONS` constant (milliseconds) per action state, e.g. `{"attacking": 400, "using_item": 300, "jumping": 500}` — a placeholder table, not full per-weapon data-driven timing (that can layer on top later via the entity's equipped item once such data exists).
2. Record when the action state started (`entity.state_started_at`, a `time.monotonic()` or tick-count timestamp) whenever `entity.state` is set to one of these values.
3. Add a `"jump"` action type to `ActionFactory`/`execute_action` (today only `move`/`attack`/`use_item`/`interact` exist), setting `entity.state = "jumping"` the same way as the existing actions.

**File:** `backend/game/tick.py`

4. Each tick, for any entity whose `state` is a key in `ACTION_DURATIONS` and whose elapsed time since `state_started_at` exceeds that duration, revert `state` to `"idle"` or `"moving"` (based on current velocity, matching the logic the `move` action already uses) and mark the entity dirty. This reuses the existing `state_update` delta broadcast — no new SocketIO message type — the reversion just looks like any other state change to the client.

**File:** `client/engine/entity_renderer.py` (sprite/billboard path)

5. Extend the existing `entity.state` → animation-name mapping (today: `stand`/`walk`) with one-shot entries for `attacking`/`jumping`/`using_item`, each backed by a `loop: false` clip (already supported by the clip schema's existing `loop` field — no schema change needed). `AnimationController.play()` (the `client/engine/animation.py` port of `animation.js`, per `wgpu-py-migration.prompt.md` Step 7 — class name stays `AnimationController` in the port, only its own method bodies became `snake_case`) already resets to frame 0 on a genuine animation switch and no-ops if already playing the same clip, so wiring the mapping is the only change needed — when the backend reverts `state` (task 4), the next `state_update` naturally switches the client back to `stand`/`walk`.

**File:** `client/engine/entity_renderer.py` (mesh path, using Step 11's `sample_transform_clip`)

6. A `parts[]` entry gains an optional `action_animations: { attacking: "anim-sword-swing", jumping: "anim-jump-arc" }` map (transform clip ids). When `entity.state` transitions into one of these keys, start a one-shot playback (ignore the clip's own `loop` field — action playback is always one-shot) layered on top of the Step 9 attachment chain; when `state` reverts, fall back to the part's regular `animation_id` (Step 11) if set, or its rest transform.
7. Action clips, Step 11's looping clips, and Step 10's dangle offset all compose additively — a sword swing plays while a tassel on the hilt keeps dangling.

Verify: triggering an attack (`player_action: {type: 'attack'}`) plays the one-shot swing animation exactly once on both a sprite character and a mesh weapon part, then automatically returns to idle/walk without the client sending any explicit "stop attacking" message. Triggering a jump behaves the same way with its own duration.

---

## Step 13 — Update Documentation Status

**File:** `docs/graphics/COORDINATE_MAPPING.md`

Once Steps 2–12 are implemented and verified, update the "2.5D / 3D (Future)" heading to reflect what's now implemented vs. still planned (mirror the ✅ checklist style used in `OVERVIEW.md`'s migration path). Note explicitly that: Step 8's hooks are optional, independently-toggleable stylization flags, not the mesh path's default rendering behaviour; Step 6's glTF support is a build-time authoring convenience, not a runtime import feature; Step 10's dangle system is a cosmetic client-side spring, not a physics engine; and Step 12 is the only step that touches backend Python, scoped narrowly to action-duration timing. Do not claim completeness beyond what was actually built and verified — e.g., if rotation transforms weren't exercised, say so.

Also note explicitly, per the system-change banner above Step 9: Steps 1–8 live in the JS/WebGPU browser client (`frontend/js/engine/`), Steps 9–12 live in the native Python client (`client/engine/`) — this feature is split across two different client codebases, not implemented twice or migrated wholesale. State which client each documented capability actually lives in rather than describing "the renderer" as a single undifferentiated thing.

---

## Step 14 — Smoke Test

Per the system-change banner above, this task's smoke test is now genuinely two separate passes against two different clients — do not conflate them, and do not consider Steps 9–12 "verified" just because the JS pass below already passed (it covers Steps 1–8 only).

### Pass A — Steps 1–8 (JS/WebGPU browser client)

Run using `run_browser.py`/`run_desktop_test.py` for DevTools access:

```text
python run_browser.py
```

Status honestly reflects what's actually been confirmed in-browser as of this edit, not what's merely been implemented and self-reviewed — several Step 8 items are implemented and passed self-review (matrix-balance checks, hand-traced WGSL) but not yet re-confirmed visually after the most recent fog fix, so they stay unchecked:

- [x] Steps 1–7 (2D-path regression, billboard facing/occlusion, mesh perspective/rotation, `render_template`/two-independent-instances, glTF-converted mesh via `tools/convert_mesh.py`, `manifest.json` `"meshes"` resolution) — visually confirmed in the desktop client.
- [ ] Step 8: `ambientColor` visibly tints a mesh; `[1,1,1]` is a no-op — implemented, not yet visually re-confirmed.
- [ ] Step 8: a mesh entity with `vertex_color`/`affine_uv`/`color_levels` unset and scene `fogFar: 0` renders identically to one where those fields are absent entirely — implemented, not yet visually re-confirmed.
- [ ] Step 8: enabling `vertex_color`, `affine_uv`, `color_levels`, and fog individually each produces only its own visual effect; enabling two together doesn't misbehave — `affine_uv` and fog specifically each went through a real bug-then-fix cycle (a mismatched `@interpolate` type between the vertex output and fragment input that invalidated the whole pipeline and blanked the frame, then a fog-distance calculation that produced no visible fog at all) and need a fresh look, not just a re-read of the fix.
- [x] Depth ordering between a billboard and a mesh is correct (confirmed during Step 4).
- [ ] No `GPUValidationError`/WGSL pipeline-creation error in the console — true as of the last fix, needs reconfirming against the current code after the fog rewrite.

### Pass B — Steps 9–12 (native Python `client/` — not yet run)

Once `client/main.py` exists (`wgpu-py-migration.prompt.md` Step 15), run it and confirm — socket/part/dangle/clip mechanics carried over unchanged from the design above, just in the Python client instead of the browser:

- [ ] A multi-part staff entity (shaft + socket-attached charm) renders correctly, with the charm following the shaft rigidly when no `dangle` is set.
- [ ] Giving the charm part a `dangle` config makes it lag/swing during movement and settle at rest when idle, without affecting any other entity.
- [ ] A part with a looping `animation_id` (Step 11) animates continuously and independently of entity movement.
- [ ] Triggering `attack` plays a one-shot swing animation once on both a sprite entity and a mesh part entity, then automatically returns to idle/walk with no explicit "stop" message from the client.
- [ ] Triggering `jump` behaves the same way with its own duration and does not interfere with a concurrent `dangle` or looping `animation_id` on the same entity's parts.
- [ ] No `wgpu` validation error in the console/log during any of the above.
- [ ] No lint/type errors on any modified/new file under `client/engine/`.

---

## Success Criteria

- [ ] `frontend/js/engine/mat4.js` — `identity`, `perspective`, `lookAt`, `multiply`, `translationScale`, `rotationXYZ`, `compose`; documented Z-then-Y-then-X Euler order; no external math library
- [ ] `frontend/js/engine/renderer.js` — `camera.mode`/`position`/`target`/`up`/`fov`/`near`/`far`/`fogColor`/`fogNear`/`fogFar`/`ambientColor` fields; `getViewProjectionMatrix()`; 2D path untouched when `mode` is `'2d'` or unset
- [ ] `frontend/js/engine/entityRenderer.js` (JS, Step 4, done) — `drawEntity3D` (billboards) added; `render_template` resolution added ahead of mesh/2D routing; existing 2D/material paths unchanged for entities without `render_template`
- [ ] `client/engine/entity_renderer.py` (Python, Step 9, not started) — `draw_entity_mesh_parts` (static/multi-part meshes) added on top of the ported `draw_entity_mesh`, once `wgpu-py-migration.prompt.md`'s port of `entityRenderer.js` exists
- [ ] `frontend/js/engine/mesh.js` — `Mesh` class; interleaved vertex + index buffer upload including optional per-vertex `color`
- [ ] `frontend/js/engine/sprites/shaderCache.js` — `'mesh'` pipeline variant added, with `color` correctly threaded from vertex attribute through to a fragment varying, and independent `vertex_color`/`affine_uv`/`color_levels`/fog/ambient branches; existing variants (`base`, `overlay`, `ramp`, `hue`) untouched
- [ ] `frontend/assets/data/mesh/` — new directory with at least one example mesh JSON
- [ ] `tools/convert_mesh.py` — parses `.gltf`/`.glb` (stdlib only, no new pip dependency) and emits the Step 5 mesh JSON format plus Step 9 sockets; refuses (doesn't silently mishandle) skins/morph targets/multiple primitives
- [ ] `tools/build_manifest.py` — `"meshes"` **and `"entities"`** categories scanned and included in the manifest and build summary
- [ ] `frontend/js/engine/assetLoader.js` — `"meshes"` **and `"entities"`** added to `loadManifest()`'s `categories`
- [ ] `backend/engine/ecs/entity.py` — `render_template` **and** `transform3d` (`{rotation, scale}`, no `position` key) fields added to `serialize()`/`to_dict()`/`from_dict()`, following the `race`/`model_version` pattern exactly; both `None` by default, no other `Entity` behaviour changed; `transform3d` never appears on the entity-definition file
- [ ] Two entities sharing one `render_template` render as independently positioned and rotated copies — the concrete proof `transform3d`/position are per-instance, not baked into the shared definition
- [ ] Entity-definition `parts[]` array (Step 9) with `attachTo`/`localOffset`, `dangle` (Step 10), `animation_id` (Step 11), and `action_animations` (Step 12) all implemented as independently opt-in fields
- [ ] `client/engine/dangle.py` (Python, Step 10) — `DangleState`/`update_dangle`; no physics-engine dependency; no backend involvement; no "physics"-named identifiers anywhere in the file; opening comment points to the "Physics & Simulation Boundary" section in `.github/copilot-instructions.md`
- [ ] `client/engine/transform_clip.py` (Python, Step 11) — `sample_transform_clip`; hand-rolled linear interpolation, no new dependency
- [ ] `backend/game/entities/player.py`, `backend/game/systems/actions.py`, `backend/game/tick.py` — `ACTION_DURATIONS`, `state_started_at`, per-tick auto-revert, and a new `"jump"` action type; no other backend behaviour changed
- [ ] `docs/graphics/DATA_STRUCTURES.md` — `mesh` sockets, entity `parts`, `render_template`, the Step 8 stylization fields (including `ambientColor`), and the Step 10/11/12 part-level fields all documented
- [ ] `docs/graphics/COORDINATE_MAPPING.md` — 2.5D/3D section updated to reflect actual implementation status, noting stylization hooks are opt-in, glTF support is build-time-only, dangle is cosmetic-only, Steps 5/12 are the only backend touch-points, and — per the system-change banner above Step 9 — that Steps 1–8 live in `frontend/js/engine/` (JS/WebGPU browser client) while Steps 9–12 live in `client/engine/` (native Python client)
- [ ] No entity lacking `render_template`, `mesh`, `transform3d`, or 3D `camera.mode` renders any differently than before this task
- [ ] No mesh/material lacking the Step 8 flags renders any differently than it did at the end of Step 5 — stylization is strictly additive and opt-in
- [ ] No part lacking `attachTo`/`dangle`/`animation_id`/`action_animations` renders or behaves any differently than a plain Step 5 single-mesh entity
- [ ] No existing action (`move`, `attack`, `use_item`, `interact`) behaves differently to a client that ignores animation entirely — the backend state machine's game-logic effects (unchanged) are separate from its new animation-timing side effect (additive)
