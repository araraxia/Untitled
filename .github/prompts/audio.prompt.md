---
agent: agent
description: Implement the audio engine for Phase 8 on the native Python client/backend — SuperCollider + OSC event mapping as the primary runtime path, and a small Python playback engine (client/engine/audio.py) for basic fallback tasks. Rebuilt 2026-08-25 against the post-migration engine/game branch split; the previous version targeted the deleted frontend/js/ browser client.
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

You are implementing the audio engine for this project — Phase 8 of
`ROADMAP.md` (sections 8.1–8.4). Phase 5 (Asset Pipeline) is a
prerequisite and is complete.

> **Target client, read before anything else:** this task targets the
> native Python `client/` (wgpu-py + GLFW + imgui-bundle) and
> `backend/engine/`/`backend/game/`, per
> `.github/prompts/wgpu-py-migration.prompt.md` and CLAUDE.md's Branch
> model. **This is a full rebuild of this prompt file, not an edit** —
> the previous version was written against `frontend/js/` (`AudioContext`,
> `frontend/js/engine/network.js`, `frontend/js/game/main.js`,
> `backend/app.py` as always-present code), all of which is either
> deleted (the entire `frontend/js/` tree) or, for `backend/app.py`,
> no longer part of this branch at all — CLAUDE.md's Branch model
> section: `engine` carries engine/tooling code only, no game content
> and no bootable server; `backend/app.py` moved to game branches
> (`legacy` today) along with `backend/game/`/`client/game/`. Every
> step below is scoped against **this** branch's actual boundary, not
> the old one.

**Primary vs. fallback, unchanged in spirit from the original plan:**
SuperCollider + OSC is still the primary runtime audio path for
event-driven music behavior. A small in-engine Python playback engine
(`client/engine/audio.py`, replacing the old Web Audio `AudioEngine`)
remains required, but stays focused on basic tasks (UI sounds, simple
fallback music/SFX, safe degraded behavior when OSC/SuperCollider is
unavailable) — it is not a second full mixing/spatialization engine to
build to the same depth as SuperCollider.

**What's actually new here, architecturally:** a native desktop app
has no browser autoplay policy, no `fetch()`/`<audio>` elements, and no
`AudioContext` — the entire premise of the old 8.1 ("Web Audio API
Wrapper") no longer applies. And because `backend/app.py` doesn't
exist on `engine`, the *engine-layer* pieces (a generic playback
engine, a generic OSC sender, client-side SocketIO callback slots) are
what this task actually builds here; the *game-layer* pieces (which
concrete gameplay events map to which OSC cue or `play_music` call,
and `backend/app.py`'s own SocketIO handlers) are explicitly deferred
to a game branch, the same split every other cross-boundary phase in
this repo already follows (`ROADMAP.md` Phase 11/12/14 rows).

| Buildable on `engine` now | Blocked on a game branch |
| --- | --- |
| `client/engine/audio.py` — Python playback engine: bus mixing, basic spatial pan/attenuation, listener update from a plain position/forward vector | Deciding *when* `play_music`/`play_sfx`/an OSC cue fires for a real gameplay event (`combat_start`, `low_health`, an area-enter equivalent) |
| `client/engine/network.py` — `play_music`/`stop_music`/`play_sfx` callback slots (mirrors the existing `on_scene_cue` pattern) | `backend/app.py`'s SocketIO handlers that actually emit those events (doesn't exist on `engine` — a game branch supplies it, same as `handle_load_game()` today) |
| `backend/engine/osc.py` — generic, config-driven, no-op-safe OSC sender (`send_tempo`/`send_pattern`/`send_event`), mirroring where `SpatialGrid`/`GroupRegistry`/`EventBus` already live | A game branch's own `backend/game/systems/`-level system subscribing to `EventBus` and calling `osc.py` — mirrors exactly where `zones.prompt.md`'s per-tick driving code lives (`backend/game/area.py`'s `Area.update()`), not `backend/engine/` |
| Standalone smoke-testing (Step 5) via `area_viewer.py`, proving the plumbing works in isolation | Real end-to-end verification against actual gameplay triggers — needs a live game session, which `engine` cannot boot (CLAUDE.md's Running section) |

Manifest/config schema work (Step 2) has no "blocked" counterpart — it's
fully buildable now, nothing about it depends on a game branch.

Complete Steps 1–6 and 8–9 in order; each must leave the repository in
a state where `python -m py_compile` succeeds on everything touched
before proceeding to the next. **Step 7 is the one exception**: it is
documentation only on this branch (see its own header) and can never
be "completed" here — do not let it block Step 8 or 9. Treat it as
read, acknowledged, and skipped, not as a gate.

---

## Required Reading

Read these files before writing any code:

- `ROADMAP.md` Phase 8 (sections 8.1–8.4) and its Branch model section
  (top of the file) — the latter is *why* this task splits the way it
  does.
- CLAUDE.md's "Running" and "Networking" sections — confirms
  `backend/app.py` is game-branch-only and that `player_loaded`/
  `state_update` are the only contracts this branch defines; audio
  SocketIO events are additive to that contract, authored by whichever
  game branch implements Step 7.
- `frontend/assets/manifest.json`'s `"audio"` section and
  `tools/build_manifest.py`'s `audio_type()`/`AUDIO_EXTENSIONS`/the
  `audio_dir` scan block near the bottom of `build_manifest()` — **this
  already exists and already works** (scans `frontend/assets/audio/`,
  classifies `music`/`sfx` by subdirectory, hashes each file). Step 2
  extends this, it does not build it from scratch — read it first so
  you don't duplicate it.
- `client/engine/asset_loader.py` — `MANIFEST_CATEGORIES` already
  includes `"audio"`; `resolve(key)`/`list_category("audio")` are how
  the playback engine finds a file's path. This client reads files
  directly off disk (no `fetch()`) — see this module's own docstring
  for why.
- `client/engine/network.py` — **read this whole file**, especially
  `_state_handlers`/`set_state_handlers()` and the `on_scene_cue`
  event's handler + its rationale comment (the "engine code must never
  hold a direct `Scene` reference" rule). The new audio callback slots
  in Step 4 follow this exact pattern, not a new ad hoc mechanism.
- `client/engine/camera_modes.py`, `client/engine/free_camera.py` —
  every camera controller writes `position`/`target`/`up` into a plain
  `camera` dict via `apply(camera)`. The playback engine's listener
  update (Step 3) is driven the same way: whatever owns the live
  `camera` dict each frame calls `audio.update_listener(...)` from it,
  computing forward as `normalize(target - position)` — the playback
  engine itself never reaches into `Scene` or a camera controller
  directly.
- `client/engine/area_viewer.py` — the self-contained boot path (no
  network connection, no game branch needed) used to smoke-test
  engine-layer additions without a live backend, the same way
  `FreeCamera`/the gizmo/grid overlays are exercised today. Step 5
  uses this (or a small standalone script mirroring
  `run_client_test.py`'s pattern) to verify Step 3 actually plays
  something, since there is no game branch here to drive it end to
  end.
- `backend/engine/events.py` — `EventBus`, the pub/sub mechanism a game
  branch's Step 7 system subscribes to for gameplay-triggered audio
  cues (`ROADMAP.md`'s Phase 4 note: "other systems (audio, UI,
  particles) subscribe" to events like `CombatEvent`).
- `backend/engine/config.py` — `EngineConfig`/`_SCHEMA` is a flat,
  strictly-typed dataclass; it does not support nested blocks. Step 2's
  `"audio"` config block is deliberately **not** added to this schema
  (see that step for why) — read `load_engine_config()`'s filtering
  behavior (`{k: v for k, v in data.items() if k in _SCHEMA}`) to
  understand why a nested block would just be silently dropped if you
  tried.
- `config/engine.json` — current fields, for context on where the new
  `"audio"` block sits alongside them.

---

## Constraints

- Follow PEP 8 for all Python: 4-space indent, 79-column lines, type
  hints for non-trivial signatures. `snake_case.py` file names — no JS,
  no camelCase, anywhere in this task.
- **No browser constraints carry over.** There is no autoplay policy
  to gate against, no user-gesture requirement, no `AudioContext`, no
  `fetch()`, no `<audio>` element. The playback engine initializes at
  client startup like any other subsystem (`renderer.init_renderer()`
  is the pattern to match) and reads files directly off disk via
  `asset_loader.resolve()`.
- **Engine/game boundary is load-bearing, not a formality**:
  `client/engine/audio.py` and `backend/engine/osc.py` must never
  reference a specific gameplay event name (`combat_start`, etc.), a
  game-content asset ID, `Scene`, or any `client.game`/`backend.game`
  module. They are generic capabilities — "play this bus-tagged sound
  at this position," "send this OSC message" — the same way
  `SpatialGrid`/`GroupRegistry`/`EventBus` are generic. Deciding *which*
  gameplay event triggers *which* sound is Step 7's job, on a game
  branch, in `backend/game/systems/`.
- SuperCollider + OSC (Steps 6–7) is the default orchestration path for
  dynamic, event-driven music/audio behavior. The Python playback
  engine (Step 3) is fallback/basic-tasks scope and must remain
  available when SuperCollider is disabled, not installed, or fails at
  runtime — never make it a hard dependency of anything.
- SocketIO naming stays project convention (unchanged from before):
  client→server events use `request_*`, server→client events use
  descriptive snake_case names (`play_music`, `play_sfx`,
  `stop_music`). Payload keys are snake_case. This still applies
  because the transport (Flask-SocketIO ↔ `python-socketio` client) is
  unchanged — only which files implement each side changed.
- All audio goes through three named buses (`music`, `sfx`, `ambient`)
  before a master volume multiplier is applied — implemented as plain
  gain multiplication over PCM frames in the mixing callback (Step 3),
  not a Web Audio-style node graph. Never write a source's samples
  straight to the output device unmultiplied.
- Volume values are 0.0–1.0 floats. Bus levels and spatial-falloff
  distances come from `config/engine.json`'s `"audio"` block (Step 2),
  never hard-coded.
- Spatial audio is a **manual approximation**, not `PannerNode`/HRTF:
  stereo pan + distance-based gain attenuation computed once per
  mixer callback from the listener/source position vectors. Reference/
  max distance are still config-driven. State plainly in code comments
  that true HRTF-quality spatialization is SuperCollider's job, not
  this fallback path's.
- No third-party dependency beyond what this task explicitly adds
  (`miniaudio` for decode + device playback, `python-osc` for the OSC
  bridge) — do not pull in a general game-audio middleware (FMOD/Wwise
  bindings, `pygame.mixer`, etc.). Pin whatever version actually
  installs cleanly on both Windows and Linux (this project's two dev
  targets, see `docs/DEBIAN_SETUP.md`) in `requirements.txt`, with a
  rationale comment matching the existing `wgpu`/`glfw`/`imgui-bundle`
  entries' style.
- `config/engine.json`'s `"audio"` block is read directly via
  `json.loads` by both `client/engine/audio.py` and
  `backend/engine/osc.py` — **not** threaded through
  `backend/engine/config.py`'s `EngineConfig`. This mirrors
  `client/engine/network.py`'s own `_client_url()`, which already reads
  `config/engine.json`'s `port` field ad hoc rather than going through
  `EngineConfig`. Do not extend `_SCHEMA` for this.
- Run `python -m py_compile <changed files>` after every step. There is
  no `backend/app.py` on this branch to import-check against (the old
  `python -c "from backend.app import app; ..."` verification no
  longer applies here) — Step 7 (on a game branch) is where that kind
  of check belongs again.

---

## Step 1 — Audit Current State

Before writing any code, read the files listed above and produce a
short summary covering:

1. What `frontend/assets/manifest.json`'s `"audio"` section currently
   contains, and the exact shape `tools/build_manifest.py` writes
   into it today (confirm it's just `{"path", "type", "hash"}` — no
   loop metadata, no `"ambient"` type yet).
2. What `client/engine/network.py`'s `_state_handlers` dict and
   `on_scene_cue` event currently look like — the new audio callback
   slots must match that shape exactly.
3. Whether `client/engine/camera_modes.py`/`free_camera.py` exist yet
   and what shape the `camera` dict they write (`position`/`target`/
   `up`) takes — this defines `update_listener()`'s inputs.
4. What audio files (if any) already exist under
   `frontend/assets/audio/music/` and `frontend/assets/audio/sfx/`.
5. Confirm `backend/app.py` genuinely does not exist on this branch
   (`git show engine:backend/app.py` or a simple file check) before
   assuming Step 7 is out of scope here — don't take this prompt's
   word for it if the branch state has since changed.

Do not create or edit any files in this step. Output findings, then
proceed.

---

## Step 2 — Audio Manifest & Config

**Files to modify:** `config/engine.json`, `tools/build_manifest.py`

### `config/engine.json`

Add an `"audio"` block (read ad hoc, per Constraints — not part of
`EngineConfig`):

```json
"audio": {
  "master_volume":    1.0,
  "music_volume":     0.6,
  "sfx_volume":       1.0,
  "ambient_volume":   0.5,
  "spatial_ref_distance":  100,
  "spatial_max_distance":  1500,
  "crossfade_duration_ms": 1500,
  "supercollider": {
    "enabled": true,
    "host": "127.0.0.1",
    "port": 57120,
    "auto_launch": false,
    "launch_command": "scsynth"
  }
}
```

### `tools/build_manifest.py`

**Extend, don't replace**, the existing audio scan (`audio_type()` and
the `audio_dir` block in `build_manifest()`):

1. `audio_type()` currently returns only `"music"`/`"sfx"` based on
   whether `"music"` is in the path's parts. Add a third case:
   `"ambient"` when `"ambient"` is in the relative path's parts
   (`frontend/assets/audio/ambient/`), falling back to `"sfx"`
   otherwise — keep the existing `"music"` check first.
2. Add loop metadata to each audio entry: `"loop"` (`true` for
   `music`/`ambient`, `false` for `sfx`), `"loop_start_s": 0.0`, and
   `"loop_end_s": null` by default. Support an optional sidecar
   `<filename>.meta.json` next to the audio file to override
   `loop_start_s`/`loop_end_s`/`loop` — read it if present, same
   override pattern this file doesn't currently have for any category,
   so keep it narrowly scoped to audio only.
3. Verify: run `python tools/build_manifest.py` (or however it's
   invoked — check `tools/build_assets.py`'s orchestration if it
   wraps this) and confirm `frontend/assets/manifest.json`'s
   `"audio"` section now includes the new fields without breaking any
   existing non-audio section.

---

## Step 3 — Engine-Layer Fallback Playback Engine

**New file:** `client/engine/audio.py`

This is the rebuilt replacement for the old `AudioEngine`
(`frontend/js/engine/audioEngine.js`, deleted). No Web Audio concepts
carry over — this is a real audio device opened via `miniaudio`
(decode + output), mixed manually in Python.

**Considered and rejected, for the record**: `synthplayer` (same
author as `miniaudio`, built on top of it) already provides
generator-based real-time mixing of multiple short clips — it would
cover a chunk of the mixing work below out of the box. Deliberately
not used: it's a second, less-vetted dependency for a fallback path
that's explicitly basic-tasks scope (see the top-level framing above),
and this project generally prefers explicit, hand-rolled control over
a convenience abstraction (`docs/graphics/OVERVIEW.md`'s stated
Goals). Hand-roll the mixer directly over `miniaudio` instead. If a
future pass finds the hand-rolled mixer genuinely painful to maintain,
revisit this decision explicitly rather than silently pulling in
`synthplayer` mid-implementation.

### Before building: confirm the dependency

Do this before writing the mixer, not after — it's cheap to check and
expensive to discover late:

1. `pip install miniaudio`, open a `PlaybackDevice`, and play one real
   file to a speaker on **both** Windows and Linux (the project's two
   dev targets — `docs/DEBIAN_SETUP.md`). Confirm it installs from a
   prebuilt wheel or builds cleanly; note which.
2. If Linux needs a system package to build or run it (miniaudio talks
   to ALSA/PulseAudio directly — confirm whether that needs
   `libasound2-dev`/`libpulse-dev` at install time, or nothing extra),
   add a documented note to `docs/DEBIAN_SETUP.md`'s "System
   Dependencies Required" section, matching how `libglfw3`/
   `mesa-vulkan-drivers` are already documented there — do not leave
   this undocumented the way it would be if you only pinned the
   `requirements.txt` line.
3. Only proceed to the full mixer below once step 1 is confirmed
   working on both platforms.

### Scope

- Open one output device at init (module-level `init()` function,
  called once from client startup — mirrors `renderer.init_renderer()`,
  not gated on any user interaction).
- Three named buses (`music`, `sfx`, `ambient`) plus a master volume,
  all read from `config/engine.json`'s `"audio"` block at init and
  exposed as runtime-settable (`set_bus_volume(bus, value)`,
  `set_master_volume(value)`).
- A list of active "voices" (decoded-audio-in-progress + bus + gain +
  loop flag + optional world position for spatial sources); the
  device's per-frame audio callback sums all active voices' PCM
  frames, each multiplied by `bus_volume * master_volume` and, for
  spatial voices, a manually-computed stereo pan + distance
  attenuation (see Constraints) before mixing to the output buffer.
- **Thread safety, not optional**: `miniaudio`'s device callback runs
  on its own audio thread, while `play_music`/`play_sfx`/etc. are
  called from the main thread. Adding/removing voices from that list
  is a cross-thread mutation — guard it with a lock (a short critical
  section only around the list mutation, never held across the actual
  mixing math) or hand new voices off through a thread-safe queue the
  callback drains at the start of each invocation. Confirm this with a
  stress test (rapid-fire `play_sfx` calls from the main thread while
  audio is playing) before considering this step done — a race here
  fails silently or crashes intermittently, not on every run.
- Use `client/engine/audio.py`'s own `Logger` instance
  (`backend.independant_logger.Logger`, `log_name="audio"`,
  `log_file="audio.log"`) for failed loads/device errors — matching
  `area_viewer.py`'s established precedent for client-side engine
  modules, not `network.py`'s older bare-`print()` convention (both
  exist in this codebase today; use the `Logger`-based one for new
  code).
- Public API, matching the shape callers in Step 4 need:

```python
def init() -> None: ...
def load(asset_id: str) -> None:
    """Resolve asset_id via asset_loader and decode it, caching the
    decoded frames (or a re-openable decoder for long music tracks --
    don't fully decode a multi-minute track into memory)."""

def play_music(asset_id: str, crossfade: bool = True) -> None: ...
def stop_music(fade: bool = True) -> None: ...
def play_sfx(asset_id: str, world_x: float, world_y: float, world_z: float = 0.0) -> None: ...
def play_ui_sfx(asset_id: str) -> None:
    """No spatialization -- always full volume on the sfx bus, position-independent."""

def update_listener(position: "list[float]", forward: "list[float]", up: "list[float]") -> None:
    """Called once per frame by whatever owns the live camera dict --
    see Required Reading's camera_modes.py note for the exact call
    shape (normalize(target - position) for forward)."""

def set_bus_volume(bus: str, value: float) -> None: ...
def set_master_volume(value: float) -> None: ...
```

- Crossfade (`play_music(..., crossfade=True)`) is a linear gain
  ramp over `crossfade_duration_ms` between the outgoing and incoming
  music voice — implement it as a per-voice fade-in/fade-out gain
  curve applied inside the same mixing callback, not a separate timer
  thread.
- Loop points: honor `loop_start_s`/`loop_end_s` from the manifest
  entry (Step 2) when looping a decoded track — seek back to
  `loop_start_s` (in frames) instead of the file's start when playback
  reaches `loop_end_s` (or true EOF if `loop_end_s` is `null`).

### What this step explicitly does not build

Real HRTF spatialization, a node-graph/effects-chain API, procedural/
generative audio, or anything SuperCollider is meant to own. If a
requirement here starts looking like "basically reimplement
SuperCollider in Python," stop — that's scope creep into the primary
path's territory, not this fallback engine's job.

Verify: `python -m py_compile client/engine/audio.py`.

---

## Step 4 — Network Client Wiring

**File to modify:** `client/engine/network.py`

Add audio callback slots following the exact *shape* of the existing
`on_scene_cue` handler (a dict of optional callables, a `set_*`
registration function, `@sio.on(...)` handlers inside `init_network()`
that look up and invoke the registered callback — never a direct call
into `client/engine/audio.py` from this module, so the engine/network
boundary stays symmetric with the engine/audio boundary above).

**Deliberately a new `_audio_handlers` dict, not three more keys added
to `_state_handlers`**: this file already has two separate dicts for
two separate concerns (`_state_handlers` for connection/game-state
sync, `character_flow_callbacks` for onboarding) — audio intents are a
third, distinct concern, so a third dict follows the file's own
established "one dict per concern" precedent rather than overloading
`_state_handlers` with an unrelated responsibility.

```python
_audio_handlers: dict = {
    "on_play_music": None,
    "on_stop_music": None,
    "on_play_sfx": None,
}


def set_audio_handlers(
    on_play_music: Optional[Callable] = None,
    on_stop_music: Optional[Callable] = None,
    on_play_sfx: Optional[Callable] = None,
) -> None:
    ...
```

Register inside `init_network()`:

```python
@sio.on("play_music")
def on_play_music_event(data):
    # data: {"asset_id": str, "crossfade": bool}
    handler = _audio_handlers.get("on_play_music")
    if callable(handler):
        handler(data)

@sio.on("stop_music")
def on_stop_music_event(data):
    # data: {"fade": bool}
    ...

@sio.on("play_sfx")
def on_play_sfx_event(data):
    # data: {"asset_id": str, "world_x": float, "world_y": float,
    #        "world_z": float}  -- world_* absent/None for UI SFX
    ...
```

Whatever wires a real client together (a game branch's own
`client/main.py`-equivalent bootstrap, following the same pattern
`character_flow_callbacks`/`_state_handlers` already establish) calls
`set_audio_handlers(...)` with closures over its own
`client.engine.audio` calls — this module itself never imports
`client.engine.audio` directly, keeping it a pure event-routing layer.

Verify: `python -m py_compile client/engine/network.py`.

---

## Step 5 — Standalone Verification (no game branch needed)

**Files to modify:** `client/engine/area_viewer.py` (small, optional
addition) **or** a new standalone script mirroring
`run_client_test.py`'s pattern — pick whichever is less invasive.

Since this branch cannot boot a real game session, prove Steps 3–4
actually work with a minimal, self-contained smoke test:

1. Call `client.engine.audio.init()`, `load()` a real or placeholder
   file under `frontend/assets/audio/` (add one silent/short
   placeholder `.wav`/`.ogg` if none exist yet — note this in Step 1's
   findings), then `play_ui_sfx()` it and confirm audible output (or,
   in a headless CI-style check, confirm no exception and that a voice
   was actually added to the active-voices list).
2. Drive `update_listener()` from `area_viewer.py`'s existing
   `scene.camera` dict once per frame (same call site pattern as
   `free_cam.apply(scene.camera)`) if you extend `area_viewer.py`,
   purely to prove the position/forward plumbing works end to end —
   this is a dev-only smoke hook, not a real feature of the level
   editor, and must not be left enabled by default (gate it behind an
   explicit flag/env var, same spirit as this file's other dev-only
   additions).

This step's job is narrow: prove the engine-layer half works in
isolation. It is not where gameplay-triggered audio gets wired up —
that's Step 7, on a game branch.

---

## Step 6 — Engine-Layer OSC Sender

**New file:** `backend/engine/osc.py`
**File to modify:** `requirements.txt`

A generic, config-driven OSC sender — no game-event knowledge at all
(see Constraints). Mirrors `backend/engine/events.py`/`spatial.py`/
`group.py` in scope and placement: reusable capability, zero
game-content awareness.

1. Add `python-osc` to `requirements.txt` with a pinned version
   (`pythonosc.udp_client.SimpleUDPClient` is the actual class this
   wraps — confirmed against the package's own docs, not assumed).
2. Read `config/engine.json` directly (`json.loads`, same reasoning as
   Step 2/Constraints — not through `EngineConfig`) and pull out
   `config["audio"]["supercollider"]` for host/port/enabled/
   auto_launch.
3. Public API:

```python
def send_tempo(bpm: float) -> None: ...
def send_pattern(name: str, payload: dict) -> None: ...
def send_event(event_name: str, payload: dict) -> None: ...
def is_available() -> bool:
    """False when disabled in config, or the last send failed --
    callers (a future game branch's Step 7 system) use this to decide
    whether to also fall back to client.engine.audio for the same cue."""
```

4. All three send functions must be no-op safe: disabled config,
   unreachable host, or `python-osc` raising on send must never
   propagate an exception to the caller — catch it, log a warning via
   this module's own `Logger` instance (`backend.independant_logger.
   Logger`, `log_name="osc"`, `log_file="osc.log"` — establish this
   here, Step 8 only extends it), and return.
5. Optional `scsynth` process launch/supervision when
   `auto_launch` is true — a `subprocess.Popen` wrapper with basic
   liveness checking, not a full process manager.

Verify: `python -m py_compile backend/engine/osc.py` and
`python -c "from backend.engine.osc import send_event; send_event('smoke_test', {}); print('osc ok')"`
with SuperCollider *not* running — must print `osc ok` and log a
warning, not raise.

---

## Step 7 — Game-Layer Event Mapping (notes only — do not implement on `engine`)

This step cannot be completed on this branch — `backend/app.py`,
`backend/game/`, and `client/game/` don't exist here (CLAUDE.md's
Branch model). It's documented so whichever game branch picks this up
knows exactly what's expected, the same way `zones.prompt.md`'s
`Area.update()` wiring note and `area-system.prompt.md`'s game-layer
shim note work.

A game branch's own work, once it exists:

1. **`backend/game/systems/audio_system.py`** (or wherever that
   branch's own systems live, following its own `GameTick`/`Area`
   conventions) subscribes to `EventBus` for the real gameplay events
   (`combat_start`, `low_health`, an `area_enter` equivalent) and, for
   each, calls `backend.engine.osc.send_event(...)` with a payload
   shaped like:

   ```json
   {
     "event_name": "area_enter|combat_start|low_health",
     "timestamp": 0,
     "area_id": "string-or-null",
     "intensity": 0.0,
     "hp_ratio": 1.0
   }
   ```

   If `osc.is_available()` is `False`, this system also emits the
   equivalent `play_music`/`play_sfx` SocketIO event so
   `client.engine.audio` (Step 3) can cover the same cue in fallback
   mode.

2. **That branch's `backend/app.py`** adds the SocketIO emit helpers
   (`emit_play_music`, `emit_play_sfx`, mirroring `handle_load_game()`'s
   existing emit style) and, for local debugging without full
   gameplay, `request_play_music`/`request_play_sfx`/
   `request_osc_event` handlers that echo back the corresponding
   `play_music`/`play_sfx`/`osc_dispatch_complete` event.

3. Verification on that branch:
   `python -c "from backend.app import app; print('app ok')"` — this
   is the check the *old* version of this prompt file specified; it's
   correct again once a real `backend/app.py` exists, just not here.

---

## Step 8 — OSC Hardening (engine-layer portion, buildable now)

**File to modify:** `backend/engine/osc.py`

Health tracking, retries, and rate limiting are generic concerns that
belong in the sender itself, not in whichever game-layer system calls
it — extend Step 6's module:

1. Track last-send status/timestamp per event name for `is_available()`
   and future diagnostics.
2. Bounded retry (fixed small count, short backoff) for transient send
   failures — OSC is UDP/fire-and-forget, so "failure" here means the
   underlying socket call raising, not a delivery acknowledgment.
3. Simple rate limiting/debouncing per event name (config-driven
   minimum interval) so a high-frequency gameplay event (e.g. repeated
   `low_health` ticks) doesn't flood the OSC socket.
4. Structured warning logs (the `Logger` instance Step 6 already
   created, per CLAUDE.md's Logging section) including event name and
   payload size on any dropped/failed send.

Game-specific diagnostics (a debug UI panel reporting OSC-vs-fallback
per cue) are Step 7's job, on a game branch, once there's a real UI to
put it in.

Verify: `python -m py_compile backend/engine/osc.py`.

---

## Step 9 — ROADMAP Update

**File to modify:** `ROADMAP.md`

The Phase 8 section's 8.1–8.4 headers/content were already rewritten
to describe this architecture (`miniaudio`-based mixer, manual
spatialization, the engine/game split) as part of rebuilding this
prompt file itself, 2026-08-25 — confirm that text still matches what
Steps 1–6/8 actually built (implementation may have deviated; if so,
update the spec text to match reality, per this repo's own convention
of prompt/spec files tracking actual code, not the other way around).
What's *not* done yet is the Phase Progress table row itself. Update
the Phase Progress table's Phase 8 row with the
same density of detail Phases 11/12/14 already use: what's actually
implemented and verified on `engine`, and what remains explicitly
blocked on a game branch (Step 7) — do not mark Phase 8 "Complete" if
Step 7 hasn't happened anywhere, the same way Phase 11/12's rows stay
at "🔶 In Progress" for exactly this reason.

Add the prompt file reference if not already present in the phase
reference table near the bottom of `ROADMAP.md`:

```text
**Prompt file:** `.github/prompts/audio.prompt.md`
```
