"""[DEV ONLY] Standalone smoke test for client/engine/picking.py -- no
GPU, no window. Step 6 of .github/prompts/level-editor.prompt.md.

Usage:
    python run_picking_test.py
"""

import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.independant_logger import Logger

logger = Logger(
    log_name="run_picking_test",
    log_file="picking_test.log",
    log_level=20,
).get_logger()

from client.engine.picking import (
    pick_entity_2d,
    pick_entity_3d,
    ray_sphere_intersect,
    screen_to_ray,
)


def check(label: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    logger.info(f"[{status}] {label}")
    if not condition:
        raise AssertionError(label)


def approx(a, b, eps=1e-6) -> bool:
    return abs(a - b) < eps


def test_screen_to_ray_center_matches_forward() -> None:
    camera = {"position": [0, 0, 100], "target": [0, 0, 0], "up": [0, 1, 0], "fov": math.pi / 4}
    origin, direction = screen_to_ray(400, 300, 800, 600, camera)
    check("center pixel ray origin == camera position", origin == (0, 0, 100))
    check(
        "center pixel ray direction points toward target (straight down -Z)",
        approx(direction[0], 0) and approx(direction[1], 0) and approx(direction[2], -1),
    )


def test_screen_to_ray_edges_diverge() -> None:
    camera = {"position": [0, 0, 100], "target": [0, 0, 0], "up": [0, 1, 0], "fov": math.pi / 4}
    _, left = screen_to_ray(0, 300, 800, 600, camera)
    _, right = screen_to_ray(800, 300, 800, 600, camera)
    check("left-edge ray points toward -X", left[0] < 0)
    check("right-edge ray points toward +X", right[0] > 0)
    _, top = screen_to_ray(400, 0, 800, 600, camera)
    _, bottom = screen_to_ray(400, 600, 800, 600, camera)
    check("top-edge (screen Y=0) ray points toward +Y (up)", top[1] > 0)
    check("bottom-edge (screen Y=height) ray points toward -Y (down)", bottom[1] < 0)


def test_ray_sphere_intersect() -> None:
    origin = (0, 0, 100)
    direction = (0, 0, -1)
    check("ray hits sphere directly ahead", ray_sphere_intersect(origin, direction, (0, 0, 0), 10) is not None)
    check("ray misses sphere far off to the side", ray_sphere_intersect(origin, direction, (200, 0, 0), 10) is None)
    check(
        "ray behind the origin (sphere is behind the camera) does not hit",
        ray_sphere_intersect(origin, direction, (0, 0, 200), 10) is None,
    )


def test_pick_entity_3d_nearest_wins() -> None:
    camera = {"position": [0, 0, 100], "target": [0, 0, 0], "up": [0, 1, 0], "fov": math.pi / 4}
    entities = {
        "far": {"x": 0, "y": 0, "z": -50},
        "near": {"x": 0, "y": 0, "z": 20},  # directly in front, closer to camera
    }
    picked = pick_entity_3d(400, 300, 800, 600, camera, entities)
    check("nearer entity wins when both are along the same ray", picked == "near")


def test_pick_entity_3d_miss() -> None:
    camera = {"position": [0, 0, 100], "target": [0, 0, 0], "up": [0, 1, 0], "fov": math.pi / 4}
    entities = {"a": {"x": 500, "y": 500, "z": 0}}
    check("clicking empty space (center) with nothing along the ray returns None", pick_entity_3d(400, 300, 800, 600, camera, entities) is None)


def test_pick_entity_2d() -> None:
    camera = {"mode": "2d", "x": 0, "y": 0, "zoom": 1.0}
    entities = {"a": {"x": 100, "y": 100}, "b": {"x": 500, "y": 500}}
    check("2D pick hits the entity under the cursor", pick_entity_2d(100, 100, camera, entities) == "a")
    check("2D pick misses when nothing is under the cursor", pick_entity_2d(300, 300, camera, entities) is None)


def test_pick_entity_2d_respects_camera_offset() -> None:
    # camera.x/y = world position of the screen's top-left corner --
    # an entity at world (600, 600) should be picked at screen (100,100)
    # when the camera is offset to (500, 500).
    camera = {"mode": "2d", "x": 500, "y": 500, "zoom": 1.0}
    entities = {"a": {"x": 600, "y": 600}}
    check("2D pick accounts for camera offset", pick_entity_2d(100, 100, camera, entities) == "a")


def main() -> None:
    logger.info("=" * 50)
    logger.info("[DEV ONLY] picking.py smoke test")
    logger.info("=" * 50)

    test_screen_to_ray_center_matches_forward()
    test_screen_to_ray_edges_diverge()
    test_ray_sphere_intersect()
    test_pick_entity_3d_nearest_wins()
    test_pick_entity_3d_miss()
    test_pick_entity_2d()
    test_pick_entity_2d_respects_camera_offset()

    logger.info("PASS: screen_to_ray, ray_sphere_intersect, pick_entity_3d/2d all verified.")


if __name__ == "__main__":
    main()
