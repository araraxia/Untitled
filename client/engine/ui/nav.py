"""Input-method-agnostic navigation focus.

Maps keyboard (via imgui.is_key_pressed) and gamepad (via gamepad.poll(),
this package's own per-frame poll) to one abstract action set --
UP/DOWN/LEFT/RIGHT/CONFIRM/BACK -- so widgets.py never checks "was this
keyboard or a controller". Mouse stays a fully independent path: hover
and click are read directly (draw.UIDrawContext.hovering/clicked), and
hovering an element moves nav focus onto it, so keyboard/gamepad nav and
mouse control never disagree about which element is "active".
"""

from __future__ import annotations

import enum
from typing import Dict, List, Optional, Tuple

from imgui_bundle import imgui

from client.engine.ui import gamepad

Point = Tuple[float, float]
Rect = Tuple[Point, Point]


class NavAction(enum.Enum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    CONFIRM = "confirm"
    BACK = "back"


_KEY_MAP = {
    imgui.Key.up_arrow: NavAction.UP,
    imgui.Key.down_arrow: NavAction.DOWN,
    imgui.Key.left_arrow: NavAction.LEFT,
    imgui.Key.right_arrow: NavAction.RIGHT,
    imgui.Key.enter: NavAction.CONFIRM,
    imgui.Key.space: NavAction.CONFIRM,
    imgui.Key.escape: NavAction.BACK,
}

_GAMEPAD_BUTTON_MAP = {
    gamepad.BUTTON_DPAD_UP: NavAction.UP,
    gamepad.BUTTON_DPAD_DOWN: NavAction.DOWN,
    gamepad.BUTTON_DPAD_LEFT: NavAction.LEFT,
    gamepad.BUTTON_DPAD_RIGHT: NavAction.RIGHT,
    gamepad.BUTTON_A: NavAction.CONFIRM,
    gamepad.BUTTON_B: NavAction.BACK,
}


class FocusManager:
    """Tracks nav focus for one independent group of focusable elements
    (e.g. one open menu screen). Don't share a single instance across
    unrelated screens -- arrow/gamepad-dpad presses would move focus on
    whichever screen happens to share the instance, not just the one the
    player is looking at.

    Usage, once per frame:
        nav.begin_frame()
        # ...draw widgets, each calling nav.register()/hovering()/
        # consume_confirm() as it draws itself (see widgets.button)...
        nav.end_frame()
    """

    def __init__(self) -> None:
        self._order: List[str] = []
        self._rects: Dict[str, Rect] = {}
        self._focus_id: Optional[str] = None
        self._actions_this_frame: List[NavAction] = []

    def begin_frame(self) -> None:
        """Call once per frame, before any widget registers itself."""
        self._order = []
        self._rects = {}

        actions: List[NavAction] = []
        for key, action in _KEY_MAP.items():
            if imgui.is_key_pressed(key):
                actions.append(action)

        pad = gamepad.poll()
        if pad.connected:
            for button, action in _GAMEPAD_BUTTON_MAP.items():
                if pad.buttons_pressed.get(button, False):
                    actions.append(action)

        self._actions_this_frame = actions

    def register(self, element_id: str, rect: Rect) -> None:
        """Widgets call this once per frame, in draw order, to become
        nav-focusable. The first element registered after a menu opens
        (i.e. the first call after _focus_id was last None) becomes
        focused automatically, so keyboard/gamepad users always have
        something focused without an explicit default-focus call.
        """
        self._order.append(element_id)
        self._rects[element_id] = rect
        if self._focus_id is None:
            self._focus_id = element_id

    def hovering(self, element_id: str) -> bool:
        """True if the mouse is over element_id's registered rect.
        Also claims nav focus for it -- see module docstring."""
        rect = self._rects.get(element_id)
        if rect is None:
            return False
        is_hovering = imgui.is_mouse_hovering_rect(imgui.ImVec2(*rect[0]), imgui.ImVec2(*rect[1]))
        if is_hovering:
            self._focus_id = element_id
        return is_hovering

    def is_focused(self, element_id: str) -> bool:
        return self._focus_id == element_id

    def consume_confirm(self, element_id: str) -> bool:
        """True if this frame's CONFIRM action applies to element_id
        (it currently has nav focus). widgets.button() combines this
        with a direct mouse click to decide whether it fired."""
        return self._focus_id == element_id and NavAction.CONFIRM in self._actions_this_frame

    def consumed_back(self) -> bool:
        """True if BACK fired this frame, for anything that doesn't tie
        it to one specific element (e.g. closing a whole dialog)."""
        return NavAction.BACK in self._actions_this_frame

    def end_frame(self) -> None:
        """Move focus along registration order per this frame's
        directional actions. Call once per frame, after every widget
        for this screen has drawn (and thus registered) -- focus
        movement needs the complete list, not a partial one.

        v1 treats focus order as one flat sequence (UP/LEFT step back,
        DOWN/RIGHT step forward) rather than true 2D-grid navigation --
        sufficient for menu-style vertical/horizontal button rows. A
        real grid (e.g. an inventory) would need register() to also
        carry a row/column and this method to navigate on that instead.
        """
        if not self._order:
            self._focus_id = None
            return
        if self._focus_id not in self._order:
            self._focus_id = self._order[0]
            return

        index = self._order.index(self._focus_id)
        if NavAction.DOWN in self._actions_this_frame or NavAction.RIGHT in self._actions_this_frame:
            index = (index + 1) % len(self._order)
        elif NavAction.UP in self._actions_this_frame or NavAction.LEFT in self._actions_this_frame:
            index = (index - 1) % len(self._order)
        self._focus_id = self._order[index]
