"""Asset preview mode -- a single-asset viewer with an orbit camera and
live stylization toggles. Step 4 of
.github/prompts/level-editor.prompt.md. Generalises and supersedes
ROADMAP.md Phase 9.2's "Animation Preview" page concept.

Read-only inspection: no editing affordances, no `Scene`/`EditorCommands`
involvement at all -- just load one asset into an otherwise-empty scene
and look at it from every angle.
"""

import json
import math
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.independant_logger import Logger

logger = Logger(
    log_name="asset_preview",
    log_file="asset_preview.log",
    log_level=20,
).get_logger()

from imgui_bundle import imgui
from wgpu.utils.imgui import ImguiRenderer

from client.engine import imgui_wgpu_compat  # noqa: F401
from client.engine import interpolation, renderer
from client.engine.asset_loader import asset_loader
from client.engine.scene import Scene

import client.main as client_main

_PREVIEW_ENTITY_DIR = REPO_ROOT / "frontend" / "assets" / "data" / "entity"
_PREVIEW_TEMPLATE_KEY = "_preview_tmp"


class OrbitCamera:
    """Drag to orbit, scroll to zoom -- same shape as
    run_client_test.py's own OrbitCamera (dev-tool-only, independent of
    client/engine/input.py's game input system).
    """

    def __init__(self, target=(0.0, 0.0, 0.0), radius: float = 200.0) -> None:
        self.yaw = 0.4
        self.pitch = 0.3
        self.radius = radius
        self.target = list(target)
        self._dragging = False
        self._last_x = 0.0
        self._last_y = 0.0

    def bind(self, canvas) -> None:
        canvas.add_event_handler(self._on_pointer_button, "pointer_down", "pointer_up")
        canvas.add_event_handler(self._on_pointer_move, "pointer_move")
        canvas.add_event_handler(self._on_wheel, "wheel")

    def _on_pointer_button(self, event: dict) -> None:
        if event.get("button") != 1:
            return
        if event["event_type"] == "pointer_down":
            self._dragging = True
            self._last_x = event["x"]
            self._last_y = event["y"]
        elif event["event_type"] == "pointer_up":
            self._dragging = False

    def _on_pointer_move(self, event: dict) -> None:
        if not self._dragging:
            return
        dx = event["x"] - self._last_x
        dy = event["y"] - self._last_y
        self._last_x = event["x"]
        self._last_y = event["y"]
        self.yaw -= dx * 0.008
        self.pitch = max(-1.4, min(1.4, self.pitch - dy * 0.008))

    def _on_wheel(self, event: dict) -> None:
        self.radius = max(20.0, min(2000.0, self.radius + event["dy"] * 0.5))

    def apply(self, camera: dict) -> None:
        x = self.target[0] + self.radius * math.cos(self.pitch) * math.sin(self.yaw)
        y = self.target[1] + self.radius * math.sin(self.pitch)
        z = self.target[2] + self.radius * math.cos(self.pitch) * math.cos(self.yaw)
        camera["mode"] = "3d"
        camera["position"] = [x, y, z]
        camera["target"] = list(self.target)
        camera.setdefault("up", [0, 1, 0])
        camera.setdefault("fov", math.pi / 4)
        camera.setdefault("near", 1)
        camera.setdefault("far", 2000)


def _write_synthetic_definition(asset_id: str, asset_type: str) -> str:
    """For `asset_type in ('mesh', 'material')`, `render_template`
    resolution needs a real entity-*definition* file (there's no
    "just render this raw mesh" shortcut in `draw_entity` -- it always
    resolves `entity.render_template` to a definition file first). This
    writes a small throwaway one to a fixed scratch path and registers
    it under a fixed key, reused/overwritten on every preview launch
    rather than accumulating files. Not part of the real asset catalog
    -- never manifest-registered.

    Material preview is a documented simplification: there's no
    standalone "flat textured quad" mesh asset in this project to
    apply an arbitrary material to, so it reuses the example crate
    mesh's geometry as a stand-in preview surface, per the prompt's
    "or a bare textured quad for type=material" allowance.
    """
    if asset_type == "entity":
        return asset_id  # already a real entity-definition id

    _PREVIEW_ENTITY_DIR.mkdir(parents=True, exist_ok=True)
    path = _PREVIEW_ENTITY_DIR / f"entity-{_PREVIEW_TEMPLATE_KEY}.json"

    if asset_type == "mesh":
        definition = {"mesh": asset_id}
    elif asset_type == "material":
        if not asset_loader.has("mesh-example-crate"):
            asset_loader.register("mesh-example-crate", "assets/data/mesh/mesh-example-crate.json")
        definition = {"mesh": "mesh-example-crate", "material_id": f"material/{asset_id}.json"}
    else:
        raise ValueError(f"Unknown asset_type: {asset_type!r}")

    path.write_text(json.dumps(definition, indent=2), encoding="utf-8")
    asset_loader.register(_PREVIEW_TEMPLATE_KEY, f"assets/data/entity/entity-{_PREVIEW_TEMPLATE_KEY}.json")
    return _PREVIEW_TEMPLATE_KEY


class _PreviewState:
    def __init__(self) -> None:
        self.vertex_color = False
        self.affine_uv = False
        self.color_levels = 0
        self.fog_color = [0.1, 0.1, 0.15]
        self.fog_near = 0.0
        self.fog_far = 0.0
        self.ambient_color = [1.0, 1.0, 1.0]
        self.simulate_motion = False
        self.paused = False


def _apply_material_overrides(entity_renderer_module, entity_id: str, part_id: "str | None", state: _PreviewState) -> None:
    """Mutate the cached material handle directly -- `vertex_color`/
    `affine_uv`/`color_levels` are read straight off the loaded
    material handle each frame (`entity_renderer.py`'s mesh-draw path),
    not through `set_entity_runtime`'s override mechanism (that only
    covers a different field set -- glow/tint/ramp/cosine-palette).
    Reaching into `EntityRenderer._material_handles` directly is a
    targeted, preview-mode-only mechanism, not something a real game
    would ever need to do.
    """
    for er in entity_renderer_module.entity_renderers.values():
        for handle_key, handle in list(er._material_handles.items()):
            if handle_key == entity_id or handle_key.startswith(f"{entity_id}:"):
                if handle:
                    handle["vertex_color"] = state.vertex_color
                    handle["affine_uv"] = state.affine_uv
                    handle["color_levels"] = state.color_levels


def run(asset_id: str, asset_type: str) -> bool:
    """Load *asset_id* (of *asset_type*: 'mesh'/'entity'/'material')
    into an empty scene and look at it with an orbit camera. Blocks
    until the window closes. Returns True if closed via the "Back to
    Launcher" button (the caller should show the launcher again), False
    on a plain window-close (the caller should treat this as a quit).
    """
    logger.info(f"Asset preview -- {asset_type}:{asset_id}")

    asset_loader.load_manifest()
    render_template = _write_synthetic_definition(asset_id, asset_type)

    scene = Scene()
    scene.add_entity(
        "preview",
        {
            "entity_id": "preview",
            "x": 0.0,
            "y": 0.0,
            "z": 0.0,
            "state": "idle",
            "facing": "down",
            "animation_data_paths": ["assets/data/example_human_animations.json"],
            "render_template": render_template,
            "transform3d": {"rotation": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0]},
        },
        "local",
    )

    renderer.init_renderer()
    imgui_renderer = ImguiRenderer(renderer.device, renderer.canvas)

    orbit = OrbitCamera()
    orbit.bind(renderer.canvas)
    orbit.apply(scene.camera)

    render_state = {"entities": scene.entities, "camera": scene.camera}
    state = _PreviewState()
    back_to_launcher = [False]

    def gui() -> None:
        imgui.begin("Asset Preview")
        imgui.text(f"{asset_type}: {asset_id}")
        imgui.text_wrapped("Drag to orbit, scroll to zoom. Read-only.")
        imgui.separator()

        _, state.vertex_color = imgui.checkbox("vertex_color", state.vertex_color)
        _, state.affine_uv = imgui.checkbox("affine_uv", state.affine_uv)
        _, state.color_levels = imgui.slider_int("color_levels", state.color_levels, 0, 16)
        _, state.fog_color = imgui.input_float3("fogColor", state.fog_color)
        _, state.fog_near = imgui.input_float("fogNear", state.fog_near)
        _, state.fog_far = imgui.input_float("fogFar", state.fog_far)
        _, state.ambient_color = imgui.input_float3("ambientColor", state.ambient_color)
        _, state.simulate_motion = imgui.checkbox("Simulate Motion", state.simulate_motion)
        _, state.paused = imgui.checkbox("Pause animation", state.paused)

        if imgui.button("Back to Launcher"):
            back_to_launcher[0] = True
            # Do not close the canvas here -- see launcher.py's `gui()`
            # docstring note for the real crash this caused
            # ("Texture with '<Surface Texture>' label has been
            # destroyed"): this callback runs inside
            # imgui_renderer.render()'s own frame bracket, before it's
            # done submitting its own draw commands. draw() below
            # closes the canvas once the frame is actually finished.

        imgui.end()

    imgui_renderer.set_gui(gui)

    last_time = [None]
    start_time = time.perf_counter()

    def draw() -> None:
        now = time.perf_counter()
        delta_ms = 0.0 if last_time[0] is None else (now - last_time[0]) * 1000.0
        last_time[0] = now

        scene.camera["fogColor"] = list(state.fog_color)
        scene.camera["fogNear"] = state.fog_near
        scene.camera["fogFar"] = state.fog_far
        scene.camera["ambientColor"] = list(state.ambient_color)
        orbit.apply(scene.camera)

        entity = scene.entities["preview"]
        if state.simulate_motion:
            elapsed = now - start_time
            entity["x"] = math.sin(elapsed * 0.8) * 20.0
        else:
            entity["x"] = 0.0

        effective_delta_ms = 0.0 if state.paused else delta_ms
        interpolation.update_interpolation(scene.entities, effective_delta_ms / 1000.0)
        client_main.draw_game_scene(render_state, effective_delta_ms)
        _apply_material_overrides(client_main, "preview", None, state)
        imgui_renderer.render()
        if back_to_launcher[0]:
            renderer.canvas.close()

    renderer.run(draw)
    logger.info("Asset preview closed.")
    return back_to_launcher[0]


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--asset", required=True)
    parser.add_argument("--asset-type", required=True, choices=["mesh", "entity", "material"])
    args = parser.parse_args()
    run(asset_id=args.asset, asset_type=args.asset_type)


if __name__ == "__main__":
    main()
