"""Milestone-1 game client -- owns the live `Scene`, the third-person
camera, and the two network state-sync callbacks. `client/main.py`
owns the window/render-loop/imgui orchestration; this module is
exactly the game-specific sliver on top of it.

Uses `Scene` as the live client-side gameplay state container, not a
bespoke `game_state` dict -- `Scene`'s own module docstring already
says it's meant to eventually fill this role on a game branch, so this
closes that gap with real engine code instead of duplicating it.
"""

from __future__ import annotations

from typing import Optional

from client.engine.asset_loader import asset_loader
from client.engine.camera_modes import ThirdPersonCamera
from client.engine.scene import Scene
from client.engine import input as input_engine
from client.engine import interpolation, renderer

scene = Scene()
player_entity_id: Optional[str] = None
camera: Optional[ThirdPersonCamera] = None

# Milestone 1 has no real character/ground art yet (see
# .github/prompts, "Area content" step) -- reuse the existing
# dev-fixture crate mesh (excluded from the real asset manifest by
# tools/build_manifest.py's "example_" skip, so it must be registered
# directly, same as area_viewer.py's own _register_dev_fixtures()
# does for the same fixture) as a stand-in for both the player and a
# few static landmark entities, purely for visual motion confirmation.
_LANDMARK_TEMPLATE = "entity-example-crate"
_LANDMARK_POSITIONS = [
    (150.0, 0.0, 0.0),
    (-150.0, 0.0, 0.0),
    (0.0, 0.0, 200.0),
]


def _register_dev_assets() -> None:
    asset_loader.register(
        "mesh-example-crate", "assets/data/mesh/mesh-example-crate.json"
    )
    asset_loader.register(
        _LANDMARK_TEMPLATE, "assets/data/entity/entity-example-crate.json"
    )


def _add_landmarks() -> None:
    for i, (x, y, z) in enumerate(_LANDMARK_POSITIONS):
        scene.add_entity(
            f"landmark_{i}",
            {
                "x": x,
                "y": y,
                "z": z,
                "render_template": _LANDMARK_TEMPLATE,
                "transform3d": {
                    "rotation": [0.0, 0.0, 0.0],
                    "scale": [1.0, 1.0, 1.0],
                },
                # Required to clear EntityRenderer.draw_entity()'s
                # loading_complete gate -- see area.py's
                # create_milestone1_area() for the full story.
                "animation_data_paths": [
                    "assets/data/example_human_animations.json"
                ],
            },
            "local",
        )


def init() -> None:
    """Call once before connecting -- loads the real asset manifest
    (every other rendering boot path -- area_viewer.py/asset_preview.py/
    launcher.py -- does this; a real bug, found via a blank live-run
    screenshot, not assumed: skipping it left the crate mesh/material's
    own texture references unresolved, rendering nothing at all despite
    no exception anywhere) and registers the dev-fixture assets and
    static landmark entities described above.
    """
    asset_loader.load_manifest()
    _register_dev_assets()
    _add_landmarks()


def on_initial_state(data: dict) -> None:
    global player_entity_id, camera
    for entity_id, entity_data in (data.get("entities") or {}).items():
        scene.add_entity(entity_id, entity_data, "authoritative")
    player_entity_id = data.get("player_entity_id")
    if player_entity_id and player_entity_id in scene.entities:
        camera = ThirdPersonCamera(target=scene.entities[player_entity_id])
        camera.bind(renderer.canvas)
        # Always-on mouse-look starts exactly when the camera does --
        # nothing to look at/lock the cursor for before this. See
        # ThirdPersonCamera's own docstring for why locking the cursor
        # is this caller's job, not the camera's.
        renderer.set_cursor_locked(True)


def on_state_update(data: dict) -> None:
    delta = data.get("delta") or {}
    for entity_id, entity_data in (delta.get("entities") or {}).items():
        if entity_id in scene.entities:
            scene.update_entity(entity_id, entity_data)
        else:
            scene.add_entity(entity_id, entity_data, "authoritative")
    for entity_id in delta.get("removed") or []:
        scene.remove_entity(entity_id)


def frame(delta_time_ms: float) -> None:
    """Called once per rendered frame by client/main.py's draw loop."""
    interpolation.update_interpolation(scene.entities, delta_time_ms / 1000.0)
    if camera is not None:
        camera.update(delta_time_ms / 1000.0)
        camera.apply(scene.camera)


def process_movement_input() -> None:
    """Registered as `input_engine`'s `on_process` callback -- the one
    place that bridges the engine-layer input system and this game's
    camera, since `input.process_gameplay_input_camera_relative()`
    deliberately takes a plain `camera_yaw` float rather than importing
    a camera object itself (see that function's own docstring). Which
    style is active comes from `input_config.json`'s `settings.
    movement_style` (`input_engine.get_movement_style()`), not
    hardcoded here.
    """
    style = input_engine.get_movement_style()
    if style == "camera_relative" and camera is not None:
        input_engine.process_gameplay_input_camera_relative(camera.yaw)
    else:
        input_engine.process_gameplay_input_area_relative()
