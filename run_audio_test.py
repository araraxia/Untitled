"""[DEV ONLY] Standalone smoke test for client/engine/audio.py -- the
fallback Python playback engine (Phase 8, Step 5 of
.github/prompts/audio.prompt.md). No GPU, no imgui, no backend server,
no game branch involvement -- proves the engine-layer half (Steps 3-4)
actually works in isolation, since this branch cannot boot a real game
session to drive it end to end.

Mirrors run_zone_test.py/run_scene_test.py's no-GPU verification
pattern: a real, permanent script, not a one-off manual check.

**Volume capped at 50% for every test run, regardless of
config/engine.json's configured master_volume** -- this script plays
real audio out loud on whatever machine runs it; a full-volume blast
during an unattended/CI test run is a bad surprise, not a feature.
Production playback (a real game branch) is unaffected -- this cap
only ever applies inside this script.

Usage:
    python run_audio_test.py
"""

import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.independant_logger import Logger

logger = Logger(
    log_name="run_audio_test",
    log_file="audio_test.log",
    log_level=20,  # INFO
).get_logger()

from client.engine import audio
from client.engine.asset_loader import asset_loader

# See module docstring -- deliberate test-only cap, not the config value.
TEST_MASTER_VOLUME = 0.5

# Real project assets (Step 1's audit found these already in place).
# footstep1/hit4 stand in for a music track in the crossfade tests
# below too -- no real music/ambient file exists yet (frontend/assets/
# audio/music|ambient/ are empty), and miniaudio doesn't care about an
# asset's semantic category, only its data -- this still exercises the
# real streaming/crossfade code path end to end.
SFX_A = "footstep1"
SFX_B = "hit4"


def check(label: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    logger.info(f"[{status}] {label}")
    if not condition:
        raise AssertionError(label)


def voice_count() -> int:
    with audio._voices_lock:
        return len(audio._voices)


def wait_until_drained(timeout_s: float = 3.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if voice_count() == 0:
            return True
        time.sleep(0.05)
    return False


def test_play_ui_sfx_and_cleanup() -> None:
    audio.play_ui_sfx(SFX_B)
    check("play_ui_sfx: voice added", voice_count() == 1)
    check("play_ui_sfx: drains to 0 once finished", wait_until_drained())


def test_play_sfx_spatial() -> None:
    audio.play_sfx(SFX_A, 50.0, 0.0, 0.0)
    with audio._voices_lock:
        voices = list(audio._voices)
    check("play_sfx: voice added", len(voices) == 1)
    check("play_sfx: position stored", voices[0].position == [50.0, 0.0, 0.0])
    check("play_sfx: drains to 0 once finished", wait_until_drained())


def test_spatial_gain_math() -> None:
    audio.update_listener([0.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, 1.0, 0.0])
    check(
        "update_listener: right = cross(forward, up) = (-1, 0, 0)",
        audio._listener_right == [-1.0, 0.0, 0.0],
    )

    # A source directly ahead (on the forward axis) should pan center.
    left, right = audio._spatial_gains([0.0, 0.0, 50.0])
    check("spatial gain: source ahead pans ~center", abs(left - right) < 1e-6)

    # A source at ref distance should be at full attenuation (gain 1.0
    # combined across channels); one further than max distance should
    # be silent in both channels.
    left_near, right_near = audio._spatial_gains([0.0, 0.0, 50.0])
    left_far, right_far = audio._spatial_gains([0.0, 0.0, 999999.0])
    check(
        "spatial gain: within ref distance is louder than past max distance",
        (left_near + right_near) > (left_far + right_far),
    )
    check(
        "spatial gain: past max distance is silent",
        left_far == 0.0 and right_far == 0.0,
    )

    # A source to the listener's right should favor the right channel.
    # right axis here is (-1, 0, 0), so "to the right" is -X.
    left_r, right_r = audio._spatial_gains([-50.0, 0.0, 0.0])
    favors_right = right_r > left_r
    check("spatial gain: source to the right favors right ch.", favors_right)


def test_bus_and_master_volume_setters() -> None:
    audio.set_bus_volume("sfx", 0.25)
    check("set_bus_volume: clamped/stored", audio._bus_volumes["sfx"] == 0.25)
    audio.set_bus_volume("sfx", 5.0)  # out of range -> clamps to 1.0
    check("set_bus_volume: clamps above 1.0", audio._bus_volumes["sfx"] == 1.0)
    audio.set_bus_volume("nonexistent_bus", 1.0)  # must not raise

    audio.set_master_volume(0.3)
    check("set_master_volume: stored", audio._master_volume == 0.3)
    audio.set_master_volume(-1.0)  # out of range -> clamps to 0.0
    check("set_master_volume: clamps below 0.0", audio._master_volume == 0.0)

    # Restore the test-wide cap for the remaining tests.
    audio.set_master_volume(TEST_MASTER_VOLUME)
    audio.set_bus_volume("sfx", 1.0)


def test_music_crossfade_mechanics() -> None:
    audio.play_music(SFX_A, crossfade=False)
    with audio._voices_lock:
        voices = list(audio._voices)
    is_lone_music_voice = len(voices) == 1 and voices[0].bus == "music"
    check(
        "play_music (no crossfade): one voice, bus=music", is_lone_music_voice
    )
    no_fade = voices[0].fade_from == voices[0].fade_to == 1.0
    check("play_music (no crossfade): no fade applied", no_fade)

    audio.play_music(SFX_B, crossfade=True)
    with audio._voices_lock:
        voices = list(audio._voices)
    check("play_music (crossfade): two voices while fading", len(voices) == 2)
    outgoing = next(v for v in voices if v.asset_id == SFX_A)
    incoming = next(v for v in voices if v.asset_id == SFX_B)
    fades_out = outgoing.fade_from == 1.0 and outgoing.fade_to == 0.0
    check("crossfade: outgoing voice fades 1.0 -> 0.0", fades_out)
    fades_in = incoming.fade_from == 0.0 and incoming.fade_to == 1.0
    check("crossfade: incoming voice fades 0.0 -> 1.0", fades_in)
    is_current = audio._current_music_voice is incoming
    check("crossfade: current music voice is the new one", is_current)

    audio.stop_music(fade=False)
    voice_cleared = audio._current_music_voice is None
    check("stop_music(fade=False): current voice cleared", voice_cleared)
    removed = incoming not in audio._voices
    check("stop_music(fade=False): voice removed immediately", removed)

    # The outgoing crossfade voice is independent of stop_music() and
    # cleans itself up once its own fade-out completes.
    drained = wait_until_drained(timeout_s=3.0)
    check("crossfade: outgoing voice eventually drains on its own", drained)


def test_thread_safety_stress() -> None:
    """The prompt's own required check: rapid-fire play_sfx calls from
    multiple threads while audio is playing must not raise, and must
    respect _MAX_SFX_VOICES rather than degrading playback for
    everyone (see audio.py's module docstring -- a real bug, found
    and fixed via this exact test during Step 3).
    """
    errors = []

    def hammer() -> None:
        try:
            for _ in range(300):
                audio.play_sfx(SFX_A, 0.0, 0.0, 0.0)
        except Exception as err:  # any exception here is a real bug
            errors.append(err)

    threads = [threading.Thread(target=hammer) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    check(
        "stress test: no exceptions across 1200 concurrent calls", not errors
    )
    check(
        f"stress test: voice cap holds ({audio._MAX_SFX_VOICES})",
        voice_count() <= audio._MAX_SFX_VOICES,
    )
    drained = wait_until_drained(timeout_s=5.0)
    check("stress test: all voices eventually drain to 0", drained)


def main() -> None:
    logger.info("=" * 50)
    logger.info("[DEV ONLY] client/engine/audio.py smoke test")
    logger.info("=" * 50)

    asset_loader.load_manifest()
    audio.init()
    check("init(): device opened", audio._device is not None)

    audio.set_master_volume(TEST_MASTER_VOLUME)
    logger.info(f"Master volume capped at {TEST_MASTER_VOLUME} for this run.")

    try:
        test_play_ui_sfx_and_cleanup()
        test_play_sfx_spatial()
        test_spatial_gain_math()
        test_bus_and_master_volume_setters()
        test_music_crossfade_mechanics()
        test_thread_safety_stress()
    finally:
        audio.shutdown()

    logger.info(
        "PASS: init/shutdown, ui/spatial sfx playback + auto-cleanup, "
        "spatial pan/attenuation math, bus/master volume clamping, "
        "music streaming + crossfade mechanics, and the required "
        "cross-thread stress test (voice cap holds, no exceptions, "
        "clean drain) all verified."
    )


if __name__ == "__main__":
    main()
