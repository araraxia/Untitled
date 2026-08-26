"""Runtime piece for UI menus authored by `client/engine/ui_editor.py`
-- loads a menu's JSON, shows/hides it in response to its triggers.
Step 14 task 7 of .github/prompts/level-editor.prompt.md.

**Keybind triggers are fully functional here** -- purely client-local,
polled every frame against `client/engine/input.py`'s key state, no
backend/network involvement at all.

**Zone/entity-interact triggers are registration-only, not yet
consumable end to end** -- both fire *server-side* (`EventBus` events
published from backend zone/collider code) and need a `menu_trigger`
SocketIO event to reach the client. Neither `area-system.prompt.md` nor
`zones.prompt.md` built an EventBus-to-SocketIO bridge (confirmed by
audit), so there is nothing yet to register `on_menu_trigger` against
on `engine` -- this module exposes the registration point
(`network.set_state_handlers` doesn't have one; a game branch adding
the bridge should add a matching handler here, following the exact
callback-registration shape `on_scene_cue` already established in
`client/engine/network.py`) but cannot exercise it standalone.
"""

import json
from pathlib import Path
from typing import Callable, Optional

from client.engine.ui import draw, templates, widgets
from client.engine.ui.nav import FocusManager

UI_MENU_DIR_REL = "assets/data/ui"


class MenuRuntime:
    """Owns the currently-visible set of menus and polls keybind
    triggers each frame. `render(ctx, nav, theme)` draws every visible
    menu via the same real widget functions the editor's live preview
    uses -- what was seen while authoring is exactly what renders here.
    """

    def __init__(self, frontend_dir: Path) -> None:
        self._frontend_dir = frontend_dir
        self._menus: dict[str, dict] = {}  # menu_id -> parsed JSON
        self._visible: set[str] = set()
        self._keys_down_last_frame: set[str] = set()

    def load_menu(self, menu_id: str) -> Optional[dict]:
        if menu_id in self._menus:
            return self._menus[menu_id]
        path = self._frontend_dir / UI_MENU_DIR_REL / f"menu-{menu_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        self._menus[menu_id] = data
        return data

    def show(self, menu_id: str) -> None:
        if self.load_menu(menu_id) is not None:
            self._visible.add(menu_id)

    def hide(self, menu_id: str) -> None:
        self._visible.discard(menu_id)

    def is_visible(self, menu_id: str) -> bool:
        return menu_id in self._visible

    def poll_keybind_triggers(self, keys_down: dict) -> None:
        """Call once per frame with `client.engine.input.keys` (or an
        equivalent `{key_name: bool}` mapping) -- edge-triggered, only
        fires on the frame a configured key transitions up -> down.

        **Authoring gotcha, found while verifying this method**: `show`
        and `hide` are independent trigger lists, not a toggle -- if
        the *same* key appears in both a menu's `show` and `hide`
        lists, pressing it fires both in the same frame (show, then
        hide) and nets to "stays hidden," not "toggles." For an
        escape-to-toggle pause menu, put `escape` in only one list and
        close the menu a different way (a Resume button, a distinct
        key) or build a dedicated toggle trigger type later -- this
        module deliberately doesn't guess at toggle semantics the
        schema itself doesn't define.
        """
        pressed_now = {k for k, v in keys_down.items() if v}
        newly_pressed = pressed_now - self._keys_down_last_frame
        self._keys_down_last_frame = pressed_now

        if not newly_pressed:
            return

        for menu_id, menu in self._menus.items():
            triggers = menu.get("triggers", {})
            for trigger in triggers.get("show", []):
                if trigger.get("type") == "keybind" and trigger.get("key", "").lower() in newly_pressed:
                    self.show(menu_id)
            for trigger in triggers.get("hide", []):
                if trigger.get("type") == "keybind" and trigger.get("key", "").lower() in newly_pressed:
                    self.hide(menu_id)

    def on_menu_trigger_event(self, payload: dict) -> None:
        """Registration point for a future `menu_trigger` SocketIO
        event -- `payload = {"event": "show_menu:<id>" | "hide_menu:<id>"}`.
        Not wired to any real network handler on `engine` (see module
        docstring); a game branch's `network.set_state_handlers`-style
        registration would call this once the backend bridge exists.
        """
        event = payload.get("event", "")
        if event.startswith("show_menu:"):
            self.show(event[len("show_menu:") :])
        elif event.startswith("hide_menu:"):
            self.hide(event[len("hide_menu:") :])

    def render(self, ctx, nav: FocusManager, theme) -> None:
        for menu_id in list(self._visible):
            menu = self._menus.get(menu_id)
            if menu is None:
                continue
            for element in menu.get("elements", []):
                self._render_element(ctx, nav, theme, element)

    def _render_element(self, ctx, nav: FocusManager, theme, element: dict) -> None:
        rect = element.get("rect", [[0, 0], [100, 30]])
        p_min, p_max = tuple(rect[0]), tuple(rect[1])
        element_type = element.get("type", "panel")
        element_id = element.get("id", "?")

        if element_type == "panel":
            widgets.panel(ctx, p_min, p_max, theme)
        elif element_type == "label":
            widgets.label(ctx, p_min, element.get("text", ""), theme, font_key=element.get("font_key", "body"))
        elif element_type == "button":
            widgets.button(ctx, nav, element_id, p_min, p_max, element.get("text", "Button"), theme)
        elif element_type == "progress_bar":
            widgets.progress_bar(ctx, p_min, p_max, element.get("fraction", 0.0), theme)
