"""Viewport picking -- the prerequisite for the gizmo (Step 7) and
property panel (Step 8): you can't move or edit what you haven't
selected. Step 6 of .github/prompts/level-editor.prompt.md.

3D picking derives a world-space ray directly from the camera's own
basis vectors and FOV rather than inverting a 4x4 view-projection
matrix (`client/engine/mat4.py` has no general inverse, and one isn't
needed here) -- mathematically equivalent to an inverse-unprojection
for a symmetric perspective frustum, and this is editor tooling, not a
place that needs to match a GPU pipeline's exact numerics.

Picking tests a cheap bounding-sphere/rectangle approximation, not
exact mesh geometry -- an approximate, cheap test is fine for editor
tooling, not gameplay-critical precision (mirrors the prompt's own
framing).
"""

import math
from typing import Optional

# Default bounding-sphere radius (3D) / half-extent (2D) used for
# picking. Entities don't carry a real bounding-box/radius field today
# -- this is a reasonable fixed heuristic, not exact mesh bounds.
DEFAULT_PICK_RADIUS_3D = 32.0
DEFAULT_PICK_HALF_EXTENT_2D = 16.0


def camera_basis(position, target, up) -> tuple:
    """(forward, right, up) unit basis vectors for a 3D camera --
    same convention `client/engine/mat4.py`'s `look_at()` uses
    internally (forward = normalize(target - eye)).
    """
    fx = target[0] - position[0]
    fy = target[1] - position[1]
    fz = target[2] - position[2]
    flen = math.sqrt(fx * fx + fy * fy + fz * fz) or 1.0
    forward = (fx / flen, fy / flen, fz / flen)

    rx = forward[1] * up[2] - forward[2] * up[1]
    ry = forward[2] * up[0] - forward[0] * up[2]
    rz = forward[0] * up[1] - forward[1] * up[0]
    rlen = math.sqrt(rx * rx + ry * ry + rz * rz) or 1.0
    right = (rx / rlen, ry / rlen, rz / rlen)

    ux = right[1] * forward[2] - right[2] * forward[1]
    uy = right[2] * forward[0] - right[0] * forward[2]
    uz = right[0] * forward[1] - right[1] * forward[0]

    return forward, right, (ux, uy, uz)


def screen_to_ray(
    mouse_x: float, mouse_y: float, width: float, height: float, camera: dict
) -> tuple:
    """Build a world-space ray `(origin, direction)` from the camera
    through the clicked screen pixel (pixel coordinates, Y down --
    matches `client/engine/input.py`'s `mouse_x`/`mouse_y`
    convention).
    """
    position = tuple(camera["position"])
    target = tuple(camera["target"])
    up = camera.get("up", [0.0, 1.0, 0.0])
    fov = camera.get("fov", math.pi / 4)
    aspect = (width / height) if height else 1.0

    forward, right, true_up = camera_basis(position, target, up)

    ndc_x = (2.0 * mouse_x / width) - 1.0 if width else 0.0
    ndc_y = 1.0 - (2.0 * mouse_y / height) if height else 0.0  # screen Y grows down, NDC Y grows up

    half_height = math.tan(fov / 2.0)
    half_width = half_height * aspect

    dx = forward[0] + right[0] * ndc_x * half_width + true_up[0] * ndc_y * half_height
    dy = forward[1] + right[1] * ndc_x * half_width + true_up[1] * ndc_y * half_height
    dz = forward[2] + right[2] * ndc_x * half_width + true_up[2] * ndc_y * half_height
    dlen = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0

    return position, (dx / dlen, dy / dlen, dz / dlen)


def ray_sphere_intersect(
    ray_origin: tuple, ray_direction: tuple, sphere_center: tuple, sphere_radius: float
) -> "float | None":
    """Nearest non-negative intersection distance along the ray, or
    None. Standard quadratic ray-sphere test.
    """
    ox, oy, oz = ray_origin
    dx, dy, dz = ray_direction
    cx, cy, cz = sphere_center

    lx, ly, lz = ox - cx, oy - cy, oz - cz
    a = dx * dx + dy * dy + dz * dz
    b = 2.0 * (dx * lx + dy * ly + dz * lz)
    c = lx * lx + ly * ly + lz * lz - sphere_radius * sphere_radius

    discriminant = b * b - 4 * a * c
    if discriminant < 0 or a == 0:
        return None

    sqrt_disc = math.sqrt(discriminant)
    t1 = (-b - sqrt_disc) / (2 * a)
    t2 = (-b + sqrt_disc) / (2 * a)

    if t1 >= 0:
        return t1
    if t2 >= 0:
        return t2
    return None


def entity_pick_radius(entity: dict) -> float:
    """Cheap heuristic bounding-sphere radius for 3D picking -- see
    module docstring on why this isn't exact mesh bounds.
    """
    return DEFAULT_PICK_RADIUS_3D


def pick_entity_3d(
    mouse_x: float, mouse_y: float, width: float, height: float, camera: dict, entities: dict
) -> Optional[str]:
    """Nearest entity (by ray-hit distance -- correctly resolves
    occlusion, a nearer entity wins over a farther one even if both
    bounding spheres are hit) whose bounding sphere the screen-space
    ray from the camera intersects, or None. `entities` is a
    `Scene.entities`-shaped dict.
    """
    ray_origin, ray_direction = screen_to_ray(mouse_x, mouse_y, width, height, camera)

    best_id = None
    best_t = None
    for entity_id, entity in entities.items():
        center = (entity.get("x", 0.0), entity.get("y", 0.0), entity.get("z", 0.0))
        radius = entity_pick_radius(entity)
        t = ray_sphere_intersect(ray_origin, ray_direction, center, radius)
        if t is not None and (best_t is None or t < best_t):
            best_t = t
            best_id = entity_id

    return best_id


def pick_entity_2d(mouse_x: float, mouse_y: float, camera: dict, entities: dict) -> Optional[str]:
    """2D-mode pick: inverse the camera's screen transform (`camera.x`/
    `camera.y` as the world position of the screen's top-left corner,
    matching `client/main.py`'s own `_on_state_update` convention:
    `camera.x = player.x - width/2`, i.e. `world_x = screen_x +
    camera.x`) to get world coordinates, hit-test against each
    entity's fixed-size rectangle. Nearest center wins on overlap.
    """
    cam_x = camera.get("x", 0.0)
    cam_y = camera.get("y", 0.0)
    zoom = camera.get("zoom", 1.0) or 1.0

    world_x = cam_x + mouse_x / zoom
    world_y = cam_y + mouse_y / zoom

    half_extent = DEFAULT_PICK_HALF_EXTENT_2D

    best_id = None
    best_dist_sq = None
    for entity_id, entity in entities.items():
        ex = entity.get("x", 0.0)
        ey = entity.get("y", 0.0)
        if abs(world_x - ex) <= half_extent and abs(world_y - ey) <= half_extent:
            dist_sq = (world_x - ex) ** 2 + (world_y - ey) ** 2
            if best_dist_sq is None or dist_sq < best_dist_sq:
                best_dist_sq = dist_sq
                best_id = entity_id

    return best_id


def pick_entity(
    mouse_x: float, mouse_y: float, width: float, height: float, camera: dict, entities: dict
) -> Optional[str]:
    """Dispatches on `camera.get("mode")` -- the one entry point
    `area_viewer.py`'s click handler calls, so it never needs to check
    2D-vs-3D itself.
    """
    if camera.get("mode") == "3d":
        return pick_entity_3d(mouse_x, mouse_y, width, height, camera, entities)
    return pick_entity_2d(mouse_x, mouse_y, camera, entities)
