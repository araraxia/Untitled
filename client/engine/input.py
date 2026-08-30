"""Dual input system: keyboard for player, mouse for party.

Port of frontend/js/engine/input.js -- Step 12 of
.github/prompts/wgpu-py-migration.prompt.md.

**Retroactive correction, found while researching Step 15's real
GLFW/wgpu/imgui integration, not caught by Step 12's own testing**:
this file originally registered raw `glfw.set_key_callback()`/
`glfw.set_cursor_pos_callback()`/`glfw.set_mouse_button_callback()`
directly on the GLFW window. That is broken: `renderer.py`'s
`RenderCanvas` (`rendercanvas.glfw`) *already* registers its own raw
GLFW callbacks on that exact window handle to power its own
backend-agnostic event system (`canvas.add_event_handler(...)`) --
confirmed by reading `rendercanvas/glfw.py` directly, not assumed.
GLFW only allows one callback per event type per window, so this
module's original `glfw.set_key_callback(window, ...)` call silently
*replaced* rendercanvas's own callback, breaking rendercanvas's entire
event system as an unintended side effect (Step 12's own test never
caught this because it never checked whether rendercanvas's other
event-driven behavior -- resize, close, and critically the events
`wgpu.utils.imgui.ImguiRenderer` needs for the UI to receive any input
at all -- still worked afterward).

Fixed by using `canvas.add_event_handler(...)` instead -- the same
mechanism `ImguiRenderer` itself uses (confirmed by reading
`wgpu/utils/imgui/imgui_renderer.py`), which supports multiple
independent handlers per event type via an `order` priority and
`event['stop_propagation']`. `ImguiRenderer` registers its own
handlers at `order=-99` (i.e. before this module's default `order=0`)
and sets `stop_propagation` when `io.want_capture_mouse`/
`want_capture_keyboard`/`want_text_input` is true -- e.g. while a text
field in `client/game/character_creation.py` is focused. Because this
module registers at the default order (*after* imgui's), that
mechanism correctly and automatically suppresses game input (WASD
movement, etc.) while an imgui widget is capturing the keyboard/mouse,
with zero code needed here to detect that case explicitly.

**Bonus simplification from the same fix**: `rendercanvas.glfw`'s own
`_on_key` already maps GLFW keycodes to DOM/JS-style `KeyboardEvent.key`
strings itself (its own `KEY_MAP` is explicitly commented "Map keys to
JS key definitions", citing the same MDN `KeyboardEvent.key` reference
this port has used throughout) -- named keys arrive as `"ArrowUp"`,
`"Escape"`, `"Tab"`, etc., and unmapped printable keys arrive as their
raw (lowercased-unless-Shift-held) character, e.g. `"w"`, `"p"`, or
`" "` for the spacebar. This is already exactly JS's `e.key` --
meaning `input_config.json`'s existing key names now resolve correctly
with a single `.lower()` call, no `_GLFW_KEY_NAMES` lookup table
needed at all (removed; the version of this file with that table was
built against raw GLFW callbacks, which no longer exist here).

**Mouse button numbering, re-derived for the real event source**:
`input_config.json`'s `mouse.select`/`mouse.contextMenu` (`0`/`2`) use
DOM convention (left=0, middle=1, right=2). `rendercanvas`'s own
pointer events use a *third*, 1-based numbering (confirmed by reading
`rendercanvas/glfw.py`'s `_on_mouse_button`: `MOUSE_BUTTON_1(left)->1,
MOUSE_BUTTON_2(right)->2, MOUSE_BUTTON_3(middle)->3`) -- different from
both DOM's convention and raw GLFW's own (left=0, right=1, middle=2).
`_DOM_TO_RENDERCANVAS_BUTTON` translates explicitly, replacing the
`_DOM_TO_GLFW_BUTTON` table from this file's original raw-callback
version.
"""

import math
import time
from typing import Callable, Optional

from client.engine import network
from client.engine.asset_loader import FRONTEND_DIR

# DOM mouse button convention (used by input_config.json, matching the
# JS client) -> rendercanvas's own pointer-event button numbering. See
# module docstring.
_DOM_TO_RENDERCANVAS_BUTTON = {
    0: 1,  # left
    1: 3,  # middle
    2: 2,  # right
}

_DEFAULT_KEY_CONFIG = {
    "movement": {
        "up": ["w", "arrowup"],
        "down": ["s", "arrowdown"],
        "left": ["a", "arrowleft"],
        "right": ["d", "arrowright"],
    },
    "actions": {
        "interact": ["e"],
        "inventory": ["i", "tab"],
        "menu": ["escape"],
    },
    "mouse": {"select": 0, "contextMenu": 2},
    "settings": {"inputPollingRate": 16, "movement_style": "area_relative"},
}

keys: dict[str, bool] = {}
mouse_x = 0.0
mouse_y = 0.0
key_config: "dict | None" = None

_input_handlers: dict = {
    "on_pause_toggle": None,  # called when a configured 'pause' key transitions up -> down
    "on_left_click": None,  # called (mouse_x, mouse_y) on a configured 'select' button press
    "on_right_click": None,  # called (mouse_x, mouse_y) on a configured 'contextMenu' button press
    "on_process": None,  # called once per throttled tick, see process_input()
}

_last_process_time = 0.0


def set_input_handlers(
    on_pause_toggle: Optional[Callable] = None,
    on_left_click: Optional[Callable] = None,
    on_right_click: Optional[Callable] = None,
    on_process: Optional[Callable] = None,
) -> None:
    """Register game-layer input handlers. See module docstring for why
    these are callbacks rather than this module reaching into game
    state directly.
    """
    if on_pause_toggle is not None:
        _input_handlers["on_pause_toggle"] = on_pause_toggle
    if on_left_click is not None:
        _input_handlers["on_left_click"] = on_left_click
    if on_right_click is not None:
        _input_handlers["on_right_click"] = on_right_click
    if on_process is not None:
        _input_handlers["on_process"] = on_process


def init_input(canvas) -> None:
    """Load key configuration and register event handlers on the given
    rendercanvas RenderCanvas instance (renderer.canvas) -- NOT a raw
    GLFW window handle, see module docstring for why.

    Registered at the default priority (order=0), which runs *after*
    `wgpu.utils.imgui.ImguiRenderer`'s own handlers (order=-99) --
    letting imgui consume/stop-propagate input it wants to capture
    (e.g. a focused text field) before this module ever sees it.

    Unlike the JS version's `setInterval(processInput, pollingRate)`,
    there is no internal timer here -- `process_input()` must be called
    externally once per frame (e.g. from the render loop); it
    self-throttles against `key_config['settings']['inputPollingRate']`
    internally, preserving the same "don't flood the network with
    per-frame move commands" behavior without needing its own thread.
    """
    load_key_config()

    canvas.add_event_handler(_on_key_event, "key_down", "key_up")
    canvas.add_event_handler(_on_cursor_pos, "pointer_move")
    canvas.add_event_handler(_on_mouse_button, "pointer_down", "pointer_up")


def load_key_config() -> None:
    """Load key configuration from input_config.json, falling back to
    the built-in default on any read/parse failure.
    """
    global key_config
    full_path = FRONTEND_DIR / "assets" / "data" / "input_config.json"
    try:
        import json

        key_config = json.loads(full_path.read_text(encoding="utf-8"))
    except (OSError, __import__("json").JSONDecodeError):
        key_config = _DEFAULT_KEY_CONFIG


def is_action_pressed(action: str, category: str = "movement") -> bool:
    """Check if any of the configured keys for an action are pressed."""
    if not key_config:
        return False
    category_config = key_config.get(category)
    if not category_config or action not in category_config:
        return False

    action_keys = category_config[action]
    return any(keys.get(key.lower(), False) for key in action_keys)


def get_movement_style() -> str:
    """Return the configured movement style ("area_relative" or
    "camera_relative") from `input_config.json`'s `settings` block --
    not hardcoded, same reasoning every other keybind lives in that
    file. Reuses the already-loaded `key_config`, no extra file I/O.
    """
    if not key_config:
        return "area_relative"
    settings = key_config.get("settings", {})
    return settings.get("movement_style", "area_relative")


def get_movement_input() -> "tuple[float, float, str | None]":
    """Read WASD/arrow key state into a raw, diagonal-normalized
    `(dx, dy)` movement vector plus a facing label (`None` if idle) --
    the shared first step both movement-style senders below build on.
    `dy < 0` is the "up"/forward key, `dx > 0` is the "right" key
    (`input_config.json`'s own convention, unchanged from the original
    single-style version of this function).
    """
    dx = 0.0
    dy = 0.0

    if is_action_pressed("up"):
        dy -= 1
    if is_action_pressed("down"):
        dy += 1
    if is_action_pressed("left"):
        dx -= 1
    if is_action_pressed("right"):
        dx += 1

    if dx != 0 and dy != 0:
        dx *= 0.707
        dy *= 0.707

    facing = None
    if dy < 0:
        facing = "up"
    elif dy > 0:
        facing = "down"
    elif dx < 0:
        facing = "left"
    elif dx > 0:
        facing = "right"

    return dx, dy, facing


def process_gameplay_input_area_relative() -> None:
    """"Area relative" movement style (renamed from this project's
    original, only movement style -- `process_gameplay_input()`; same
    behavior, unchanged): W/S/A/D map directly to fixed world axes
    (forward is always world +Z, right is always world -X, confirmed
    against a real hands-on test), regardless of which way the camera
    is currently facing. This stays in the engine layer (not a
    callback) because it touches no game-layer concept beyond
    `network.send_player_action`, a peer engine module.
    """
    dx, dy, facing = get_movement_input()
    if dx != 0 or dy != 0:
        network.send_player_action("move", direction={"x": dx, "y": dy}, facing=facing)
    else:
        network.send_player_action("move", direction={"x": 0, "y": 0})


def process_gameplay_input_camera_relative(camera_yaw: float) -> None:
    """"Camera relative" movement style: forward is whichever direction
    the camera is currently looking (ground-projected, ignoring pitch),
    left/right are tangent to that. Takes `camera_yaw` (radians, same
    convention as `ThirdPersonCamera.yaw`: yaw=0 -> camera offset
    faces +Z, so the camera itself *looks* -Z at yaw=0) as a plain
    float parameter rather than importing a camera object directly --
    a camera is a game-layer concept this engine-layer module must not
    reach for itself; the caller (game-layer glue code, e.g.
    `client/game/game_client.py`) is responsible for reading
    `camera.yaw` and passing it in.

    The rotation math sends `direction` pre-negated to match
    `Area.process_player_action`'s existing, already-verified
    "-direction.x -> world x, -direction.y -> world z" convention --
    this function must never change what a receiving server does with
    `direction`, only what values it computes for it, so area-relative
    movement's already-tested behavior can't regress. Derivation: the
    camera's ground-projected forward is `(-sin(yaw), -cos(yaw))` and
    its right is `(cos(yaw), -sin(yaw))` (matching `ThirdPersonCamera`/
    `FreeCamera`'s shared convention); composing
    `forward_amount=-dy, right_amount=dx` against those two vectors and
    then negating for the server's convention simplifies to the two
    lines below. Verified: at the default camera yaw (directly behind
    the target), this produces bit-identical output to area-relative
    for the same keys, since the camera starts facing the same way
    area-relative always assumes.
    """
    dx, dy, facing = get_movement_input()
    if dx == 0 and dy == 0:
        network.send_player_action("move", direction={"x": 0, "y": 0})
        return

    sin_yaw = math.sin(camera_yaw)
    cos_yaw = math.cos(camera_yaw)
    direction_x = -dy * sin_yaw - dx * cos_yaw
    direction_y = -dy * cos_yaw + dx * sin_yaw

    network.send_player_action(
        "move", direction={"x": direction_x, "y": direction_y}, facing=facing
    )


def process_input() -> None:
    """Throttled per-tick input processing driver. Call this once per
    frame from the render loop; it self-throttles against
    key_config['settings']['inputPollingRate'] and invokes the
    registered on_process callback no more often than that (matching
    the JS version's independent setInterval cadence, just driven
    externally instead of by its own timer -- see init_input's
    docstring).
    """
    global _last_process_time

    if not key_config:
        return

    polling_rate_ms = key_config.get("settings", {}).get("inputPollingRate", 16)
    now = time.perf_counter() * 1000.0
    if now - _last_process_time < polling_rate_ms:
        return
    _last_process_time = now

    on_process = _input_handlers.get("on_process")
    if callable(on_process):
        on_process()


# ------------------------------------------------------------------
# rendercanvas event handlers -- each receives a single event dict,
# not GLFW's raw callback signature. See module docstring.
# ------------------------------------------------------------------


def _on_key_event(event: dict) -> None:
    key_name = event["key"].lower()

    if event["event_type"] == "key_down":
        # Edge-triggered pause check, matching the JS version's
        # "only trigger once per key press" (!keys[key] guard).
        # rendercanvas itself never emits a "key_down" for OS-level key
        # repeat while a key is held (confirmed in rendercanvas/glfw.py's
        # _on_key: it returns early for glfw.REPEAT before building the
        # event at all), so no separate repeat-guard is needed here.
        if not keys.get(key_name, False):
            pause_keys = (key_config or {}).get("actions", {}).get("pause", [])
            if key_name in pause_keys:
                on_pause_toggle = _input_handlers.get("on_pause_toggle")
                if callable(on_pause_toggle):
                    on_pause_toggle()
        keys[key_name] = True
    elif event["event_type"] == "key_up":
        keys[key_name] = False


def _on_cursor_pos(event: dict) -> None:
    global mouse_x, mouse_y
    # rendercanvas's pointer position is already window-relative logical
    # coordinates, unlike the JS version's e.clientX/Y which needed an
    # explicit getBoundingClientRect() offset subtraction -- nothing to
    # subtract here.
    mouse_x = event["x"]
    mouse_y = event["y"]


def _on_mouse_button(event: dict) -> None:
    if event["event_type"] != "pointer_down":
        return

    button = event["button"]
    mouse_config = (key_config or {}).get("mouse", {})
    select_button = _DOM_TO_RENDERCANVAS_BUTTON.get(mouse_config.get("select", 0))
    context_menu_button = _DOM_TO_RENDERCANVAS_BUTTON.get(mouse_config.get("contextMenu", 2))

    if button == select_button:
        on_left_click = _input_handlers.get("on_left_click")
        if callable(on_left_click):
            on_left_click(mouse_x, mouse_y)
    elif button == context_menu_button:
        on_right_click = _input_handlers.get("on_right_click")
        if callable(on_right_click):
            on_right_click(mouse_x, mouse_y)
