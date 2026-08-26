"""[DEV ONLY] Standalone smoke test for client/engine/gizmo.py's pure
math and interaction logic -- no GPU, no imgui window (drawing itself
needs a live imgui frame and isn't exercised here; hit-testing/drag
math/mode-switching all are). Step 7 of
.github/prompts/level-editor.prompt.md.

Usage:
    python run_gizmo_test.py
"""

import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.independant_logger import Logger

logger = Logger(
    log_name="run_gizmo_test",
    log_file="gizmo_test.log",
    log_level=20,
).get_logger()

from client.engine.gizmo import (
    Gizmo,
    angle_delta,
    rotate_angle_at,
    scale_drag_factor,
    screen_space_gizmo_size,
    translate_drag_delta,
    world_to_screen,
)
from client.engine.picking import screen_to_ray


def check(label: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    logger.info(f"[{status}] {label}")
    if not condition:
        raise AssertionError(label)


def approx(a, b, eps=1e-3) -> bool:
    return abs(a - b) < eps


CAMERA = {"position": [0, 0, 100], "target": [0, 0, 0], "up": [0, 1, 0], "fov": math.pi / 4}


def test_world_to_screen_center() -> None:
    screen = world_to_screen((0, 0, 0), CAMERA, 800, 600)
    check("origin (on the look-at axis) projects to screen center", approx(screen[0], 400) and approx(screen[1], 300))


def test_world_to_screen_behind_camera_is_none() -> None:
    check("a point behind the camera returns None", world_to_screen((0, 0, 200), CAMERA, 800, 600) is None)


def test_world_to_screen_round_trips_with_screen_to_ray() -> None:
    """screen_to_ray (picking.py) and world_to_screen (gizmo.py) are
    inverses of each other for a symmetric perspective frustum -- a
    point placed along a screen_to_ray-derived ray should project back
    to (approximately) the same screen pixel.
    """
    origin, direction = screen_to_ray(250, 450, 800, 600, CAMERA)
    world_point = tuple(origin[i] + direction[i] * 80 for i in range(3))
    screen = world_to_screen(world_point, CAMERA, 800, 600)
    check("round-trip screen_to_ray -> world_to_screen recovers the original pixel", screen is not None and approx(screen[0], 250, 1.0) and approx(screen[1], 450, 1.0))


def test_screen_space_gizmo_size_scales_with_distance() -> None:
    near = screen_space_gizmo_size((0, 0, 50), CAMERA)   # 50 units from camera at z=100
    far = screen_space_gizmo_size((0, 0, -500), CAMERA)  # 600 units from camera
    check("gizmo size grows with distance from camera", far > near)
    check("gizmo size never shrinks below the minimum", screen_space_gizmo_size((0, 0, 99), CAMERA) >= 24.0 - 1e-6)


def test_translate_drag_delta_along_axis() -> None:
    # Camera looking down -Z from (0,0,100) at the origin, up=(0,1,0).
    # Dragging along world +X should require a screen-space delta
    # roughly aligned with the projected +X axis (positive screen dx).
    entity_pos = [0.0, 0.0, 0.0]
    delta = translate_drag_delta(entity_pos, "x", mouse_dx=10.0, mouse_dy=0.0, camera=CAMERA, width=800, height=600)
    check("dragging right (positive screen dx) moves a +X-axis handle in +X", delta > 0)

    delta_perp = translate_drag_delta(entity_pos, "x", mouse_dx=0.0, mouse_dy=10.0, camera=CAMERA, width=800, height=600)
    check("dragging perpendicular to the X axis on screen produces ~zero X movement", abs(delta_perp) < abs(delta) * 0.2)


def test_angle_delta_wraparound() -> None:
    check("small forward delta", approx(angle_delta(0.1, 0.3), 0.2))
    check("wraparound near +pi/-pi doesn't produce a huge jump", abs(angle_delta(3.1, -3.1)) < 0.5)
    check("wraparound the other direction", abs(angle_delta(-3.1, 3.1)) < 0.5)


def test_rotate_angle_at_and_delta_full_cycle() -> None:
    center = (400, 300)
    a0 = rotate_angle_at(center, (450, 300))  # 0 radians (east)
    a1 = rotate_angle_at(center, (400, 350))  # ~pi/2 (south, screen Y down)
    check("angle changes as the mouse moves around the center", not approx(a0, a1))
    delta = angle_delta(a0, a1)
    check("quarter-turn delta is close to pi/2", approx(abs(delta), math.pi / 2, 0.05))


def test_scale_drag_factor() -> None:
    center = (400, 300)
    start = (450, 300)  # 50px from center
    same = scale_drag_factor(center, start, start)
    check("no movement -> scale factor 1.0", approx(same, 1.0))

    farther = (500, 300)  # 100px from center -- 2x the start distance
    factor = scale_drag_factor(center, start, farther)
    check("moving twice as far from center doubles the scale factor", approx(factor, 2.0))

    closer = (425, 300)  # 25px -- half the start distance
    factor2 = scale_drag_factor(center, start, closer)
    check("moving to half the start distance halves the scale factor", approx(factor2, 0.5))


def test_gizmo_mode_switching() -> None:
    gizmo = Gizmo()
    check("default mode is translate", gizmo.mode == "translate")
    gizmo.set_mode("rotate")
    check("mode switches to rotate", gizmo.mode == "rotate")
    gizmo.set_mode("bogus")
    check("an invalid mode is ignored, not applied", gizmo.mode == "rotate")


def test_gizmo_translate_drag_lifecycle() -> None:
    gizmo = Gizmo()
    gizmo.set_mode("translate")
    entity = {"x": 0.0, "y": 0.0, "z": 0.0, "transform3d": {"rotation": [0, 0, 0], "scale": [1, 1, 1]}}

    center = world_to_screen((0, 0, 0), CAMERA, 800, 600)
    gizmo.begin_drag("x", center, entity)
    check("live_position initialised to entity's starting position", gizmo.live_position == [0.0, 0.0, 0.0])

    gizmo.update_drag((center[0] + 20, center[1]), CAMERA, 800, 600)
    check("dragging moved the live X position away from 0", gizmo.live_position[0] != 0.0)
    check("Y/Z stayed put during an X-axis drag", gizmo.live_position[1] == 0.0 and gizmo.live_position[2] == 0.0)

    mode = gizmo.end_drag()
    check("end_drag reports which mode was active", mode == "translate")
    check("dragging_axis cleared after end_drag", gizmo.dragging_axis is None)


def test_gizmo_rotate_drag_lifecycle() -> None:
    gizmo = Gizmo()
    gizmo.set_mode("rotate")
    entity = {"x": 0.0, "y": 0.0, "z": 0.0, "transform3d": {"rotation": [0, 0, 0], "scale": [1, 1, 1]}}

    center = world_to_screen((0, 0, 0), CAMERA, 800, 600)
    gizmo.begin_drag("z", (center[0] + 50, center[1]), entity)
    # First update_drag after begin_drag only establishes the angle
    # baseline (by design -- "track the *change* since the previous
    # move", so there's no previous move to diff against yet); a real
    # delta only appears from the second call onward.
    gizmo.update_drag((center[0] + 35, center[1] + 35), CAMERA, 800, 600)  # ~1/8 turn
    gizmo.update_drag((center[0], center[1] + 50), CAMERA, 800, 600)  # ~1/4 turn total
    check("rotating changed the live Z rotation", gizmo.live_rotation[2] != 0.0)
    check("X/Y rotation untouched by a Z-axis rotate drag", gizmo.live_rotation[0] == 0.0 and gizmo.live_rotation[1] == 0.0)
    gizmo.end_drag()


def test_gizmo_scale_uniform_drag() -> None:
    gizmo = Gizmo()
    gizmo.set_mode("scale")
    entity = {"x": 0.0, "y": 0.0, "z": 0.0, "transform3d": {"rotation": [0, 0, 0], "scale": [1, 1, 1]}}

    center = world_to_screen((0, 0, 0), CAMERA, 800, 600)
    gizmo.begin_drag("uniform", (center[0] + 50, center[1]), entity)
    gizmo.update_drag((center[0] + 100, center[1]), CAMERA, 800, 600)
    check("uniform scale grew all three axes equally", gizmo.live_scale[0] == gizmo.live_scale[1] == gizmo.live_scale[2])
    check("uniform scale factor doubled (start 50px -> current 100px)", approx(gizmo.live_scale[0], 2.0))
    gizmo.end_drag()


def test_hit_test_2d_has_no_z_handle() -> None:
    gizmo = Gizmo()
    gizmo.set_mode("translate")
    entity_pos = (0.0, 0.0, 0.0)
    center = world_to_screen(entity_pos, CAMERA, 800, 600)
    handle_length = screen_space_gizmo_size(entity_pos, CAMERA)
    z_endpoint = world_to_screen((0, 0, handle_length), CAMERA, 800, 600)
    # In 2D mode, clicking where the Z handle *would* be in 3D mode
    # must not register as a hit.
    hit_2d = gizmo.hit_test(z_endpoint, entity_pos, CAMERA, 800, 600, is_3d=False)
    check("2D mode never reports a 'z' translate handle hit", hit_2d != "z")


def main() -> None:
    logger.info("=" * 50)
    logger.info("[DEV ONLY] gizmo.py smoke test")
    logger.info("=" * 50)

    test_world_to_screen_center()
    test_world_to_screen_behind_camera_is_none()
    test_world_to_screen_round_trips_with_screen_to_ray()
    test_screen_space_gizmo_size_scales_with_distance()
    test_translate_drag_delta_along_axis()
    test_angle_delta_wraparound()
    test_rotate_angle_at_and_delta_full_cycle()
    test_scale_drag_factor()
    test_gizmo_mode_switching()
    test_gizmo_translate_drag_lifecycle()
    test_gizmo_rotate_drag_lifecycle()
    test_gizmo_scale_uniform_drag()
    test_hit_test_2d_has_no_z_handle()

    logger.info("PASS: gizmo projection math, drag math, and interaction lifecycle all verified.")


if __name__ == "__main__":
    main()
