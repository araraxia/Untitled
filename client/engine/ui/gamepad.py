"""Per-frame gamepad/controller polling.

GLFW (already a project dependency, used by client/engine/renderer.py
for window setup) exposes joystick/gamepad polling directly --
`get_gamepad_state`/`joystick_is_gamepad`/`joystick_present` and the
`GAMEPAD_BUTTON_*`/`GAMEPAD_AXIS_*` constants, all confirmed present in
this project's installed `glfw` package. Nothing in this codebase polled
any of it before this module.

Unlike client/engine/input.py's keyboard/mouse handling (event-driven,
via rendercanvas's canvas.add_event_handler), GLFW gamepad state is
poll-based -- there is no "button down" event to subscribe to. `poll()`
must be called once per frame from the render loop (see client/main.py),
not registered as a handler. It self-diffs against the previous frame's
button state to produce edge-triggered `buttons_pressed`, the same
"went !down -> down, once" semantics client/engine/input.py's key
handling already has for the pause key.

Not verified against a physical controller in this session (no hardware
available) -- the button/axis index constants and the presence of
`get_gamepad_state`/`joystick_is_gamepad` are confirmed via direct
introspection of the installed `glfw` package, but the exact attribute
names on the object `get_gamepad_state` returns (assumed `.buttons`/
`.axes`, matching GLFW's C `GLFWgamepadstate` struct) should be confirmed
against real hardware before shipping a controller-dependent feature.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple

import glfw

BUTTON_A = glfw.GAMEPAD_BUTTON_A
BUTTON_B = glfw.GAMEPAD_BUTTON_B
BUTTON_X = glfw.GAMEPAD_BUTTON_X
BUTTON_Y = glfw.GAMEPAD_BUTTON_Y
BUTTON_START = glfw.GAMEPAD_BUTTON_START
BUTTON_BACK = glfw.GAMEPAD_BUTTON_BACK
BUTTON_DPAD_UP = glfw.GAMEPAD_BUTTON_DPAD_UP
BUTTON_DPAD_DOWN = glfw.GAMEPAD_BUTTON_DPAD_DOWN
BUTTON_DPAD_LEFT = glfw.GAMEPAD_BUTTON_DPAD_LEFT
BUTTON_DPAD_RIGHT = glfw.GAMEPAD_BUTTON_DPAD_RIGHT


@dataclass
class GamepadState:
    connected: bool = False
    buttons_down: Dict[int, bool] = field(default_factory=dict)
    buttons_pressed: Dict[int, bool] = field(default_factory=dict)  # edge-triggered, this frame only
    left_stick: Tuple[float, float] = (0.0, 0.0)
    right_stick: Tuple[float, float] = (0.0, 0.0)


# Previous frame's button state, per joystick id -- needed to compute
# buttons_pressed's rising-edge detection.
_last_down: Dict[int, Dict[int, bool]] = {}


def poll(joystick_id: int = glfw.JOYSTICK_1) -> GamepadState:
    """Poll one gamepad's state for this frame. Safe to call every frame
    regardless of whether anything is plugged in -- returns
    connected=False rather than raising.
    """
    if not glfw.joystick_present(joystick_id) or not glfw.joystick_is_gamepad(joystick_id):
        _last_down.pop(joystick_id, None)
        return GamepadState(connected=False)

    state = glfw.get_gamepad_state(joystick_id)
    if not state:
        return GamepadState(connected=False)

    buttons_down = {i: bool(v) for i, v in enumerate(state.buttons)}
    previous = _last_down.get(joystick_id, {})
    buttons_pressed = {
        i: (down and not previous.get(i, False)) for i, down in buttons_down.items()
    }
    _last_down[joystick_id] = buttons_down

    axes = state.axes
    return GamepadState(
        connected=True,
        buttons_down=buttons_down,
        buttons_pressed=buttons_pressed,
        left_stick=(axes[0], axes[1]) if len(axes) >= 2 else (0.0, 0.0),
        right_stick=(axes[2], axes[3]) if len(axes) >= 4 else (0.0, 0.0),
    )
