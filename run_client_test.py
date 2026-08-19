"""[DEV ONLY] Open a hand-built 3D test scene in the native wgpu-py
desktop client.

This was originally written as the native-client equivalent of
`run_desktop_test.py`, which used to open `frontend/test-3d.html` in a
PyWebView window using the real Edge WebView2 (Chromium) engine so
WebGPU behaved the same way it would in the packaged app, rather than
depending on whatever the OS's default browser happened to be. That
legacy browser/PyWebView client (`frontend/js/`, `frontend/index.html`,
`frontend/test-3d.html`, `run_browser.py`, `run_desktop_test.py`) has
since been deleted entirely -- there is nothing left to compare this
script against, it's simply the dev-test entry point for 3D rendering
now. This opens the real GLFW/`wgpu-py` window and GPU device
`client/main.py` uses, with a hand-built scene instead of connecting
to the backend's game state, so 3D rendering can be verified visually
in isolation.

The scene mirrors what `test-3d.html` used to render, since nothing
else in the repo defines an equivalent test scene: 3 billboards at
different depths (closer ones must occlude farther ones, all facing
the camera), 2 plain crates sharing one `render_template` at different
positions/rotations (proves placement is per-instance, not baked into
the shared definition file), and 3 more crates each isolating exactly
one mesh stylization hook (`vertex_color`/`affine_uv`/`color_levels`)
-- each should be the *only* visual difference from a plain crate.
Drag to orbit, scroll to zoom.

**None of test-3d.html's crate mesh/material/entity-definition assets
ever existed as real files anywhere in the repo** -- confirmed by
search at the time this script was written, not assumed. They're
created here as real, permanent fixtures under `frontend/assets/data/
{mesh,material,entity}/` (not registered in `manifest.json`, to avoid
touching the asset-build pipeline; registered directly via
`asset_loader.register()` below instead). No dedicated crate texture
exists either -- they reuse the real human sprite atlas as a
placeholder (matching `material-example-fire.json`'s own precedent of
reusing `human_atlas` for the same reason), noted via a `_note` field
in each fixture file (harmless -- nothing here reads it, and no
schema-validation step exists anywhere in this repo to reject the
extra key).

Usage:
    python run_client_test.py               # opens the 3D test scene
    python run_client_test.py 3d-scene       # same, explicit
"""

import math
import socket
import sys
import threading
import time
from pathlib import Path

# Add the project root to the Python path early.
REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.independant_logger import Logger

# Initialize logger.
logger = Logger(
    log_name="run_client_test",
    log_file="client_test.log",
    log_level=20,  # INFO
).get_logger()

from backend.app import app, socketio

from imgui_bundle import imgui
from wgpu.utils.imgui import ImguiRenderer

from client.engine import imgui_wgpu_compat  # noqa: F401 -- apply before ImguiRenderer construction
from client.engine import interpolation, renderer
from client.engine.asset_loader import asset_loader

# draw_game_scene()/entity_renderers live in client/main.py, not
# client/engine/renderer.py -- see that module's own docstring for the
# circular-import reason. Reused directly here rather than duplicated.
import client.main as client_main

DEFAULT_SCENE = "3d-scene"


def is_server_ready(host="127.0.0.1", port=5000, timeout=10):
    """Check if the server is ready to accept connections. Same as
    run_desktop_test.py's version -- this test scene doesn't itself
    need the backend (it's hand-built, no network state), but the
    server is started anyway for parity with every other entry point
    and in case a future test scene wants live data.
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
        except Exception:
            pass
        time.sleep(0.1)
    return False


def start_server():
    """Start the Flask-SocketIO server in a separate thread."""
    logger.info("Starting game server...")
    socketio.run(
        app, host="127.0.0.1", port=5000, debug=False, allow_unsafe_werkzeug=True
    )


def register_test_assets():
    """Register the dev-test crate mesh/material/entity-definition
    fixtures directly with the asset loader, rather than through
    manifest.json (avoids touching the asset-build pipeline/schema for
    fixtures that only this dev tool uses).
    """
    asset_loader.register("mesh-example-crate", "assets/data/mesh/mesh-example-crate.json")
    asset_loader.register(
        "mesh-example-crate-vertexcolor", "assets/data/mesh/mesh-example-crate-vertexcolor.json"
    )
    asset_loader.register("entity-example-crate", "assets/data/entity/entity-example-crate.json")
    asset_loader.register(
        "entity-example-crate-vertexcolor", "assets/data/entity/entity-example-crate-vertexcolor.json"
    )
    asset_loader.register(
        "entity-example-crate-affine", "assets/data/entity/entity-example-crate-affine.json"
    )
    asset_loader.register(
        "entity-example-crate-quantized", "assets/data/entity/entity-example-crate-quantized.json"
    )


def _make_billboard_entity(x, y, z):
    """Direct port of test-3d.html's mkEntity() -- a 2D-sprite-based
    entity, drawn as a camera-facing billboard once camera.mode is
    '3d' (client/engine/entity_renderer.py's draw_entity routing).
    """
    return {
        "x": x,
        "y": y,
        "z": z,
        "size": [64, 64],
        "pivot": [0.5, 1.0],  # bottom-center, like a character standing at (x, y, z)
        "state": "idle",
        "facing": "down",
        "animation_data_paths": ["assets/data/example_human_animations.json"],
    }


def _make_mesh_entity(x, y, z, rotation, render_template="entity-example-crate"):
    """Direct port of test-3d.html's mkMeshEntity() -- with one small
    deliberate addition, not in the JS original: an explicit, real
    `animation_data_paths`. Mesh entities don't use sprite animation
    data at all, but `render_entities()` (client/main.py) unconditionally
    requests it for every entity regardless of draw path -- with none
    set, it falls back to `DEFAULT_ANIMATION_DATA_PATHS`
    ("assets/data/human_animations.json"), which is a real,
    already-documented pre-existing gap (Step 15's own notes): that
    file doesn't exist, so every mesh entity would otherwise print a
    "Failed to load animation data"/"Animation type 'stand' not found"
    warning on every single frame. Purely cosmetic log noise either
    way (confirmed: zero actual draw errors with or without this), not
    a rendering bug -- added only for a quieter dev-tool console.
    """
    return {
        "x": x,
        "y": y,
        "z": z,
        "render_template": render_template,
        "transform3d": {"rotation": rotation, "scale": [1, 1, 1]},
        "animation_data_paths": ["assets/data/example_human_animations.json"],
    }


def build_test_scene():
    """Direct port of test-3d.html's hand-built gameState -- no
    network, no Scene/Area file, just enough to exercise the 3D
    billboard and mesh draw paths directly.
    """
    return {
        "entities": {
            "billboard_near": _make_billboard_entity(-60, 0, 150),
            "billboard_mid": _make_billboard_entity(0, 0, 0),
            "billboard_far": _make_billboard_entity(60, 0, -150),
            # Step 5: two entities sharing one render_template, placed
            # and rotated independently -- proves the definition file
            # is a template (appearance only), placement genuinely
            # lives on the entity, not baked into the shared file.
            "crate_a": _make_mesh_entity(-180, 32, -50, [0, 0, 0]),
            "crate_b": _make_mesh_entity(180, 32, -50, [0, math.pi / 4, 0.4]),
            # Step 8: each of these isolates exactly one stylization
            # hook -- everything else matches a plain crate, so any
            # visual difference beyond the one hook under test is a bug.
            "crate_vertexcolor": _make_mesh_entity(
                -360, 32, -50, [0, 0, 0], "entity-example-crate-vertexcolor"
            ),
            "crate_affine": _make_mesh_entity(
                360, 32, -50, [0, math.pi / 4, 0], "entity-example-crate-affine"
            ),
            "crate_quantized": _make_mesh_entity(
                540, 32, -50, [0, 0, 0], "entity-example-crate-quantized"
            ),
        },
        "player": None,
        "camera": {
            "mode": "3d",
            "position": [0, 100, 300],
            "target": [0, 32, 0],
            "up": [0, 1, 0],
            "fov": math.pi / 4,
            "near": 1,
            "far": 2000,
        },
        "world_size": {"width": 1000, "height": 1000},
        "paused": False,
    }


class OrbitCamera:
    """Drag to orbit, scroll to zoom -- direct port of test-3d.html's
    own pointer-driven orbit controls, wired through rendercanvas's
    cross-backend event system (`canvas.add_event_handler`) instead of
    raw DOM `window.addEventListener` calls. This is deliberately
    separate from `client/engine/input.py`'s game input system (no
    `input_config.json` involvement) -- orbit-camera controls are a
    dev-tool-only concern, not part of the actual game's input scheme.
    """

    def __init__(self, target):
        self.yaw = 0.4
        self.pitch = 0.35
        self.radius = 350.0
        self.target = target
        self._dragging = False
        self._last_x = 0.0
        self._last_y = 0.0

    def on_pointer_button(self, event):
        if event["event_type"] == "pointer_down":
            self._dragging = True
            self._last_x = event["x"]
            self._last_y = event["y"]
        elif event["event_type"] == "pointer_up":
            self._dragging = False

    def on_pointer_move(self, event):
        if not self._dragging:
            return
        dx = event["x"] - self._last_x
        dy = event["y"] - self._last_y
        self._last_x = event["x"]
        self._last_y = event["y"]
        self.yaw -= dx * 0.008
        self.pitch = max(-1.4, min(1.4, self.pitch - dy * 0.008))

    def on_wheel(self, event):
        self.radius = max(80.0, min(1200.0, self.radius + event["dy"] * 0.5))

    def apply(self, camera):
        x = self.target[0] + self.radius * math.cos(self.pitch) * math.sin(self.yaw)
        y = self.target[1] + self.radius * math.sin(self.pitch)
        z = self.target[2] + self.radius * math.cos(self.pitch) * math.cos(self.yaw)
        camera["position"] = [x, y, z]
        camera["target"] = list(self.target)


def main():
    """Main application entry point."""
    scene = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SCENE
    if scene != DEFAULT_SCENE:
        logger.warning(
            f"Unknown test scene '{scene}' -- only '{DEFAULT_SCENE}' exists today, using it anyway."
        )

    logger.info("=" * 50)
    logger.info("[DEV ONLY] Native Client Test Launcher")
    logger.info(f"Target: {scene}")
    logger.info("=" * 50)

    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    logger.info("Waiting for server to start...")
    if not is_server_ready():
        logger.error("ERROR: Server failed to start within timeout period!")
        return

    logger.info("Server is ready!")
    time.sleep(0.5)

    register_test_assets()

    logger.info("Opening test window...")
    renderer.init_renderer()

    imgui_renderer = ImguiRenderer(renderer.device, renderer.canvas)

    state = build_test_scene()
    orbit = OrbitCamera(list(state["camera"]["target"]))

    renderer.canvas.add_event_handler(orbit.on_pointer_button, "pointer_down", "pointer_up")
    renderer.canvas.add_event_handler(orbit.on_pointer_move, "pointer_move")
    renderer.canvas.add_event_handler(orbit.on_wheel, "wheel")

    def gui():
        imgui.begin("Native 3D Test Scene")
        imgui.text("[DEV-ONLY TEST] -- native-client equivalent of frontend/test-3d.html")
        imgui.text_wrapped(
            "Drag to orbit, scroll to zoom. 3 billboards at z = -150 / 0 / +150 -- "
            "closer ones must occlude farther ones, all must face the camera. "
            "2 plain crates (x = -180/180) share one render_template at different "
            "positions/rotations -- proves placement is per-instance. 3 more crates "
            "(x = -360/360/540) each isolate one stylization hook: vertex_color "
            "(rainbow faces), affine_uv (warped texture on rotation), color_levels "
            "(banded colour) -- each must be the only difference from a plain crate."
        )
        imgui.separator()
        pos = [round(v, 1) for v in state["camera"]["position"]]
        imgui.text(f"camera.position = {pos}  yaw={orbit.yaw:.2f}  pitch={orbit.pitch:.2f}  radius={orbit.radius:.0f}")
        imgui.end()

    imgui_renderer.set_gui(gui)

    last_time = [None]

    def draw():
        now = time.perf_counter()
        delta_ms = 0.0 if last_time[0] is None else (now - last_time[0]) * 1000.0
        last_time[0] = now

        orbit.apply(state["camera"])
        interpolation.update_interpolation(state["entities"], delta_ms / 1000.0)
        client_main.draw_game_scene(state, delta_ms)
        imgui_renderer.render()

    renderer.run(draw)

    logger.info("Test window closed. Exiting...")


if __name__ == "__main__":
    main()
