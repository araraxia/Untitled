"""Generic, config-driven OSC sender -- Phase 8, Step 6 of
`.github/prompts/audio.prompt.md`. Thin wrapper around `python-osc`'s
`SimpleUDPClient`, mirroring where `backend/engine/events.py`/
`spatial.py`/`group.py` already live: a reusable engine capability with
zero game-content awareness. Deciding *which* gameplay event maps to
*which* OSC cue is Step 7's job, on a game branch, in
`backend/game/systems/` -- this module only knows how to send a
message, never what the message means or when to send it.

**OSC address scheme (a design decision this file makes -- the prompt
left exact wire format unspecified)**: tempo goes to `/tempo` as a
single float arg; patterns and events go to `/pattern/<name>` /
`/event/<event_name>` respectively, each carrying one JSON-encoded
string as `payload`. OSC has no native dict type; JSON keeps this
wrapper's payload shape unconstrained (matches this project's
JSON-everywhere convention for area/manifest/config files) instead of
inventing a bespoke flatten/unflatten scheme SuperCollider would need
to match exactly.

**Config**: reads `config/engine.json` directly via `json.loads`,
pulling `config["audio"]["supercollider"]` for host/port/enabled/
auto_launch -- deliberately NOT through `backend.engine.config`'s
`EngineConfig` (a flat, strictly-typed dataclass with no nested-block
support); see the prompt file's own Constraints section for why.

**No-op safe by design**: disabled config, a client-construction
failure, or `send_message()` raising are all caught and logged as a
warning, never propagated. Note what `is_available()` actually means,
though, since OSC over UDP is fire-and-forget by nature (confirmed:
sending to a syntactically valid host:port with nothing listening
raises nothing at all) -- it reflects "enabled, and the last local
`send_message()` call didn't raise," not "SuperCollider is actually
receiving these." That's the honest guarantee UDP gives; Step 7's
future game-layer caller uses it to decide whether to also invoke
`client.engine.audio` for the same cue, not as a delivery receipt.
"""

import json
import subprocess
from pathlib import Path

from pythonosc.udp_client import SimpleUDPClient

from backend.independant_logger import Logger

REPO_ROOT = Path(__file__).resolve().parents[2]
ENGINE_CONFIG_PATH = REPO_ROOT / "config" / "engine.json"

logger = Logger(log_name="osc", log_file="osc.log", log_level=20).get_logger()

_DEFAULT_SUPERCOLLIDER_CONFIG = {
    "enabled": True,
    "host": "127.0.0.1",
    "port": 57120,
    "auto_launch": False,
    "launch_command": "scsynth",
}

_client: "SimpleUDPClient | None" = None
_enabled = True
_last_send_ok = True
_scsynth_process: "subprocess.Popen | None" = None


def _read_supercollider_config() -> dict:
    config = dict(_DEFAULT_SUPERCOLLIDER_CONFIG)
    if not ENGINE_CONFIG_PATH.exists():
        return config
    try:
        data = json.loads(ENGINE_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        logger.warning(f"Failed to read {ENGINE_CONFIG_PATH}: {err}")
        return config
    config.update(data.get("audio", {}).get("supercollider", {}))
    return config


def init() -> None:
    """Create the UDP client (and optionally launch scsynth). Safe to
    call more than once -- re-reads config and recreates the client.
    """
    global _client, _enabled, _last_send_ok
    config = _read_supercollider_config()
    _enabled = bool(config.get("enabled", True))
    _last_send_ok = True

    if not _enabled:
        _client = None
        logger.info("SuperCollider/OSC disabled in config; sender is a no-op")
        return

    host = config.get("host", "127.0.0.1")
    port = int(config.get("port", 57120))
    try:
        _client = SimpleUDPClient(host, port)
    except Exception as err:  # no-op safe -- see module docstring
        _client = None
        logger.warning(f"Failed to create OSC client for {host}:{port}: {err}")
        return

    if config.get("auto_launch", False):
        _launch_scsynth(config.get("launch_command", "scsynth"))


def _launch_scsynth(command: str) -> None:
    global _scsynth_process
    if _scsynth_process is not None and _scsynth_process.poll() is None:
        return  # already running
    try:
        _scsynth_process = subprocess.Popen(
            [command], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except OSError as err:
        logger.warning(f"Failed to launch {command!r}: {err}")
        _scsynth_process = None


def shutdown() -> None:
    """Stop a launched scsynth process, if any. Not part of Step 6's
    literal API table, but the natural counterpart to init()/
    _launch_scsynth() -- needed for a clean process exit or test
    teardown.
    """
    global _scsynth_process
    if _scsynth_process is not None and _scsynth_process.poll() is None:
        _scsynth_process.terminate()
    _scsynth_process = None


def is_available() -> bool:
    """See module docstring's note on what this does and doesn't
    guarantee, given UDP's fire-and-forget nature.
    """
    return _enabled and _client is not None and _last_send_ok


def _send(address: str, value) -> None:
    global _last_send_ok
    if not _enabled or _client is None:
        return
    try:
        _client.send_message(address, value)
        _last_send_ok = True
    except Exception as err:  # no-op safe -- see module docstring
        _last_send_ok = False
        logger.warning(f"OSC send to {address!r} failed: {err}")


def send_tempo(bpm: float) -> None:
    _send("/tempo", float(bpm))


def send_pattern(name: str, payload: dict) -> None:
    _send(f"/pattern/{name}", json.dumps(payload))


def send_event(event_name: str, payload: dict) -> None:
    _send(f"/event/{event_name}", json.dumps(payload))
