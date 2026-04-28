---
agent: agent
description: Build a reliable, repeatable pipeline from source assets to engine-ready data (Phase 5 of ROADMAP.md). Covers asset manifest generation, build tooling, procedural generation framework, and hot-reload dev mode.
tools:
  - read_file
  - create_file
  - replace_string_in_file
  - multi_replace_string_in_file
  - grep_search
  - file_search
  - get_errors
  - run_in_terminal
---

# Task: Asset Pipeline (Phase 5)

You are building the asset pipeline for this project. This is Phase 5 of `ROADMAP.md`. Phase 3 (ECS Overhaul) and Phase 4 (Simulation Systems) are prerequisites.

Complete all steps in order. Each step must leave the application in a runnable state before proceeding to the next.

---

## Required Reading

Read these files before writing any code:

- `ROADMAP.md` — Phase 5 specification
- `frontend/js/engine/assetLoader.js` — `AssetLoader` class; currently uses a hard-coded `registerAll()` call at the bottom of the file
- `frontend/assets/data/material/material-example-lantern.json` — current material JSON schema (`atlas`, `param_map`, `color_ramp`, `overlays`)
- `frontend/assets/data/animation/animation-00000000-0000-0000-0000-000000000001.json` — animation JSON schema
- `frontend/assets/data/entity/entity-example-lantern.json` — entity JSON schema
- `tools/pack_param_map.py` — existing param map packer (PIL-based); already functional
- `setup.bat` — project setup script; build tools should be hooked in here
- `frontend/assets/README.md` — asset organisation notes
- `config/engine.json` — runtime engine config; manifest path should be added here

---

## Constraints

- Follow PEP 8 for all Python: 4-space indent, max 79 characters per line.
- Use Python type hints throughout. All new public functions and classes must be fully typed.
- All new Python classes must have docstrings. Do not add docstrings to existing code you did not touch.
- Follow the Airbnb JavaScript style guide for any JavaScript changes: 2-space indent, single quotes.
- The `AssetLoader` manifest loading must be backward-compatible — assets registered via hard-coded `registerAll()` must continue to work alongside manifest-sourced entries.
- Do not modify existing material/animation/entity JSON schemas; only extend them.
- Do not break the existing SocketIO `state_update` event contract.
- Run `python -c "from backend.app import app; print('app ok')"` after each step to confirm no import errors.
- The build tool must be idempotent: running it twice must produce the same output without re-processing unchanged files.

---

## Step 1 — Audit Current State

Before writing any code, read the key files listed above and produce a short summary covering:

1. What assets are currently registered manually in `assetLoader.js` and what their path conventions are.
2. What metadata each JSON schema type (material, animation, entity) currently carries versus what the manifest will need to surface.
3. What the current `tools/pack_param_map.py` does and does not do (inputs, outputs, caching).
4. How `setup.bat` currently runs setup steps and where the build tool hook should go.
5. What directories under `frontend/assets/` exist and their contents.

Do not create or edit any files in this step. Output your findings and then proceed.

---

## Step 2 — Asset Manifest (Phase 5.1)

**New file:** `frontend/assets/manifest.json` (generated, not hand-authored)
**New file:** `tools/build_manifest.py`
**Files to modify:** `config/engine.json`

### Manifest schema

The manifest is a single JSON object. Top-level keys are asset type categories. Each entry within a category is keyed by **logical asset ID** (the short string used by `AssetLoader.resolve()`).

```json
{
  "version": 1,
  "generated_at": "<ISO-8601 timestamp>",
  "images": {
    "<asset_id>": {
      "path": "assets/images/...",
      "type": "atlas|param_map|color_ramp|effect|ui",
      "width": 0,
      "height": 0,
      "hash": "<sha256 hex, first 16 chars>"
    }
  },
  "animations": {
    "<asset_id>": {
      "path": "assets/data/animation/<filename>.json",
      "hash": "<sha256 hex, first 16 chars>"
    }
  },
  "materials": {
    "<asset_id>": {
      "path": "assets/data/material/<filename>.json",
      "hash": "<sha256 hex, first 16 chars>"
    }
  },
  "audio": {
    "<asset_id>": {
      "path": "assets/audio/...",
      "type": "music|sfx",
      "hash": "<sha256 hex, first 16 chars>"
    }
  }
}
```

The `asset_id` for images is derived from the filename stem with directory prefix stripped (e.g. `lantern_atlas` from `images/sprites/objects/lantern_atlas.png`). For JSON assets the ID comes from the `"id"` field inside the file; fall back to the filename stem if no `"id"` field exists.

Image `width`/`height` are read from the PNG/JPEG header using `PIL.Image`. Leave `width`/`height` as `0` for non-image formats.

### `tools/build_manifest.py`

```python
"""Auto-generate frontend/assets/manifest.json from the assets directory."""
```

The script:

1. Walks `frontend/assets/images/`, `frontend/assets/data/animation/`, `frontend/assets/data/material/`, and `frontend/assets/audio/` recursively.
2. Skips files whose extension is not in `{'.png', '.jpg', '.jpeg', '.webp', '.json', '.mp3', '.ogg', '.wav'}`.
3. Skips files whose name starts with `example_` (example/placeholder assets).
4. Builds the manifest dict following the schema above.
5. Writes to `frontend/assets/manifest.json`, pretty-printed with 2-space indent.
6. Prints a one-line summary: `Generated manifest: N images, M animations, K materials, J audio`.

Add `"asset_manifest_path": "frontend/assets/manifest.json"` to `config/engine.json`.

Verify:

```cmd
python tools/build_manifest.py
python -c "
import json
m = json.load(open('frontend/assets/manifest.json'))
print('manifest version:', m['version'])
print('image count:', len(m['images']))
"
```

---

## Step 3 — Manifest-Driven AssetLoader (Phase 5.1 continued)

**Files to modify:** `frontend/js/engine/assetLoader.js`

Extend `AssetLoader` to load the manifest at startup and auto-register all entries.

### New method: `loadManifest(manifestUrl)`

```js
/**
 * Fetch the asset manifest JSON and register all entries.
 * Entries already registered via registerAll() are NOT overwritten.
 *
 * @param {string} manifestUrl - URL to manifest.json relative to origin.
 * @returns {Promise<void>}
 */
async loadManifest(manifestUrl) { ... }
```

- `fetch(manifestUrl)` → parse JSON.
- For each category (`images`, `animations`, `materials`, `audio`), iterate entries and call `this.register(id, entry.path)` — but only if `!this._registry.has(id)` (hard-coded entries take priority).
- On fetch error, log a warning and continue — the loader must degrade gracefully if no manifest exists yet.

### Bootstrap call

At the bottom of `assetLoader.js`, after the existing `registerAll({...})` block, add:

```js
// Load manifest asynchronously. Modules that depend on manifest assets
// must await assetLoader.manifestReady before resolving keys.
assetLoader.manifestReady = assetLoader.loadManifest("assets/manifest.json");
```

Verify manually: open the browser, open the DevTools console, and confirm no `[AssetLoader]` errors appear and `assetLoader._registry.size` is greater than the number of hard-coded entries.

---

## Step 4 — Build Tools (Phase 5.2)

**New file:** `tools/build_assets.py`
**Files to modify:** `setup.bat`

### `tools/build_assets.py`

```python
"""Orchestrate all asset pre-processing steps."""
```

This is the single entry point for the full asset build. It must:

1. **Pack param maps** — call `pack_param_map.py` logic for each sprite that has a matching set of source channel images under `frontend/assets/pending/`. Skip sprites whose output param map already exists AND whose source files have not changed (compare SHA-256 hashes stored in a `tools/.asset_cache.json` file).
2. **Build manifest** — call `build_manifest.py` logic (import and invoke, do not shell out).
3. **Validate animation JSON** — for each file in `frontend/assets/data/animation/`, confirm it is valid JSON and contains the required top-level keys (`"id"`, `"frames"`). Print a warning for any that fail; do not abort the build.
4. **Report summary** — print total elapsed time and counts for each step.

### Hash cache

`tools/.asset_cache.json` maps `"<source_file_path>": "<sha256>"` and is written after each successful build. On the next run, files with unchanged hashes are skipped.

### `setup.bat` hook

Add the following line to `setup.bat` after the `pip install` step:

```bat
python tools/build_assets.py
```

Verify:

```cmd
python tools/build_assets.py
```

Expect: no errors; manifest rebuilt; summary line printed.

---

## Step 5 — Procedural Generation Framework (Phase 5.3)

**New directory:** `backend/engine/procgen/`
**New files:** `backend/engine/procgen/__init__.py`, `backend/engine/procgen/wfc.py`

### Wave Function Collapse (`wfc.py`)

Implement a 2-D tile-based WFC solver.

#### `TileRule`

```python
@dataclass
class TileRule:
    """Adjacency constraint for a single tile type.

    ``allowed[direction]`` is the set of tile IDs that may appear
    next to this tile in that direction.  Direction keys:
    ``'north'``, ``'south'``, ``'east'``, ``'west'``.
    """
    tile_id: str
    weight: float
    allowed: dict[str, set[str]]
```

#### `WFCSolver`

```python
class WFCSolver:
    """Wave Function Collapse solver for 2-D tile grids.

    Args:
        rules: Mapping of tile_id → TileRule.
        width: Grid width in cells.
        height: Grid height in cells.
        seed: Optional RNG seed for reproducible output.
    """

    def __init__(
        self,
        rules: dict[str, TileRule],
        width: int,
        height: int,
        seed: int | None = None,
    ) -> None: ...

    def inject(self, x: int, y: int, tile_id: str) -> None:
        """Force a specific cell to a known tile before solving."""
        ...

    def solve(self) -> list[list[str]]:
        """Run the WFC algorithm and return the solved tile grid.

        Returns a ``height × width`` list of lists of tile IDs.
        Raises ``WFCContradiction`` if no valid layout exists.
        """
        ...
```

#### `WFCContradiction`

```python
class WFCContradiction(Exception):
    """Raised when the WFC solver reaches an unsolvable state."""
```

#### Algorithm outline

- Initialise each cell's superposition as the full set of all tile IDs.
- Propagate adjacency constraints after each collapse (arc consistency / AC-3).
- At each step, collapse the cell with the lowest non-zero Shannon entropy (weighted by `TileRule.weight`); break ties by `(row, col)` order.
- After collapsing, propagate constraint removal to all four neighbours recursively.
- Repeat until all cells are collapsed or a contradiction is detected.

#### Rule loader

```python
def load_rules(rule_def: dict) -> dict[str, TileRule]:
    """Parse a rule definition dict (loaded from JSON) into TileRule objects.

    Expected JSON format (stored under ``config/game.json`` key
    ``'wfc_tile_rules'``):

    {
      "grass": {
        "weight": 10,
        "allowed": {
          "north": ["grass", "dirt"],
          "south": ["grass", "dirt"],
          "east":  ["grass", "dirt"],
          "west":  ["grass", "dirt"]
        }
      },
      "dirt": { ... }
    }
    """
```

Add a minimal `"wfc_tile_rules"` entry to `config/game.json` with at least three tile types: `"grass"`, `"dirt"`, `"water"`.

#### `__init__.py` exports

Export `WFCSolver`, `TileRule`, `WFCContradiction`, and `load_rules` from `backend/engine/procgen/__init__.py`.

Verify:

```python
python -c "
from backend.engine.procgen.wfc import WFCSolver, load_rules
import json, pathlib
cfg = json.loads(pathlib.Path('config/game.json').read_text())
rules = load_rules(cfg['wfc_tile_rules'])
solver = WFCSolver(rules, width=8, height=8, seed=42)
grid = solver.solve()
print('grid size:', len(grid), 'x', len(grid[0]))
print('top-left tile:', grid[0][0])
"
```

```python
python -c "from backend.app import app; print('app ok')"
```

---

## Step 6 — Hot Reload (Phase 5.4, Dev Mode)

**New file:** `backend/engine/hot_reload.py`
**Files to modify:** `backend/app.py`, `setup.bat`

### `backend/engine/hot_reload.py`

```python
"""File-system watcher for dev-mode hot reload of assets and shaders."""
```

Use `watchdog` (add `watchdog==6.0.0` to `requirements.txt` via `pip install watchdog==6.0.0 -r requirements.txt`) to watch `frontend/assets/` and `frontend/js/engine/sprites/` for changes.

#### `HotReloadWatcher`

```python
class HotReloadWatcher:
    """Watches asset and shader directories; emits SocketIO reload events.

    Args:
        socketio: The Flask-SocketIO instance.
        assets_dir: Path to ``frontend/assets/``.
        shaders_dir: Path to ``frontend/js/engine/sprites/``.
    """

    def __init__(
        self,
        socketio: Any,
        assets_dir: str | Path,
        shaders_dir: str | Path,
    ) -> None: ...

    def start(self) -> None:
        """Start the background observer thread."""
        ...

    def stop(self) -> None:
        """Stop the observer thread cleanly."""
        ...
```

#### On asset change

When any file under `assets_dir` changes:

1. Re-run the param map packer if the changed file is a source channel image under `frontend/assets/pending/`.
2. Re-run `build_manifest.py` to refresh `manifest.json`.
3. Emit a SocketIO event: `asset_reload` with payload `{'path': '<changed relative path>'}`.

#### On shader change

When any `.wgsl` or `.js` file under `shaders_dir` changes, emit a SocketIO event: `shader_reload` with payload `{'path': '<changed relative path>'}`.

#### Integration in `backend/app.py`

Import `HotReloadWatcher` and conditionally start it:

```python
import os
if os.environ.get('DEV_HOT_RELOAD', '0') == '1':
    from backend.engine.hot_reload import HotReloadWatcher
    _hot_reload = HotReloadWatcher(socketio, 'frontend/assets',
                                   'frontend/js/engine/sprites')
    _hot_reload.start()
```

Only start the watcher when `DEV_HOT_RELOAD=1` so production deployments are not affected.

#### `setup.bat` addition

Add the following comment and environment variable guidance near the top of `setup.bat` (do not set `DEV_HOT_RELOAD` automatically — it is opt-in):

```bat
REM To enable hot reload in dev mode, set: set DEV_HOT_RELOAD=1
```

Verify:

```python
python -c "from backend.engine.hot_reload import HotReloadWatcher; print('hot_reload ok')"
```

```python
python -c "from backend.app import app; print('app ok')"
```

---

## Step 7 — Smoke Test

Run the full import check:

```cmd
python -c "from backend.app import app; print('app ok')"
```

Run the build tool end-to-end:

```cmd
python tools/build_assets.py
```

Verify the manifest was written:

```cmd
python -c "
import json
m = json.load(open('frontend/assets/manifest.json'))
print('manifest ok — version:', m['version'], '— images:', len(m['images']))
"
```

Verify the WFC solver:

```cmd
python -c "
from backend.engine.procgen.wfc import WFCSolver, load_rules
import json, pathlib
rules = load_rules(json.loads(pathlib.Path('config/game.json').read_text())['wfc_tile_rules'])
grid = WFCSolver(rules, 8, 8, seed=0).solve()
assert len(grid) == 8 and len(grid[0]) == 8
print('wfc ok')
"
```

Manual checks:

- [ ] `python tools/build_assets.py` runs without errors and prints a summary.
- [ ] `frontend/assets/manifest.json` exists, is valid JSON, and contains `"version": 1`.
- [ ] `assetLoader.loadManifest()` resolves without error in the browser console.
- [ ] `WFCSolver` produces an 8×8 grid with no `WFCContradiction`.
- [ ] `HotReloadWatcher` starts when `DEV_HOT_RELOAD=1` and does not affect the non-dev boot path.
- [ ] `python -c "from backend.app import app; print('app ok')"` passes cleanly.

---

## Success Criteria

- [ ] `tools/build_manifest.py` — generates `frontend/assets/manifest.json` from the assets directory
- [ ] `tools/build_assets.py` — orchestrates param map packing, manifest build, and animation validation; hash-cached
- [ ] `tools/.asset_cache.json` — hash cache written by `build_assets.py`
- [ ] `frontend/assets/manifest.json` — auto-generated; contains `images`, `animations`, `materials`, `audio` sections
- [ ] `frontend/js/engine/assetLoader.js` — `loadManifest()` method; `manifestReady` promise; backward-compatible with hard-coded entries
- [ ] `config/engine.json` — `"asset_manifest_path"` key added
- [ ] `config/game.json` — `"wfc_tile_rules"` key with at least `"grass"`, `"dirt"`, `"water"` tiles
- [ ] `backend/engine/procgen/__init__.py` — exports `WFCSolver`, `TileRule`, `WFCContradiction`, `load_rules`
- [ ] `backend/engine/procgen/wfc.py` — `WFCSolver`, `TileRule`, `WFCContradiction`, `load_rules`
- [ ] `backend/engine/hot_reload.py` — `HotReloadWatcher`; only activated when `DEV_HOT_RELOAD=1`
- [ ] `requirements.txt` — `watchdog==6.0.0` added
- [ ] `setup.bat` — `python tools/build_assets.py` added; hot-reload opt-in comment added
- [ ] SocketIO `state_update` payload unchanged
- [ ] No game-layer Python files modified
