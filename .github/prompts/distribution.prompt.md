---
agent: agent
description: Implement one-step distributable builds, in-engine developer tools, and release versioning (Phase 9 of ROADMAP.md). Covers PyInstaller packaging, entity inspector, perf overlay, animation preview page, and semantic versioning.
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

# Task: Distribution & Tooling (Phase 9)

> **STALE — predates the native client migration, re-audit before starting.** This entire prompt was written when `main.py` opened a PyWebView window around the `frontend/js/*` browser client. As of `.github/prompts/wgpu-py-migration.prompt.md`, that's no longer true: `main.py` launches `client/main.py`'s native GLFW/`wgpu-py`/`imgui-bundle` window instead, and `frontend/js/*`/`run_browser.py`/`run_desktop_test.py` are legacy, not used, kept only for historical reference. Concretely, before starting this task: **do not** bundle PyWebView in the PyInstaller spec, **do not** defer Linux distribution or plan around `run_browser.py`/AppImage (the native client already ships on Linux with no browser dependency), **do not** point the Animation Preview tool or Entity Inspector/Perf Overlay at `frontend/js/engine/renderer.js`/`frontend/js/game/main.js` or link them from `run_browser.py`/`frontend/index.html` — re-derive these against `client/main.py`/`client/engine/`/`client/game/` instead. The Required Reading list and steps below still describe the old architecture; treat them as a description of *what this task used to assume*, not current instructions, and re-verify every file path against the current repo before acting on it.

You are implementing the distribution and developer-tooling phase for
this project. This is Phase 9 of `ROADMAP.md`. All earlier phases are
prerequisites; Phase 5 (Asset Pipeline), Phase 1 (Engine–Game
Separation), and Phase 13 (Native wgpu-py Desktop Client) are most
directly relevant.

Complete all steps in order. Each step must leave the application in a
runnable state before proceeding to the next.

---

## Required Reading

Read these files before writing any code:

- `ROADMAP.md` — Phase 9 specification (sections 9.1–9.3)
- `main.py` — PyWebView entry point; the PyInstaller spec must replicate
  its import graph and resource paths correctly
- `backend/app.py` — Flask app; note `PROJECT_ROOT`, `FRONTEND_PATH`,
  and `ASSET_PATH` path constructions — these must still resolve when
  the binary runs from a temporary `_MEIPASS` directory
- `backend/engine/config.py` — `EngineConfig` dataclass; a `version`
  field will be added here
- `requirements.txt` — current Python dependencies; `pyinstaller` will
  be added here
- `setup.bat` / `run.bat` — existing developer workflow scripts; a new
  `build.bat` will mirror their style
- `tools/build_assets.py` — orchestration pattern to follow when writing
  `tools/build.py`
- `run_browser.py` — browser-mode entry point; the Animation Preview
  page will be linked from it
- `frontend/js/engine/renderer.js` — `gpuDevice`, `useGPU`, render loop
  timing; the Perf Overlay reads from these
- `frontend/js/game/main.js` — `gameState`, `GameContext`, `init()`;
  developer tools activate from here
- `frontend/index.html` — script load order; dev-tool scripts are added
  here behind a `?dev=1` query-parameter guard
- `config/engine.json` — runtime config; a `version` key will be added
  here

---

## Constraints

- Follow PEP 8 for all Python: 4-space indent, max 79 characters per
  line. Use type hints on all new public functions and classes.
- Follow the Airbnb JavaScript style guide for JS: 2-space indent,
  single quotes, semicolons.
- All new JS classes and public functions must have JSDoc comments.
- Developer tools (`entityInspector.js`, `perfOverlay.js`) must be
  completely inert in production. Gate their initialisation behind
  `window.location.search.includes('dev=1')` checked once in `main.js`;
  never load their scripts in a production build.
- The PyInstaller spec targets **Windows** as the primary platform.
  macOS notes are documented as comments; Linux support is explicitly
  deferred (document this in `tools/build.py`).
- Path resolution inside the frozen binary must use a
  `get_resource_path(relative)` helper that substitutes `sys._MEIPASS`
  when frozen. This helper lives in `main.py` and is imported by
  `backend/app.py`.
- Version strings follow `MAJOR.MINOR.PATCH` exactly. The single source
  of truth is `config/engine.json`; all other references read from it.
- Run `python -c "from backend.app import app; print('app ok')"` after
  any Python changes to confirm no import errors.

---

## Step 1 — Audit Current State

Before writing any code, read the key files listed above and produce a
short summary covering:

1. How `main.py` constructs paths to the frontend and backend (absolute,
   relative, or via `__file__`) — these are the paths that break when
   frozen.
2. How `backend/app.py` constructs `PROJECT_ROOT`, `FRONTEND_PATH`, and
   `ASSET_PATH` — same concern.
3. Whether `config/engine.json` already has a `"version"` key.
4. What `EngineConfig` in `backend/engine/config.py` already exposes and
   whether a `version` field is present.
5. What `run_browser.py` currently does and how the Animation Preview
   page would be linked from it.
6. What `GPUDevice` fields are accessible from `renderer.js` that could
   feed the Perf Overlay (frame time variable, entity count, etc.).

Do not create or edit any files in this step. Output findings, then
proceed.

---

## Step 2 — Release Versioning (Phase 9.3)

**Files to modify:** `config/engine.json`, `backend/engine/config.py`

### `config/engine.json`

Add a top-level `"version"` key:

```json
"version": "0.1.0"
```

### `backend/engine/config.py`

Add a `version: str = "0.0.0"` field to `EngineConfig` and load it from
the JSON. Also expose a module-level constant:

```python
ENGINE_VERSION: str = "0.0.0"
```

This constant is set to `engine_config.version` after `load_engine_config()`
runs at module import time.

### Version reporting

In `backend/app.py`, add a route:

```python
@app.route('/api/version')
def get_version():
    """Return the engine version as JSON."""
    ...
```

It must return `{"version": ENGINE_VERSION}`. This endpoint is used by
build scripts and the Perf Overlay.

---

## Step 3 — Path Resolution Helper (Phase 9.1 prerequisite)

**Files to modify:** `main.py`, `backend/app.py`

### `main.py`

Add the following helper near the top of the file, before any path
constructions:

```python
def get_resource_path(relative: str) -> str:
    """Resolve a path relative to the project root.

    When running as a PyInstaller frozen binary, ``sys._MEIPASS`` is the
    temporary extraction directory.  Otherwise the project root is the
    directory containing this file.

    Args:
        relative: A path string relative to the project root
            (e.g. ``'frontend/index.html'``).

    Returns:
        The absolute path as a string.
    """
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative)
```

Update every hard-coded path in `main.py` that points into `frontend/`
or `backend/` to use `get_resource_path(...)`.

### `backend/app.py`

Import `get_resource_path` from `main` is not possible (circular).
Instead, duplicate the same logic as a private helper `_resource_path`
local to `app.py`, or extract it to a new `backend/utils.py` module
that both files import. Choose whichever approach avoids circular
imports given the existing import graph.

Update `PROJECT_ROOT`, `FRONTEND_PATH`, `ASSET_PATH`, `CSS_PATH`,
`JS_PATH`, and `DATA_PATH` to resolve through the helper.

Verify:

```bash
python -c "from backend.app import app; print('app ok')"
```

---

## Step 4 — PyInstaller Spec & Build Script (Phase 9.1)

**New files:** `tools/build.py`, `tools/game.spec`,
`build.bat`  
**Files to modify:** `requirements.txt`

### `requirements.txt`

Add:

```text
pyinstaller==6.11.1
```

Use the exact version above to ensure reproducible builds.

### `tools/game.spec`

Write a PyInstaller spec file that:

- Sets `name = 'UntitledGame'`.
- Uses `onedir` mode (not `onefile`) for faster cold-start on Windows.
- Sets `console = False` (no terminal window in the shipped binary).
- Includes the following data trees via the `datas` list:

  ```python
  datas = [
      ('frontend',  'frontend'),
      ('config',    'config'),
      ('saves',     'saves'),    # included empty; populated at runtime
  ]
  ```

- Adds hidden imports for all Flask, SocketIO, and PyWebView internals
  that PyInstaller misses: at minimum
  `flask_socketio`, `engineio`, `socketio`, `webview`,
  `simple_websocket`, `engineio.async_drivers.threading`.
- Excludes `tkinter`, `matplotlib`, `numpy`, `scipy` to keep the bundle
  small.
- On Windows, sets `icon = 'frontend/assets/images/icon.ico'` if the
  file exists, otherwise omits it.

### `tools/build.py`

```python
"""One-step build script: run asset pipeline, then invoke PyInstaller."""
```

The script must:

1. Run `tools/build_assets.py` (import and call, do not subprocess).
2. Invoke PyInstaller programmatically:

   ```python
   import PyInstaller.__main__
   PyInstaller.__main__.run(['tools/game.spec', '--noconfirm'])
   ```

3. Print the output directory (`dist/UntitledGame/`) on success.
4. Exit with a non-zero code on failure.

Document at the top of the file why Linux is deferred:

```python
# Linux distribution is deferred until WebKitGTK ships WebGPU support.
# On Linux, use run_browser.py or package as an AppImage manually.
```

### `build.bat`

Mirror the style of `run.bat`:

```bat
@echo off
echo Building UntitledGame...
echo.

if not exist "venv\Scripts\python.exe" (
    echo Error: Virtual environment not found!
    echo Please run setup.bat first.
    pause
    exit /b 1
)

venv\Scripts\python.exe tools/build.py
if %errorlevel% neq 0 (
    echo Build failed.
    pause
    exit /b 1
)

echo.
echo Build complete. Output: dist\UntitledGame\
pause
```

---

## Step 5 — Perf Overlay (Phase 9.2)

**New file:** `frontend/js/engine/perfOverlay.js`  
**Files to modify:** `frontend/index.html`, `frontend/js/game/main.js`

### `frontend/js/engine/perfOverlay.js`

```js
/**
 * PerfOverlay — lightweight developer overlay showing frame time,
 * tick time, entity count, and GPU memory usage.
 *
 * Only active when ?dev=1 is present in the URL.
 * Draws onto the overlay canvas via Canvas 2D.
 */
```

The overlay must display (top-right corner, monospace font):

| Row               | Source                                                                    |
| ----------------- | ------------------------------------------------------------------------- |
| `FPS: <n>`        | Computed from the render loop's `lastFrameTime` delta                     |
| `Frame: <ms>ms`   | Same delta in milliseconds                                                |
| `Entities: <n>`   | `Object.keys(gameState.entities).length`                                  |
| `GPU mem: <mb>MB` | `gpuDevice?.limits?.maxBufferSize / 1e6` — omit row if WebGPU unavailable |
| `Version: <v>`    | Fetched once from `/api/version` on init                                  |

```js
class PerfOverlay {
  /**
   * @param {HTMLCanvasElement} overlayCanvas
   */
  constructor(overlayCanvas) { ... }

  /** Fetch version from /api/version and cache it. */
  async init() { ... }

  /**
   * Update timing metrics.
   * @param {number} frameMs - Time since last frame in milliseconds.
   */
  update(frameMs) { ... }

  /**
   * Draw the overlay onto the canvas context.
   * @param {CanvasRenderingContext2D} ctx
   */
  draw(ctx) { ... }
}
```

Expose a module-level `let perfOverlay = null;` and a function
`initPerfOverlay(canvas)` that instantiates and returns the overlay.

### Wiring into `main.js`

Add to `init()`:

```js
if (window.location.search.includes("dev=1")) {
  perfOverlay = initPerfOverlay(overlayCanvas);
  await perfOverlay.init();
}
```

In the render loop, pass the current frame delta to
`perfOverlay?.update(frameMs)` and call `perfOverlay?.draw(ctx)` after
all other overlay draws.

### `frontend/index.html`

Add a script tag for `perfOverlay.js` in the Engine section. The script
is always present in the HTML; the guard lives in `main.js` so no
server-side templating is required.

---

## Step 6 — Entity Inspector (Phase 9.2)

**New file:** `frontend/js/engine/entityInspector.js`  
**Files to modify:** `frontend/index.html`, `frontend/js/engine/network.js`,
`frontend/js/game/main.js`

### `frontend/js/engine/entityInspector.js`

The entity inspector is a DOM overlay (inside `#ui-overlay`) that
shows all entities in the current area with live component values.

```js
/**
 * EntityInspector — developer overlay listing all entities and their
 * live component values.  Active only when ?dev=1 is in the URL.
 *
 * Triggered by pressing F1 while in-game.
 */
```

Requirements:

- Renders as a semi-transparent scrollable panel anchored to the
  left side of the screen.
- Each entity is a collapsible row showing its ID and type; expanding
  it shows all component fields as `key: value` pairs.
- Data is sourced from `gameState.entities`; refreshed on every
  `state_update` SocketIO event.
- `show()` / `hide()` / `toggle()` methods control visibility.
- Does not emit any SocketIO events.

### Wiring into `main.js`

```js
if (window.location.search.includes("dev=1")) {
  entityInspector = new EntityInspector();
}
```

In the keyboard input handler, toggle on `F1` when `dev=1` is active.

### `frontend/index.html`

Add a script tag for `entityInspector.js` after `perfOverlay.js`.

---

## Step 7 — Animation Preview Page (Phase 9.2)

**New file:** `frontend/animation-preview.html`  
**Files to modify:** `run_browser.py`

### `frontend/animation-preview.html`

A standalone HTML page (separate from `index.html`) that:

- Loads `js/engine/sprites/spritesheet.js`, `animation.js`,
  `shaderCache.js`, `gpuBuffers.js`, `gpuSpriteSheet.js`,
  `assetLoader.js`, and `entityRenderer.js` — the minimal set required
  to render a sprite.
- Fetches `assets/manifest.json` on load and populates a `<select>`
  dropdown with all image asset IDs.
- On selection, loads the corresponding `GPUSpriteSheet` and plays the
  first animation clip found in the animations manifest whose
  `spritesheet` field matches the selected asset.
- Renders the animation onto a centred `<canvas>` using `requestAnimationFrame`.
- Provides playback controls: Play / Pause button, frame slider, clip
  selector dropdown, and a speed multiplier input (0.25×–4×).
- Uses the same `css/style.css` as the main page.

### `run_browser.py`

After the server starts and the browser opens, print the animation
preview URL to the terminal:

```
Animation Preview: http://127.0.0.1:5000/animation-preview.html
```

Also add a Flask route in `backend/app.py` to serve the page:

```python
@app.route('/animation-preview.html')
def animation_preview():
    """Serve the animation preview developer tool."""
    ...
```

---

## Step 8 — ROADMAP Update

**File to modify:** `ROADMAP.md`

Mark Phase 9 as complete in the phase progress table and add the prompt
file reference at the bottom of the Phase 9 section:

```text
**Prompt file:** `.github/prompts/distribution.prompt.md`
```
