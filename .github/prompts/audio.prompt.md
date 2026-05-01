---
agent: agent
description: Implement the integrated audio engine for music and spatial sound effects (Phase 8 of ROADMAP.md). Covers Web Audio API wrapper, music bus with crossfade, spatial SFX, audio manifest, and backend SocketIO events.
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

# Task: Audio (Phase 8)

You are implementing the audio engine for this project. This is Phase 8
of `ROADMAP.md`. Phase 5 (Asset Pipeline) is a prerequisite and is
complete.

Complete all steps in order. Each step must leave the application in a
runnable state before proceeding to the next.

---

## Required Reading

Read these files before writing any code:

- `ROADMAP.md` — Phase 8 specification (sections 8.1–8.3)
- `frontend/assets/manifest.json` — current asset registry; the `"audio"`
  section is an empty object; audio entries will be added here
- `frontend/js/engine/assetLoader.js` — `AssetLoader`; audio file URLs
  will be resolved through it
- `frontend/js/engine/network.js` — existing SocketIO event registrations;
  audio trigger events (`play_music`, `play_sfx`, `stop_music`) will be
  added here
- `frontend/js/game/main.js` — `GameContext`, `gameState`, `initUI()`
  wiring; `AudioEngine` initialises here on the first user interaction
- `frontend/js/engine/renderer.js` — render loop and camera state;
  the camera `x`/`y` position defines the Web Audio listener position
- `frontend/index.html` — script load order; new audio scripts will be
  added in the Engine section
- `backend/app.py` — SocketIO event handlers; audio trigger stubs will
  be added here
- `config/engine.json` — runtime config; `audio` settings block will be
  added here

---

## Constraints

- Follow the Airbnb JavaScript style guide for all JS: 2-space indent,
  single quotes, semicolons.
- All new JS classes and public functions must have JSDoc comments.
- `AudioContext` must not be created until after a user gesture (click
  or keydown) to comply with browser autoplay policy. Gate all
  `AudioEngine` initialisation behind this interaction.
- All audio routed through the three gain buses (`music`, `sfx`,
  `ambient`) before the master gain. Never connect a source node
  directly to `AudioContext.destination`.
- Volume values are 0.0–1.0 floats. Bus levels are configurable via
  `config/engine.json` and must not be hard-coded.
- Spatial audio uses `PannerNode` with `panningModel: 'HRTF'` and
  `distanceModel: 'inverse'`. The reference distance and max distance
  are read from the theme/config, not hard-coded.
- `fetch()` is used to load audio files; do not use `<audio>` elements.
- File naming: new JS files use camelCase (`audioEngine.js`).
- Run `python -c "from backend.app import app; print('app ok')"` after
  any Python changes to confirm no import errors.

---

## Step 1 — Audit Current State

Before writing any code, read the key files listed above and produce a
short summary covering:

1. What the `"audio"` section of `manifest.json` currently contains, and
   what schema shape other sections use (so audio entries match it).
2. What SocketIO events in `network.js` are already registered, and
   whether any carry audio-related payloads today.
3. How `gameState.camera` is structured (fields, types) in `main.js` or
   `renderer.js`, since it will drive the listener position.
4. Whether any interaction-gate logic (first-click / first-keydown)
   already exists in `main.js` or `input.js`.
5. What audio files (if any) are already present under
   `frontend/assets/audio/music/` and `frontend/assets/audio/sfx/`.

Do not create or edit any files in this step. Output findings, then
proceed.

---

## Step 2 — Audio Manifest & Config (Phase 8 prerequisite)

**Files to modify:** `config/engine.json`,
`frontend/assets/manifest.json`

### `config/engine.json`

Add an `"audio"` block:

```json
"audio": {
  "master_volume":    1.0,
  "music_volume":     0.6,
  "sfx_volume":       1.0,
  "ambient_volume":   0.5,
  "spatial_ref_distance":  100,
  "spatial_max_distance":  1500,
  "crossfade_duration_ms": 1500
}
```

### `frontend/assets/manifest.json`

Populate the `"audio"` section with the schema below. Add one entry per
audio file found under `frontend/assets/audio/`. If no files exist yet,
add two placeholder stubs so the loader has something to exercise:

```json
"audio": {
  "<asset_id>": {
    "path":   "assets/audio/<subdir>/<filename>",
    "type":   "music" | "sfx" | "ambient",
    "loop":   true | false,
    "loop_start_s": 0.0,
    "loop_end_s":   null
  }
}
```

- `type` is `"music"` for files under `music/`, `"sfx"` for files under
  `sfx/`, and `"ambient"` for any looping background textures.
- `loop_start_s` / `loop_end_s` define loop points (in seconds).
  `loop_end_s: null` means loop to the natural end of the file.
- `loop` is `true` for music and ambient, `false` for sfx.

---

## Step 3 — AudioEngine (Phase 8.1)

**New file:** `frontend/js/engine/audioEngine.js`  
**Files to modify:** `frontend/index.html`, `frontend/js/game/main.js`

### `frontend/js/engine/audioEngine.js`

```js
/**
 * AudioEngine — Web Audio API wrapper providing master gain, three
 * named buses (music, sfx, ambient), and spatial SFX support.
 *
 * Initialisation is deferred until the first user gesture.
 */
```

The class must expose:

```js
class AudioEngine {
  /**
   * @param {object} config  - The engine config `audio` block.
   * @param {AssetLoader} assetLoader
   */
  constructor(config, assetLoader) { ... }

  /**
   * Create the AudioContext and bus graph.
   * Must be called from a user-gesture handler (click / keydown).
   * Safe to call more than once — subsequent calls are no-ops.
   */
  init() { ... }

  /**
   * Pre-fetch and decode an audio asset into an AudioBuffer.
   * Resolved buffers are cached by asset ID.
   * @param {string} assetId - Key from manifest `audio` section.
   * @returns {Promise<AudioBuffer>}
   */
  async load(assetId) { ... }

  /**
   * Set the gain for a named bus.
   * @param {'master'|'music'|'sfx'|'ambient'} bus
   * @param {number} value - 0.0–1.0
   */
  setVolume(bus, value) { ... }

  /**
   * Play a music track, optionally crossfading from the current one.
   * @param {string} assetId
   * @param {object} [opts]
   * @param {boolean} [opts.crossfade=true]
   */
  playMusic(assetId, opts = {}) { ... }

  /**
   * Stop the current music track.
   * @param {object} [opts]
   * @param {boolean} [opts.fade=true]
   */
  stopMusic(opts = {}) { ... }

  /**
   * Fire-and-forget spatial SFX.
   * @param {string}  assetId
   * @param {number}  worldX  - World-space X of the source.
   * @param {number}  worldY  - World-space Y of the source.
   */
  playSFX(assetId, worldX, worldY) { ... }

  /**
   * Play a non-spatial (UI) SFX.
   * @param {string} assetId
   */
  playUISFX(assetId) { ... }

  /**
   * Update the Web Audio listener position from the camera.
   * Call once per frame before spatial SFX are fired.
   * @param {number} cameraX
   * @param {number} cameraY
   */
  updateListener(cameraX, cameraY) { ... }
}
```

#### Bus graph

```
[source nodes]
     │
[PannerNode]  ← spatial SFX only; UI SFX bypass the panner
     │
[sfx GainNode]  /  [music GainNode]  /  [ambient GainNode]
     └─────────────────┬────────────────────────┘
               [master GainNode]
                       │
            [AudioContext.destination]
```

#### Music crossfade

`playMusic(assetId, { crossfade: true })` must:

1. Start the new track at gain 0 on the music bus (a separate per-source
   `GainNode` chained into the music bus).
2. Ramp the new track gain from 0 → 1 over `crossfade_duration_ms`.
3. Ramp the previous track gain from 1 → 0 over the same duration, then
   stop the old source node.

Use `AudioParam.linearRampToValueAtTime` for ramps.

#### Loop points

When creating a `BufferSourceNode` for a `loop: true` asset, set:

```js
source.loop = true;
source.loopStart = manifest.audio[assetId].loop_start_s;
if (manifest.audio[assetId].loop_end_s !== null) {
  source.loopEnd = manifest.audio[assetId].loop_end_s;
}
```

#### Spatial positioning

`playSFX` creates a `PannerNode` configured as:

```js
panner.panningModel = "HRTF";
panner.distanceModel = "inverse";
panner.refDistance = config.spatial_ref_distance;
panner.maxDistance = config.spatial_max_distance;
panner.rolloffFactor = 1;
panner.setPosition(worldX, worldY, 0);
```

The Web Audio listener (`audioContext.listener`) must be updated each
frame via `updateListener(cameraX, cameraY)`. Set only `positionX` /
`positionY` (and `positionZ = 0`); do not alter orientation.

### Wiring into `main.js`

1. Add a module-level `let audioEngine = null;` variable.
2. In the first-user-interaction handler (or create one if absent):
   ```js
   audioEngine = new AudioEngine(engineConfig.audio, assetLoader);
   audioEngine.init();
   ```
3. Call `audioEngine.updateListener(gameState.camera.x, gameState.camera.y)`
   in the render loop, after camera state is updated.

### `frontend/index.html`

Add the script tag for `audioEngine.js` in the Engine section, before
`network.js`.

---

## Step 4 — Music Playback Integration (Phase 8.2)

**Files to modify:** `frontend/js/engine/network.js`,
`frontend/js/game/main.js`

### SocketIO events in `network.js`

Register the following events. Expose setter callbacks so other modules
can subscribe without touching `network.js` internals.

```js
socket.on("play_music", (data) => {
  // data: { asset_id: string, crossfade?: boolean }
  if (onPlayMusic) onPlayMusic(data);
});

socket.on("stop_music", (data) => {
  // data: { fade?: boolean }
  if (onStopMusic) onStopMusic(data);
});
```

Expose:

```js
function setPlayMusicCallback(fn) {
  onPlayMusic = fn;
}
function setStopMusicCallback(fn) {
  onStopMusic = fn;
}
```

### Wiring into `main.js`

After `audioEngine` is created, register the callbacks:

```js
setPlayMusicCallback(({ asset_id, crossfade = true }) => {
  audioEngine
    .load(asset_id)
    .then(() => audioEngine.playMusic(asset_id, { crossfade }));
});
setStopMusicCallback(({ fade = true }) => audioEngine.stopMusic({ fade }));
```

---

## Step 5 — Spatial SFX Integration (Phase 8.3)

**Files to modify:** `frontend/js/engine/network.js`,
`frontend/js/game/main.js`

### SocketIO event in `network.js`

```js
socket.on("play_sfx", (data) => {
  // data: { asset_id: string, world_x: number, world_y: number }
  // world_x / world_y absent for UI SFX
  if (onPlaySFX) onPlaySFX(data);
});
```

Expose `setPlaySFXCallback(fn)`.

### Wiring into `main.js`

```js
setPlaySFXCallback(({ asset_id, world_x, world_y }) => {
  if (world_x !== undefined && world_y !== undefined) {
    audioEngine.playSFX(asset_id, world_x, world_y);
  } else {
    audioEngine.playUISFX(asset_id);
  }
});
```

---

## Step 6 — Backend SocketIO Stubs

**File to modify:** `backend/app.py`

Add the following SocketIO event stubs. These are development helpers
that let the frontend be exercised without a full game session; they will
be replaced with real game-driven emissions in a later phase.

```python
@socketio.on('request_play_music')
def handle_request_play_music(data):
    """Debug: emit a play_music event back to the requesting client."""
    ...

@socketio.on('request_play_sfx')
def handle_request_play_sfx(data):
    """Debug: emit a play_sfx event back to the requesting client."""
    ...
```

Also add a helper that the game tick can call to broadcast music changes
on area transition:

```python
def emit_play_music(asset_id: str, crossfade: bool = True) -> None:
    """Broadcast a play_music event to all connected clients."""
    socketio.emit('play_music', {'asset_id': asset_id, 'crossfade': crossfade})
```

Verify:

```bash
python -c "from backend.app import app; print('app ok')"
```

---

## Step 7 — Asset Pipeline Update

**Files to modify:** `tools/build_assets.py`, `tools/build_manifest.py`
(or whichever script generates `manifest.json`)

Update the manifest builder so that it:

1. Scans `frontend/assets/audio/music/` and `frontend/assets/audio/sfx/`
   for `.ogg`, `.mp3`, and `.wav` files.
2. Derives the asset ID from the filename without extension
   (e.g. `town_day.ogg` → `"town_day"`).
3. Infers `"type"` from the subdirectory (`music/` → `"music"`,
   `sfx/` → `"sfx"`).
4. Sets `"loop": true` for music, `"loop": false` for sfx.
5. Sets `"loop_start_s": 0.0` and `"loop_end_s": null` as defaults;
   these can be overridden by a sidecar `<filename>.meta.json` if
   present.
6. Writes the results into the `"audio"` section of `manifest.json`,
   replacing any previous audio entries.

If `build_assets.py` is the orchestrator, ensure this scan step is
included in its run sequence.

---

## Step 8 — ROADMAP Update

**File to modify:** `ROADMAP.md`

Mark Phase 8 as complete in the phase progress table and add the prompt
file reference at the bottom of the Phase 8 section:

```text
**Prompt file:** `.github/prompts/audio.prompt.md`
```
