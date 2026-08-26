"""Fallback Python audio playback engine -- Phase 8, Step 3 of
`.github/prompts/audio.prompt.md`. Rebuilt replacement for the deleted
`frontend/js/engine/audioEngine.js`'s Web Audio `AudioEngine`; see that
prompt file's own framing for why this exists (SuperCollider + OSC is
the primary event-driven path, this is basic-tasks fallback only --
UI sounds, simple music/SFX, safe degraded behavior) and what it
deliberately does not build (real HRTF spatialization, a node-graph
API, procedural audio generation -- see the prompt's own "What this
step explicitly does not build" note).

No browser concepts carry over: this opens a real output device at
`init()`, called once at client startup like `renderer.init_renderer()`
-- no `AudioContext`, no user-gesture gate, no `fetch()`. Files are
read straight off disk via `asset_loader.resolve()`/`get_entry()`.

Backed by `miniaudio` (decode + device output) -- confirmed installed
from a prebuilt wheel and able to open a device and play a real
project asset on Windows during this task's own "confirm the
dependency" checkpoint (`audio.prompt.md` Step 3); Linux confirmation
is still outstanding, see that step's own note about updating
`docs/DEBIAN_SETUP.md` once checked there. Bus mixing, crossfade, and
spatial pan/attenuation are hand-rolled directly over `miniaudio`
rather than pulling in `synthplayer` -- a deliberate, recorded choice,
see the prompt file's own "Considered and rejected" note in Step 3.

**Threading, not optional**: `miniaudio.PlaybackDevice` pulls PCM
frames from `_mixer_generator()` on its own audio-callback thread,
while `play_music()`/`play_sfx()`/etc. run on whichever thread calls
them (the main thread, and potentially `client/engine/network.py`'s
SocketIO callback thread too, once Step 4 wires this module in). Every
mutation or snapshot-read of the shared `_voices` list goes through
`_voices_lock` -- a short critical section around the list itself
only, never held across the actual per-frame mixing math, so the audio
thread is never blocked waiting on a caller.

**Config**: reads `config/engine.json`'s `"audio"` block directly via
`json.loads` in `_read_config()`, deliberately NOT through
`backend.engine.config`'s `EngineConfig` -- that's a flat, strictly
-typed dataclass with no nested-block support; see the prompt file's
own Constraints section for why this bypass is intentional, not an
oversight.

**Deviation from the prompt's literal Step 3 API table, noted**:
`play_ambient()` isn't in that table, but Step 2 already introduced an
`"ambient"` bus and manifest `type` with no public function to
actually start one playing -- added here (mirrors `play_music()`'s
streaming approach, minus crossfade, since ambient loops don't need
cross-track blending) rather than leaving that bus permanently silent.

**Real bug found via the prompt's own required stress test, not
theorized**: the mixer's per-sample Python mixing loop performs fine
at realistic voice counts (confirmed clean at 40 concurrent voices,
rapid-fire from 4 threads) but cannot keep the audio callback's
real-time deadline at extreme counts -- 1200 concurrent voices never
drained even 2.5s after they should have finished; the callback was
too slow to make progress. `_MAX_SFX_VOICES` caps concurrent sfx/ui
voices at 64 so a runaway `play_sfx()` caller (a spam bug, not normal
gameplay) degrades to "some sounds get dropped" instead of stalling
audio for everyone -- re-verified after adding the cap: same 1200-call
stress test now settles at 64 concurrent voices and drains to 0
cleanly afterward.
"""

import array
import json
import math
import threading
from pathlib import Path
from typing import Optional

import miniaudio

from backend.independant_logger import Logger
from client.engine.asset_loader import FRONTEND_DIR, asset_loader

REPO_ROOT = Path(__file__).resolve().parents[2]
ENGINE_CONFIG_PATH = REPO_ROOT / "config" / "engine.json"

_SAMPLE_RATE = 44100
_CHANNELS = 2
_SAMPLE_FORMAT = miniaudio.SampleFormat.SIGNED16
_INT16_MIN, _INT16_MAX = -32768, 32767

# Hard cap on simultaneous sfx/ui voices -- confirmed empirically, not
# guessed: the mixer's per-sample Python loop (see _mixer_generator)
# keeps up fine at dozens of simultaneous voices (a realistic worst
# case) but real-time-audio-thread-stalls at ~1000+ (tested: 1200
# concurrent voices never drained, even 2.5s after they should have
# finished -- the mixer callback simply couldn't complete fast enough
# to keep pace with the device). Music/ambient aren't capped here --
# they're normally 1-2 concurrent voices even mid-crossfade, not the
# realistic attack surface for a spam bug the way per-frame play_sfx()
# calls are.
_MAX_SFX_VOICES = 64

logger = Logger(
    log_name="audio", log_file="audio.log", log_level=20
).get_logger()

_DEFAULT_AUDIO_CONFIG = {
    "master_volume": 1.0,
    "music_volume": 0.6,
    "sfx_volume": 1.0,
    "ambient_volume": 0.5,
    "spatial_ref_distance": 100.0,
    "spatial_max_distance": 1500.0,
    "crossfade_duration_ms": 1500.0,
}

_master_volume = 1.0
_bus_volumes = {"music": 1.0, "sfx": 1.0, "ambient": 1.0}
_spatial_ref_distance = 100.0
_spatial_max_distance = 1500.0
_crossfade_duration_ms = 1500.0

_device: "miniaudio.PlaybackDevice | None" = None

# The only state the audio-callback thread and callers both touch --
# see module docstring's threading note. Voice objects themselves are
# only ever mutated by the mixer thread once appended here; callers
# only ever construct a brand-new Voice and append/remove it.
_voices: "list[_Voice]" = []
_voices_lock = threading.Lock()

# Decoded sfx/ui buffers only (short clips) -- never a music/ambient
# track, see module docstring / Step 3's "don't fully decode a
# multi-minute track into memory". Read/written only from whichever
# thread calls play_sfx()/play_ui_sfx()/load(), never the mixer thread;
# a benign race between two calling threads just means decoding the
# same file twice, not corruption -- not worth a second lock here.
_decoded_cache: dict = {}

_listener_position = [0.0, 0.0, 0.0]
_listener_forward = [0.0, 0.0, 1.0]
_listener_right = [1.0, 0.0, 0.0]
_listener_lock = threading.Lock()

_current_music_voice: "_Voice | None" = None


def _read_config() -> dict:
    config = dict(_DEFAULT_AUDIO_CONFIG)
    if not ENGINE_CONFIG_PATH.exists():
        return config
    try:
        data = json.loads(ENGINE_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        logger.warning(f"Failed to read {ENGINE_CONFIG_PATH}: {err}")
        return config
    config.update(data.get("audio", {}))
    return config


class _Voice:
    """One in-progress sound: either a fully-decoded buffer (sfx/ui --
    short) or a `miniaudio.stream_file()` generator (music/ambient --
    long). Only ever touched by the mixer thread once added to
    `_voices` under `_voices_lock`.
    """

    def __init__(
        self,
        asset_id: str,
        bus: str,
        path: "str | None" = None,
        samples: "array.array | None" = None,
        stream=None,
        loop: bool = False,
        loop_start_frame: int = 0,
        loop_end_frame: "int | None" = None,
        gain: float = 1.0,
        position: "list[float] | None" = None,
    ) -> None:
        self.asset_id = asset_id
        self.bus = bus
        self.path = path
        self.samples = samples
        self.stream = stream
        self.loop = loop
        self.loop_start_frame = loop_start_frame
        self.loop_end_frame = loop_end_frame
        self.gain = gain
        self.position = position
        self.frame_pos = 0
        self.stream_pos = loop_start_frame if stream is not None else 0
        self.finished = False

        # Fade state for crossfade/stop-fade -- see play_music()/
        # stop_music(). fade_gain ramps linearly from fade_from to
        # fade_to over fade_frames_total frames.
        self.fade_from = 1.0
        self.fade_to = 1.0
        self.fade_frames_total = 0
        self.fade_frames_done = 0

    def current_fade_gain(self, frames: int) -> float:
        if self.fade_frames_total <= 0:
            return self.fade_to
        t = min(1.0, self.fade_frames_done / self.fade_frames_total)
        gain = self.fade_from + (self.fade_to - self.fade_from) * t
        self.fade_frames_done += frames
        return gain

    def fade_out_complete(self) -> bool:
        return (
            self.fade_frames_total > 0
            and self.fade_frames_done >= self.fade_frames_total
            and self.fade_to == 0.0
        )

    def _restart_stream_at_loop(self) -> None:
        self.stream = miniaudio.stream_file(
            self.path,
            output_format=_SAMPLE_FORMAT,
            nchannels=_CHANNELS,
            sample_rate=_SAMPLE_RATE,
            seek_frame=self.loop_start_frame,
        )
        next(self.stream)
        self.stream_pos = self.loop_start_frame

    def read(self, n_frames: int) -> array.array:
        """Return exactly n_frames of interleaved stereo int16 samples
        (zero-padded once the voice ends and isn't looping), and set
        self.finished when there's nothing left to give.
        """
        if self.stream is not None:
            return self._read_stream(n_frames)
        return self._read_buffer(n_frames)

    def _read_buffer(self, n_frames: int) -> array.array:
        total_frames = len(self.samples) // _CHANNELS
        out = array.array("h", bytes(n_frames * _CHANNELS * 2))
        written = 0
        while written < n_frames:
            if self.frame_pos >= total_frames:
                if self.loop:
                    self.frame_pos = 0
                else:
                    self.finished = True
                    break
            take = min(n_frames - written, total_frames - self.frame_pos)
            src_start = self.frame_pos * _CHANNELS
            src_end = src_start + take * _CHANNELS
            dst_start = written * _CHANNELS
            dst_end = dst_start + take * _CHANNELS
            out[dst_start:dst_end] = self.samples[src_start:src_end]
            self.frame_pos += take
            written += take
        return out

    def _read_stream(self, n_frames: int) -> array.array:
        out = array.array("h", bytes(n_frames * _CHANNELS * 2))
        written = 0
        while written < n_frames:
            want = n_frames - written
            if self.loop_end_frame is not None:
                remaining = self.loop_end_frame - self.stream_pos
                if remaining <= 0:
                    self._restart_stream_at_loop()
                    continue
                want = min(want, remaining)
            try:
                chunk = self.stream.send(want)
            except StopIteration:
                chunk = array.array("h")
            got_frames = len(chunk) // _CHANNELS
            if got_frames == 0:
                if self.loop:
                    self._restart_stream_at_loop()
                    continue
                self.finished = True
                break
            dst_start = written * _CHANNELS
            dst_end = dst_start + got_frames * _CHANNELS
            out[dst_start:dst_end] = chunk
            written += got_frames
            self.stream_pos += got_frames
        return out


def _spatial_gains(position: "list[float]") -> "tuple[float, float]":
    """Manual approximation of `PannerNode`/HRTF -- see
    `audio.prompt.md`'s Constraints ("Spatial audio is a manual
    approximation... true HRTF-quality spatialization is
    SuperCollider's job, not this fallback path's"). Equal-power
    stereo pan from the source's position relative to the listener's
    right axis, plus linear distance attenuation between
    `spatial_ref_distance` (full volume) and `spatial_max_distance`
    (silent).
    """
    with _listener_lock:
        lx, ly, lz = _listener_position
        rx, ry, rz = _listener_right
    dx, dy, dz = position[0] - lx, position[1] - ly, position[2] - lz
    distance = math.sqrt(dx * dx + dy * dy + dz * dz)

    if distance <= _spatial_ref_distance:
        attenuation = 1.0
    elif distance >= _spatial_max_distance:
        attenuation = 0.0
    else:
        span = _spatial_max_distance - _spatial_ref_distance
        attenuation = 1.0 - (distance - _spatial_ref_distance) / span

    pan = 0.0 if distance < 1e-6 else (dx * rx + dy * ry + dz * rz) / distance
    pan = max(-1.0, min(1.0, pan))

    angle = (pan + 1.0) * (math.pi / 4.0)  # [-1, 1] -> [0, pi/2]
    return math.cos(angle) * attenuation, math.sin(angle) * attenuation


def _mixer_generator():
    """The single generator `PlaybackDevice.start()` pulls from -- runs
    on miniaudio's own audio-callback thread. Sums every active
    voice's gain-adjusted (and, for spatial voices, pan/attenuated)
    samples into one interleaved stereo int16 buffer per pull.
    """
    n_frames = yield array.array("h")
    while True:
        with _voices_lock:
            voices_snapshot = list(_voices)

        mix = [0] * (n_frames * _CHANNELS)
        finished = []
        for voice in voices_snapshot:
            samples = voice.read(n_frames)
            fade_gain = voice.current_fade_gain(n_frames)
            bus_gain = _bus_volumes.get(voice.bus, 1.0) * _master_volume
            if voice.position is not None:
                left_gain, right_gain = _spatial_gains(voice.position)
            else:
                left_gain = right_gain = 1.0
            g_left = bus_gain * fade_gain * voice.gain * left_gain
            g_right = bus_gain * fade_gain * voice.gain * right_gain
            for i in range(n_frames):
                mix[i * 2] += int(samples[i * 2] * g_left)
                mix[i * 2 + 1] += int(samples[i * 2 + 1] * g_right)
            if voice.finished or voice.fade_out_complete():
                finished.append(voice)

        if finished:
            with _voices_lock:
                for voice in finished:
                    if voice in _voices:
                        _voices.remove(voice)
                    # _current_music_voice already points at whichever
                    # voice replaced this one (play_music()) or was
                    # cleared to None (stop_music()) by the time this
                    # runs -- nothing to do with it here.

        clipped = (max(_INT16_MIN, min(_INT16_MAX, v)) for v in mix)
        out = array.array("h", clipped)
        n_frames = yield out


def init() -> None:
    """Open the output device and start the mixer. Called once at
    client startup, like `renderer.init_renderer()` -- not gated on
    any user interaction. Safe to call more than once (re-reads
    config, but won't reopen an already-open device).
    """
    global _device, _master_volume, _spatial_ref_distance
    global _spatial_max_distance, _crossfade_duration_ms

    config = _read_config()
    _master_volume = float(config.get("master_volume", 1.0))
    _bus_volumes["music"] = float(config.get("music_volume", 0.6))
    _bus_volumes["sfx"] = float(config.get("sfx_volume", 1.0))
    _bus_volumes["ambient"] = float(config.get("ambient_volume", 0.5))
    _spatial_ref_distance = float(config.get("spatial_ref_distance", 100.0))
    _spatial_max_distance = float(config.get("spatial_max_distance", 1500.0))
    _crossfade_duration_ms = float(config.get("crossfade_duration_ms", 1500.0))

    if _device is not None:
        return

    gen = _mixer_generator()
    next(gen)  # PlaybackDevice.start() requires an already-started generator
    try:
        device = miniaudio.PlaybackDevice(
            output_format=_SAMPLE_FORMAT,
            nchannels=_CHANNELS,
            sample_rate=_SAMPLE_RATE,
        )
        device.start(gen)
    except miniaudio.MiniaudioError as err:
        logger.warning(f"Failed to open audio output device: {err}")
        return
    _device = device
    logger.info("Audio device opened, mixer running.")


def shutdown() -> None:
    """Stop and close the output device. Not part of Step 3's literal
    API table, but the natural counterpart to init() -- needed for a
    clean process exit or test teardown (Step 5).
    """
    global _device
    if _device is None:
        return
    try:
        _device.stop()
        _device.close()
    except miniaudio.MiniaudioError as err:
        logger.warning(f"Error closing audio device: {err}")
    _device = None
    with _voices_lock:
        _voices.clear()


def _resolve_path(asset_id: str) -> str:
    return str(FRONTEND_DIR / asset_loader.resolve(asset_id))


def _get_decoded(
    asset_id: str, path: str
) -> "miniaudio.DecodedSoundFile | None":
    cached = _decoded_cache.get(asset_id)
    if cached is not None:
        return cached
    try:
        decoded = miniaudio.decode_file(
            path,
            output_format=_SAMPLE_FORMAT,
            nchannels=_CHANNELS,
            sample_rate=_SAMPLE_RATE,
        )
    except miniaudio.DecodeError as err:
        logger.warning(f"Failed to decode {asset_id!r} ({path}): {err}")
        return None
    _decoded_cache[asset_id] = decoded
    return decoded


def load(asset_id: str) -> None:
    """Resolve and pre-decode/cache asset_id ahead of first playback.
    Optional -- play_*() calls do this lazily too; this just avoids a
    decode hitch on the first play. Only meaningful for sfx/ui assets
    (fully decoded and cached); music/ambient assets are streamed on
    demand instead (see module docstring), so this just confirms they
    decode without caching a full buffer for them.
    """
    entry = asset_loader.get_entry("audio", asset_id) or {}
    kind = entry.get("type", "sfx")
    path = _resolve_path(asset_id)
    if kind == "sfx":
        _get_decoded(asset_id, path)
        return
    try:
        miniaudio.get_file_info(path)
    except miniaudio.DecodeError as err:
        logger.warning(f"load(): {asset_id!r} failed to decode: {err}")


def _make_stream_voice(asset_id: str, bus: str) -> "_Voice | None":
    entry = asset_loader.get_entry("audio", asset_id) or {}
    path = _resolve_path(asset_id)
    loop = bool(entry.get("loop", True))
    loop_start_s = float(entry.get("loop_start_s") or 0.0)
    loop_end_s = entry.get("loop_end_s")
    loop_start_frame = int(loop_start_s * _SAMPLE_RATE)
    loop_end_frame = int(loop_end_s * _SAMPLE_RATE) if loop_end_s else None

    try:
        stream = miniaudio.stream_file(
            path,
            output_format=_SAMPLE_FORMAT,
            nchannels=_CHANNELS,
            sample_rate=_SAMPLE_RATE,
        )
        next(stream)
    except miniaudio.DecodeError as err:
        logger.warning(
            f"Failed to open {asset_id!r} ({path}) for streaming: {err}"
        )
        return None

    return _Voice(
        asset_id=asset_id,
        bus=bus,
        path=path,
        stream=stream,
        loop=loop,
        loop_start_frame=loop_start_frame,
        loop_end_frame=loop_end_frame,
    )


def play_music(asset_id: str, crossfade: bool = True) -> None:
    global _current_music_voice
    new_voice = _make_stream_voice(asset_id, "music")
    if new_voice is None:
        return

    fade_ms = _crossfade_duration_ms
    fade_frames = int((fade_ms / 1000.0) * _SAMPLE_RATE) if crossfade else 0
    if fade_frames:
        new_voice.fade_from = 0.0
        new_voice.fade_to = 1.0
        new_voice.fade_frames_total = fade_frames

    with _voices_lock:
        old_voice = _current_music_voice
        if old_voice is not None:
            if crossfade and fade_frames:
                old_voice.fade_from = old_voice.current_fade_gain(0)
                old_voice.fade_to = 0.0
                old_voice.fade_frames_total = fade_frames
                old_voice.fade_frames_done = 0
            elif old_voice in _voices:
                _voices.remove(old_voice)
        _voices.append(new_voice)
        _current_music_voice = new_voice


def stop_music(fade: bool = True) -> None:
    global _current_music_voice
    with _voices_lock:
        voice = _current_music_voice
        _current_music_voice = None
        if voice is None:
            return
        if fade and _crossfade_duration_ms > 0:
            voice.fade_from = voice.current_fade_gain(0)
            voice.fade_to = 0.0
            voice.fade_frames_total = int(
                (_crossfade_duration_ms / 1000.0) * _SAMPLE_RATE
            )
            voice.fade_frames_done = 0
        elif voice in _voices:
            _voices.remove(voice)


def play_ambient(asset_id: str, loop: bool = True) -> None:
    """Not in Step 3's original public-API table -- added because
    Step 2 already introduced an "ambient" bus/manifest type with no
    way to actually start one playing. Mirrors play_music()'s
    streaming approach, minus crossfade (ambient loops don't need
    cross-track blending the way music transitions do).
    """
    voice = _make_stream_voice(asset_id, "ambient")
    if voice is None:
        return
    voice.loop = loop
    with _voices_lock:
        _voices.append(voice)


def play_sfx(
    asset_id: str, world_x: float, world_y: float, world_z: float = 0.0
) -> None:
    _play_sfx_voice(asset_id, position=[world_x, world_y, world_z])


def play_ui_sfx(asset_id: str) -> None:
    """No spatialization -- always full volume on the sfx bus,
    position-independent.
    """
    _play_sfx_voice(asset_id, position=None)


def _play_sfx_voice(asset_id: str, position: "list[float] | None") -> None:
    path = _resolve_path(asset_id)
    decoded = _get_decoded(asset_id, path)
    if decoded is None:
        return
    voice = _Voice(
        asset_id=asset_id,
        bus="sfx",
        samples=decoded.samples,
        loop=False,
        position=position,
    )
    with _voices_lock:
        sfx_voice_count = sum(1 for v in _voices if v.bus == "sfx")
        if sfx_voice_count >= _MAX_SFX_VOICES:
            logger.debug(
                f"Sfx voice cap ({_MAX_SFX_VOICES}) reached, dropping"
                f" {asset_id!r}"
            )
            return
        _voices.append(voice)


def update_listener(
    position: "list[float]", forward: "list[float]", up: "list[float]"
) -> None:
    """Called once per frame by whatever owns the live camera dict --
    see `audio.prompt.md`'s camera_modes.py note for the exact call
    shape (`forward = normalize(target - position)`).
    """
    fx, fy, fz = forward
    flen = math.sqrt(fx * fx + fy * fy + fz * fz) or 1.0
    fx, fy, fz = fx / flen, fy / flen, fz / flen

    ux, uy, uz = up
    rx = fy * uz - fz * uy
    ry = fz * ux - fx * uz
    rz = fx * uy - fy * ux
    rlen = math.sqrt(rx * rx + ry * ry + rz * rz) or 1.0
    rx, ry, rz = rx / rlen, ry / rlen, rz / rlen

    with _listener_lock:
        _listener_position[:] = position
        _listener_forward[:] = [fx, fy, fz]
        _listener_right[:] = [rx, ry, rz]


def set_bus_volume(bus: str, value: float) -> None:
    if bus not in _bus_volumes:
        logger.warning(f"set_bus_volume(): unknown bus {bus!r}")
        return
    _bus_volumes[bus] = max(0.0, min(1.0, value))


def set_master_volume(value: float) -> None:
    global _master_volume
    _master_volume = max(0.0, min(1.0, value))
