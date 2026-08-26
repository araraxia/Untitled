"""New native desktop entry point -- replaces PyWebView. Step 15 of
.github/prompts/wgpu-py-migration.prompt.md.

Reproduces root main.py's server bootstrap (background Flask/SocketIO
thread, health-check poll, same Logger), then -- once the server is
ready -- creates the real GLFW window + wgpu device (client/engine/
renderer.py, Step 5), a real `wgpu.utils.imgui.ImguiRenderer` (see
client/engine/imgui_wgpu_compat.py's docstring for a confirmed,
currently-open upstream wgpu/imgui-bundle version-compatibility bug
this shim works around: pygfx/wgpu-py#829, fix pending in #830),
connects the Step 11 network client, and runs the real render loop on
the main thread (GLFW/most native windowing requires this, unlike
PyWebView's `webview.start()`).

**`should_disable_gpu()` and all `webview.*` calls are gone, not
ported** -- per Step 15 task 4, those existed specifically to work
around WebKitGTK/PyWebView issues this whole migration removes.

**This file does real, necessary synthesis work beyond any single JS
file's 1:1 port** -- `getEntityRenderer`/`renderEntities`/
`_gatherLights`/the WebGPU half of `render()` all live in
frontend/js/engine/renderer.js in the JS source, but can't live in
`client/engine/renderer.py` here: `client/engine/entity_renderer.py`
(Step 9) already imports `client.engine.renderer` for device/canvas/
shader_cache access, so `renderer.py` importing `entity_renderer.py`
back would be a real circular import -- a constraint Python enforces
that JS's flat, import-free `<script>` model never had to. Keeping
that orchestration here, the one place that can safely import both,
is the fix (see renderer.py's `run()` docstring for the other half of
this same note). Separately, wiring `network.py`/`input.py`/
`player_select.py`/`character_creation.py`/`ui.py`'s already-built
callback registration points together into one running app has no
single JS analogue at all -- `frontend/js/game/main.js` is the closest
comparison, but this needed synthesizing pieces from Steps 11, 12, and
14 that main.js itself never had to combine explicitly (JS's shared
`<script>` scope did that implicitly).

**Two real gaps found and fixed while wiring this together, both
documented in their origin steps' own prompt entries**:
`character_creation.py`'s `init_character_creation()` now preserves
externally-registered character-flow callbacks instead of wiping them
(needed so this file's own `on_new_player_initialized`/`on_save_list`
registrations survive character creation starting), and
`_handle_character_created()` now actually hands off to
`player_select.select_player()` -- without both fixes, Step 14's own
declared verify condition ("the full player-select ->
character-creation -> in-game flow completes end to end") would not
actually hold.
"""

import socket
import sys
import threading
import time
from pathlib import Path

# client/main.py -> client -> repo root. Mirrors root main.py's own
# sys.path.insert pattern so `python client/main.py` works directly,
# not just `python -m client.main`.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.independant_logger import Logger

logger = Logger(
    log_name="client.main",
    log_file="main.log",
    log_level=20,  # INFO
).get_logger()

try:
    from backend.app import app, socketio
except ImportError:
    # backend.app only exists on a game branch (see ARCHITECTURE.md's
    # Branch model note) -- rendering-only consumers of this module
    # (draw_game_scene/get_entity_renderer/render_entities/_gather_lights,
    # e.g. run_client_test.py) don't need it, only start_server()/main()
    # do, and those already can't run without a game branch either.
    app = None
    socketio = None

from imgui_bundle import imgui
from wgpu.utils.imgui import ImguiRenderer

from client.engine import imgui_wgpu_compat  # noqa: F401 -- apply the compat shim before constructing ImguiRenderer
from client.engine import input as input_engine
from client.engine import interpolation, network, renderer
from client.engine.entity_renderer import EntityRenderer

try:
    from client.game import character_creation, player_select, ui
    from client.game.player_select import GameContext, game_state
except ImportError:
    # client.game only exists on a game branch -- see note above.
    character_creation = player_select = ui = None
    GameContext = None
    game_state = None

DEFAULT_ANIMATION_DATA_PATHS = ["assets/data/human_animations.json"]

entity_renderers: dict = {}
imgui_renderer: "ImguiRenderer | None" = None
_last_frame_time: "float | None" = None


def is_server_ready(host="127.0.0.1", port=5000, timeout=10) -> bool:
    """Check if the server is ready to accept connections. Same as
    root main.py's version.
    """
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                return True
        except OSError:
            pass
        time.sleep(0.1)
    return False


def start_server() -> None:
    """Start the Flask-SocketIO server in a separate thread. Same as
    root main.py's version.
    """
    logger.info("Starting game server...")
    socketio.run(app, host="127.0.0.1", port=5000, debug=False, allow_unsafe_werkzeug=True)


# --------------------------------------------------------------------
# Entity rendering orchestration -- port of renderer.js's
# getEntityRenderer/renderEntities/_gatherLights/render's WebGPU
# branch. Lives here rather than client/engine/renderer.py; see this
# module's docstring for why (circular import).
# --------------------------------------------------------------------


def get_entity_renderer(entity_id: str, animation_data_paths: list) -> EntityRenderer:
    """Get or create an EntityRenderer for a specific entity."""
    if entity_id not in entity_renderers:
        er = EntityRenderer(entity_id, animation_data_paths)
        # Register before load completes, matching renderer.js's own
        # reasoning: render happens every frame, and registering first
        # avoids re-triggering a duplicate load on an in-between frame.
        entity_renderers[entity_id] = er
        er.load_all_animation_data()
    return entity_renderers[entity_id]


def render_entities(state: dict, delta_time_ms: float, pass_encoder) -> None:
    """Update and draw all entity animations for the current frame."""
    entities = state["entities"]

    for entity_id in list(entity_renderers.keys()):
        if entity_id not in entities:
            entity_renderers[entity_id].destroy()
            del entity_renderers[entity_id]

    for entity_id, entity in entities.items():
        animation_data_paths = entity.get("animation_data_paths") or DEFAULT_ANIMATION_DATA_PATHS
        er = get_entity_renderer(entity_id, animation_data_paths)
        er.update_entity_animation(entity_id, entity, delta_time_ms)
        er.draw_entity(entity, state["camera"], pass_encoder)


def _gather_lights(state: dict) -> list:
    """Collect the active light list for the current frame: backend-
    driven entity `light` components plus frontend-registered runtime
    lights.
    """
    lights = []

    for entity in (state.get("entities") or {}).values():
        light = entity.get("light")
        if light:
            lights.append(
                {
                    "x": entity.get("display_x", entity.get("x")),
                    "y": entity.get("display_y", entity.get("y")),
                    "color": light.get("color", [1.0, 1.0, 0.9]),
                    "radius": light.get("radius", 150),
                }
            )

    for entity_id, er in entity_renderers.items():
        entity = (state.get("entities") or {}).get(entity_id)
        if entity is None:
            continue
        reg_light = er.get_registered_light(entity)
        if reg_light:
            lights.append(reg_light)

    return lights


def draw_game_scene(state: dict, delta_time_ms: float) -> None:
    """Two-pass game render: particle simulation, sprite/mesh pass
    (into scene_texture when a lighting pass is active, else straight
    to the swap chain), lighting composite onto the swap chain. Port
    of renderer.js's render()'s WebGPU branch -- its Canvas 2D branch
    has no port (see entity_renderer.py's "no Canvas-2D fallback"
    note; same reasoning applies here, this client is always on the
    GPU path).
    """
    command_encoder = renderer.device.create_command_encoder()
    current_texture = renderer.context.get_current_texture()
    swap_chain_view = current_texture.create_view()

    for er in entity_renderers.values():
        er.simulate_particles(command_encoder, delta_time_ms / 1000.0)

    pass1_view = renderer.scene_texture.create_view() if renderer.lighting_pass else swap_chain_view

    # Real bug, found and fixed here (not just in a test this time) --
    # see Step 9's own verify notes for the earlier sighting: native
    # wgpu (unlike, per renderer.js's own comment, browser WebGPU) is
    # strict about depth-stencil format matching between a render pass
    # and the pipeline used within it -- "RenderPipeline... uses an
    # attachment with format None" (the 2D sprite pipeline, which
    # declares no depth state) is REJECTED by a render pass that has a
    # depth-stencil attachment bound, even though the pipeline never
    # touches it. Step 9's test worked around this by splitting 2D-mode
    # and 3D-mode draws into separate passes; this is the first place
    # with a real per-frame render loop where the actual fix belongs:
    # only bind the depth attachment when the camera is actually in 3D
    # mode (the only case anything -- 3D billboards/meshes -- reads or
    # writes it), matching camera.mode being a per-*frame* property,
    # never per-entity (a single frame's entities are never a 2D/3D
    # mix requiring different attachments mid-pass).
    camera_is_3d = state["camera"].get("mode") == "3d"

    render_pass = command_encoder.begin_render_pass(
        color_attachments=[
            {
                "view": pass1_view,
                "clear_value": (42 / 255, 42 / 255, 42 / 255, 1.0),
                "load_op": "clear",
                "store_op": "store",
            }
        ],
        depth_stencil_attachment=(
            {
                "view": renderer.depth_texture.create_view(),
                "depth_clear_value": 1.0,
                "depth_load_op": "clear",
                "depth_store_op": "store",
            }
            if renderer.depth_texture is not None and camera_is_3d
            else None
        ),
    )

    render_entities(state, delta_time_ms, render_pass)

    render_pass.end()

    if renderer.lighting_pass is not None:
        lights = _gather_lights(state)
        width, height = renderer.canvas.get_physical_size()
        renderer.lighting_pass.update_lights(lights, state["camera"], width, height)
        renderer.lighting_pass.render(command_encoder, swap_chain_view)

    renderer.device.queue.submit([command_encoder.finish()])


# --------------------------------------------------------------------
# Game-layer wiring -- connects the already-built callback registration
# points from network.py (Step 11), input.py (Step 12), and
# player_select.py/character_creation.py/ui.py (Step 14) into one
# running app.
# --------------------------------------------------------------------


def _on_connect() -> None:
    """Port of network.js's connect handler: auto-request the save
    list if currently in the player-select context. Fires on every
    real connect event, including reconnects -- matching the JS
    original's per-event (not one-shot) behavior. Note: on the very
    first connect during main()'s own startup sequence, this overlaps
    harmlessly with main()'s own explicit
    player_select.show_player_selection_menu() call, which performs
    the same connected-check-and-request -- a a minor, harmless
    duplicate request on first launch (the server just answers twice
    with the same list), not a correctness bug; kept simple rather
    than added complexity to suppress it, since JS's original design
    has the same two-call shape (initNetwork()'s connect handler,
    separately, main()'s own showPlayerSelectionMenu() call).
    """
    if game_state["context"] == GameContext.PLAYER_SELECT:
        if network.sio is not None and network.sio.connected:
            network.sio.emit("request_save_list")


def _on_state_update(data: dict) -> None:
    """Port of main.js's handleStateUpdate(): apply a state_update
    delta to game_state.entities, tracking the player entity and
    centering the camera on it.
    """
    if game_state["paused"]:
        return

    delta = data.get("delta") or {}

    if delta.get("entities"):
        for entity_id, entity_data in delta["entities"].items():
            entity = game_state["entities"].setdefault(entity_id, {})

            # Matches JS's `entity.prevX = entity.x || entityData.x` --
            # a falsy-OR check (not "is missing"), including its quirk
            # of treating x=0 as if it were absent. Ported as-is.
            entity["prev_x"] = entity.get("x") or entity_data.get("x")
            entity["prev_y"] = entity.get("y") or entity_data.get("y")

            if entity_data.get("state") is None:
                entity_data["state"] = "idle"
            if entity_data.get("facing") is None and not entity.get("facing"):
                entity_data["facing"] = "down"

            entity.update(entity_data)

            if entity_id.startswith("player_"):
                game_state["player"] = entity
                width, height = renderer.canvas.get_logical_size()
                game_state["camera"]["x"] = entity.get("x", 0) - width / 2
                game_state["camera"]["y"] = entity.get("y", 0) - height / 2

    if delta.get("removed"):
        for entity_id in delta["removed"]:
            game_state["entities"].pop(entity_id, None)


def _on_new_player_initialized(data: dict) -> None:
    """Port of the (previously never-wired-up, see character_creation.py's
    docstring) new_player_initialized -> character creation hand-off.
    """
    logger.info(f"New player initialized: {data.get('player_id')}")
    character_creation.init_character_creation()


def _on_save_list(data: dict) -> None:
    player_select.populate_player_list(data.get("saves"))


def _on_pause_toggle() -> None:
    """Port of input.js's toggleDebugPause(). No render-loop
    restart/stop here (unlike JS's requestAnimationFrame chain) --
    see player_select.py's docstring for why the continuous
    rendercanvas loop doesn't need one.
    """
    was_paused = game_state["paused"]
    game_state["paused"] = not was_paused

    if game_state["paused"]:
        game_state["previous_context"] = game_state["context"]
        game_state["context"] = GameContext.PAUSED
    else:
        game_state["context"] = game_state.get("previous_context") or GameContext.IN_GAME

    logger.info(
        f"Game {'PAUSED' if game_state['paused'] else 'RESUMED'} - Context: {game_state['context']}"
    )


def _on_process_input() -> None:
    """Port of input.js's processInput()'s GameContext switch.
    MENU/INVENTORY/DIALOGUE input processing has no port -- the JS
    original's processMenuInput/processInventoryInput/
    processDialogueInput are empty TODO-stub bodies with nothing to
    port (see frontend/js/engine/input.js).
    """
    if game_state["paused"]:
        return

    if game_state["context"] == GameContext.IN_GAME:
        input_engine.process_gameplay_input()


def _on_resize(event: dict) -> None:
    width, height = renderer.canvas.get_physical_size()
    renderer.resize(width, height)


def _imgui_gui_update() -> None:
    """The per-frame imgui widget-building function, registered via
    ImguiRenderer.set_gui(). Dispatches to whichever screen(s) are
    relevant for the current game_state.context.
    """
    context = game_state["context"]

    if context == GameContext.PLAYER_SELECT:
        player_select.render_player_select_screen()
    elif context == GameContext.IN_GAME:
        ui.render_hud(game_state["player"], game_state["entities"])
        ui.render_party_command_menu()

    # Independent overlay, not gated by game_state['context'] -- matches
    # characterCreation.js's own design (see that module's docstring);
    # no-ops internally unless init_character_creation() has been
    # called and hasn't finished/errored out.
    character_creation.render_character_creation_screen()


def _combined_draw() -> None:
    """The canvas's real per-frame draw function: game-layer update
    (interpolation, throttled input processing), the game scene render
    pass, then the imgui pass on top (separate command encoder/submit,
    LOAD not CLEAR -- confirmed safe to call get_current_texture()
    again within the same frame; see this task's Step 15 research
    notes).
    """
    global _last_frame_time

    now = time.perf_counter()
    if _last_frame_time is None:
        # First frame: 0 delta, matching JS's renderLoop's own first-
        # frame guard in effect (no interpolation movement yet) without
        # literally skipping a frame the way JS's guard does -- this
        # client's continuous rendercanvas loop doesn't have an
        # equivalent "don't draw this one" step to skip to.
        delta_time_ms = 0.0
    else:
        delta_time_ms = (now - _last_frame_time) * 1000.0
    _last_frame_time = now

    if not game_state["paused"]:
        interpolation.update_interpolation(game_state["entities"], delta_time_ms / 1000.0)

    input_engine.process_input()

    draw_game_scene(game_state, delta_time_ms)
    imgui_renderer.render()


def main() -> None:
    """Main application entry point."""
    logger.info("=" * 50)
    logger.info("ASCII Art Logo Placeholder")
    logger.info("=" * 50)

    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    logger.info("Waiting for server to start...")
    if not is_server_ready():
        logger.error("ERROR: Server failed to start within timeout period!")
        logger.error("Try running the backend directly: python -m backend.app")
        return

    logger.info("Server is ready!")
    time.sleep(0.5)  # Brief additional delay for stability

    logger.info("Opening game window...")
    renderer.init_renderer()

    global imgui_renderer
    imgui_renderer = ImguiRenderer(renderer.device, renderer.canvas)
    imgui_renderer.set_gui(_imgui_gui_update)

    input_engine.init_input(renderer.canvas)
    input_engine.set_input_handlers(
        on_pause_toggle=_on_pause_toggle,
        on_left_click=lambda x, y: ui.handle_world_click(x, y, game_state["camera"], game_state["entities"]),
        on_right_click=lambda x, y: (
            ui.show_command_menu(x, y, ui.selected_party_member) if ui.selected_party_member else None
        ),
        on_process=_on_process_input,
    )

    renderer.canvas.add_event_handler(_on_resize, "resize")

    network.set_state_handlers(
        on_initial_state=player_select.load_game_state,
        on_state_update=_on_state_update,
        on_connect=_on_connect,
    )
    network.set_character_flow_callbacks(
        {
            "on_save_list": _on_save_list,
            "on_new_player_initialized": _on_new_player_initialized,
        }
    )
    network.init_network()

    player_select.show_player_selection_menu()

    renderer.run(_combined_draw)

    logger.info("Game window closed. Exiting...")


if __name__ == "__main__":
    # Step 6 task 2 of area-system.prompt.md (--area=) extended by Step
    # 3 task 0 of level-editor.prompt.md, found by audit: the original
    # --area=-only check left no path to the launcher (or even the
    # empty-scene viewer fallback) through this entry point at all --
    # zero arguments fell straight through to real gameplay main(),
    # which needs backend.app/client.game (neither present on `engine`)
    # and fails immediately. Real gameplay now needs an explicit
    # --play, so "no recognized editor argument" unambiguously means
    # "show the launcher," never an accidental gameplay-boot attempt.
    _args = sys.argv[1:]
    if any(a.startswith("--area") for a in _args):
        from client.engine import area_viewer

        area_viewer.main()
    elif any(a.startswith("--asset") for a in _args):
        from client.engine import asset_preview

        asset_preview.main()
    elif "--play" in _args:
        main()
    else:
        from client.engine import launcher

        launcher.main()
