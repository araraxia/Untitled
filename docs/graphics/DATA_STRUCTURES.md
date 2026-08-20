# Graphics System — Data Structures

JSON schemas used by the material/animation pipeline. All live under `frontend/assets/data/`.

Asset keys (plain string values such as `"lantern_atlas"` or `"lantern_params"`) are resolved to file paths at runtime by `AssetLoader` (`frontend/js/engine/assetLoader.js`). Game code and material JSON never reference raw file paths directly — always use the registered key.

---

## Animation Clip

**File path:** `frontend/assets/data/animation/animation-<uuid>.json`

An animation clip defines a sequence of atlas frames and their timing. The clip does **not** know anything about position, scale, or material — it is purely a list of frames and durations.

**Field reference:**

| Field | Type | Description |
| --- | --- | --- |
| `id` | `string` (UUID) | Unique identifier for this clip |
| `name` | `string` | Human-readable name |
| `type` | `string` | Clip category (e.g. `"body"`, `"effect"`, `"overlay"`) |
| `atlas` | `string` | Key referencing the atlas PNG this clip samples from |
| `frame_size` | `[w, h]` | Pixel dimensions of a single frame |
| `frames` | `array` | Ordered list of frame definitions |
| `frames[].index` | `int` | Linear frame index into the atlas (row-major) |
| `frames[].duration_ms` | `int` | Display time in milliseconds |
| `loop` | `bool` | Whether the clip loops back to frame 0 on completion |

**Directional variants:** For characters that face 4 or 8 directions, store each direction as a separate clip and reference them from the entity's `animations` map by direction key (e.g. `"walk_n"`, `"walk_ne"`, etc.).

**Example — lantern glow pulse** (`animation-example-lantern-glow.json`):

```json
{
  "id": "11111111-0000-0000-0000-000000000001",
  "name": "lantern_glow_pulse",
  "type": "overlay",
  "atlas": "glow_pulse_atlas",
  "frame_size": [32, 32],
  "frames": [
    { "index": 0, "duration_ms": 120 },
    { "index": 1, "duration_ms": 180 },
    { "index": 2, "duration_ms": 300 },
    { "index": 3, "duration_ms": 180 },
    { "index": 4, "duration_ms": 120 }
  ],
  "loop": true
}
```

See example file: [`frontend/assets/data/animation/animation-example-lantern-glow.json`](../../frontend/assets/data/animation/animation-example-lantern-glow.json)

---

## Material

**File path:** `frontend/assets/data/material/material-<uuid-or-name>.json`

A material is the single source of truth for **how something is drawn**. It names the atlases, param maps, colour ramps, and overlay effects. Entity instances reference a material rather than duplicating this data.

**Field reference:**

| Field | Type | Description |
| --- | --- | --- |
| `id` | `string` | Unique identifier |
| `name` | `string` | Human-readable name |
| `atlas` | `string` | Key → atlas PNG for the base animation |
| `param_map` | `string \| null` | Key → RGBA param map PNG (`null` if not used) |
| `color_ramp` | `object \| null` | Colour remapping definition (see sub-fields below) |
| `overlays` | `array` | List of secondary overlay definitions |
| `overlays[].type` | `string` | `"animation"`, `"static"` |
| `overlays[].animation_id` | `string` | UUID of the overlay animation clip |
| `overlays[].blend_mode` | `string` | `"additive"` or `"alpha"` |
| `overlays[].intensity` | `float` | Default blend strength (can be overridden at runtime via entity state) |
| `vertex_color` | `bool` | 3D mesh only (Step 8 stylization hook) — tint by the mesh's per-vertex `color` attribute. Default `false`: renders as if no vertex colour existed, byte-identical to omitting the field. Has no effect on 2D sprite entities. |
| `affine_uv` | `bool` | 3D mesh only (Step 8) — interpolate UVs without perspective correction (the N64 texture-warp look). Default `false`: standard perspective-correct interpolation. |
| `color_levels` | `int` | 3D mesh only (Step 8) — quantise final colour into this many bands per channel. Default `0`: continuous colour, no quantisation. |

**`color_ramp` sub-fields:**

| Field | Type | Description |
| --- | --- | --- |
| `type` | `string` | `"texture"` (gradient map PNG) or `"cosine"` (math-based) |
| `texture` | `string` | Key → 256×1 PNG (only if `type = "texture"`) |
| `ramp_steps` | `float` | Quantisation steps; `0.0` = smooth, `2+` = cel banding |
| `a`, `b`, `c`, `d` | `[r,g,b]` | Cosine palette params (only if `type = "cosine"`) |

**Example — lantern** (`material-example-lantern.json`):

```json
{
  "id": "mat-lantern-001",
  "name": "lantern_base",
  "atlas": "lantern_atlas",
  "param_map": "lantern_params",
  "color_ramp": null,
  "overlays": [
    {
      "type": "animation",
      "animation_id": "11111111-0000-0000-0000-000000000001",
      "blend_mode": "additive",
      "intensity": 0.8
    }
  ]
}
```

See example file: [`frontend/assets/data/material/material-example-lantern.json`](../../frontend/assets/data/material/material-example-lantern.json)

---

## Mesh

**File path:** `frontend/assets/data/mesh/mesh-<name>.json`

The project-defined mesh JSON format — geometry attributes only (position/normal/UV, optionally per-vertex color), never a general glTF subset (`tools/convert_mesh.py` refuses skins/morph targets/extra primitives). Loaded by `client/engine/mesh.py`'s `Mesh` class.

| Field | Type | Description |
| --- | --- | --- |
| `vertices` | `array` | Interleaved vertex attribute data (format documented alongside `Mesh.load()`) |
| `indices` | `array` | Triangle index list |
| `sockets` | `array \| null` | Optional named local-space attachment points: `{"name": string, "position": [x, y, z], "rotation": [x, y, z]}`. Omit entirely for meshes with no attachment points. Exported by `tools/convert_mesh.py` from glTF nodes that have a `name` but no `mesh` reference (a Blender "Empty" placed at the attachment point) — metadata only, not geometry, so it doesn't broaden the converter's narrow scope. |

---

## Entity / Object

**File path:** `frontend/assets/data/entity/entity-<uuid>.json`

An entity references a material and an animation clip. It carries only the data that is **unique to this instance** — identity, size, spatial properties, and runtime state.

**3D usage is different, and it matters:** for a 3D mesh entity, this same file type is reached via a networked entity's `render_template` field (`backend/engine/ecs/entity.py`) and is treated as a **reusable template**, not an instance — the `mesh`/`material_id` fields describe what something looks like, and are deliberately shared across every networked entity that references this file. Placement (position, rotation, scale) is **never** stored here for 3D content — it lives on the networked entity itself (`x`/`y`/`z`, `transform3d`), specifically so multiple entities can reference the same template and still be independently positioned. This doesn't change anything about the existing 2D usage above (still one definition file per placed 2D object, as always) — it's an additional way this file format gets used, not a replacement.

**Field reference:**

| Field | Type | Description |
| --- | --- | --- |
| `id` | `string` (UUID) | Unique entity identifier |
| `name` | `string` | Human-readable name |
| `material_id` | `string` | Reference to a material file |
| `animations` | `object` | Map of state key → animation clip UUID (e.g. `"idle"`, `"walk_n"`) |
| `size` | `[w, h]` | Logical size in world units |
| `pivot` | `[x, y]` | Anchor point as a fraction of size (e.g. `[0.5, 1.0]` = bottom-centre) |
| `runtime` | `object` | Initial runtime state values (any material uniforms to override at startup) |
| `mesh` | `string \| null` | 3D only — asset key for a mesh JSON file (`frontend/assets/data/mesh/`, see `Mesh` below and `client/engine/mesh.py`). Presence of this field (or `parts`, below) is what routes a `render_template`-resolved entity to the 3D mesh draw path instead of the 2D/billboard path. No placement data — see the note above. |
| `parts` | `array \| null` | 3D only, alternative to `mesh` for multi-part entities (a staff with a separately-modeled charm hanging off it) — see "Parts / Attachment Sockets" below. A definition has either `mesh` or `parts`, never both. |

**`runtime` object:** A flat key-value store whose keys correspond to named uniforms in the material's shader. Common keys:

| Key | Description |
| --- | --- |
| `glow_intensity` | Overrides the overlay `intensity` at runtime |
| `hue_shift` | HSV hue shift (0–1) |
| `tint` | `[r, g, b, a]` uniform tint |
| `ramp_steps` | Quantisation step count |

**Example — lantern entity** (`entity-example-lantern.json`):

```json
{
  "id": "00000000-0000-0000-0000-000000000002",
  "name": "lantern",
  "material_id": "mat-lantern-001",
  "animations": {
    "idle": "11111111-0000-0000-0000-000000000001"
  },
  "size": [16, 32],
  "pivot": [0.5, 1.0],
  "runtime": {
    "glow_intensity": 0.8
  }
}
```

See example file: [`frontend/assets/data/entity/entity-example-lantern.json`](../../frontend/assets/data/entity/entity-example-lantern.json)

### Parts / Attachment Sockets (3D only)

An alternative to the single `mesh` field for entities built from more than one mesh, each positioned relative to a named socket (see `Mesh`, above) on another part rather than the world — e.g. a staff (`shaft`) with a separately-modeled `charm` hanging from a socket on it.

```json
"parts": [
  { "id": "shaft", "mesh": "mesh-staff-shaft" },
  {
    "id": "charm",
    "mesh": "mesh-staff-charm",
    "attachTo": { "part": "shaft", "socket": "charm_socket" },
    "localOffset": { "position": [0, -0.3, 0], "rotation": [0, 0, 0], "scale": [1, 1, 1] }
  }
]
```

| Field | Type | Description |
| --- | --- | --- |
| `id` | `string` | Unique within this `parts` array. |
| `mesh` | `string` | Asset key for this part's mesh, same as the top-level `mesh` field. |
| `material_id` | `string \| null` | Optional per-part material override. |
| `attachTo` | `object \| null` | `{"part": id, "socket": name}` — the part named must appear *earlier* in the array (forward references and cycles are rejected at load time with a clear error, never silently mis-rendered). Omit for a part that attaches directly to the entity's own per-instance placement (`x`/`y`/`z` + `transform3d`) — identical to a plain `mesh` entity. |
| `localOffset` | `object \| null` | `{"position": [x,y,z], "rotation": [x,y,z], "scale": [x,y,z]}`, default identity. **Deliberately not called `transform3d`** — `localOffset` is definition-level (the fixed relationship between two meshes of the same asset, true for every placed instance); `transform3d` (on the networked entity, not here) is per-instance. Conflating the two names would make it easy to confuse "adjust this asset's internal composition" with "adjust where this one placement is". |
| `dangle` | `object \| null` | Optional secondary-motion spring — see "Dangle (Secondary Motion)" below. Absent = rigid attachment. |
| `animation_id` | `string \| null` | Optional transform animation clip id (an authored, looping motion — spin, bob) — see "Transform Animation Clips" below. When present, the clip's sampled `position`/`rotation`/`scale` fields replace this part's own `localOffset` fields of the same name; a field the clip doesn't animate keeps its `localOffset` value. |
| `action_animations` | `object \| null` | Optional `{state_name: clip_id}` map — see "Action-Triggered Animations" below. Takes priority over `animation_id` whenever the entity's current `state` matches a key; falls back to `animation_id` (or rest) otherwise. |

A part's world transform is `attachTo`'s part's world transform × that socket's local transform × this part's own `localOffset`. A part with no `attachTo` composes directly off the entity's own per-instance placement, the chain's root.

### Dangle (Secondary Motion)

Optional per-part cosmetic spring-damper (`client/engine/dangle.py`, Step 10) — a part that hangs and sways slightly as its parent moves, rather than staying perfectly rigid. Client-side only, purely visual — see `.github/copilot-instructions.md`'s "Physics & Simulation Boundary"; this never touches the backend or an entity's authoritative state.

```json
"dangle": { "stiffness": 8.0, "damping": 0.3, "inertia": 1.0, "gravity": null, "maxOffset": 0.2 }
```

| Field | Type | Description |
| --- | --- | --- |
| `stiffness` | `float` | How strongly the part springs back toward rest. Higher = snappier. |
| `damping` | `float` | Velocity lost per second, `0`–`1`. Higher = settles faster, less oscillation. |
| `inertia` | `float` | How strongly the part resists its parent's sudden movement — what actually reads as "weight" swinging on the end of a staff. **Not in this task's original schema sketch, added here since the spring algorithm genuinely needs it as a tunable, same as `stiffness`/`damping`** — flagged explicitly since a future reader comparing against an older draft of this task might otherwise assume it's missing by mistake, not by design. |
| `gravity` | `[x, y, z] \| null` | Optional constant pull. `null` (default) = no gravity. |
| `maxOffset` | `float` | Clamp on the offset's magnitude (world units) so a teleport/network hiccup can't fling the part off-screen. |

Absent `dangle` = perfectly rigid attachment, exactly the "Parts / Attachment Sockets" behaviour above. A dangle-enabled part on a stationary entity settles to zero offset at rest, never drifts.

### Transform Animation Clips

**File path:** `frontend/assets/data/animation/animation-transform-<name>.json`

Authored, repeating motion for a mesh part (a spinning coin, a bobbing crate lid) — a second clip `type` alongside the existing frame-based sprite animation clips, sampled by `client/engine/transform_clip.py`'s `sample_transform_clip()`.

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

| Field | Type | Description |
| --- | --- | --- |
| `id` | `string` | Clip id, referenced by a `parts[]` entry's `animation_id`. |
| `type` | `"transform"` | Distinguishes this from the existing frame-based clip schema. |
| `loop` | `bool` | Whether playback wraps back to `time_ms: 0` after the last keyframe. |
| `keyframes` | `array` | `{"time_ms": number, "position"?: [x,y,z], "rotation"?: [x,y,z], "scale"?: [x,y,z]}`, sorted ascending by `time_ms`. Any subset of the three fields per keyframe — omitted fields hold the part's `localOffset` rest value (see the `animation_id` row above), not `[0,0,0]`/`[1,1,1]`. |

A part plays its clip and Step 10's dangle offset simultaneously, not one-or-the-other — the clip's sampled transform composes as the part's local transform (in place of the corresponding static `localOffset` fields), with dangle's offset then added to the resulting position, same as the non-animated case. A coin part can spin (via `animation_id`) and sway from motion (via `dangle`) at the same time.

### Action-Triggered Animations

One-shot animations fired by a discrete, server-authoritative action (an attack, a jump) rather than continuous motion — see [ACTION_TRIGGERED_ANIMATIONS.md](ACTION_TRIGGERED_ANIMATIONS.md) for the full pattern (backend timing + both client draw paths) and a worked example. Summary of the schema pieces:

- A `parts[]` entry's optional `action_animations: {state_name: clip_id}` (mesh path) — same transform-clip format as `animation_id` above, always played one-shot regardless of the referenced clip's own `loop` field, and takes priority over `animation_id` while the entity's `state` matches a key.
- A sprite/billboard entity's animation data JSON (`frontend/assets/data/*_animations.json`, the format `stand`/`walk` already use) can define a clip whose top-level key matches an `entity.state` value exactly (e.g. `"activate"`) with `"loop": false` — the sprite path selects it automatically whenever `entity.state` names an existing clip, purely by data, before falling back to the ordinary `walk`/`stand` pair.

---

## Camera / Scene

Not a JSON asset file — the `camera` object is a runtime object, and will eventually be written by the Area/Scene system (Phase 11). Documented here because `client/engine/renderer.py`'s `getViewProjectionMatrix()` and `client/engine/entity_renderer.py`'s mesh-drawing path are the readers, and because the Step 8 fields below are consumed the same way materials are — as opt-in stylization inputs.

> The original hand-authored harness for this (`frontend/test-3d.html`, opened via the now-deleted `run_desktop_test.py`) was part of the PyWebView/browser client and no longer exists — see `ARCHITECTURE.md`'s Branch model note. Until Phase 11 lands, there is no standalone camera-authoring harness on this branch.

**3D camera fields** (see Step 3 of `3d-coordinate-mapping.prompt.md`): `mode` (`'2d'` default | `'3d'`), `position`, `target`, `up`, `fov`, `near`, `far`.

**Step 8 stylization fields**, all optional and independently defaulting to a no-op — consumed only by the 3D mesh draw path, no effect on 2D or billboard entities:

| Field | Type | Description |
| --- | --- | --- |
| `fogColor` | `[r, g, b]` | Colour the mesh path fades toward with distance. Meaningless while fog is disabled. |
| `fogNear` | `float` | Distance at which fog starts blending in. |
| `fogFar` | `float` | Distance at which fog is fully opaque. **Default `0`: fog is completely disabled** — the shader skips the blend entirely rather than computing a zero-strength one. |
| `ambientColor` | `[r, g, b]` | Multiplies final mesh colour. **Default `[1, 1, 1]`: no-op tint.** |

---

## File Organisation

```text
frontend/assets/data/
├── animation/          – Animation clip JSON files
├── entity/             – Entity definition JSON files
├── material/           – Material JSON files  ← new, create as needed
├── player/             – Player-specific save data
└── example_*.json      – Ad-hoc examples (legacy; migrate to typed subdirs)
```

See also:
- [COMBINER.md](COMBINER.md) — param map channel layout and material JSON detail
- [RENDER_WORKFLOWS.md](RENDER_WORKFLOWS.md) — how materials are used in shaders
