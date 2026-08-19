"""SocketIO network client -- connects to the (unmodified) Flask/
SocketIO backend.

Port of frontend/js/engine/network.js -- Step 11 of
.github/prompts/wgpu-py-migration.prompt.md. Uses python-socketio's
synchronous `socketio.Client()` (already a project dependency, used
server-side today) rather than `AsyncClient` -- matches every other
`load()`-style method in this port in not committing to an
asyncio-first design.

**Deliberate architectural fix, not a straight port**: the JS version's
`initNetwork()` calls `handleInitialState`/`handleStateUpdate` (defined
in frontend/js/game/main.js) directly, and checks
`gameState.context === GameContext.PLAYER_SELECT` (also a game-layer
concept, from the same file) before auto-requesting the save list on
connect. Both are `client/engine/` -> `client/game/` references, which
violates this project's own "Engine code never imports game content"
rule (CLAUDE.md) -- already true of the JS version, just structurally
possible there because every `<script>` shares one global scope. Python
has no equivalent implicit sharing, so this port doesn't recreate the
violation: `set_state_handlers()` (extending the same explicit-callback
pattern the JS version *already* uses correctly for
`characterFlowCallbacks`) lets whichever game-layer module owns
connection/state concerns register `on_initial_state`/`on_state_update`/
`on_connect` handlers. The "auto-request save list if in player-select"
decision moves entirely into whatever `on_connect` handler the caller
registers -- this module has no opinion on `GameContext` at all.
"""

import json
from pathlib import Path
from typing import Callable, Optional

import socketio

# client/engine/network.py -> client/engine -> client -> repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]
ENGINE_CONFIG_PATH = REPO_ROOT / "config" / "engine.json"

# The shared SocketIO client instance, created by init_network(). Mirrors
# the JS version's module-level `socket` variable (populated by
# initNetwork(), not at declaration) and its `window.socket` exposure --
# other modules import this reference directly instead of reaching into
# a window global.
sio: "socketio.Client | None" = None

# Character flow callbacks. Network layer forwards onboarding-related
# events through this dict -- ported unchanged from network.js, this
# part of the JS design already respects the engine/game boundary
# correctly.
character_flow_callbacks: dict = {
    "on_save_list": None,
    "on_new_player_initialized": None,
    "on_character_created": None,
    "on_races_list": None,
    "on_backgrounds_list": None,
    "on_character_flow_error": None,
}

# State/connection callbacks -- this port's generalization of the same
# pattern to replace the JS version's direct handleInitialState/
# handleStateUpdate/GameContext references. All optional; a caller only
# sets the ones it needs.
_state_handlers: dict = {
    "on_initial_state": None,
    "on_state_update": None,
    "on_connect": None,
}


def set_character_flow_callbacks(callbacks: Optional[dict]) -> None:
    """Register character flow callbacks.

    Args:
        callbacks: dict with any of the keys in character_flow_callbacks
            above, each a callable or None.
    """
    if not callbacks or not isinstance(callbacks, dict):
        return

    for key in character_flow_callbacks:
        character_flow_callbacks[key] = callbacks.get(key)


def _invoke_character_flow_callback(callback_name: str, payload) -> None:
    """Invoke a registered character flow callback safely."""
    callback = character_flow_callbacks.get(callback_name)
    if not callable(callback):
        return
    try:
        callback(payload)
    except Exception as err:  # noqa: BLE001 -- matches the JS catch-all
        print(f"[network] Character flow callback failed: {callback_name}: {err}")


def set_state_handlers(
    on_initial_state: Optional[Callable] = None,
    on_state_update: Optional[Callable] = None,
    on_connect: Optional[Callable] = None,
) -> None:
    """Register connection/state handlers -- the engine-boundary-safe
    replacement for the JS version's direct handleInitialState/
    handleStateUpdate calls and GameContext check. See module docstring.
    """
    if on_initial_state is not None:
        _state_handlers["on_initial_state"] = on_initial_state
    if on_state_update is not None:
        _state_handlers["on_state_update"] = on_state_update
    if on_connect is not None:
        _state_handlers["on_connect"] = on_connect


def _client_url() -> str:
    """Build the URL to connect to, from config/engine.json's port --
    deliberately *not* its host (0.0.0.0 is a server bind address, not
    something a client can connect to); always connects to 127.0.0.1,
    matching this port's Constraints section.
    """
    port = 5000
    if ENGINE_CONFIG_PATH.exists():
        try:
            config = json.loads(ENGINE_CONFIG_PATH.read_text(encoding="utf-8"))
            port = config.get("port", 5000)
        except (OSError, json.JSONDecodeError):
            pass
    return f"http://127.0.0.1:{port}"


def init_network() -> None:
    """Initialize the SocketIO connection and register event handlers.

    Connects to the server and registers handlers for the full event
    list network.js currently handles: connect, disconnect,
    connection_response, initial_state, state_update, save_list,
    races_list, backgrounds_list, save_complete, autosave_complete,
    player_loaded, error, player_deleted, new_player_initialized,
    character_created.
    """
    global sio
    sio = socketio.Client()

    @sio.event
    def connect():
        print("[network] Connected to server")
        on_connect = _state_handlers.get("on_connect")
        if callable(on_connect):
            on_connect()

    @sio.event
    def disconnect():
        print("[network] Disconnected from server")

    @sio.on("connection_response")
    def on_connection_response(data):
        print(f"[network] Connection response: {data}")

    @sio.on("initial_state")
    def on_initial_state_event(data):
        print(f"[network] Received initial state: {data}")
        handler = _state_handlers.get("on_initial_state")
        if callable(handler):
            handler(data)

    @sio.on("state_update")
    def on_state_update_event(data):
        handler = _state_handlers.get("on_state_update")
        if callable(handler):
            handler(data)

    @sio.on("save_list")
    def on_save_list(data):
        print(f"[network] Received save list: {data}")
        _invoke_character_flow_callback("on_save_list", data)

    @sio.on("races_list")
    def on_races_list(data):
        _invoke_character_flow_callback("on_races_list", data)

    @sio.on("backgrounds_list")
    def on_backgrounds_list(data):
        _invoke_character_flow_callback("on_backgrounds_list", data)

    @sio.on("save_complete")
    def on_save_complete(data):
        print(f"[network] Save complete: {data}")
        if data.get("status") == "error":
            print(f"[network] Save failed: {data.get('message')}")

    @sio.on("autosave_complete")
    def on_autosave_complete(data):
        print(f"[network] Autosave: {data.get('status')} at tick {data.get('tick')}")

    @sio.on("player_loaded")
    def on_player_loaded(data=None):
        # Real bug, found via a real socket.io round trip against the
        # running backend (not assumed): backend/app.py's
        # handle_load_game() emits 'player_loaded' TWICE for one real
        # load -- once with NO payload at all right after
        # SaveManager.load_game() (a vestigial "save file loaded OK"
        # signal), and again later with the actual full game-state
        # payload. python-socketio's client calls this handler with
        # zero arguments for the first one, which crashed with
        # TypeError against the original `def on_player_loaded(data):`
        # signature (no default) -- every single real player load hit
        # this. `data=None` default plus an explicit skip below fixes
        # it without changing the backend's emission shape.
        print(f"[network] Player loaded: {data}")
        if not data:
            return
        handler = _state_handlers.get("on_initial_state")
        if callable(handler):
            handler(data)

    @sio.on("error")
    def on_error(data):
        print(f"[network] Server error: {data.get('message')}")
        _invoke_character_flow_callback("on_character_flow_error", data)

    @sio.on("player_deleted")
    def on_player_deleted(data):
        print(f"[network] Player deleted: {data.get('player_id')}")
        sio.emit("request_save_list")

    @sio.on("new_player_initialized")
    def on_new_player_initialized(data):
        print(f"[network] New player initialized: {data.get('player_id')}")
        _invoke_character_flow_callback("on_new_player_initialized", data)

    @sio.on("character_created")
    def on_character_created(data):
        print(f"[network] Character created successfully: {data}")
        _invoke_character_flow_callback("on_character_created", data)

    sio.connect(_client_url())
    print("[network] Network initialized")


def send_player_action(action_type: str, **params) -> None:
    """Send a player action to the server.

    Args:
        action_type: e.g. 'move', 'attack', 'interact'.
        **params: Additional parameters for the action.
    """
    sio.emit("player_action", {"type": action_type, **params})


def send_party_command(member_id: str, command_type: str, **params) -> None:
    """Send a command to a party member.

    Args:
        member_id: ID of the party member to command.
        command_type: e.g. 'move_to', 'attack', 'follow'.
        **params: Additional parameters for the command.
    """
    sio.emit("party_command", {"member_id": member_id, "type": command_type, **params})
