"""[DEV ONLY] Standalone smoke test for client/engine/ui/ -- the
custom-drawn, art-asset-skinned UI framework (Phase 7, redesigned).

No backend, no game content, no game branch needed -- everything here is
either engine-layer (client/engine/ui/) or a hand-built dev fixture,
mirroring run_client_test.py's own "hand-built scene, no network state"
approach for the same reason: this proves the primitives render
correctly in isolation, independent of whatever game eventually consumes
them.

Exercises, in one screen:
  - a themed window (templates.window) with a title and background/border
  - two custom-drawn buttons (widgets.button), each mouse-clickable AND
    keyboard/gamepad-navigable via nav.FocusManager
  - a progress bar (widgets.progress_bar) animating over time, standing
    in for an HP/AP bar
  - an animated icon (widgets.animated_icon) using a real 4-frame sprite
    strip (frontend/assets/images/ui/test_cursor_strip.png, created for
    this test) driven by AnimationController/GPUSpriteSheet -- both
    confirmed entity-free, reused here with no fake game entity involved
  - one embedded panel3d.Panel3D showing a rotating 3D mesh (reusing
    run_client_test.py's crate mesh/entity fixtures), proving the
    render-to-texture-then-imgui.image() bridge end to end
  - a confirm_dialog (templates.confirm_dialog), opened by one of the
    two buttons

Usage:
    python run_ui_test.py
"""

import math
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.independant_logger import Logger

logger = Logger(
    log_name="run_ui_test",
    log_file="ui_test.log",
    log_level=20,  # INFO
).get_logger()

from imgui_bundle import imgui
from wgpu.utils.imgui import ImguiRenderer

from client.engine import imgui_wgpu_compat  # noqa: F401 -- apply before ImguiRenderer construction
from client.engine import renderer
from client.engine.animation import Animation, AnimationController
from client.engine.asset_loader import FRONTEND_DIR, asset_loader
from client.engine.entity_renderer import EntityRenderer
from client.engine.gpu_sprite_sheet import GPUSpriteSheet
from client.engine.ui import draw, panel3d, templates, theme as ui_theme, widgets
from client.engine.ui.nav import FocusManager


def register_test_assets() -> None:
    """Register this test's fixtures directly, bypassing manifest.json
    (same reasoning as run_client_test.py's own register_test_assets):
    a dev-only test has no business touching the real asset-build
    pipeline for fixtures only it uses.
    """
    asset_loader.register("ui_theme", "assets/data/ui_theme.json")
    asset_loader.register("ui_cursor_strip", "assets/images/ui/test_cursor_strip.png")
    asset_loader.register("mesh-example-crate", "assets/data/mesh/mesh-example-crate.json")
    asset_loader.register("entity-example-crate", "assets/data/entity/entity-example-crate.json")


def main() -> None:
    logger.info("=" * 50)
    logger.info("[DEV ONLY] client/engine/ui/ smoke test")
    logger.info("=" * 50)

    renderer.init_renderer()
    register_test_assets()

    imgui_renderer = ImguiRenderer(renderer.device, renderer.canvas)
    draw.init(imgui_renderer)

    theme = ui_theme.load_theme(renderer.device, "ui_theme")
    nav = FocusManager()

    # -- animated icon: a real 4-frame sprite strip, entity-free --------
    cursor_sheet = GPUSpriteSheet(
        renderer.device,
        "assets/images/ui/test_cursor_strip.png",
        frame_width=16,
        frame_height=16,
        columns=4,
        rows=1,
    )
    cursor_sheet.load()
    cursor_controller = AnimationController(
        {"bounce": Animation("bounce", start_frame=0, frame_count=4, frame_time=120.0, loop=True)}
    )
    cursor_controller.play("bounce")

    # -- embedded 3D preview: a rotating crate, via panel3d.Panel3D -----
    preview = panel3d.Panel3D(renderer.device, width=200, height=200)
    preview_entity_renderer = EntityRenderer("ui_preview_crate")
    crate_path = FRONTEND_DIR / asset_loader.resolve("entity-example-crate")
    import json

    crate_definition = json.loads(crate_path.read_text(encoding="utf-8"))
    preview_camera = {
        "mode": "3d",
        "position": [0, 60, 220],
        "target": [0, 0, 0],
        "up": [0, 1, 0],
        "fov": math.pi / 4,
        "near": 1,
        "far": 2000,
    }

    state = {
        "hp_fraction": 1.0,
        "hp_direction": -1,
        "confirm_open": False,
        "confirm_result": None,
        "start_time": time.perf_counter(),
    }

    def gui() -> None:
        now = time.perf_counter()
        elapsed = now - state["start_time"]

        # Progress bar animates back and forth 0..1 to prove
        # widgets.progress_bar actually redraws every frame.
        state["hp_fraction"] += state["hp_direction"] * 0.01
        if state["hp_fraction"] <= 0.0 or state["hp_fraction"] >= 1.0:
            state["hp_direction"] *= -1
            state["hp_fraction"] = max(0.0, min(1.0, state["hp_fraction"]))

        cursor_controller.update(16.0)

        # Render the crate preview into its own offscreen texture this
        # frame -- rotation driven by elapsed time.
        preview_entity = {
            "id": "ui_preview_crate",
            "x": 0.0,
            "y": 0.0,
            "z": 0.0,
            "transform3d": {"rotation": [0.3, elapsed * 0.8, 0.0], "scale": [1, 1, 1]},
        }

        def draw_preview(pass_encoder) -> None:
            preview_entity_renderer.draw_entity_mesh_parts(
                preview_entity, preview_camera, pass_encoder, crate_definition
            )

        preview_view = preview.render(draw_preview, clear_value=(0.08, 0.08, 0.12, 1.0))

        ctx = draw.begin_frame()

        win_min, win_max = (40.0, 40.0), (560.0, 420.0)
        templates.window(ctx, win_min, win_max, "client/engine/ui/ smoke test", theme)

        nav.begin_frame()

        widgets.progress_bar(
            ctx,
            (60.0, 80.0),
            (400.0, 104.0),
            state["hp_fraction"],
            theme,
            fill_key="health_full" if state["hp_fraction"] >= 0.3 else "health_low",
            overlay_text=f"HP {state['hp_fraction']:.0%}",
        )

        widgets.animated_icon(ctx, (420.0, 78.0), (452.0, 110.0), cursor_sheet, cursor_controller)

        if widgets.button(ctx, nav, "btn_confirm_demo", (60.0, 130.0), (220.0, 168.0), "Open Confirm Dialog", theme):
            state["confirm_open"] = True
        if widgets.button(ctx, nav, "btn_noop", (240.0, 130.0), (400.0, 168.0), "Does Nothing", theme):
            pass

        ctx.image(preview_view, (60.0, 190.0), (260.0, 390.0))
        widgets.label(ctx, (60.0, 396.0), "embedded 3D preview (panel3d.Panel3D)", theme, color_key="text_muted", size=13.0)

        if state["confirm_open"]:
            dialog_min, dialog_max = (180.0, 160.0), (500.0, 280.0)
            result = templates.confirm_dialog(
                ctx,
                nav,
                "smoke_test_confirm",
                dialog_min,
                dialog_max,
                "This is a templates.confirm_dialog(). Confirm or cancel?",
                theme,
            )
            if result is not None:
                state["confirm_result"] = result
                state["confirm_open"] = False

        if state["confirm_result"]:
            widgets.label(ctx, (60.0, 300.0), f"Last dialog result: {state['confirm_result']}", theme)

        nav.end_frame()

    imgui_renderer.set_gui(gui)

    def draw_frame() -> None:
        current_texture = renderer.context.get_current_texture()
        command_encoder = renderer.device.create_command_encoder()
        pass_encoder = command_encoder.begin_render_pass(
            color_attachments=[
                {
                    "view": current_texture.create_view(),
                    "clear_value": renderer.BACKGROUND_COLOR,
                    "load_op": "clear",
                    "store_op": "store",
                }
            ],
        )
        pass_encoder.end()
        renderer.device.queue.submit([command_encoder.finish()])

        imgui_renderer.render()

    renderer.run(draw_frame)

    logger.info("Test window closed. Exiting...")


if __name__ == "__main__":
    main()
