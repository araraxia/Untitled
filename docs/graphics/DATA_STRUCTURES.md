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

## Entity / Object

**File path:** `frontend/assets/data/entity/entity-<uuid>.json`

An entity references a material and an animation clip. It carries only the data that is **unique to this instance** — identity, size, spatial properties, and runtime state.

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
