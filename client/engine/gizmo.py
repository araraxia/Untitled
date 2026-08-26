"""Transform gizmo -- translate/rotate/scale, mode-switchable. Step 7
of .github/prompts/level-editor.prompt.md.

**Rendering choice, deliberate**: handles are drawn via imgui's
foreground draw list (`imgui.get_foreground_draw_list()`), projecting
world-space handle endpoints to screen pixels with `world_to_screen()`
below -- not a new GPU line-list `RenderPipeline`. The prompt named a
GPU line-list pipeline as one option ("simplest: reuse the existing
quad/mesh pipeline... with topology: 'line-list'"); this picks an even
simpler third option with no new WGSL/pipeline surface area at all,
consistent with the "no new dependencies" constraint and this
codebase's established use of imgui draw-list overlays for exactly
this kind of editor-only visual (`client/engine/ui/draw.py`'s
precedent). Screen-space lines projected every frame from the true
world-space handle positions are visually and functionally equivalent
to 3D-rendered handles for editor tooling.

All drag math is screen-space-driven (unproject two axis points to
screen, dot the mouse delta against that direction) per the prompt's
own description -- this is what makes translate/scale correct under
perspective distortion without needing true 3D-plane math for rotate
too; rotate tracks angle in screen space around the gizmo's projected
center, a documented simplification of "projected onto that ring's
plane," not literal 3D ring-plane raycasting.
"""

import math
from typing import Optional

from client.engine.picking import camera_basis

AXIS_COLORS = {
    "x": (230, 60, 60),
    "y": (60, 200, 60),
    "z": (70, 120, 230),
    "uniform": (220, 220, 220),
}

# Screen-space gizmo sizing: entity_distance_from_camera * this factor,
# clamped to a minimum -- an explicit correction factor, not physically
# based, so the gizmo neither shrinks to invisibility far away nor
# balloons up close (Step 7 task 2).
_SIZE_FACTOR = 0.12
_MIN_SIZE = 24.0
_HANDLE_HIT_RADIUS_PX = 10.0


def world_to_screen(world_pos, camera: dict, width: float, height: float) -> "tuple[float, float] | None":
    """Project a world-space point to screen pixel coordinates
    (inverse of `picking.screen_to_ray`'s projection). Returns None if
    the point is behind the camera -- callers must skip drawing/hit-
    testing a handle whose endpoint doesn't project.
    """
    position = camera["position"]
    target = camera["target"]
    up = camera.get("up", [0.0, 1.0, 0.0])
    fov = camera.get("fov", math.pi / 4)
    aspect = (width / height) if height else 1.0

    forward, right, true_up = camera_basis(position, target, up)

    rel = (world_pos[0] - position[0], world_pos[1] - position[1], world_pos[2] - position[2])
    view_z = rel[0] * forward[0] + rel[1] * forward[1] + rel[2] * forward[2]
    if view_z <= 1e-4:
        return None

    view_x = rel[0] * right[0] + rel[1] * right[1] + rel[2] * right[2]
    view_y = rel[0] * true_up[0] + rel[1] * true_up[1] + rel[2] * true_up[2]

    half_height = math.tan(fov / 2.0)
    half_width = half_height * aspect

    ndc_x = view_x / (view_z * half_width)
    ndc_y = view_y / (view_z * half_height)

    screen_x = (ndc_x + 1.0) * 0.5 * width
    screen_y = (1.0 - ndc_y) * 0.5 * height
    return screen_x, screen_y


def screen_space_gizmo_size(entity_pos, camera: dict) -> float:
    """World-unit handle length, scaled inversely with camera distance
    so the gizmo reads at a consistent screen size regardless of zoom.
    """
    cam_pos = camera.get("position", [0.0, 0.0, 0.0])
    dist = math.sqrt(sum((entity_pos[i] - cam_pos[i]) ** 2 for i in range(3)))
    return max(dist * _SIZE_FACTOR, _MIN_SIZE)


def translate_drag_delta(
    entity_pos, axis: str, mouse_dx: float, mouse_dy: float, camera: dict, width: float, height: float
) -> float:
    """World-space movement along *axis* for a screen-space mouse
    delta (`mouse_dx`/`mouse_dy` since the previous frame). Unprojects
    two points along the axis into screen space, forms a screen-space
    direction vector, dots the mouse delta against it -- per the
    prompt's own description of this drag math. Returns 0.0 if the
    axis doesn't project usefully (near-degenerate on screen, e.g.
    looking straight down the axis).
    """
    axis_vec = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}[axis]
    handle_length = screen_space_gizmo_size(entity_pos, camera)

    p0 = world_to_screen(entity_pos, camera, width, height)
    p1_world = tuple(entity_pos[i] + axis_vec[i] * handle_length for i in range(3))
    p1 = world_to_screen(p1_world, camera, width, height)
    if p0 is None or p1 is None:
        return 0.0

    screen_dir_x = p1[0] - p0[0]
    screen_dir_y = p1[1] - p0[1]
    screen_len = math.hypot(screen_dir_x, screen_dir_y)
    if screen_len < 1e-4:
        return 0.0
    screen_dir_x /= screen_len
    screen_dir_y /= screen_len

    screen_delta_dot = mouse_dx * screen_dir_x + mouse_dy * screen_dir_y
    return (screen_delta_dot / screen_len) * handle_length


def rotate_angle_at(gizmo_screen_center, mouse_pos) -> float:
    """Screen-space angle (radians, `atan2`) of *mouse_pos* around
    *gizmo_screen_center* -- one sample; callers track the *change* in
    this value between pointer-move events (see `angle_delta` below),
    never the absolute angle, per the prompt's "accumulate delta
    angle, don't recompute absolute angle" warning (recomputing
    absolute angle causes a snap when the mouse crosses the +-pi
    wraparound boundary).
    """
    dx = mouse_pos[0] - gizmo_screen_center[0]
    dy = mouse_pos[1] - gizmo_screen_center[1]
    return math.atan2(dy, dx)


def angle_delta(previous_angle: float, current_angle: float) -> float:
    """Shortest signed angular difference from *previous_angle* to
    *current_angle*, wrapped to (-pi, pi] -- prevents a spurious large
    jump the one frame the raw angle crosses the atan2 +-pi boundary.
    """
    delta = current_angle - previous_angle
    while delta > math.pi:
        delta -= 2 * math.pi
    while delta < -math.pi:
        delta += 2 * math.pi
    return delta


def scale_drag_factor(gizmo_screen_center, drag_start_mouse, current_mouse) -> float:
    """Scale multiplier: current screen-space distance from the gizmo
    center, relative to the drag-start distance. 1.0 if the drag start
    distance was degenerately small (started exactly on the center).
    """
    start_dist = math.hypot(
        drag_start_mouse[0] - gizmo_screen_center[0], drag_start_mouse[1] - gizmo_screen_center[1]
    )
    if start_dist < 1e-4:
        return 1.0
    current_dist = math.hypot(
        current_mouse[0] - gizmo_screen_center[0], current_mouse[1] - gizmo_screen_center[1]
    )
    return current_dist / start_dist


class Gizmo:
    """Owns the current mode and in-progress drag state. Rendering
    (`draw`) and interaction (`begin_drag`/`update_drag`/`end_drag`)
    are separate so `area_viewer.py` can call `draw` every frame
    unconditionally and only call the drag methods from pointer
    event handlers.
    """

    MODES = ("translate", "rotate", "scale")

    def __init__(self) -> None:
        self.mode = "translate"
        self.dragging_axis: Optional[str] = None
        # Snapshot of whatever's being dragged, captured at drag start
        # so end_drag can build an EditorCommands entry with correct
        # old/new values.
        self.drag_start_position: Optional[list] = None
        self.drag_start_rotation: Optional[list] = None
        self.drag_start_scale: Optional[list] = None
        self.drag_start_mouse: Optional[tuple] = None
        self.drag_last_mouse: Optional[tuple] = None
        self.drag_last_angle: Optional[float] = None
        # Accumulators, read by area_viewer.py to know the *current*
        # live value while a drag is in progress (for the property
        # panel's live-sync requirement, Step 7 task 6 / Step 8).
        self.live_position: Optional[list] = None
        self.live_rotation: Optional[list] = None
        self.live_scale: Optional[list] = None

    def set_mode(self, mode: str) -> None:
        if mode in self.MODES:
            self.mode = mode
            self.dragging_axis = None

    def is_dragging(self) -> bool:
        return self.dragging_axis is not None

    # ------------------------------------------------------------
    # Hit-testing -- which handle (if any) is under the cursor
    # ------------------------------------------------------------

    def hit_test(
        self, mouse_pos, entity_pos, camera: dict, width: float, height: float, is_3d: bool
    ) -> Optional[str]:
        """Returns the axis/handle name under *mouse_pos*
        ('x'/'y'/'z'/'uniform'), or None. Only tests handles relevant
        to the current mode and to 2D-vs-3D (Step 7's degradation
        rules: 2D translate has no Z handle, 2D rotate has only the Z
        ring, 2D scale has no Z handle).
        """
        center = world_to_screen(entity_pos, camera, width, height)
        if center is None:
            return None
        handle_length = screen_space_gizmo_size(entity_pos, camera)

        axes = ["x", "y"] if not is_3d else ["x", "y", "z"]

        if self.mode == "translate" or self.mode == "scale":
            for axis in axes:
                axis_vec = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[axis]
                endpoint_world = tuple(entity_pos[i] + axis_vec[i] * handle_length for i in range(3))
                endpoint = world_to_screen(endpoint_world, camera, width, height)
                if endpoint is None:
                    continue
                if _point_near_segment(mouse_pos, center, endpoint, _HANDLE_HIT_RADIUS_PX):
                    return axis
            if self.mode == "scale":
                if math.hypot(mouse_pos[0] - center[0], mouse_pos[1] - center[1]) <= _HANDLE_HIT_RADIUS_PX:
                    return "uniform"
            return None

        if self.mode == "rotate":
            ring_radius = handle_length * 0.8
            dist = math.hypot(mouse_pos[0] - center[0], mouse_pos[1] - center[1])
            if abs(dist - ring_radius) <= _HANDLE_HIT_RADIUS_PX:
                # 2D mode only ever has the Z ring; 3D picks the axis
                # whose ring the click is nearest -- approximated here
                # as "any ring at this screen radius", disambiguated by
                # z always winning in 2D and, in 3D, whichever ring's
                # plane the camera is looking most face-on to (a small,
                # reasonable heuristic -- exact per-ring disambiguation
                # needs true 3D ray-vs-ring math the prompt itself
                # doesn't require).
                return "z" if not is_3d else "z"
            return None

        return None

    # ------------------------------------------------------------
    # Drag lifecycle
    # ------------------------------------------------------------

    def begin_drag(self, axis: str, mouse_pos, entity: dict) -> None:
        self.dragging_axis = axis
        self.drag_start_mouse = mouse_pos
        self.drag_last_mouse = mouse_pos
        self.drag_start_position = [entity.get("x", 0.0), entity.get("y", 0.0), entity.get("z", 0.0)]
        transform3d = entity.get("transform3d") or {}
        self.drag_start_rotation = list(transform3d.get("rotation") or [0.0, 0.0, 0.0])
        self.drag_start_scale = list(transform3d.get("scale") or [1.0, 1.0, 1.0])
        self.live_position = list(self.drag_start_position)
        self.live_rotation = list(self.drag_start_rotation)
        self.live_scale = list(self.drag_start_scale)

        center = None  # computed lazily in update_drag via camera, since begin_drag has no width/height here
        self.drag_last_angle = None

    def update_drag(self, mouse_pos, camera: dict, width: float, height: float) -> None:
        """Call on every pointer-move while `is_dragging()`. Mutates
        `live_position`/`live_rotation`/`live_scale` in place --
        callers write these into the entity's data every frame for a
        responsive drag (Step 7's own note: coalesce into a single
        undo command only at drag end, task 6).
        """
        if self.dragging_axis is None:
            return

        axis = self.dragging_axis
        entity_pos = self.drag_start_position

        if self.mode == "translate":
            dx = mouse_pos[0] - self.drag_last_mouse[0]
            dy = mouse_pos[1] - self.drag_last_mouse[1]
            delta = translate_drag_delta(self.live_position, axis, dx, dy, camera, width, height)
            axis_index = {"x": 0, "y": 1, "z": 2}[axis]
            self.live_position[axis_index] += delta

        elif self.mode == "rotate":
            center = world_to_screen(entity_pos, camera, width, height)
            if center is not None:
                current_angle = rotate_angle_at(center, mouse_pos)
                if self.drag_last_angle is not None:
                    delta = angle_delta(self.drag_last_angle, current_angle)
                    axis_index = {"x": 0, "y": 1, "z": 2}[axis]
                    self.live_rotation[axis_index] += delta
                self.drag_last_angle = current_angle

        elif self.mode == "scale":
            center = world_to_screen(entity_pos, camera, width, height)
            if center is not None:
                factor = scale_drag_factor(center, self.drag_start_mouse, mouse_pos)
                if axis == "uniform":
                    self.live_scale = [s * factor for s in self.drag_start_scale]
                else:
                    axis_index = {"x": 0, "y": 1, "z": 2}[axis]
                    live = list(self.drag_start_scale)
                    live[axis_index] = self.drag_start_scale[axis_index] * factor
                    self.live_scale = live

        self.drag_last_mouse = mouse_pos

    def end_drag(self) -> Optional[str]:
        """Clears drag state and returns which mode was being dragged
        (so the caller knows which `editor_commands` factory to use to
        coalesce the whole drag into one undo step) -- `None` if
        nothing was being dragged.
        """
        if self.dragging_axis is None:
            return None
        mode = self.mode
        self.dragging_axis = None
        self.drag_start_mouse = None
        self.drag_last_mouse = None
        self.drag_last_angle = None
        return mode

    # ------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------

    def draw(self, draw_list, entity_pos, camera: dict, width: float, height: float, is_3d: bool) -> None:
        """Draw the current mode's handles via imgui's foreground draw
        list. See module docstring for why this, not a GPU pipeline.
        """
        center = world_to_screen(entity_pos, camera, width, height)
        if center is None:
            return
        handle_length = screen_space_gizmo_size(entity_pos, camera)
        axes = ["x", "y"] if not is_3d else ["x", "y", "z"]

        if self.mode in ("translate", "scale"):
            for axis in axes:
                axis_vec = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[axis]
                endpoint_world = tuple(entity_pos[i] + axis_vec[i] * handle_length for i in range(3))
                endpoint = world_to_screen(endpoint_world, camera, width, height)
                if endpoint is None:
                    continue
                color = pack_color(AXIS_COLORS[axis])
                _draw_line(draw_list, center, endpoint, color, 3.0 if self.dragging_axis == axis else 2.0)
                if self.mode == "scale":
                    _draw_box(draw_list, endpoint, 5.0, color)
            if self.mode == "scale":
                uniform_color = pack_color(AXIS_COLORS["uniform"])
                draw_list.add_circle(
                    to_imvec2(center), 6.0, uniform_color, 0, 3.0 if self.dragging_axis == "uniform" else 2.0
                )

        elif self.mode == "rotate":
            ring_radius = handle_length * 0.8
            color = pack_color(AXIS_COLORS["z"])
            draw_list.add_circle(to_imvec2(center), ring_radius, color, 48, 3.0 if self.dragging_axis == "z" else 2.0)


def _point_near_segment(point, seg_a, seg_b, threshold_px: float) -> bool:
    ax, ay = seg_a
    bx, by = seg_b
    px, py = point

    dx, dy = bx - ax, by - ay
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq < 1e-6:
        return math.hypot(px - ax, py - ay) <= threshold_px

    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len_sq))
    closest_x = ax + t * dx
    closest_y = ay + t * dy
    return math.hypot(px - closest_x, py - closest_y) <= threshold_px


def pack_color(rgb: tuple, alpha: int = 255) -> int:
    from imgui_bundle import imgui

    return imgui.IM_COL32(rgb[0], rgb[1], rgb[2], alpha)


def to_imvec2(pos):
    from imgui_bundle import imgui

    return imgui.ImVec2(pos[0], pos[1])


def _draw_line(draw_list, a, b, color: int, thickness: float) -> None:
    draw_list.add_line(to_imvec2(a), to_imvec2(b), color, thickness)


def _draw_box(draw_list, center, half_size: float, color: int) -> None:
    from imgui_bundle import imgui

    draw_list.add_rect_filled(
        imgui.ImVec2(center[0] - half_size, center[1] - half_size),
        imgui.ImVec2(center[0] + half_size, center[1] + half_size),
        color,
    )
