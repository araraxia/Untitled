---
agent: agent
description: Implement the integrated audio engine for Phase 8 with SuperCollider + OSC event mapping as the primary method, and the in-engine Web Audio path focused on basic fallback tasks.
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
of `ROADMAP.md` (sections 8.1-8.4). Phase 5 (Asset Pipeline) is a
prerequisite and is complete.

Treat SuperCollider + OSC as the primary runtime audio path for
event-driven music behavior. The in-engine Web Audio `AudioEngine`
remains required, but should focus on basic tasks (UI sounds, simple
fallback music, and safe degraded behavior when OSC is unavailable).

Complete all steps in order. Each step must leave the application in a
runnable state before proceeding to the next.

---

## Required Reading

Read these files before writing any code:

- `ROADMAP.md` — Phase 8 specification (sections 8.1-8.4)
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
- SuperCollider + OSC event mapping is the default orchestration path
  for dynamic music and game-state-reactive audio behavior.
- SocketIO naming must follow existing project conventions:
  client->server events use `request_*`, server->client events use
  descriptive snake_case names (for example: `play_music`,
  `play_sfx`, `save_complete`). Payload keys must use snake_case.
- `AudioContext` must not be created until after a user gesture (click
  or keydown) to comply with browser autoplay policy. Gate all
  `AudioEngine` initialisation behind this interaction.
- Web Audio is the fallback/basic path and must remain available when
  SuperCollider is disabled, not installed, or fails at runtime.
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

## Step 3 — Primary Audio Path: SuperCollider + OSC Event Mapping

**Files to modify:** `backend/app.py`, `config/engine.json`,
`requirements.txt`, `frontend/js/engine/network.js`,
`frontend/js/game/main.js`

Implement SuperCollider + OSC as the primary event-driven audio runtime.
This step is not optional.

### Config and dependency setup

1. Add an `audio.supercollider` block to `config/engine.json`:

```json
"supercollider": {
  "enabled": true,
  "host": "127.0.0.1",
  "port": 57120,
  "auto_launch": false,
  "launch_command": "scsynth"
}
```

2. Add `python-osc` to `requirements.txt` with a pinned version.

### Backend OSC bridge (`backend/app.py`)

1. Add an OSC sender wrapper initialised from config.
2. Add helpers:

```python
def osc_send_tempo(bpm: float) -> None: ...
def osc_send_pattern(name: str, payload: dict) -> None: ...
def osc_send_event(event_name: str, payload: dict) -> None: ...
```

3. Add optional process launch/supervision when
   `audio.supercollider.auto_launch` is true.
4. Ensure send paths are no-op safe when disabled or unavailable.

### Required event mapping

- `area_enter` -> tempo or scene pattern change
- `combat_start` -> intensity layer/pattern trigger
- `low_health` -> warning texture/sidechain cue

Payloads should include `event_name`, `timestamp`, `area_id`, `intensity`,
`hp_ratio` where applicable.

### Frontend control wiring

Add client->server debug controls in `network.js`/`main.js` for local
validation of OSC dispatches without full gameplay.

Use these SocketIO event names for OSC dispatch requests/results:

- client -> server: `request_osc_event`
- server -> client: `osc_dispatch_complete`

Use this payload schema for `request_osc_event`:

```json
{
  "event_name": "area_enter|combat_start|low_health",
  "timestamp": 0,
  "area_id": "string-or-null",
  "intensity": 0.0,
  "hp_ratio": 1.0
}
```

Use this payload schema for `osc_dispatch_complete`:

```json
{
  "status": "ok|error|fallback",
  "event_name": "string",
  "message": "string"
}
```

---

## Step 4 — Event Routing Integration (OSC-first)

**Files to modify:** `frontend/js/engine/network.js`,
`frontend/js/game/main.js`, `backend/app.py`

Create an OSC-first event routing contract:

1. Server emits snake_case audio intent events (`play_music`,
   `stop_music`, `play_sfx`) and gameplay event signals mapped to OSC
   (`area_enter`, `combat_start`, `low_health`).
2. Frontend routes those intents to backend OSC dispatch endpoints first.
3. If OSC is unavailable, frontend invokes basic `AudioEngine` fallback
   handlers for simple playback.

Add or extend callbacks to preserve this order:

```text
intent event -> OSC dispatch attempt -> fallback Web Audio action
```

---

## Step 5 — Basic Audio Engine Fallback (Phase 8.1-8.3 subset)

**New file:** `frontend/js/engine/audioEngine.js`
**Files to modify:** `frontend/index.html`,
`frontend/js/engine/network.js`, `frontend/js/game/main.js`

### Scope of this step

Implement only the basic in-engine behaviors needed as fallback:

- UI SFX playback
- Simple music start/stop with optional fade
- Spatial SFX support sufficient for degraded mode
- Listener position updates from camera

Do not treat this step as the primary orchestration layer.

Create a minimal `AudioEngine` wrapper with only the fallback APIs used
in this prompt (`init`, `load`, `playMusic`, `stopMusic`, `playSFX`,
`playUISFX`, `updateListener`). Add its script in `frontend/index.html`
before `network.js`.

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

After `audioEngine` is created, register fallback callbacks:

```js
setPlayMusicCallback(({ asset_id, crossfade = true }) => {
  audioEngine
    .load(asset_id)
    .then(() => audioEngine.playMusic(asset_id, { crossfade }));
});
setStopMusicCallback(({ fade = true }) => audioEngine.stopMusic({ fade }));
```

---

## Step 6 — Spatial SFX Fallback Integration

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

## Step 7 — Backend SocketIO Stubs

**File to modify:** `backend/app.py`

Add the following SocketIO event stubs. These are development helpers
that let the frontend be exercised without a full game session; they will
be replaced with real game-driven emissions in a later phase.

```python
@socketio.on("request_play_music")
def handle_request_play_music(data):
    """Debug: emit a play_music event back to the requesting client."""
    ...

@socketio.on("request_play_sfx")
def handle_request_play_sfx(data):
    """Debug: emit a play_sfx event back to the requesting client."""
    ...

@socketio.on("request_osc_event")
def handle_request_osc_event(data):
    """Dispatch an OSC event and report completion status to client."""
    ...
```

Also add a helper that the game tick can call to broadcast music changes
on area transition:

```python
def emit_play_music(asset_id: str, crossfade: bool = True) -> None:
    """Broadcast a play_music event to all connected clients."""
    socketio.emit(
        "play_music",
        {"asset_id": asset_id, "crossfade": crossfade},
    )

def emit_play_sfx(asset_id: str, world_x: float, world_y: float) -> None:
    """Broadcast a play_sfx event to all connected clients."""
    socketio.emit(
        "play_sfx",
        {"asset_id": asset_id, "world_x": world_x, "world_y": world_y},
    )
```

Verify:

```bash
python -c "from backend.app import app; print('app ok')"
```

---

## Step 8 — Asset Pipeline Update

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

## Step 9 — OSC Production Hardening

**Files to modify:** `backend/app.py`, `config/engine.json`,
`requirements.txt`, `frontend/js/engine/network.js`,
`frontend/js/game/main.js`

Harden the primary SuperCollider + OSC pipeline for production behavior
and observability. Do not re-implement setup from Step 3.

### Hardening tasks

1. Add OSC health tracking and last-send status for diagnostics.
2. Add rate limiting/debouncing for high-frequency game events.
3. Add bounded retry logic for transient OSC send failures.
4. Add a dead-letter log path for dropped OSC messages.
5. Add structured warning logs that include event name and payload size.
6. Add a clear fallback decision path in logs when Web Audio handles an
   event due to OSC unavailability.

### Frontend diagnostics

Expose a debug callback/state in `main.js` that reports whether each
audio intent was handled by OSC or fallback Web Audio.

### Verification

```bash
python -c "from backend.app import app; print('app ok')"
```

When SuperCollider is unavailable, verify startup succeeds, a warning is
logged, and basic Web Audio fallback still works.

---

## Step 10 — ROADMAP Update

**File to modify:** `ROADMAP.md`

Mark Phase 8 as complete in the phase progress table and add the prompt
file reference at the bottom of the Phase 8 section:

```text
**Prompt file:** `.github/prompts/audio.prompt.md`
```
