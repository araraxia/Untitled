---
agent: agent
description: Replace the PyWebView + browser/WebGPU-JS desktop client with a native Python client built on wgpu-py, GLFW, and imgui-bundle, so the desktop app works on Linux out of the box instead of depending on WebKitGTK's incomplete WebGPU support.
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

# Task: Native wgpu-py Client — Replace PyWebView

You are replacing the desktop client entirely: today `main.py` opens a PyWebView window pointing at `http://127.0.0.1:5000`, and everything the player sees — rendering, input, menus — runs as JavaScript inside PyWebView's embedded browser engine (WebKitGTK on Linux, WebView2 on Windows). WebKitGTK does not yet have stable WebGPU support, which is why Linux development today falls back to `run_browser.py` and a system browser instead of a native window (see `ARCHITECTURE.md`'s "Linux note"). That workaround still depends on the *user's* browser having working WebGPU, which is not "out of the box."

The fix is to stop rendering inside a browser engine at all. `wgpu-py` binds directly to `wgpu-native` (the same Rust WebGPU implementation, via Vulkan/Metal/D3D12), so a native Python client using it gets solid Linux support without waiting on any browser vendor. This task builds that client as a new top-level `client/` package — mirroring the existing `backend/engine` vs `backend/game` (and `frontend/js/engine` vs `frontend/js/game`) separation described in `CLAUDE.md` — and ports the renderer, asset loader, input, interpolation, and networking layers from JavaScript to Python. The Flask/SocketIO backend is untouched: the new client is just a different Socket.IO client connecting to the same server, which keeps the networked-multiplayer-ready client/server split intact rather than collapsing everything into one process.

**Decided up front (do not re-litigate these):**

- **Windowing/canvas: GLFW** (`wgpu.gui.glfw`), not Qt/wx — lightest dependency, the library wgpu-py's own examples are built around, proven on Linux X11/Wayland.
- **UI: imgui-bundle**, immediate-mode, overlaid on the same GLFW window/wgpu surface — character creation, player select, and in-game HUD are re-authored as imgui widget code. Not Qt widgets, not an embedded browser panel for menus.
- **Scope: full replacement.** Once the native client reaches parity, `frontend/js/engine`, `frontend/js/game`, and `run_browser.py` are marked legacy/deprecated (Step 16) rather than dual-maintained.

**This is not a rendering redesign.** WGSL shaders in `shaderCache.js` are inline JS template-literal strings — they port to Python triple-quoted strings essentially verbatim; do not rewrite shader logic while porting it. The goal is a faithful, mechanical port of the existing JS engine's *orchestration* code (buffer setup, draw calls, entity/component iteration, matrix math) to Python at the same abstraction level it already lives at — not a rewrite around a scene-graph library, and not an opportunity to redesign the material/sprite/mesh systems. If something looks like it needs redesigning to port cleanly, flag it in Step 1's audit instead of improvising a new design mid-port.

**Concurrent-work warning — read before Step 9:** another in-progress task (`3d-coordinate-mapping.prompt.md`) is actively modifying `frontend/js/engine/entityRenderer.js`, `renderer.js`, `shaderCache.js`, `mesh.js`, and `mat4.js` (adding the 3D mesh path, multi-part attachment sockets, the dangle spring, transform animation clips, and action-triggered playback). Steps 4–9 of this task port those exact files. Before starting each of those steps, re-read the current state of its source file rather than trusting any function/line description in this prompt — it may have changed since this prompt was written. If `3d-coordinate-mapping.prompt.md`'s own step checkmarks show it isn't finished yet, prefer porting what already exists and flag the gap in that step's Verify block rather than blocking entirely on the other task landing first.

**Known state of `3d-coordinate-mapping.prompt.md` as of this note (Steps 1–8 of 14 complete, in JS — read this before starting Step 1's audit, then re-verify against the live files, since this is a snapshot, not a substitute for re-reading):**

- ✅ Step 1 (audit), Step 2 (`frontend/js/engine/mat4.js` — `identity`/`perspective`/`lookAt`/`multiply`/`translationScale`/`rotationXYZ`/`compose`, Z-then-Y-then-X Euler order), Step 3 (`renderer.js`'s `camera.mode`/`position`/`target`/`up`/`fov`/`near`/`far` fields and `getViewProjectionMatrix()`), Step 4 (`entityRenderer.js`'s `drawEntity3D` billboard path), Step 5 (`frontend/js/engine/mesh.js`'s `Mesh` class; `entityRenderer.js`'s `drawEntityMesh`/`_resolveRenderTemplate`; `backend/engine/ecs/entity.py`'s `render_template`/`transform3d` fields — **this backend addition is already real and Step 9 of this porting task does not need to touch `entity.py` again**), Step 6 (`tools/convert_mesh.py` — already Python/stdlib-only, nothing to port, reuse as-is for the Python client too), Step 7 (`"meshes"`/`"entities"` manifest categories in `tools/build_manifest.py` and `assetLoader.js`'s `categories` array), Step 8 (`shaderCache.js`'s mesh pipeline gains `vertex_color`/`affine_uv`/`color_levels`/fog/ambient stylization hooks — the `MatUniforms` struct grew from 192 to 256 bytes for the mesh pipeline specifically; the WGSL text to port verbatim in this task's Step 6 is `buildMeshWgslCommon()` and `buildMeshStyleWgslTail()`, not the older `MESH_WGSL_COMMON`/`MESH_STYLE_WGSL_TAIL` constants named in earlier drafts of that prompt — both are now functions parameterized on `affineUv`, and **both must agree on the value passed** since WGSL requires a vertex output and the fragment input it feeds at the same `@location` to declare the same `@interpolate` type — a real bug was hit and fixed here (mismatched interpolation attributes produced an invalid pipeline that silently poisoned every command buffer it was used in); port that agreement, not just the shader text).
- 🔲 Not started: Steps 9–14 (multi-part meshes/sockets, dangle spring, transform clips, action-triggered playback, doc status update, smoke test) — per this repository's decision (see the three prompt files this note's edit accompanies — `3d-coordinate-mapping.prompt.md`, `area-system.prompt.md`, `level-editor.prompt.md`), **Steps 9–14 of `3d-coordinate-mapping.prompt.md` now target `client/engine/` (this task's Python port) directly rather than `frontend/js/engine/`** — they were redirected once the wgpu-py migration was decided, rather than being built in JS first and ported later. Practically: this porting task's Steps 4 (`mat4.py`), 6 (`shader_cache.py`), 8 (`mesh.py`), and 9 (`entity_renderer.py`) must exist and cover at least the Step 1–8 JS feature set *before* `3d-coordinate-mapping.prompt.md`'s Steps 9–14 can be implemented against them — check that prompt file's own step checkmarks for exactly how far the Python side has gotten before assuming Steps 4–9 here are still simply "port the JS."
- Not yet started at all (no JS or Python implementation exists): the multi-part/socket/dangle/transform-clip/action-animation feature set itself. There is nothing to port for these — Step 8 of this task (mesh/dangle/transform-clip port) will find `dangle.js`/`transformClip.js` do not exist in `frontend/js/engine/` and should follow this task's own Step 8 task 4 (stub with `NotImplementedError`, do not invent behaviour ahead of a reference implementation) *unless* `3d-coordinate-mapping.prompt.md`'s Steps 9–11 have since landed directly in `client/engine/` per the redirect above, in which case there's a real Python implementation to read instead of a stub to write.

## Required Reading

Read these before writing any code:

- `CLAUDE.md`, `ARCHITECTURE.md` — engine/game separation rule, current networking protocol (`initial_state`/`state_update`/`player_action`/`party_command`), Linux note explaining why this task exists
- `docs/graphics/OVERVIEW.md` — "explicit control and mathematical clarity over convenience abstractions"; this rules out pulling in `numpy`/`pyglm` for matrix math the same way it ruled out `gl-matrix` in JS — the Python port keeps the same flat, explicit, hand-rolled style
- `main.py`, `run_browser.py`, `backend/app.py` — current PyWebView bootstrap, health-check pattern, Flask/SocketIO server setup (`async_mode="threading"`), to understand what the new entry point must reproduce
- `frontend/index.html` — the exact script load order today; the Python port's module init order should follow the same dependency chain (spritesheet/animation → shaderCache → gpuBuffers → mat4 → mesh → gpuSpriteSheet → lightingPass → particleSystem → assetLoader → materialLoader → entityRenderer → network → interpolation → renderer → input → game/UI)
- Every file under `frontend/js/engine/` and `frontend/js/engine/sprites/` — full contents, not summaries; this task ports each one
- `frontend/js/game/*.js` and `frontend/js/game/characterFlow/*.js` — the screens/flow Step 14 rebuilds in imgui; note `characterCreation.js` (735 lines) and `playerSelect.js` (468 lines) are the largest of these
- `config/engine.json` — `host`/`port` the client must connect to (`127.0.0.1:5000`, not `0.0.0.0`, from the client side)
- `frontend/assets/data/input_config.json` — key-binding schema `input.js` loads and Step 12 reuses unchanged
- `docs/graphics/DATA_STRUCTURES.md`, `docs/graphics/RENDER_WORKFLOWS.md` — entity/material/mesh JSON schemas and the shader-combiner logic the ported renderer must reproduce byte-for-byte
- `.github/copilot-instructions.md` — "Physics & Simulation Boundary" (governs the `dangle.js` → Python port's naming, if that file exists by the time Step 8 runs), "Pip Packages" (bloat-avoidance policy — read before Step 2), "Code Style Guidelines" (PEP 8, 79-char lines, 4-space indent — applies to every new `client/` file)
- `requirements.txt` — current pinned deps; note `python-socketio` is already present (used server-side today), so the new client's Socket.IO connection needs no *new* networking dependency, only a different usage of an existing one

## Constraints

- All new Python code follows PEP 8: 4-space indent, 79-char line limit (per `CLAUDE.md`/`.github/copilot-instructions.md`).
- No `numpy`, no `pyglm`, no third-party matrix/vector math library. Port `mat4.js` to a Python module with the same explicit, flat-list, column-major, hand-built style — this mirrors the existing JS constraint (`.github/prompts/3d-coordinate-mapping.prompt.md`'s Step 2) and `docs/graphics/OVERVIEW.md`'s stated philosophy, not a new rule invented for this task.
- New package layout is `client/engine/` (renderer, camera/matrix math, mesh, asset loader, network, input, interpolation, sprites/materials/particles/lighting — the Python analog of `frontend/js/engine/`) and `client/game/` (character creation, player select, HUD — the Python analog of `frontend/js/game/`). Engine/game separation is preserved in the port exactly as it exists in JS today: `client/engine/` never imports from `client/game/`.
- WGSL shader source strings are ported verbatim (JS template literal → Python triple-quoted string). Do not edit shader logic as part of this task — if a shader needs a change to work correctly from wgpu-py, that's a bug to flag and fix minimally, not a rewrite.
- The backend (`backend/`) is out of scope. Do not modify Flask routes, SocketIO event names/payloads, the ECS, or the tick loop — the new client is a consumer of the existing network protocol, not a reason to change it.
- Do not add a general-purpose ECS, ORM, or scene-graph library on the client. The ported `entityRenderer.js` → `client/engine/entity_renderer.py` keeps the same "iterate entities, branch on render kind" structure it has today, not a redesign around a new abstraction.
- Every new pip dependency (`wgpu`, `glfw`, `imgui-bundle`) goes in `requirements.txt` with a pinned version, per the "Pip Packages" section of `.github/copilot-instructions.md`. `pywebview` and the Linux-only `PyGObject` line are removed in the same step, so this is a net-neutral-to-small dependency change, not pure addition — call this out explicitly in Step 2 rather than leaving it implicit.
- Assets: the Python client reads `frontend/assets/**` directly off disk (it runs on the same machine as the server) rather than issuing HTTP requests to Flask's static file route — no `requests`/`urllib` dependency needed for asset loading. `manifest.json` and every asset path it references stay exactly as they are; only the *loading mechanism* changes from `fetch()` to `open()`.
- Keep `frontend/`, `backend/`, and the new `client/` as three clearly separate top-level trees. Do not move backend files into `client/`, and do not have `client/` import anything from `frontend/js/` (there is nothing to import — JS and Python don't share code — but do not duplicate JSON schemas either; both clients read the same `frontend/assets/` files as their one shared source of truth).

---

## Step 1 — Audit Current State

Before writing code:

1. Read every file in `frontend/js/engine/` and `frontend/js/engine/sprites/` in full. For each, note its public functions/classes, what state it owns (module-level `let`/`const` vs. instance fields), and what other engine files it depends on — this becomes the porting order for Steps 4–13 (roughly: `mat4` → `shaderCache`/`gpuBuffers` → `mesh`/`gpuSpriteSheet`/`materialLoader` → `particleSystem`/`lightingPass`/`animation` → `entityRenderer` → `assetLoader` → `network` → `interpolation` → `renderer` → `input`).
2. Confirm which of `dangle.js`, `transformClip.js`, and the mesh/multi-part/socket code described in `.github/prompts/3d-coordinate-mapping.prompt.md` actually exist yet, and which of that prompt's steps are checked off. Record the actual current state — do not assume the prompt file's step list reflects finished work.
3. Read `frontend/js/game/*.js` and `characterFlow/*.js` in full; list every distinct UI screen/state (player select, character creation steps, in-game HUD elements) Step 14 needs to reproduce in imgui, and every SocketIO event each screen sends/listens for.
4. Confirm `python-socketio`'s client API (`socketio.Client()`, `@sio.event`/`@sio.on(...)`, `sio.emit(...)`, `sio.connect(...)`) supports every event `network.js` currently handles (`connect`, `disconnect`, `connection_response`, `initial_state`, `state_update`, `save_list`, `races_list`, `backgrounds_list`, `save_complete`, `autosave_complete`, `player_loaded`, `error`, `player_deleted`, `new_player_initialized`, `character_created`) and every event it emits (`player_action`, `party_command`, `request_save_list`).
5. Confirm `wgpu-py`'s current stable API surface for: adapter/device request, GLFW canvas creation (`wgpu.gui.glfw.WgpuCanvas` or current equivalent — package/module names shift between wgpu-py versions, verify against the installed version in Step 2, not from memory), shader module creation, render pipeline creation, buffer/texture creation and upload, and per-frame command encoding — note any API differences from the browser `GPUDevice`/`GPUCanvasContext` JS API that `renderer.js`/`shaderCache.js`/`gpuBuffers.js` rely on, so later steps aren't surprised mid-port.

Do not create or edit files in this step.

---

## Step 2 — Dependency Changes

**File:** `requirements.txt`

1. Add `wgpu`, `glfw`, and `imgui-bundle`, each with a pinned version — check current stable versions (`pip index versions <package>` or PyPI) rather than guessing; do not leave any of the three unpinned.
2. Remove `pywebview` and the Linux-only `PyGObject>=3.42.0; sys_platform == 'linux'` line — both existed only to support the PyWebView window, which this task removes entirely (Step 15).
3. Leave `Flask`, `Flask-SocketIO`, `python-socketio`, `python-engineio`, `simple-websocket`, `Pillow`, `watchdog` untouched — the backend and its existing dependencies are out of scope.

Verify: `pip install -r requirements.txt` succeeds in a clean venv on the current platform; `python -c "import wgpu, glfw, imgui_bundle"` succeeds with no import errors.

---

## Step 3 — `client/` Package Layout

Create the new top-level package, mirroring the existing engine/game split:

```text
client/
  __init__.py
  main.py
  engine/
    __init__.py
    mat4.py
    renderer.py
    shader_cache.py
    gpu_buffers.py
    gpu_sprite_sheet.py
    material_loader.py
    particle_system.py
    lighting_pass.py
    animation.py
    mesh.py
    entity_renderer.py
    asset_loader.py
    network.py
    interpolation.py
    input.py
  game/
    __init__.py
    ui.py
    character_creation.py
    player_select.py
    character_flow/
      __init__.py
      flow_controller.py
      module_registry.py
      module_types.py
```

Only create empty/stub modules in this step (module docstring + `pass` or minimal placeholder) — Steps 4–14 fill each one in. `client/engine/` must not import anything from `client/game/`; `client/game/` may import from `client/engine/`, matching the existing JS rule.

Verify: `python -c "import client.engine, client.game"` succeeds with no errors; directory structure matches the layout above.

---

## Step 4 — Port `mat4.js` → `client/engine/mat4.py`

Port `identity`, `perspective`, `lookAt`, `multiply`, `translationScale`, `rotationXYZ`, `compose` as module-level functions, each returning a flat 16-element `list[float]` (column-major, matching WGSL's `mat4x4<f32>` and the JS `Float32Array(16)` convention) rather than a `numpy` array — per the Constraints section, this is a direct translation, not a redesign. Preserve the documented Z-then-Y-then-X Euler rotation order exactly; every later step that builds a rotation matrix (camera, sockets, keyframes, action clips) depends on this convention matching the JS side so behaviour is identical between the two clients during any transition period.

Verify: unit-check `identity()` against the 16-float identity; `perspective`/`lookAt` against a hand-computed example; confirm `rotationXYZ`'s composition order matches `mat4.js`'s current documented behavior (re-check that file's own comment, since Step 1 task 2 flagged it may have changed).

---

## Step 5 — GPU/Window Bootstrap

**File:** `client/engine/renderer.py`

1. Adapter/device request: `wgpu.gpu.request_adapter_sync(...)` (or the current async/sync API per Step 1 task 5's findings) → device, mirroring `renderer.js`'s `navigator.gpu.requestAdapter()`/`requestDevice()`.
2. GLFW window + wgpu canvas creation, sized to match the current PyWebView window defaults in `main.py` (1280×720, resizable, min size 800×600).
3. Depth texture creation (`createDepthTexture` equivalent) and scene texture (`createSceneTexture` equivalent, for the lighting pass Step 7 ports).
4. `get_view_projection_matrix(camera, aspect)` — direct port of `renderer.js`'s `getViewProjectionMatrix`, using `client/engine/mat4.py` from Step 4; 2D-mode camera returns `None`/no-op exactly as the JS version does.
5. A bare render loop skeleton: acquire canvas texture, create command encoder, begin/end an (initially empty) render pass, submit, present, poll GLFW events — no entity drawing yet, just confirm the window opens and clears to a background color without errors.

Verify: running `client/main.py` (stubbed to just call this bootstrap) opens a resizable native window on the current platform that clears to a solid color every frame with no `wgpu` validation errors in the console.

---

## Step 6 — Port Shader Cache

**File:** `client/engine/shader_cache.py`

1. Port `SPRITE_WGSL` and `MATERIAL_WGSL_COMMON` (and the mesh-variant WGSL-building functions, per Step 1 task 2's findings on what currently exists in `shaderCache.js`) as Python triple-quoted strings — verbatim WGSL text, no logic changes.
2. Port the pipeline-variant caching pattern (`getSpritePipeline()` and friends): lazy-create-and-cache `GPURenderPipeline` objects keyed the same way the JS version keys them (`base`/`overlay`/`ramp`/`hue`, plus `mesh` and its stylization-flag permutations if those exist per Step 1 task 2).
3. Match bind group layouts exactly to what `gpu_buffers.py` (Step 7) and `material_loader.py` (Step 7) produce — a mismatch here is the most likely source of `wgpu` validation errors during Step 9's integration.

Verify: each pipeline variant compiles without a `wgpu` shader-compilation error; log and inspect the compiled pipeline's bind group layout against the JS version's for at least one variant.

---

## Step 7 — Port Buffers, Sprite Atlas, Materials, Particles, Lighting

**Files:** `client/engine/gpu_buffers.py`, `gpu_sprite_sheet.py`, `material_loader.py`, `particle_system.py`, `lighting_pass.py`, `animation.py`

Port each from its JS counterpart 1:1 (function/class names may become `snake_case` per PEP 8, but structure and behavior stay the same):

1. `gpu_buffers.py` — quad vertex buffer creation and any other buffer helpers `gpuBuffers.js` provides.
2. `gpu_sprite_sheet.py` — sprite atlas GPU texture upload/UV-rect lookup.
3. `material_loader.py` — JSON-driven material → bind group construction; texture loading here uses `Pillow` (already a pinned dependency) to decode images read from disk, replacing the browser's `Image`/`createImageBitmap`.
4. `particle_system.py`, `lighting_pass.py` — direct ports; these are the two largest remaining files (430 and 340 lines respectively) so budget the most porting time here.
5. `animation.py` — frame-based clip playback (`AnimationController` equivalent).

Verify: for each module, confirm it can be exercised standalone (e.g. load one known material JSON and inspect the resulting bind group layout) without needing the full entity renderer wired up yet.

---

## Step 8 — Port Mesh Path, Dangle, Transform Clips

**Files:** `client/engine/mesh.py`, and — only if they exist per Step 1 task 2's finding — `dangle.py`, `transform_clip.py`

1. `mesh.py` — port `Mesh`: load the project's mesh JSON format, pack interleaved vertex data, upload vertex/index `GPUBuffer`s. Texture/image decode again goes through `Pillow`.
2. If `dangle.js` exists yet: port to `client/engine/dangle.py`, preserving the "Physics & Simulation Boundary" comment convention from `.github/copilot-instructions.md` (a one-line comment at the top pointing back to that section) and the naming rule — no `physics` in any identifier. This stays a purely client-side cosmetic offset with no backend involvement, exactly as the JS version is scoped.
3. If `transformClip.js` exists yet: port to `client/engine/transform_clip.py` (`sample_transform_clip(clip, time_ms)`), same hand-rolled linear interpolation, no new dependency.
4. If either file doesn't exist yet in the JS source, stub the Python module with a `NotImplementedError` placeholder and a comment noting it's pending `3d-coordinate-mapping.prompt.md`'s completion — do not invent behavior ahead of the JS reference implementation landing.

Verify: a mesh JSON already used to verify the JS mesh path (e.g. `frontend/assets/data/mesh/mesh-example-crate.json` if it exists) loads and uploads without error via `mesh.py`.

---

## Step 9 — Port Entity Renderer

**File:** `client/engine/entity_renderer.py`

Re-read `frontend/js/engine/entityRenderer.js` fresh before starting this step (per the concurrent-work warning above — this file is the most likely to have changed).

1. Port the per-entity routing logic: 2D sprite path, 3D billboard path (`draw_entity_3d`), and mesh path (`draw_entity_mesh_parts` or whatever the current JS function is named), branching the same way the JS version does on `camera.mode` and the entity's resolved `render_template`.
2. Port `render_template` resolution (fetch-once-and-cache an `entity-<uuid>.json` definition via `client/engine/asset_loader.py`, Step 10) with the same caching behavior as the JS version.
3. Preserve exact behavior for entities with no `render_template` — same fallback path as JS.

Verify: with a stubbed/fake entity list, confirm the routing branches select the correct draw path for a 2D-only entity, a 3D billboard entity, and a mesh entity, matching what the JS version would select for the same entity data.

---

## Step 10 — Port Asset Loader

**File:** `client/engine/asset_loader.py`

1. Port `AssetLoader`'s manifest-driven resolution (`categories` array, `resolve(key)`) exactly, including whatever categories exist today (`images`, `animations`, `materials`, `audio`, and `meshes`/`entities` if `3d-coordinate-mapping.prompt.md`'s Step 7 has landed — check current `loadManifest()` categories rather than assuming).
2. Replace `fetch(manifestPath)`/`fetch(assetPath)` with direct filesystem reads (`open(Path(...), 'rb')` / `json.load(...)`) resolved relative to the repo root, per the Constraints section — no HTTP round-trip to the Flask static route for a client running on the same machine as the server.
3. `manifest.json`'s structure and every path inside it stay exactly as-is; only the loading mechanism changes.

Verify: `asset_loader.resolve('<known-asset-id>')` returns the correct on-disk path for at least one entry in each manifest category; loading a known texture/material/mesh through this module succeeds.

---

## Step 11 — Port Networking

**File:** `client/engine/network.py`

1. Create a `socketio.Client()`, connect to `http://127.0.0.1:5000` (from `config/engine.json`'s `host`/`port`, not the server-side `0.0.0.0` bind address).
2. Register handlers for every event `network.js` currently handles (full list in Step 1 task 4): `connect`, `disconnect`, `connection_response`, `initial_state`, `state_update`, `save_list`, `races_list`, `backgrounds_list`, `save_complete`, `autosave_complete`, `player_loaded`, `error`, `player_deleted`, `new_player_initialized`, `character_created`.
3. Port `send_player_action(action_type, **params)` and `send_party_command(member_id, command_type, **params)` — same emitted event names and payload shapes (`player_action`, `party_command`) as the JS version, so the backend needs zero changes.
4. Port the character-flow callback registration pattern (`characterFlowCallbacks` in JS → a Python equivalent) that `client/game/character_flow/flow_controller.py` (Step 14) hooks into.

Verify: with the Flask/SocketIO server running (`python backend/app.py` or via `client/main.py`'s server-thread bootstrap, Step 15), the Python client connects, receives `connection_response`, and — in a player-select context — successfully requests and receives `save_list`.

---

## Step 12 — Port Input

**File:** `client/engine/input.py`

1. Load `frontend/assets/data/input_config.json` unchanged — same schema, same file, read via `client/engine/asset_loader.py`.
2. Register GLFW key callbacks (`glfw.set_key_callback`) and mouse callbacks (`glfw.set_cursor_pos_callback`, `glfw.set_mouse_button_callback`) mirroring `handleKeyDown`/`handleKeyUp`/`handleMouseMove`/`handleMouseDown`/`handleContextMenu`.
3. Preserve the configurable polling-rate processing loop (`processInput` on a timer/interval) using the same `settings.inputPollingRate` field from the config.

Verify: pressing a configured movement key results in the same `player_action`/movement-intent behavior as the JS client would produce for the same key; party-member selection via mouse click still works.

---

## Step 13 — Port Interpolation

**File:** `client/engine/interpolation.py`

Direct numeric port of `interpolation.js` (54 lines — the smallest file in this task): 20 TPS simulation state → 60 FPS render-time interpolation. No behavior changes.

Verify: with two consecutive `state_update` snapshots and a render timestamp between them, interpolated entity positions match what `interpolation.js` would produce for the same inputs (spot-check the math, not a full test suite).

---

## Step 14 — UI Layer (imgui-bundle)

**Files:** `client/game/ui.py`, `character_creation.py`, `player_select.py`, `character_flow/*.py`

Re-author each screen from Step 1 task 3's audit as imgui-bundle immediate-mode widget code, driven by the same SocketIO events ported in Step 11:

1. `player_select.py` — save-slot list (from `save_list`), new/load/delete player actions.
2. `character_creation.py` — the full character-flow module sequence (races, backgrounds, whatever steps `character_flow_service.py`/`flowController.js` currently define), driven by `races_list`/`backgrounds_list`/`new_player_initialized`/`character_created`.
3. `character_flow/flow_controller.py`, `module_registry.py`, `module_types.py` — port the flow-state-machine structure from the JS equivalents; this is UI flow control, not rendering, and shouldn't need GPU-specific code.
4. `ui.py` — in-game HUD elements (whatever `ui.js`'s 111 lines currently cover — loading indicator, connection status, etc.).

This is the largest single porting effort in this task (1,522 combined JS lines across the four game-layer files) and the one with no 1:1 API mapping (DOM/CSS → imgui widgets is a real rewrite, not a mechanical port) — budget accordingly, and prefer functional parity (same screens, same fields, same flow) over pixel-perfect visual parity with the HTML version.

Verify: the full player-select → character-creation → in-game flow completes end to end using only the imgui UI, with no DOM/browser involved at any point.

---

## Step 15 — New Desktop Entry Point

**File:** `client/main.py`

1. Reproduce `main.py`'s current server bootstrap: start `backend.app`'s Flask/SocketIO server in a background thread, health-check-poll `127.0.0.1:5000` until ready (same `is_server_ready` pattern), same logging via `backend/independant_logger.py`'s `Logger`.
2. Once the server is ready, run the GLFW window + wgpu render loop (Step 5) and imgui UI (Step 14) on the main thread — GLFW/most native windowing requires main-thread execution, unlike PyWebView's `webview.start()`.
3. Connect the Step 11 network client after the window/canvas exists.
4. Remove the `should_disable_gpu()` Nouveau workaround and all `webview.*` calls — those existed specifically to work around WebKitGTK/PyWebView issues this task removes.

**File:** root `main.py`

5. Replace its body with a thin call into `client.main.main()` (or replace `main.py` outright and update `run.bat`/any other reference to point at the new entry point — pick whichever keeps `run.bat` working with the smallest change, and note the choice in this step's completion note).

**File:** `run.bat`

6. Update if the entry point invocation changed (e.g. still `python main.py`, or now `python -m client.main`).

Verify: `run.bat` (or its updated equivalent) launches a native window on Windows with no PyWebView/WebKit involved; the same entry point (or a documented Linux equivalent) launches successfully on Linux without any browser-mode fallback.

---

## Step 16 — Deprecate Legacy Browser/JS Frontend

Per the "full replacement" scope decided up front:

**File:** `ARCHITECTURE.md`

1. Update the "Desktop Application Layer" description to describe `client/` as the primary/only supported desktop client. Mark `frontend/js/engine/`, `frontend/js/game/`, and `run_browser.py` as legacy — kept in the repository for reference during the transition, not actively developed against.

**File:** `run_browser.py`, top of `frontend/index.html`

2. Add a clear comment/log line noting this path is deprecated in favor of `client/main.py`, without deleting either — do not remove `frontend/js/*` or `run_browser.py` in this task; "mark legacy," not "delete."

**File:** `README.md`, `CLAUDE.md`

3. Update "Running" instructions to lead with the new native client; keep the old PyWebView/browser-mode instructions but clearly labeled legacy/deprecated.

Verify: a reader of `ARCHITECTURE.md`/`README.md`/`CLAUDE.md` alone (no other context) understands `client/` is the current desktop app and `frontend/js/*`/`run_browser.py` are legacy.

---

## Step 17 — Update Remaining Documentation

**Files:** `ARCHITECTURE.md`'s file-purpose tables, `docs/DEBIAN_SETUP.md`

1. Add a `client/` section to `ARCHITECTURE.md`'s architecture tables mirroring the existing `frontend/js/engine/` table (Step 3's file list), and note the new pip dependencies (`wgpu`, `glfw`, `imgui-bundle`) alongside the removed ones (`pywebview`, `PyGObject`).
2. Update `docs/DEBIAN_SETUP.md`'s Linux setup instructions — remove any WebKitGTK-specific setup steps that only existed for PyWebView, and add whatever system packages GLFW/wgpu-native actually need on Linux (verify against Step 2's install, don't guess).

Verify: following `docs/DEBIAN_SETUP.md` from a clean Debian/Ubuntu environment (or as close to one as can be verified) results in a working native window, with no manual step left undocumented.

---

## Step 18 — Smoke Test

Run the new client and confirm:

- [ ] `run.bat` (or updated entry point) opens a native window on Windows with no PyWebView/WebKit involved.
- [ ] The equivalent command opens a native window on Linux (or, if a Linux machine isn't available to verify directly, confirm no code path references `webview`/WebKitGTK and that GLFW's documented Linux backend requirements are met).
- [ ] Player-select screen loads the save list over the ported Socket.IO client and lets a save be loaded.
- [ ] Character creation completes end-to-end through imgui UI and results in `character_created`.
- [ ] Once in-game: 2D sprite entities render correctly; a 3D-mode scene (if `3d-coordinate-mapping.prompt.md` has landed billboards/mesh) renders billboards and meshes correctly with the same visual result as the JS client for the same scene.
- [ ] Movement input (keyboard) and party commands (mouse) both work and produce the same `player_action`/`party_command` traffic as the JS client would.
- [ ] Position interpolation between ticks is smooth at 60 FPS render rate against the 20 TPS simulation, matching `interpolation.js`'s behavior.
- [ ] No `wgpu` validation errors in the console/log during normal play.
- [ ] `get_errors` reports zero errors on every file under `client/`.
- [ ] `frontend/js/*` and `run_browser.py` still work unmodified (aside from the Step 16 deprecation notice) — this task doesn't break the legacy path, it supersedes it.

---

## Success Criteria

- [ ] `requirements.txt` — `wgpu`, `glfw`, `imgui-bundle` added and pinned; `pywebview`, `PyGObject` removed
- [ ] `client/engine/mat4.py` — same seven functions as `mat4.js`, same Euler order, no third-party math library
- [ ] `client/engine/renderer.py` — GLFW window + wgpu device/canvas bootstrap, `get_view_projection_matrix`, render loop
- [ ] `client/engine/shader_cache.py` — WGSL strings ported verbatim; pipeline variants match JS variant names/behavior
- [ ] `client/engine/{gpu_buffers,gpu_sprite_sheet,material_loader,particle_system,lighting_pass,animation}.py` — direct ports, `Pillow` used for texture decode
- [ ] `client/engine/mesh.py` (and `dangle.py`/`transform_clip.py` if their JS sources exist) — ported per Step 8
- [ ] `client/engine/entity_renderer.py` — same routing behavior as `entityRenderer.js` for 2D/billboard/mesh entities and `render_template` resolution
- [ ] `client/engine/asset_loader.py` — manifest-driven resolution, filesystem reads instead of `fetch`
- [ ] `client/engine/network.py` — `socketio.Client()` handling the full event list from Step 11, same emitted event names/payloads as the JS client (zero backend changes required)
- [ ] `client/engine/input.py` — GLFW key/mouse callbacks driven by the same `input_config.json`
- [ ] `client/engine/interpolation.py` — direct numeric port
- [ ] `client/game/*.py` — player select, character creation, HUD rebuilt in imgui-bundle with full functional parity (not necessarily pixel parity) with the JS screens
- [ ] `client/main.py` + updated root `main.py`/`run.bat` — server bootstrap reproduced, native window replaces PyWebView, no `webview.*` calls remain
- [ ] `backend/` unmodified — zero changes to Flask routes, SocketIO events, ECS, or tick loop
- [ ] `frontend/js/engine/`, `frontend/js/game/`, `run_browser.py` marked legacy/deprecated in docs, not deleted, and still functionally unmodified
- [ ] `ARCHITECTURE.md`, `README.md`, `CLAUDE.md`, `docs/DEBIAN_SETUP.md` updated to describe `client/` as the primary desktop path
- [ ] Full smoke test (Step 18) passes on at least Windows; Linux verified directly if a Linux environment is available, otherwise verified by absence of any WebKitGTK/PyWebView dependency in the new path
