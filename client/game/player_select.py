"""Player/save select screen (imgui-bundle).

Port of frontend/js/game/playerSelect.js (468 JS lines) -- Step 14
(checkpoint 3 of 4) of .github/prompts/wgpu-py-migration.prompt.md.
Save-slot list from `save_list`, new/load/delete player actions,
`loadGameState()`'s initial full-state handling.

**Real rewrite, not a mechanical port, exactly as the Step 14 intro
warns**: the JS original imperatively builds DOM overlay elements
(`menuOverlay`, `inputDialog`, `confirmDialog`) with inline CSS. There
is no DOM here; every screen/dialog is redrawn from scratch every
frame as imgui immediate-mode widgets. `populate_player_list()` no
longer builds anything itself -- it just stores `saves`, which
`render_player_select_screen()` (called every frame by the owner of
the main render loop, Step 15, while `game_state['context'] ==
GameContext.PLAYER_SELECT`) draws.

**This file owns `GameContext` and `game_state`, unlike the JS
original** (both are defined in frontend/js/game/main.js, reached into
by playerSelect.js/ui.js/input.js via shared `<script>` scope). Since
this port has no equivalent implicit sharing, and this file is
specifically the one responsible for `load_game_state()` -- the
function that gives `game_state['entities']` its first real content --
it's the natural owner; `client/main.py` (Step 15) and any other
game-layer module imports `player_select.game_state`/`.GameContext`
directly, the same way other modules in this port expose shared state
as plain importable module attributes (e.g. `client/engine/network.py`'s
`sio`).

**Popups opened directly, not deferred like ui.py's**: every popup
trigger here (`create_new_player()`, `delete_player()`) fires from an
imgui button click inside `render_player_select_screen()`, which is
already running inside the caller's `new_frame()`/`render()` bracket --
unlike `ui.py`'s `show_command_menu()`, which is invoked from a raw
GLFW mouse callback *outside* any imgui frame (see that module's
docstring for the segfault this caused there). Calling
`imgui.open_popup()` immediately, in the same call stack as the
triggering button, is safe and is standard Dear ImGui usage; no pending
-request indirection needed here.

**`window.innerWidth`/`innerHeight` -> `renderer.canvas.get_logical_size()`**:
JS reads the live browser window size for camera-centering math; the
native equivalent is the GLFW window's current *logical* (not
physical/HiDPI-scaled) size, which tracks live resizes the same way.

**Dropped, no native equivalent needed**: the `#loading-indicator` DOM
show/hide calls (no such element exists in this client) and the
`requestAnimationFrame(renderLoop)` call in `loadGameState()` -- the
native client's `rendercanvas` render loop (Step 5) runs continuously
for the app's lifetime once started in `client/main.py` (Step 15), it
is not started/stopped per game-state transition the way JS's
`requestAnimationFrame` chain is. Same reasoning applies to
`input.js`'s `toggleDebugPause()` restarting the loop on unpause --
nothing to restart here.

**`format_save_date`'s locale formatting is approximate, not
byte-identical**: JS's `Date.toLocaleString()` and Python's
`strftime('%c')` both produce a locale-dependent human-readable
timestamp, but the exact format differs. Acceptable per Step 14's own
"functional parity ... over pixel-perfect ... parity" guidance.
"""

from datetime import datetime

from imgui_bundle import imgui

from client.engine import interpolation, network, renderer


class GameContext:
    """Game contexts -- determines what input actions do. Plain string
    constants, matching the JS original's plain object (not a real
    enum there either).
    """

    LOADING = "loading"
    PLAYER_SELECT = "player_select"
    MENU = "menu"
    IN_GAME = "in_game"
    INVENTORY = "inventory"
    DIALOGUE = "dialogue"
    PAUSED = "paused"


game_state: dict = {
    "entities": {},
    "player": None,
    "selected_player_id": None,
    "camera": {"x": 0, "y": 0, "zoom": 1},
    "world_size": {"width": 1000, "height": 1000},
    "paused": False,
    "context": GameContext.PLAYER_SELECT,
}

_saves: "list | None" = None  # None = not yet loaded; [] = loaded, empty

_NEW_PLAYER_POPUP_ID = "new_player_dialog"
_new_player_name_buffer = ""

_DELETE_CONFIRM_POPUP_ID = "delete_player_confirm"
_delete_confirm_player_id: "str | None" = None


def show_player_selection_menu() -> None:
    """Show player selection menu and request available players from
    the server.
    """
    print("[PlayerSelect] Displaying player selection menu")
    game_state["context"] = GameContext.PLAYER_SELECT

    if network.sio is not None and network.sio.connected:
        print("[PlayerSelect] Socket already connected, requesting save list now")
        network.sio.emit("request_save_list")
    else:
        print("[PlayerSelect] Waiting for socket connection to request save list")


def create_new_player() -> None:
    """Open the new-player name-entry dialog."""
    global _new_player_name_buffer
    print("[PlayerSelect] Creating new player")
    _new_player_name_buffer = ""
    imgui.open_popup(_NEW_PLAYER_POPUP_ID)


def format_save_date(iso_string: "str | None") -> str:
    """Format an ISO-8601 timestamp for display. Returns 'Never' if the
    value is null/undefined/empty.
    """
    if not iso_string:
        return "Never"
    try:
        d = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
    except ValueError:
        return iso_string
    return d.strftime("%c")


def populate_player_list(saves: "list | None") -> None:
    """Store the save-slot summaries for render_player_select_screen()
    to draw.
    """
    global _saves
    _saves = saves or []


def select_player(player_id: str) -> None:
    """Select a player and request their game state from the server."""
    print(f"[PlayerSelect] Player selected: {player_id}")
    game_state["selected_player_id"] = player_id
    game_state["context"] = GameContext.LOADING

    if network.sio is not None and network.sio.connected:
        print("[PlayerSelect] Requesting player data from server")
        network.sio.emit("load_player", {"player_id": player_id})
    else:
        print("[PlayerSelect] Cannot load player: socket not connected")


def load_game_state(data: dict) -> None:
    """Load game state into the client. Called when the server sends
    initial game state after player selection (register as
    client/engine/network.py's on_initial_state handler).
    """
    print("[PlayerSelect] Loading game state...", data)

    if data.get("world"):
        game_state["world_size"] = data["world"]

    if data.get("player_id"):
        game_state["selected_player_id"] = data["player_id"]

    if data.get("entities"):
        game_state["entities"] = {}
        controlled_entity_ids = data.get("controlled_entity_ids") or []
        logical_width, logical_height = renderer.canvas.get_logical_size()

        for entity_id, entity_data in data["entities"].items():
            if not entity_data.get("state"):
                entity_data["state"] = "idle"
            if not entity_data.get("facing"):
                entity_data["facing"] = "down"

            game_state["entities"][entity_id] = entity_data

            if entity_id in controlled_entity_ids:
                if game_state["player"] is None:
                    game_state["player"] = entity_data
                    game_state["camera"]["x"] = entity_data.get("x", 0) - logical_width / 2
                    game_state["camera"]["y"] = entity_data.get("y", 0) - logical_height / 2
            elif entity_data.get("type") == "player" and game_state["player"] is None:
                game_state["player"] = entity_data
                game_state["camera"]["x"] = entity_data.get("x", 0) - logical_width / 2
                game_state["camera"]["y"] = entity_data.get("y", 0) - logical_height / 2

            interpolation.init_entity_interpolation(entity_id, entity_data)

    game_state["context"] = GameContext.IN_GAME

    print(f"[PlayerSelect] Game state loaded. Entities: {len(game_state['entities'])}")
    print(f"[PlayerSelect] Controlled entities: {data.get('controlled_entity_ids')}")


def delete_player(player_id: str) -> None:
    """Open the delete-player confirmation dialog."""
    global _delete_confirm_player_id
    print(f"[PlayerSelect] Delete player requested: {player_id}")
    _delete_confirm_player_id = player_id
    imgui.open_popup(_DELETE_CONFIRM_POPUP_ID)


def save_game_state() -> None:
    """Trigger a manual save via SocketIO and notify the player."""
    print("[PlayerSelect] Requesting manual save")
    if network.sio is not None and network.sio.connected:
        network.sio.emit("save_game")
    else:
        print("[PlayerSelect] Cannot save: socket not connected")


# ------------------------------------------------------------------
# imgui rendering -- call render_player_select_screen() once per frame
# while game_state['context'] == GameContext.PLAYER_SELECT.
# ------------------------------------------------------------------


def render_player_select_screen() -> None:
    """Draw the player-select screen and any open dialogs."""
    imgui.begin("Select Player")

    if _saves is None:
        imgui.text_disabled("Loading players...")
    elif len(_saves) == 0:
        imgui.text_disabled("No saved players found")
    else:
        for save in _saves:
            player_id = save.get("player_id")
            display_name = save.get("player_name") or player_id
            last_saved = format_save_date(save.get("last_save"))
            tick_count = save.get("tick_count")
            if tick_count is None:
                tick_count = 0

            imgui.push_id(player_id)
            if imgui.button(display_name):
                select_player(player_id)
            imgui.same_line()
            imgui.text_disabled(f"Last saved: {last_saved}  ·  Tick: {tick_count}")
            imgui.same_line()
            if imgui.button("Delete"):
                delete_player(player_id)
            imgui.pop_id()

    imgui.separator()
    if imgui.button("Create New Player"):
        create_new_player()

    imgui.end()

    _render_new_player_popup()
    _render_delete_confirm_popup()


def _render_new_player_popup() -> None:
    global _new_player_name_buffer

    if not imgui.begin_popup(_NEW_PLAYER_POPUP_ID):
        return

    imgui.text("New Player")
    enter_pressed, _new_player_name_buffer = imgui.input_text(
        "Name", _new_player_name_buffer, imgui.InputTextFlags_.enter_returns_true.value
    )

    create_clicked = imgui.button("Create")
    imgui.same_line()
    cancel_clicked = imgui.button("Cancel")

    if create_clicked or enter_pressed:
        player_name = _new_player_name_buffer.strip()
        if player_name:
            print(f"[PlayerSelect] Creating new player: {player_name}")
            if network.sio is not None and network.sio.connected:
                network.sio.emit("new_player", {"player_id": player_name})
            imgui.close_current_popup()
    elif cancel_clicked:
        imgui.close_current_popup()

    imgui.end_popup()


def _render_delete_confirm_popup() -> None:
    global _delete_confirm_player_id

    if not imgui.begin_popup(_DELETE_CONFIRM_POPUP_ID):
        return

    player_id = _delete_confirm_player_id
    imgui.text(f'Delete player "{player_id}"?')
    imgui.text_disabled("This action cannot be undone.")

    if imgui.button("Delete"):
        print(f"[PlayerSelect] Deleting player: {player_id}")
        if network.sio is not None and network.sio.connected:
            network.sio.emit("delete_player", {"player_id": player_id})
        # Refresh handled by network.py's player_deleted handler ->
        # request_save_list, same as the JS original's comment notes.
        imgui.close_current_popup()

    imgui.same_line()
    if imgui.button("Cancel"):
        imgui.close_current_popup()

    imgui.end_popup()
