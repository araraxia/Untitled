"""Standalone Area/Scene boot path -- viewer, builder, and test modes
all share this one entry point. Also the level editor itself
(.github/prompts/level-editor.prompt.md) once `--mode=builder` is
active: selection, transform gizmo, property panel, asset browser,
grid/snapping, undo/redo, and save/load all live here.

Reclassified engine-layer, 2026-08-20 (originally scoped as
`client/game/area_viewer.py`) -- nothing in this module's own spec is
game-specific, the same reasoning that already put `client/engine/ui/`
on `engine` instead of a game branch. See area-system.prompt.md's
branch-reconciliation banner for the full per-step breakdown.

Mirrors run_client_test.py's self-contained-boot pattern (its own
renderer.init_renderer(), its own ImguiRenderer, its own render loop)
rather than going through client/main.py's main(), which is tightly
coupled to client.game.player_select.game_state/character_creation/ui
-- none of which exist on `engine`, and none of which this mode needs:
viewer/builder/test mode never opens a network connection at all.

Usage:
    python -m client.engine.area_viewer --area=<path>
    python -m client.engine.area_viewer --area=<path> --mode=builder
    python -m client.engine.area_viewer                # empty scene, viewer mode
"""

import argparse
import json
import math
import sys
import time
import uuid
from pathlib import Path

# client/engine/area_viewer.py -> client/engine -> client -> repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.independant_logger import Logger

logger = Logger(
    log_name="area_viewer",
    log_file="area_viewer.log",
    log_level=20,  # INFO
).get_logger()

from imgui_bundle import imgui
from wgpu.utils.imgui import ImguiRenderer

from client.engine import imgui_wgpu_compat  # noqa: F401 -- apply before ImguiRenderer construction
from client.engine import interpolation, renderer
from client.engine.area_io import area_id_from_path, load_entity_definition, save_area, save_entity_definition
from client.engine.asset_loader import asset_loader
from client.engine.editor_commands import (
    Command,
    EditorCommands,
    add_entity_command,
    add_zone_command,
    move_entity_command,
    remove_entity_command,
    remove_zone_command,
    rotate_entity_command,
    scale_entity_command,
    set_start_camera_command,
    set_start_lighting_command,
    update_entity_command,
    update_zone_command,
)
from client.engine.entity_template_editing import default_part_buffer, draw_part_fields
from client.engine.free_camera import FreeCamera
from client.engine.gizmo import Gizmo
from client.engine.picking import pick_entity
from client.engine.scene import Scene

# draw_game_scene()/entity_renderers live in client/main.py, not
# client/engine/renderer.py -- see that module's own docstring for the
# circular-import reason. Reused directly here rather than duplicated,
# same as run_client_test.py already does.
import client.main as client_main

DEFAULT_AREA_DIR = REPO_ROOT / "frontend" / "assets" / "data" / "area"
ACTIONS_PATH = REPO_ROOT / "frontend" / "assets" / "data" / "actions.json"

_CLICK_MOVE_THRESHOLD_PX = 5.0  # movement below this = a click, not a drag
_DEFAULT_GRID_SIZE = 1.0
_DEFAULT_PLACE_DISTANCE = 150.0  # world units in front of the camera, for asset-browser placement


def _generate_local_id() -> str:
    return f"local_{uuid.uuid4().hex[:8]}"


def _register_dev_fixtures() -> None:
    """Register the mesh/entity/animation fixtures `frontend/assets/
    data/area/area-example.json` (Step 6's own verify content)
    references, the same way run_client_test.py registers its own test
    fixtures directly via `asset_loader.register()` -- "not registered
    in manifest.json, to avoid touching the asset-build pipeline" (that
    file's own docstring). These fixtures already exist as real files
    on disk from this session's 3D-coordinate-mapping work; this just
    makes their ids resolvable outside run_client_test.py's own process.
    """
    asset_loader.register("mesh-example-crate", "assets/data/mesh/mesh-example-crate.json")
    asset_loader.register("entity-example-crate", "assets/data/entity/entity-example-crate.json")
    asset_loader.register(
        "mesh-example-staff-shaft", "assets/data/mesh/mesh-example-staff-shaft.json"
    )
    asset_loader.register(
        "mesh-example-staff-charm", "assets/data/mesh/mesh-example-staff-charm.json"
    )
    asset_loader.register("entity-example-staff", "assets/data/entity/entity-example-staff.json")
    asset_loader.register(
        "anim-transform-charm-spin", "assets/data/animation/animation-transform-charm-spin.json"
    )
    asset_loader.register(
        "anim-transform-charm-activate-swing",
        "assets/data/animation/animation-transform-charm-activate-swing.json",
    )


def _build_empty_scene() -> Scene:
    """Step 6 task 3's fallback: no `--area` value resolves to a real
    file, so this mode is still useful for smoke-testing the renderer
    alone -- an empty scene, 3D camera looking at the origin.
    """
    scene = Scene()
    scene.set_camera(
        {
            "mode": "3d",
            "position": [0.0, 150.0, 400.0],
            "target": [0.0, 0.0, 0.0],
            "up": [0.0, 1.0, 0.0],
            "fov": 0.7853981633974483,  # pi/4
            "near": 1,
            "far": 2000,
        }
    )
    return scene


class EditorState:
    """All the mutable editor-mode state that isn't `Scene` itself --
    selection, the command stack, the gizmo, grid/snap settings, and
    small imgui-widget-state bags. One instance per `run()` call.
    """

    def __init__(self, scene: Scene) -> None:
        self.commands = EditorCommands(scene)
        self.gizmo = Gizmo()
        self.selected_entity_id: "str | None" = None
        self.selected_zone_id: "str | None" = None

        self.grid_enabled = True
        self.grid_size = _DEFAULT_GRID_SIZE
        self.rotation_snap_enabled = False
        self.rotation_snap_degrees = 15.0

        # Click-vs-drag distinction (Step 6 task 1).
        self._pointer_down_pos: "tuple | None" = None
        self._pointer_down_hit_gizmo = False

        # Small widget-state bags, plain attributes per this codebase's
        # existing immediate-mode convention.
        self.asset_browser_filter = ""
        self.status_message = ""
        self.area_id: "str | None" = None  # None until first save or loaded-from-file
        self.save_as_name = ""
        self.template_edit_buffers: dict = {}  # part_id -> in-progress edit values, cleared on confirm/deselect

        # Step 15 -- Action Definitions.
        self.action_registry = _load_action_registry()
        self.new_action_name = ""
        self.new_action_duration_ms = 400.0

        # UI cleanup: a top menu bar (toggled by F11) replacing/
        # supplementing the always-on-screen panel clutter with
        # File/Edit/View menus, plus per-panel visibility so panels a
        # user isn't using can be tucked away instead of always
        # occupying screen space.
        self.menu_bar_visible = True
        self.want_exit = False  # deferred-close flag, see draw()'s own note on why "Exit" can't call canvas.close() directly from inside gui()
        self.show_entities_zones = True
        self.show_property_panel = True
        self.show_zone_authoring = True
        self.show_asset_browser = True
        self.show_action_definitions = True
        self.show_scene_settings = True
        self.show_add_action_window = False
        self.show_area_info = False
        self.show_help_window = False


def _snap(value: float, grid_size: float) -> float:
    if grid_size <= 0:
        return value
    return round(value / grid_size) * grid_size


def _snap_degrees(value_radians: float, snap_degrees: float) -> float:
    if snap_degrees <= 0:
        return value_radians
    degrees = math.degrees(value_radians)
    snapped = round(degrees / snap_degrees) * snap_degrees
    return math.radians(snapped)


# ---------------------------------------------------------------------
# Action Definitions (Step 15) -- data only: an action's name/duration
# and which transform clip plays for it on a given mesh part. Deciding
# *when* an action fires stays real gameplay code on a game branch,
# never authored here (see docs/graphics/ACTION_TRIGGERED_ANIMATIONS.md).
# ---------------------------------------------------------------------


class ActionRegistry:
    """A flat `{action_name: {"duration_ms": number}}` registry -- the
    editor-authored equivalent of `backend/engine/example_game_loop.py`'s
    `ACTION_DURATIONS` constant. A single well-known asset (like
    `ui_theme.json`), not an enumerated manifest category.
    """

    def __init__(self) -> None:
        self.actions: dict[str, dict] = {}

    def add_action(self, name: str, duration_ms: float) -> None:
        self.actions[name] = {"duration_ms": duration_ms}

    def remove_action(self, name: str) -> None:
        self.actions.pop(name, None)

    def to_json(self) -> dict:
        return {name: dict(data) for name, data in self.actions.items()}

    @classmethod
    def from_json(cls, data: dict) -> "ActionRegistry":
        registry = cls()
        for name, entry in (data or {}).items():
            registry.actions[name] = dict(entry)
        return registry


def _load_action_registry() -> ActionRegistry:
    if not ACTIONS_PATH.exists():
        return ActionRegistry()
    try:
        return ActionRegistry.from_json(json.loads(ACTIONS_PATH.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return ActionRegistry()


def _save_action_registry(registry: ActionRegistry) -> None:
    ACTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACTIONS_PATH.write_text(json.dumps(registry.to_json(), indent=2), encoding="utf-8")


def add_action_command(registry: ActionRegistry, name: str, duration_ms: float) -> Command:
    return Command(
        do=lambda: registry.add_action(name, duration_ms),
        undo=lambda: registry.remove_action(name),
        label=f"Add action {name}",
    )


def remove_action_command(registry: ActionRegistry, name: str, data: dict) -> Command:
    data = dict(data)
    return Command(
        do=lambda: registry.remove_action(name),
        undo=lambda: registry.actions.__setitem__(name, dict(data)),
        label=f"Remove action {name}",
    )


def _draw_action_definitions_panel(state: EditorState) -> None:
    registry = state.action_registry
    imgui.begin("Action Definitions")

    for name in sorted(registry.actions.keys()):
        duration = registry.actions[name].get("duration_ms", 0)
        imgui.text(f"{name}: {duration}ms")
        imgui.same_line()
        if imgui.button(f"Remove##action-{name}"):
            state.commands.execute(remove_action_command(registry, name, registry.actions[name]))
            _save_action_registry(registry)

    imgui.end()


def _draw_add_action_window(state: EditorState) -> None:
    """Its own window (Actions menu > Add Action), split out of the
    Action Definitions list panel. Closes itself after a successful add
    (`show_add_action_window = False`) or via the Cancel button, which
    just closes it with no side effects.
    """
    registry = state.action_registry
    imgui.begin("Add Action")

    _, state.new_action_name = imgui.input_text("name", state.new_action_name)
    _, state.new_action_duration_ms = imgui.input_float("duration_ms", state.new_action_duration_ms)

    if imgui.button("Add Action") and state.new_action_name:
        state.commands.execute(add_action_command(registry, state.new_action_name, state.new_action_duration_ms))
        _save_action_registry(registry)
        state.new_action_name = ""
        state.show_add_action_window = False

    imgui.same_line()
    if imgui.button("Cancel"):
        state.show_add_action_window = False

    imgui.end()


# ---------------------------------------------------------------------
# Pointer / keyboard interaction (Steps 6, 7, 12)
# ---------------------------------------------------------------------


def _zone_gizmo_pose(zone: dict) -> dict:
    """A zone's shape, reframed as an entity-shaped pose so Step 7's
    gizmo can drive it unmodified (Step 13 task 2: "reuse Step 7's
    existing translate/scale gizmo unmodified"). For an `aabb` zone,
    position = box center, scale = half-extents (dragging the scale
    gizmo grows/shrinks the box symmetrically around its center -- a
    reasonable, simple interaction, not the only possible one). For a
    `mesh` zone, position/rotation/scale map directly, same as any
    mesh entity.
    """
    shape = zone.get("shape", {})
    if shape.get("type") == "aabb":
        min_pt = shape.get("min", [0.0, 0.0, 0.0])
        max_pt = shape.get("max", [1.0, 1.0, 1.0])
        center = [(min_pt[i] + max_pt[i]) / 2.0 for i in range(3)]
        half_extent = [(max_pt[i] - min_pt[i]) / 2.0 for i in range(3)]
        return {"x": center[0], "y": center[1], "z": center[2], "transform3d": {"rotation": [0.0, 0.0, 0.0], "scale": half_extent}}
    position = shape.get("position", [0.0, 0.0, 0.0])
    rotation = shape.get("rotation", [0.0, 0.0, 0.0])
    scale = shape.get("scale", [1.0, 1.0, 1.0])
    return {"x": position[0], "y": position[1], "z": position[2], "transform3d": {"rotation": list(rotation), "scale": list(scale)}}


def _zone_shape_from_pose(zone: dict, position: list, rotation: list, scale: list) -> dict:
    """Inverse of `_zone_gizmo_pose` -- the gizmo's live pose, written
    back into the zone's `shape` dict. `scale` here is half-extents for
    an `aabb` zone (see `_zone_gizmo_pose`), a real render scale for a
    `mesh` zone.
    """
    shape = dict(zone.get("shape", {}))
    if shape.get("type") == "aabb":
        shape["min"] = [position[i] - scale[i] for i in range(3)]
        shape["max"] = [position[i] + scale[i] for i in range(3)]
    else:
        shape["position"] = list(position)
        shape["rotation"] = list(rotation)
        shape["scale"] = list(scale)
    return shape


def _get_gizmo_target(scene: Scene, state: EditorState) -> "tuple[str, str, dict] | None":
    """Returns `(kind, id, pose)` for whatever's currently selected --
    `kind` is `'entity'` or `'zone'` -- or None if nothing's selected.
    The single dispatch point pointer handlers use so they don't need
    to duplicate the entity-vs-zone branch three times.
    """
    if state.selected_entity_id is not None:
        entity = scene.entities.get(state.selected_entity_id)
        if entity is not None:
            pose = {"x": entity.get("x", 0.0), "y": entity.get("y", 0.0), "z": entity.get("z", 0.0), "transform3d": entity.get("transform3d") or {}}
            return "entity", state.selected_entity_id, pose
    if state.selected_zone_id is not None:
        zone = scene.zones.get(state.selected_zone_id)
        if zone is not None:
            return "zone", state.selected_zone_id, _zone_gizmo_pose(zone)
    return None


def _make_pointer_handlers(scene: Scene, state: EditorState, get_viewport_size, mode: str):
    def on_pointer_down(event: dict) -> None:
        if mode != "builder":
            return
        if event.get("button") != 1:  # left button only (rendercanvas numbering)
            return

        mouse_pos = (event["x"], event["y"])
        state._pointer_down_pos = mouse_pos
        state._pointer_down_hit_gizmo = False

        target = _get_gizmo_target(scene, state)
        if target is not None:
            _kind, _id, pose = target
            width, height = get_viewport_size()
            is_3d = scene.camera.get("mode") == "3d"
            entity_pos = (pose["x"], pose["y"], pose["z"])
            axis = state.gizmo.hit_test(mouse_pos, entity_pos, scene.camera, width, height, is_3d)
            if axis is not None:
                state.gizmo.begin_drag(axis, mouse_pos, pose)
                state._pointer_down_hit_gizmo = True

    def on_pointer_move(event: dict) -> None:
        if mode != "builder" or not state.gizmo.is_dragging():
            return
        width, height = get_viewport_size()
        state.gizmo.update_drag((event["x"], event["y"]), scene.camera, width, height)

        if state.selected_entity_id is not None:
            entity = scene.entities.get(state.selected_entity_id)
            if entity is None:
                return
            if state.gizmo.mode == "translate":
                pos = list(state.gizmo.live_position)
                if state.grid_enabled:
                    pos = [_snap(v, state.grid_size) for v in pos]
                entity["x"], entity["y"], entity["z"] = pos
            elif state.gizmo.mode == "rotate":
                rotation = list(state.gizmo.live_rotation)
                if state.rotation_snap_enabled:
                    rotation = [_snap_degrees(v, state.rotation_snap_degrees) for v in rotation]
                transform3d = dict(entity.get("transform3d") or {})
                transform3d["rotation"] = rotation
                entity["transform3d"] = transform3d
            elif state.gizmo.mode == "scale":
                transform3d = dict(entity.get("transform3d") or {})
                transform3d["scale"] = list(state.gizmo.live_scale)
                entity["transform3d"] = transform3d
        elif state.selected_zone_id is not None:
            zone = scene.zones.get(state.selected_zone_id)
            if zone is None:
                return
            gizmo = state.gizmo
            position = gizmo.live_position if gizmo.mode == "translate" else gizmo.drag_start_position
            rotation = gizmo.live_rotation if gizmo.mode == "rotate" else gizmo.drag_start_rotation
            scale = gizmo.live_scale if gizmo.mode == "scale" else gizmo.drag_start_scale
            zone["shape"] = _zone_shape_from_pose(zone, position, rotation, scale)

    def on_pointer_up(event: dict) -> None:
        if mode != "builder":
            return
        if event.get("button") != 1:
            return

        mouse_pos = (event["x"], event["y"])
        was_dragging = state.gizmo.is_dragging()
        drag_mode = state.gizmo.end_drag()

        if drag_mode is not None and state.selected_entity_id is not None:
            entity_id = state.selected_entity_id
            gizmo = state.gizmo
            if drag_mode == "translate":
                if gizmo.live_position != gizmo.drag_start_position:
                    command = move_entity_command(
                        scene, entity_id, tuple(gizmo.drag_start_position), tuple(gizmo.live_position)
                    )
                    state.commands.execute(command)
            elif drag_mode == "rotate":
                if gizmo.live_rotation != gizmo.drag_start_rotation:
                    command = rotate_entity_command(
                        scene, entity_id, gizmo.drag_start_rotation, gizmo.live_rotation
                    )
                    state.commands.execute(command)
            elif drag_mode == "scale":
                if gizmo.live_scale != gizmo.drag_start_scale:
                    command = scale_entity_command(scene, entity_id, gizmo.drag_start_scale, gizmo.live_scale)
                    state.commands.execute(command)
            return

        if drag_mode is not None and state.selected_zone_id is not None:
            zone_id = state.selected_zone_id
            zone = scene.zones.get(zone_id)
            gizmo = state.gizmo
            if zone is not None:
                old_shape = _zone_shape_from_pose(zone, gizmo.drag_start_position, gizmo.drag_start_rotation, gizmo.drag_start_scale)
                new_position = gizmo.live_position if drag_mode == "translate" else gizmo.drag_start_position
                new_rotation = gizmo.live_rotation if drag_mode == "rotate" else gizmo.drag_start_rotation
                new_scale = gizmo.live_scale if drag_mode == "scale" else gizmo.drag_start_scale
                new_shape = _zone_shape_from_pose(zone, new_position, new_rotation, new_scale)
                if new_shape != old_shape:
                    state.commands.execute(update_zone_command(scene, zone_id, {"shape": old_shape}, {"shape": new_shape}))
            return

        if was_dragging:
            return

        if state._pointer_down_pos is None:
            return
        moved = math.hypot(mouse_pos[0] - state._pointer_down_pos[0], mouse_pos[1] - state._pointer_down_pos[1])
        state._pointer_down_pos = None
        if moved > _CLICK_MOVE_THRESHOLD_PX:
            return  # was a camera-look/other drag, not a click

        width, height = get_viewport_size()
        picked = pick_entity(mouse_pos[0], mouse_pos[1], width, height, scene.camera, scene.entities)
        state.selected_entity_id = picked
        state.selected_zone_id = None

    return on_pointer_down, on_pointer_move, on_pointer_up


def _make_key_handler(scene: Scene, state: EditorState, mode: str, free_cam: FreeCamera):
    def on_key(event: dict) -> None:
        if event["event_type"] != "key_down":
            return
        if imgui.get_io().want_capture_keyboard or imgui.get_io().want_text_input:
            return  # Step 12 verify: shortcuts disabled while an imgui text field has focus

        key = event["key"].lower()

        # "?" and "Shift+/" both arrive as this same key (rendercanvas's
        # glfw backend derives "key" from the unshifted glyph's keycode,
        # see rendercanvas/glfw.py's _on_key) -- available in both modes,
        # unlike the builder-only shortcuts below.
        if key == "/":
            state.show_help_window = not state.show_help_window
            return

        if mode != "builder":
            return

        ctrl = imgui.get_io().key_ctrl
        shift = imgui.get_io().key_shift

        if key == "t":
            state.gizmo.set_mode("translate")
        elif key == "r":
            state.gizmo.set_mode("rotate")
        elif key == "s" and not ctrl:
            state.gizmo.set_mode("scale")
        elif key == "z" and ctrl and shift:
            label = state.commands.redo()
            if label:
                state.status_message = f"Redo: {label}"
        elif key == "z" and ctrl:
            label = state.commands.undo()
            if label:
                state.status_message = f"Undo: {label}"
        elif key == "y" and ctrl:
            label = state.commands.redo()
            if label:
                state.status_message = f"Redo: {label}"
        elif key in ("delete", "backspace"):
            _delete_selected(scene, state)
        elif key == "d" and ctrl:
            _duplicate_selected(scene, state)
        elif key == "f":
            focus_point = _focus_selected(scene, state)
            if focus_point is not None:
                free_cam.look_at(focus_point)
        elif key == "escape":
            state.selected_entity_id = None
            state.selected_zone_id = None
        elif key == "g":
            state.grid_enabled = not state.grid_enabled
        elif key == "f11":
            state.menu_bar_visible = not state.menu_bar_visible

    return on_key


def _delete_selected(scene: Scene, state: EditorState) -> None:
    if state.selected_entity_id is not None:
        entity_id = state.selected_entity_id
        data = dict(scene.entities.get(entity_id, {}))
        source = scene.entity_source(entity_id) or "local"
        state.commands.execute(remove_entity_command(scene, entity_id, data, source))
        state.selected_entity_id = None
        state.status_message = f"Deleted {entity_id}"
    elif state.selected_zone_id is not None:
        zone_id = state.selected_zone_id
        data = dict(scene.zones.get(zone_id, {}))
        state.commands.execute(remove_zone_command(scene, zone_id, data))
        state.selected_zone_id = None
        state.status_message = f"Deleted zone {zone_id}"


def _duplicate_selected(scene: Scene, state: EditorState) -> None:
    if state.selected_entity_id is None:
        return
    original = scene.entities.get(state.selected_entity_id)
    if original is None:
        return
    new_id = _generate_local_id()
    data = dict(original)
    data["entity_id"] = new_id
    data["x"] = data.get("x", 0.0) + 20.0
    data["z"] = data.get("z", 0.0) + 20.0
    state.commands.execute(add_entity_command(scene, new_id, data, "local"))
    state.selected_entity_id = new_id
    state.status_message = f"Duplicated to {new_id}"


def _focus_selected(scene: Scene, state: EditorState) -> "list | None":
    if state.selected_entity_id is None:
        return None
    entity = scene.entities.get(state.selected_entity_id)
    if entity is None:
        return None
    return [entity.get("x", 0.0), entity.get("y", 0.0), entity.get("z", 0.0)]


# ---------------------------------------------------------------------
# Panels (Steps 8, 9, 11 Scene Settings)
# ---------------------------------------------------------------------


def _draw_entity_and_zone_list(scene: Scene, state: EditorState) -> None:
    imgui.text("Entities")
    for entity_id in list(scene.entities.keys()):
        source = scene.entity_source(entity_id)
        selected = entity_id == state.selected_entity_id
        clicked, _ = imgui.selectable(f"{entity_id}  [{source}]", selected)
        if clicked:
            state.selected_entity_id = entity_id
            state.selected_zone_id = None

    if scene.zones:
        imgui.separator()
        imgui.text("Zones")
        for zone_id in list(scene.zones.keys()):
            selected = zone_id == state.selected_zone_id
            clicked, _ = imgui.selectable(f"[ZONE] {zone_id}", selected)
            if clicked:
                state.selected_zone_id = zone_id
                state.selected_entity_id = None


def _draw_property_panel(scene: Scene, state: EditorState) -> None:
    if state.selected_entity_id is None:
        return
    entity_id = state.selected_entity_id
    entity = scene.entities.get(entity_id)
    if entity is None:
        state.selected_entity_id = None
        return

    imgui.begin("Property Panel")
    imgui.text(f"Entity: {entity_id}  [{scene.entity_source(entity_id)}]")
    imgui.separator()

    # --- Instance-level: placement (Step 8 section 1) ---
    # **Two real bugs fixed here, found by audit (2026-08-22)**:
    # `imgui.is_item_deactivated_after_edit()` reports the state of the
    # *immediately preceding* widget only -- calling it once after three
    # separate input_float() calls only ever reflected the *last*
    # field's (z's) deactivation, so editing x or y alone and tabbing
    # away silently never committed an undo-tracked command (position:
    # the typed value still persisted via the live-write `else` branch,
    # bypassing undo; rotation/scale had no such branch at all, so an
    # edited rx/ry/sx/sy value was lost outright). Fixed by checking
    # deactivation immediately after each widget and OR-ing the results
    # -- and by adding the same live-sync `else` branch to rotation/
    # scale that position already had, so all three behave identically
    # (typing updates the entity/gizmo live; committing to the undo
    # stack happens once, on whichever field's edit is deactivated).
    imgui.text("Placement (this instance only)")
    x, y, z = entity.get("x", 0.0), entity.get("y", 0.0), entity.get("z", 0.0)
    _, new_x = imgui.input_float("x", x)
    position_deactivated = imgui.is_item_deactivated_after_edit()
    _, new_y = imgui.input_float("y", y)
    position_deactivated = position_deactivated or imgui.is_item_deactivated_after_edit()
    _, new_z = imgui.input_float("z", z)
    position_deactivated = position_deactivated or imgui.is_item_deactivated_after_edit()

    if position_deactivated and (new_x, new_y, new_z) != (x, y, z):
        state.commands.execute(move_entity_command(scene, entity_id, (x, y, z), (new_x, new_y, new_z)))
    else:
        entity["x"], entity["y"], entity["z"] = new_x, new_y, new_z

    transform3d = dict(entity.get("transform3d") or {})
    rotation = list(transform3d.get("rotation") or [0.0, 0.0, 0.0])
    rotation_deg = [math.degrees(v) for v in rotation]
    new_rotation_deg = list(rotation_deg)
    rotation_deactivated = False
    for i, axis_name in enumerate(("rx", "ry", "rz")):
        _, new_rotation_deg[i] = imgui.input_float(axis_name, rotation_deg[i])
        rotation_deactivated = rotation_deactivated or imgui.is_item_deactivated_after_edit()

    if rotation_deactivated and new_rotation_deg != rotation_deg:
        new_rotation = [math.radians(v) for v in new_rotation_deg]
        state.commands.execute(rotate_entity_command(scene, entity_id, rotation, new_rotation))
    else:
        transform3d["rotation"] = [math.radians(v) for v in new_rotation_deg]
        entity["transform3d"] = transform3d

    transform3d = dict(entity.get("transform3d") or {})
    scale = list(transform3d.get("scale") or [1.0, 1.0, 1.0])
    new_scale = list(scale)
    scale_deactivated = False
    for i, axis_name in enumerate(("sx", "sy", "sz")):
        _, new_scale[i] = imgui.input_float(axis_name, scale[i])
        scale_deactivated = scale_deactivated or imgui.is_item_deactivated_after_edit()

    if scale_deactivated and new_scale != scale:
        state.commands.execute(scale_entity_command(scene, entity_id, scale, new_scale))
    else:
        transform3d["scale"] = list(new_scale)
        entity["transform3d"] = transform3d

    imgui.separator()

    # --- Instance-level: appearance (Step 8 section 2) ---
    imgui.text("render_template (this instance only)")
    render_template = entity.get("render_template") or ""
    changed, new_template = imgui.input_text("render_template", render_template)
    if imgui.is_item_deactivated_after_edit() and new_template != render_template:
        if asset_loader.has(new_template):
            state.commands.execute(
                update_entity_command(scene, entity_id, {"render_template": render_template}, {"render_template": new_template})
            )
        else:
            state.status_message = f"Unknown asset id: {new_template!r}"

    imgui.separator()

    # --- Template-level: shared entity-definition parts (Step 8 section 4) ---
    _draw_template_section(scene, state, entity_id, render_template)

    imgui.end()


def _draw_template_section(scene: Scene, state: EditorState, entity_id: str, render_template: str) -> None:
    if not render_template:
        return
    definition = load_entity_definition(render_template) if "/" not in render_template else None
    if definition is None:
        return
    parts = definition.get("parts")
    if not parts:
        return

    imgui.text_colored(
        imgui.ImVec4(1.0, 0.7, 0.2, 1.0),
        f"Editing shared template '{render_template}' -- affects every entity using it",
    )

    for part in parts:
        part_id = part.get("id") or "?"
        if not imgui.collapsing_header(f"Part: {part_id}"):
            continue

        buffer_key = f"{render_template}:{part_id}"
        buffer = state.template_edit_buffers.setdefault(buffer_key, default_part_buffer(part))
        edited = draw_part_fields(part, buffer, state.action_registry, buffer_key)
        if edited is not None:
            # Defense-in-depth tripwire, mirrored from entity_builder.py's
            # own identical guard on this same shared draw_part_fields()
            # call -- per direct request that renaming a part must never
            # break a reference, id has to stay frozen after creation
            # forever. Matters even more here than in entity_builder.py:
            # the replacement below matches by the *old* part_id, so a
            # silently-changed id would still land in the right list
            # position but carry a value nothing else in this shared
            # template actually points at.
            if edited.get("id") != part_id:
                edited["id"] = part_id
            new_parts = [edited if p.get("id") == part_id else p for p in parts]
            new_definition = dict(definition)
            new_definition["parts"] = new_parts
            save_entity_definition(new_definition, render_template)
            state.status_message = f"Saved template '{render_template}' (part '{part_id}')"


_ZONE_EFFECT_TYPES = (
    "add_group",
    "remove_group",
    "set_group_attribute",
    "set_data",
    "clear_data",
    "add_component",
    "remove_component",
    "fire_event",
)

_ZONE_EFFECT_DEFAULTS = {
    "add_group": {"type": "add_group", "group": "group_name"},
    "remove_group": {"type": "remove_group", "group": "group_name"},
    "set_group_attribute": {"type": "set_group_attribute", "group": "group_name", "key": "key", "value": 0},
    "set_data": {"type": "set_data", "key": "key", "value": True},
    "clear_data": {"type": "clear_data", "key": "key"},
    "add_component": {"type": "add_component", "component": {"type": "ColliderComponent"}},
    "remove_component": {"type": "remove_component", "component_type": "ColliderComponent"},
    "fire_event": {"type": "fire_event", "event": "event_name", "payload": {}},
}


def _camera_look_at_point(camera: dict, distance: float) -> list:
    if camera.get("mode") == "3d":
        position = camera.get("position", [0, 0, 0])
        target = camera.get("target", [0, 0, 0])
        forward = [target[i] - position[i] for i in range(3)]
        length = math.sqrt(sum(v * v for v in forward)) or 1.0
        forward = [v / length for v in forward]
        return [position[i] + forward[i] * distance for i in range(3)]
    return [camera.get("x", 0.0), camera.get("y", 0.0), 0.0]


def _add_aabb_zone(scene: Scene, state: EditorState) -> None:
    """AABB zone via a default box at the camera's look-at point (then
    reposition/resize with the same gizmo, unmodified) -- Step 13 task
    2, called from the menu bar's Zones > Add Zone > AABB.
    """
    center = _camera_look_at_point(scene.camera, _DEFAULT_PLACE_DISTANCE)
    zone_id = f"zone_{_generate_local_id()}"
    data = {
        "shape": {
            "type": "aabb",
            "min": [center[i] - 1.0 for i in range(3)],
            "max": [center[i] + 1.0 for i in range(3)],
        },
        "on_enter": [],
        "on_exit": [],
        "tags": [],
    }
    state.commands.execute(add_zone_command(scene, zone_id, data))
    state.selected_zone_id = zone_id
    state.selected_entity_id = None
    state.status_message = f"Added zone {zone_id}"


def _draw_zone_authoring_panel(scene: Scene, state: EditorState) -> None:
    """Step 13 task 3: mesh-footprint zones via the asset browser's
    existing placement flow, routed to `Scene.zones` instead of
    `Scene.entities`. AABB zones are added via the menu bar (Zones >
    Add Zone > AABB, see `_add_aabb_zone`), not from this panel.
    """
    imgui.begin("Zone Authoring")

    imgui.text_wrapped(
        "AABB zones: Zones > Add Zone > AABB in the menu bar."
    )
    imgui.text_wrapped(
        "Mesh-footprint zones: use the Asset Browser's 'Place as Zone' "
        "button on a mesh entry instead of 'Place' -- placed exactly "
        "like a mesh entity, routed to Scene.zones instead."
    )

    imgui.end()


def _draw_zone_property_panel(scene: Scene, state: EditorState) -> None:
    if state.selected_zone_id is None:
        return
    zone_id = state.selected_zone_id
    zone = scene.zones.get(zone_id)
    if zone is None:
        state.selected_zone_id = None
        return

    imgui.begin("Zone Property Panel")
    shape_type = zone.get("shape", {}).get("type", "?")
    imgui.text(f"Zone: {zone_id}  [{shape_type}]")
    imgui.text_wrapped("Shape is read-only here -- reposition/resize via the gizmo (T/R/S) in the viewport.")
    imgui.text_wrapped(str(zone.get("shape", {})))
    imgui.separator()

    for list_name in ("on_enter", "on_exit"):
        imgui.text(list_name)
        effects = zone.get(list_name, [])
        for i, effect in enumerate(list(effects)):
            imgui.text(f"  {i}: {effect.get('type', '?')} {dict((k, v) for k, v in effect.items() if k != 'type')}")
            if imgui.button(f"Remove##{zone_id}-{list_name}-{i}"):
                new_effects = [e for j, e in enumerate(effects) if j != i]
                state.commands.execute(
                    update_zone_command(scene, zone_id, {list_name: list(effects)}, {list_name: new_effects})
                )

        buffer_key = f"{zone_id}-{list_name}-newtype"
        chosen = state.template_edit_buffers.get(buffer_key, _ZONE_EFFECT_TYPES[0])
        changed, chosen_index = imgui.combo(
            f"##{buffer_key}", _ZONE_EFFECT_TYPES.index(chosen) if chosen in _ZONE_EFFECT_TYPES else 0, list(_ZONE_EFFECT_TYPES)
        )
        chosen = _ZONE_EFFECT_TYPES[chosen_index]
        state.template_edit_buffers[buffer_key] = chosen
        imgui.same_line()
        if imgui.button(f"+ Add effect##{zone_id}-{list_name}"):
            new_effect = dict(_ZONE_EFFECT_DEFAULTS[chosen])
            new_effects = list(effects) + [new_effect]
            state.commands.execute(
                update_zone_command(scene, zone_id, {list_name: list(effects)}, {list_name: new_effects})
            )
        imgui.separator()

    imgui.end()


def _draw_asset_browser_panel(scene: Scene, state: EditorState) -> None:
    imgui.begin("Asset Browser")
    _, state.asset_browser_filter = imgui.input_text("Filter", state.asset_browser_filter)

    for category in ("entities", "meshes"):
        entries = asset_loader.list_category(category)
        if not entries:
            continue
        imgui.text(category)
        for asset_id in sorted(entries.keys()):
            if state.asset_browser_filter and state.asset_browser_filter.lower() not in asset_id.lower():
                continue
            if imgui.button(f"Place##{category}-{asset_id}"):
                _place_asset(scene, state, asset_id)
            imgui.same_line()
            if category == "meshes" and imgui.button(f"Place as Zone##{category}-{asset_id}"):
                _place_mesh_zone(scene, state, asset_id)
            imgui.same_line()
            imgui.text(asset_id)

    imgui.end()


def _place_asset(scene: Scene, state: EditorState, asset_id: str) -> None:
    place_pos = _camera_look_at_point(scene.camera, _DEFAULT_PLACE_DISTANCE)

    entity_id = _generate_local_id()
    data = {
        "entity_id": entity_id,
        "x": place_pos[0],
        "y": place_pos[1],
        "z": place_pos[2] if len(place_pos) > 2 else 0.0,
        "state": "idle",
        "facing": "down",
        "render_template": asset_id,
        "transform3d": {"rotation": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0]},
    }
    state.commands.execute(add_entity_command(scene, entity_id, data, "local"))
    state.selected_entity_id = entity_id
    state.selected_zone_id = None
    state.status_message = f"Placed {entity_id} ({asset_id})"


def _place_mesh_zone(scene: Scene, state: EditorState, mesh_id: str) -> None:
    """Step 13 task 3: a mesh zone is placed exactly like a mesh
    entity (same camera-look-at default position), just routed to
    `Scene.zones` instead of `Scene.entities`.
    """
    place_pos = _camera_look_at_point(scene.camera, _DEFAULT_PLACE_DISTANCE)
    zone_id = f"zone_{_generate_local_id()}"
    data = {
        "shape": {
            "type": "mesh",
            "mesh": mesh_id,
            "position": list(place_pos),
            "rotation": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
        },
        "on_enter": [],
        "on_exit": [],
        "tags": [],
    }
    state.commands.execute(add_zone_command(scene, zone_id, data))
    state.selected_zone_id = zone_id
    state.selected_entity_id = None
    state.status_message = f"Placed zone {zone_id} ({mesh_id})"


def _draw_scene_settings_panel(scene: Scene, state: EditorState) -> None:
    imgui.begin("Scene Settings")

    imgui.text("Start camera (authored spawn point)")
    if scene.start_camera:
        imgui.text_wrapped(str(scene.start_camera))
    else:
        imgui.text("(not set -- falls back to live camera on save)")
    if imgui.button("Set Start Camera to Current View"):
        state.commands.execute(set_start_camera_command(scene, scene.start_camera, dict(scene.camera)))
        state.status_message = "Start camera set."

    imgui.separator()
    imgui.text("Start lighting")
    ambient = list(scene.lighting.get("ambientColor", [1.0, 1.0, 1.0]))
    fog_color = list(scene.lighting.get("fogColor", [0.0, 0.0, 0.0]))
    fog_near = scene.lighting.get("fogNear", 0.0)
    fog_far = scene.lighting.get("fogFar", 0.0)
    _, ambient = imgui.input_float3("ambientColor", ambient)
    _, fog_color = imgui.input_float3("fogColor", fog_color)
    _, fog_near = imgui.input_float("fogNear", fog_near)
    _, fog_far = imgui.input_float("fogFar", fog_far)
    if imgui.button("Set Start Lighting"):
        new_lighting = {
            "ambientColor": list(ambient),
            "fogColor": list(fog_color),
            "fogNear": fog_near,
            "fogFar": fog_far,
        }
        state.commands.execute(set_start_lighting_command(scene, dict(scene.lighting), new_lighting))
        state.status_message = "Start lighting set."

    imgui.separator()
    imgui.checkbox("Grid enabled (G)", state.grid_enabled)
    _, state.grid_size = imgui.input_float("Grid size", state.grid_size)
    _, state.rotation_snap_enabled = imgui.checkbox("Rotation snap", state.rotation_snap_enabled)
    _, state.rotation_snap_degrees = imgui.input_float("Snap degrees", state.rotation_snap_degrees)

    imgui.separator()
    imgui.text(f"Entities: {len(scene.entities)}   Zones: {len(scene.zones)}")
    io = imgui.get_io()
    imgui.text(f"FPS: {io.framerate:.0f}")

    imgui.end()


# ---------------------------------------------------------------------
# Grid overlay (Step 10)
# ---------------------------------------------------------------------


def _draw_grid_overlay(scene: Scene, state: EditorState, width: float, height: float) -> None:
    if not state.grid_enabled or scene.camera.get("mode") != "3d":
        return
    from client.engine.gizmo import pack_color, to_imvec2, world_to_screen

    # Background, not foreground, draw list -- renders above the wgpu
    # scene (drawn in a separate pass before imgui_renderer.render()
    # runs) but below every imgui window/popup, so the grid doesn't
    # paint over the menu bar or floating panels (see `_draw_bottom_bar`'s
    # own note for why *that* one deliberately uses the foreground list
    # instead).
    draw_list = imgui.get_background_draw_list()
    color = pack_color((90, 90, 100), 120)
    grid_size = state.grid_size or _DEFAULT_GRID_SIZE
    half_extent = grid_size * 20
    step = max(grid_size, 1.0)

    line_count = int(half_extent / step)
    for i in range(-line_count, line_count + 1):
        offset = i * step
        p0 = world_to_screen((offset, 0, -half_extent), scene.camera, width, height)
        p1 = world_to_screen((offset, 0, half_extent), scene.camera, width, height)
        if p0 is not None and p1 is not None:
            draw_list.add_line(to_imvec2(p0), to_imvec2(p1), color, 1.0)

        p0 = world_to_screen((-half_extent, 0, offset), scene.camera, width, height)
        p1 = world_to_screen((half_extent, 0, offset), scene.camera, width, height)
        if p0 is not None and p1 is not None:
            draw_list.add_line(to_imvec2(p0), to_imvec2(p1), color, 1.0)


_BOX_EDGES = (
    (0, 1), (1, 3), (3, 2), (2, 0),  # bottom face
    (4, 5), (5, 7), (7, 6), (6, 4),  # top face
    (0, 4), (1, 5), (2, 6), (3, 7),  # verticals
)


def _box_corners(min_pt: list, max_pt: list) -> list:
    xs = (min_pt[0], max_pt[0])
    ys = (min_pt[1], max_pt[1])
    zs = (min_pt[2], max_pt[2])
    return [(x, y, z) for x in xs for y in ys for z in zs]


def _draw_wireframe_box(draw_list, min_pt, max_pt, camera, width, height, color) -> None:
    from client.engine.gizmo import to_imvec2, world_to_screen

    corners = _box_corners(min_pt, max_pt)
    screen_corners = [world_to_screen(c, camera, width, height) for c in corners]
    for a, b in _BOX_EDGES:
        pa, pb = screen_corners[a], screen_corners[b]
        if pa is not None and pb is not None:
            draw_list.add_line(to_imvec2(pa), to_imvec2(pb), color, 2.0)


# Nominal half-extent used to represent a mesh zone's volume as a
# wireframe box -- Step 13 task 4 asks for the zone's *actual* mesh,
# alpha-blended and tinted; drawn here as a wireframe box instead (same
# imgui-draw-list-overlay mechanism as the gizmo/grid, not a real
# alpha-blended GPU mesh draw) since that would need genuine renderer/
# material-pipeline plumbing this pass doesn't build. Documented
# simplification, not a silent shortfall.
_MESH_ZONE_NOMINAL_HALF_EXTENT = 32.0


def _draw_zone_overlays(scene: Scene, state: EditorState, width: float, height: float) -> None:
    """Step 13 task 4: translucent, distinctly-colored, editor-only
    zone visualization -- an AABB zone as a flat-colored wireframe box
    outline (its real shape, exactly); a mesh zone as a tinted cyan
    wireframe box around its placement point (a documented
    simplification of "draws its actual mesh, alpha-blended" -- see
    `_MESH_ZONE_NOMINAL_HALF_EXTENT`'s comment). Zero cost when no
    zones exist or outside editor mode -- this is only ever called from
    `mode == "builder"`'s draw() branch.
    """
    if scene.camera.get("mode") != "3d":
        return
    from client.engine.gizmo import pack_color

    # Background draw list -- see `_draw_grid_overlay`'s own note; the
    # foreground list draws over every imgui window including the menu
    # bar/bars, which made a large zone box paint straight over them.
    draw_list = imgui.get_background_draw_list()

    for zone_id, zone in scene.zones.items():
        selected = zone_id == state.selected_zone_id
        shape = zone.get("shape", {})
        if shape.get("type") == "aabb":
            color = pack_color((255, 210, 60) if selected else (255, 210, 60), 220 if selected else 140)
            _draw_wireframe_box(draw_list, shape.get("min", [0, 0, 0]), shape.get("max", [1, 1, 1]), scene.camera, width, height, color)
        elif shape.get("type") == "mesh":
            color = pack_color((60, 220, 220), 220 if selected else 140)
            position = shape.get("position", [0, 0, 0])
            half = _MESH_ZONE_NOMINAL_HALF_EXTENT
            min_pt = [position[i] - half for i in range(3)]
            max_pt = [position[i] + half for i in range(3)]
            _draw_wireframe_box(draw_list, min_pt, max_pt, scene.camera, width, height, color)


# ---------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------


def run(area_path: "str | None" = None, mode: str = "viewer") -> None:
    """The one entry function viewer/builder/test mode all share
    (Step 6 task 5: "this one entry mode *is* viewer mode as-is;
    builder mode is the same boot path with something additional
    layered on top"). No network client connection is ever opened here.
    """
    logger.info("=" * 50)
    logger.info(f"Area viewer -- mode={mode} area={area_path or '(empty scene)'}")
    logger.info("=" * 50)

    asset_loader.load_manifest()
    _register_dev_fixtures()

    resolved_path = Path(area_path) if area_path else None
    if resolved_path and resolved_path.exists():
        scene = Scene.load_from_area_file(resolved_path)
        logger.info(f"Loaded {len(scene.entities)} entities from {resolved_path}")
    else:
        if area_path:
            logger.warning(
                f"--area={area_path!r} did not resolve to a real file; using an empty scene."
            )
        scene = _build_empty_scene()
        resolved_path = None

    logger.info("Opening viewer window...")
    renderer.init_renderer()

    imgui_renderer = ImguiRenderer(renderer.device, renderer.canvas)

    free_cam = FreeCamera.from_look_at(
        list(scene.camera.get("position", [0.0, 150.0, 400.0])),
        list(scene.camera.get("target", [0.0, 0.0, 0.0])),
    )
    free_cam.bind(renderer.canvas)

    # A local convenience adapter -- draw_game_scene()/
    # update_interpolation() expect a plain {"entities": ..., "camera":
    # ...} dict; both keys here are direct references to Scene's own
    # dicts, so mutating scene.entities/scene.camera (via add_entity,
    # FreeCamera.apply, etc.) is reflected automatically, no per-frame
    # rebuild needed. This is deliberately narrow -- it is NOT
    # area-system.prompt.md Step 5's game-layer proxy (that shim
    # replaces client.game.player_select.game_state on a game branch,
    # see the branch-reconciliation banner); it's just what lets this
    # module reuse client.main's existing, unmodified render functions
    # with zero changes to them, confirming Step 3's own claim that
    # renderer.py/entity_renderer.py need no changes to read Scene.
    render_state = {"entities": scene.entities, "camera": scene.camera}

    state = EditorState(scene)
    if resolved_path is not None:
        state.area_id = area_id_from_path(resolved_path)

    def get_viewport_size():
        return renderer.canvas.get_physical_size()

    if mode == "builder":
        on_pointer_down, on_pointer_move, on_pointer_up = _make_pointer_handlers(
            scene, state, get_viewport_size, mode
        )
        renderer.canvas.add_event_handler(on_pointer_down, "pointer_down")
        renderer.canvas.add_event_handler(on_pointer_move, "pointer_move")
        renderer.canvas.add_event_handler(on_pointer_up, "pointer_up")
    renderer.canvas.add_event_handler(_make_key_handler(scene, state, mode, free_cam), "key_down")

    def gui() -> None:
        nonlocal resolved_path

        if mode == "builder":
            resolved_path = _draw_menu_bar(scene, state, resolved_path)

        _draw_bottom_bar(scene, state, mode)
        _draw_help_window(state, mode)

        if state.show_area_info:
            imgui.begin("Area Information", None, imgui.WindowFlags_.always_auto_resize)
            imgui.text(f"Area: {resolved_path or '(none -- empty scene)'}")
            imgui.text(f"Entities: {len(scene.entities)}")
            if mode == "builder":
                imgui.text(f"Grid: {'on' if state.grid_enabled else 'off'} (G)")
                # Save/Add-Zone moved to the menu bar (File > Save[/Save As],
                # Zones > Add Zone) -- the standalone Save window and the
                # zone-authoring panel's own button were removed, but their
                # status text still needs a home.
                if state.status_message:
                    imgui.separator()
                    imgui.text_wrapped(state.status_message)
                if state.commands.last_label:
                    imgui.text(f"Last action: {state.commands.last_label}")
            imgui.end()

        if mode == "builder":
            if state.show_entities_zones:
                _draw_entity_and_zone_list_window(scene, state)
            if state.show_property_panel:
                _draw_property_panel(scene, state)
                _draw_zone_property_panel(scene, state)
            if state.show_zone_authoring:
                _draw_zone_authoring_panel(scene, state)
            if state.show_asset_browser:
                _draw_asset_browser_panel(scene, state)
            if state.show_action_definitions:
                _draw_action_definitions_panel(state)
            if state.show_add_action_window:
                _draw_add_action_window(state)
            if state.show_scene_settings:
                _draw_scene_settings_panel(scene, state)

            # **Real bug fixed here (2026-08-22, found via a live crash
            # report, not caught by any of this session's own testing)**:
            # these three calls all reach a draw list accessor (originally
            # `imgui.get_foreground_draw_list()`; the gizmo/grid/zone calls
            # below have since moved to `get_background_draw_list()`, see
            # their own notes -- either accessor has the same requirement)
            # -- must run *inside* the imgui frame bracket
            # (`imgui.new_frame()` ... `imgui.render()`, established by
            # `imgui_renderer.render()` itself, which calls this `gui()`
            # function in between). They were originally called from
            # `draw()`, *before* `imgui_renderer.render()` -- i.e.
            # completely outside any active frame. This "worked" (drew
            # nothing visibly, silently) on a context that already had a
            # prior frame's stale-but-still-valid draw list sitting
            # around, but segfaulted outright on a *fresh* imgui context
            # that had never had `new_frame()` called yet -- exactly the
            # launcher-to-editor window transition. Same class of bug
            # `client/game/ui.py` (legacy branch) already documented once
            # for `imgui.open_popup()`; the fix is the same: move the
            # call inside the frame bracket, don't call it from outside.
            width, height = renderer.canvas.get_physical_size()
            is_3d = scene.camera.get("mode") == "3d"
            target = _get_gizmo_target(scene, state)
            if target is not None:
                _kind, _id, pose = target
                pos = (pose["x"], pose["y"], pose["z"])
                # Background, not foreground -- see `_draw_grid_overlay`'s
                # note; a gizmo handle shouldn't paint over the menu bar
                # or a panel sitting in front of it either.
                draw_list = imgui.get_background_draw_list()
                state.gizmo.draw(draw_list, pos, scene.camera, width, height, is_3d)
            _draw_zone_overlays(scene, state, width, height)
            _draw_grid_overlay(scene, state, width, height)

    imgui_renderer.set_gui(gui)

    last_time = [None]

    def draw() -> None:
        now = time.perf_counter()
        delta_ms = 0.0 if last_time[0] is None else (now - last_time[0]) * 1000.0
        last_time[0] = now
        delta_s = delta_ms / 1000.0

        free_cam.update(delta_s)
        free_cam.apply(scene.camera)

        interpolation.update_interpolation(scene.entities, delta_s)
        client_main.draw_game_scene(render_state, delta_ms)

        imgui_renderer.render()

        # The menu bar's "Exit" item can't call renderer.canvas.close()
        # directly -- it runs inside gui(), which runs inside
        # imgui_renderer.render()'s own frame bracket, before it's
        # finished submitting its own draw commands. Same crash, same
        # fix, as launcher.py's "Open Area"/"New Area" buttons (see
        # that file's own note): set a flag in gui(), act on it here,
        # once the frame has actually finished.
        if state.want_exit:
            renderer.canvas.close()

    renderer.run(draw)

    logger.info("Area viewer window closed. Exiting...")


def _draw_menu_bar(scene: Scene, state: EditorState, area_path: "Path | None") -> "Path | None":
    """File/Edit/View menu bar, toggled by F11 (`state.menu_bar_visible`,
    set from `_make_key_handler`). Called from `gui()`, so it's safely
    inside the imgui frame bracket like everything else in this panel
    -- see `draw()`'s own note on why "Exit" sets `state.want_exit`
    instead of calling `renderer.canvas.close()` directly here.
    """
    if not state.menu_bar_visible:
        return area_path

    if not imgui.begin_main_menu_bar():
        return area_path

    if imgui.begin_menu("File"):
        if state.area_id is not None:
            if imgui.menu_item_simple("Save", "Ctrl+S", False, True):
                area_path = save_area(scene, state.area_id)
                state.status_message = f"Saved to {area_path}"
        else:
            # No area_id yet (brand-new, never-saved area) -- "Save As"
            # needs a name from the user, so it's a submenu holding an
            # inline text field instead of a plain menu_item; this
            # replaces the standalone Save window's "New area name" +
            # "Save As" flow, folded in here per the UI cleanup.
            if imgui.begin_menu("Save As"):
                _, state.save_as_name = imgui.input_text("Name", state.save_as_name)
                if imgui.button("Save") and state.save_as_name:
                    state.area_id = state.save_as_name
                    area_path = save_area(scene, state.area_id)
                    state.status_message = f"Saved to {area_path}"
                    imgui.close_current_popup()
                imgui.end_menu()
        if imgui.menu_item_simple("Exit"):
            state.want_exit = True
        imgui.end_menu()

    if imgui.begin_menu("Zones"):
        if imgui.begin_menu("Add Zone"):
            if imgui.menu_item_simple("AABB"):
                _add_aabb_zone(scene, state)
            imgui.end_menu()
        imgui.end_menu()

    if imgui.begin_menu("Actions"):
        if imgui.menu_item_simple("Add Action"):
            state.show_add_action_window = True
        imgui.end_menu()

    if imgui.begin_menu("Edit"):
        if imgui.menu_item_simple("Undo", "Ctrl+Z", False, bool(state.commands.undo_stack)):
            label = state.commands.undo()
            if label:
                state.status_message = f"Undo: {label}"
        if imgui.menu_item_simple("Redo", "Ctrl+Shift+Z", False, bool(state.commands.redo_stack)):
            label = state.commands.redo()
            if label:
                state.status_message = f"Redo: {label}"
        imgui.separator()
        has_selection = state.selected_entity_id is not None or state.selected_zone_id is not None
        if imgui.menu_item_simple("Delete Selected", "Del", False, has_selection):
            _delete_selected(scene, state)
        if imgui.menu_item_simple("Duplicate Selected", "Ctrl+D", False, state.selected_entity_id is not None):
            _duplicate_selected(scene, state)
        imgui.end_menu()

    if imgui.begin_menu("View"):
        _, state.show_area_info = imgui.menu_item("Area Information", "", state.show_area_info)
        _, state.show_entities_zones = imgui.menu_item("Entities & Zones", "", state.show_entities_zones)
        _, state.show_property_panel = imgui.menu_item("Property Panel", "", state.show_property_panel)
        _, state.show_zone_authoring = imgui.menu_item("Zone Authoring", "", state.show_zone_authoring)
        _, state.show_asset_browser = imgui.menu_item("Asset Browser", "", state.show_asset_browser)
        _, state.show_action_definitions = imgui.menu_item("Action Definitions", "", state.show_action_definitions)
        _, state.show_scene_settings = imgui.menu_item("Scene Settings", "", state.show_scene_settings)
        imgui.separator()
        _, state.grid_enabled = imgui.menu_item("Grid", "G", state.grid_enabled)
        imgui.separator()
        if imgui.menu_item_simple("Hide Menu Bar", "F11"):
            state.menu_bar_visible = False
        imgui.end_menu()

    if imgui.begin_menu("Help"):
        _, state.show_help_window = imgui.menu_item("Show Help", "? / Shift+/", state.show_help_window)
        imgui.end_menu()

    # Right-aligned "Area id" label -- replaces the standalone Save
    # window's `imgui.text(f"Area id: ...")`, which had no other reason
    # to be its own window once Save/Save As moved into the File menu.
    label = f"Area id: {state.area_id}" if state.area_id else "Area id: (unsaved)"
    label_width = imgui.calc_text_size(label).x
    available_width = imgui.get_window_width()
    imgui.set_cursor_pos_x(max(imgui.get_cursor_pos_x(), available_width - label_width - 16))
    imgui.text(label)

    imgui.end_main_menu_bar()
    return area_path


def _draw_bottom_bar(scene: Scene, state: EditorState, mode: str) -> None:
    """A second, bottom-docked menu-bar-styled strip -- always visible
    (both viewer and builder mode), unlike `_draw_menu_bar` (builder
    only, toggled by F11), since Mode/camera.position need to stay
    visible regardless of mode or panel-visibility settings.

    Drawn straight onto the foreground draw list rather than as its own
    Begin/End window -- same mechanism the gizmo/grid/zone overlays
    already use below (see their own notes on why that call has to
    stay inside `gui()`'s frame bracket). A real window here would get
    silently buried under whichever floating panel the user last
    clicked (ImGui only keeps windows that are ever `begin_main_menu_bar`/
    `begin_viewport_side_bar`-registered pinned above regular windows,
    and imgui_bundle's Python bindings don't expose that second, bottom
    -side helper) -- the foreground draw list always composites above
    every window, no z-order fight required.
    """
    from client.engine.gizmo import pack_color, to_imvec2

    viewport = imgui.get_main_viewport()
    bar_height = imgui.get_frame_height()
    left, width = viewport.work_pos.x, viewport.work_size.x
    top = viewport.work_pos.y + viewport.work_size.y - bar_height

    draw_list = imgui.get_foreground_draw_list()
    draw_list.add_rect_filled(
        to_imvec2((left, top)), to_imvec2((left + width, top + bar_height)), pack_color((20, 20, 20), 235)
    )

    pad_x = 8.0
    text_y = top + (bar_height - imgui.get_text_line_height()) / 2.0
    text_color = pack_color((255, 255, 255), 255)

    cursor_x = left + pad_x
    mode_text = f"Mode: {mode}"
    draw_list.add_text(to_imvec2((cursor_x, text_y)), text_color, mode_text)

    if mode == "builder":
        cursor_x += imgui.calc_text_size(mode_text).x + 16.0
        gizmo_text = f"Gizmo mode: {state.gizmo.mode} (T/R/S)"
        draw_list.add_text(to_imvec2((cursor_x, text_y)), text_color, gizmo_text)

    pos = [round(v, 1) for v in scene.camera.get("position", [0, 0, 0])]
    camera_text = f"camera.position = {pos}"
    camera_text_width = imgui.calc_text_size(camera_text).x
    draw_list.add_text(to_imvec2((left + width - camera_text_width - pad_x, text_y)), text_color, camera_text)


def _draw_help_window(state: EditorState, mode: str) -> None:
    """Bound to `/` (see `_make_key_handler`'s own note -- "?" and
    "Shift+/" both arrive as this same key event).
    """
    if not state.show_help_window:
        return
    imgui.begin("Help")
    imgui.text_wrapped("WASD to move, right-drag to look, Q/E for down/up.")
    if mode == "builder":
        imgui.text("Menu bar: F11")
    imgui.end()


def _draw_entity_and_zone_list_window(scene: Scene, state: EditorState) -> None:
    imgui.begin("Entities & Zones")
    _draw_entity_and_zone_list(scene, state)
    imgui.end()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Standalone Area/Scene viewer/builder/test boot path -- no network connection."
    )
    parser.add_argument("--area", default=None, help="Path to an Area JSON file to load.")
    parser.add_argument(
        "--mode", default="viewer", choices=["viewer", "builder"], help="Boot mode."
    )
    args = parser.parse_args()
    run(area_path=args.area, mode=args.mode)


if __name__ == "__main__":
    main()
