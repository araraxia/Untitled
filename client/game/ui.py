"""In-game HUD (imgui-bundle).

Port of frontend/js/game/ui.js: player stats (HP/action points), the
party panel, and the party-command context menu -- Step 14 (checkpoint
1 of 4) of .github/prompts/wgpu-py-migration.prompt.md, as imgui
immediate-mode widgets instead of DOM elements.

**This is a real rewrite in one specific place, not a mechanical
port, and the prompt's own Step 14 intro warns exactly about this**:
JS's `showCommandMenu()` imperatively builds a DOM element once and it
persists on its own (the browser repaints it every frame for free).
imgui is immediate-mode -- there is no persistent element, the popup
must be re-declared every single frame via `begin_popup()`/
`end_popup()`, and `open_popup()` must be called to *start* that
sequence.

**Real bug found by testing against a real (bare, backend-less but
functional) imgui context, not just writing the code**: calling
`imgui.open_popup()` from outside a `new_frame()`/`render()` bracket
segfaults the process outright (confirmed directly: a bare
`imgui.open_popup(...)` call before the context's first frame, and
again between two completed frames, both crash with SIGSEGV). This
matters here specifically because `show_command_menu()` is invoked from
`client/engine/input.py`'s GLFW mouse-button callback, which fires
during `glfw.poll_events()` -- typically called once per loop
iteration *before* `imgui.new_frame()`, i.e. exactly the unsafe timing.
Fixed with a pending-request pattern: `show_command_menu()` (called
from the input callback, any time, frame-boundary-agnostic) only
records `(x, y, member_id)` in `_pending_command_menu`; the actual
`imgui.open_popup()` call happens inside `render_party_command_menu()`,
which the caller must run once per frame from inside its own
new_frame()/render() bracket (Step 15's render loop) alongside
`render_hud()`. This also matches `open_popup()`'s own docstring
("call to mark popup as open (don't call every frame!)") -- the
pending-flag approach was the intended usage pattern, not just a crash
workaround.

**Bonus, not something this port had to build**: imgui's popups
already close automatically on an outside click -- JS's `showCommandMenu`
needed a manual `setTimeout` + a one-shot `document` click listener
specifically to fake that behavior; nothing here replaces it, it's just
not needed.

**Same engine/game boundary shape as Steps 11-13**: `selectedPartyMember`
lives in `input.js` in the JS original (module-scope global, shared
implicitly across `<script>` tags), but proximity-based entity
selection and the party command menu are fundamentally UI/game
concerns, not engine ones -- consistent with `input.py`'s own Step 12
decision *not* to port `handleMouseDown`'s proximity-search or
`handleContextMenu`'s menu-opening logic itself, only to forward raw
click coordinates via `on_left_click`/`on_right_click` callbacks. Both
pieces of logic (`handle_world_click`, `show_command_menu`) live here
instead, and `selected_party_member` is this module's state, not
`client/engine/input.py`'s.

**One faithfully-preserved quirk, not fixed here**: `handle_world_click`
(the port of `handleMouseDown`) checks *every* entity for proximity,
with no `party_`-prefix filter -- unlike `render_party_panel`, which
only lists `party_`-prefixed entities. That asymmetry exists in the JS
source too; porting it as-is rather than "fixing" it, since this task
is a mechanical port, not a behavior audit.

**"Move Here"'s target reads `client/engine/input.py`'s live
`mouse_x`/`mouse_y`** at the moment the menu item is actually clicked
(inside `render_party_command_menu()`), not at the moment the menu was
opened -- this matches the JS original's behavior exactly: its
per-command `onclick` closures read the *variable* `mouseX`/`mouseY`
at click time (JS closures capture variables, not values), not a
snapshot taken when `showCommandMenu()` first ran.
"""

import math

from imgui_bundle import imgui

from client.engine import input, network

selected_party_member: "str | None" = None

_COMMAND_MENU_ID = "party_command_menu"

# (x, y, member_id) recorded by show_command_menu(), consumed by the
# next render_party_command_menu() call. See module docstring for why
# this can't just call imgui.open_popup() directly.
_pending_command_menu: "tuple | None" = None

# The member a just-opened popup targets, captured once at open time and
# held for the popup's whole (possibly multi-frame) lifetime -- mirrors
# the JS version's per-command onclick closures capturing `memberId`.
_command_menu_member_id: "str | None" = None


def init_ui() -> None:
    """Initialize UI system."""
    print("[UI] UI initialized")


def render_hud(player: "dict | None", entities: dict) -> None:
    """Draw player stats (HP/AP) and the party panel. Call once per
    frame, inside the caller's new_frame()/render() bracket.
    """
    imgui.begin("HUD")
    if player is not None:
        hp = player.get("hp", 100)
        max_hp = player.get("max_hp", 100)
        ap = player.get("action_points", 100)
        imgui.text(f"HP: {hp}/{max_hp}")
        imgui.text(f"AP: {ap}")
        imgui.separator()
    render_party_panel(entities)
    imgui.end()


def render_party_panel(entities: dict) -> None:
    """Draw the party members panel with current party status."""
    imgui.text("Party:")
    for entity_id, entity in entities.items():
        if entity_id.startswith("party_"):
            label = f"{entity_id}: {entity.get('state', 'idle')}"
            clicked, _ = imgui.selectable(label, selected_party_member == entity_id)
            if clicked:
                select_party_member(entity_id)


def select_party_member(member_id: str) -> None:
    """Select a party member for commanding."""
    global selected_party_member
    selected_party_member = member_id
    print(f"[UI] Selected party member: {member_id}")


def handle_world_click(mouse_x: float, mouse_y: float, camera: dict, entities: dict) -> None:
    """Select the nearest entity within 16 world units of a left-click.

    Port of input.js's handleMouseDown -- moved here per the module
    docstring's engine/game boundary note. Called from the game layer's
    registered `on_left_click` handler (see client/engine/input.py's
    set_input_handlers()).
    """
    world_x = mouse_x + camera.get("x", 0)
    world_y = mouse_y + camera.get("y", 0)

    for entity_id, entity in entities.items():
        dx = entity.get("x", 0) - world_x
        dy = entity.get("y", 0) - world_y
        distance = math.sqrt(dx * dx + dy * dy)

        if distance < 16:
            select_party_member(entity_id)
            print(f"Selected: {entity_id}")
            break


def show_command_menu(x: float, y: float, member_id: str) -> None:
    """Request the party command menu open at (x, y) for member_id.

    Safe to call from any context, including a GLFW callback outside
    an imgui frame boundary -- see module docstring for why this only
    records a pending request rather than calling imgui.open_popup()
    directly.
    """
    global _pending_command_menu
    _pending_command_menu = (x, y, member_id)


def render_party_command_menu() -> None:
    """Draw the party command menu popup, if one is open or was just
    requested. Call once per frame, inside the caller's
    new_frame()/render() bracket, alongside render_hud().
    """
    global _pending_command_menu, _command_menu_member_id

    if _pending_command_menu is not None:
        x, y, member_id = _pending_command_menu
        _pending_command_menu = None
        _command_menu_member_id = member_id
        imgui.set_next_window_pos(imgui.ImVec2(x, y))
        imgui.open_popup(_COMMAND_MENU_ID)

    if not imgui.begin_popup(_COMMAND_MENU_ID):
        return

    member_id = _command_menu_member_id

    if imgui.menu_item_simple("Follow Player"):
        network.send_party_command(member_id, "follow", target_id="player_1")
        imgui.close_current_popup()

    if imgui.menu_item_simple("Hold Position"):
        network.send_party_command(member_id, "hold_position")
        imgui.close_current_popup()

    if imgui.menu_item_simple("Attack Target"):
        network.send_party_command(member_id, "attack_target")
        imgui.close_current_popup()

    if imgui.menu_item_simple("Move Here"):
        network.send_party_command(
            member_id, "move_to", target={"x": input.mouse_x, "y": input.mouse_y}
        )
        imgui.close_current_popup()

    imgui.end_popup()
