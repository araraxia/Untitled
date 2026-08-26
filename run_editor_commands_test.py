"""[DEV ONLY] Standalone smoke test for client/engine/editor_commands.py
-- EditorCommands' undo/redo stack and every command factory. No GPU,
no backend. Step 5 of .github/prompts/level-editor.prompt.md.

Usage:
    python run_editor_commands_test.py
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.independant_logger import Logger

logger = Logger(
    log_name="run_editor_commands_test",
    log_file="editor_commands_test.log",
    log_level=20,
).get_logger()

from client.engine.editor_commands import (
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
from client.engine.scene import Scene


def check(label: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    logger.info(f"[{status}] {label}")
    if not condition:
        raise AssertionError(label)


def test_add_undo_redo() -> None:
    scene = Scene()
    commands = EditorCommands(scene)

    commands.execute(add_entity_command(scene, "a", {"x": 0, "y": 0, "z": 0}))
    check("add: entity present after execute", "a" in scene.entities)

    commands.undo()
    check("undo: entity removed", "a" not in scene.entities)

    commands.redo()
    check("redo: entity restored", "a" in scene.entities)


def test_move_rotate_scale() -> None:
    scene = Scene()
    commands = EditorCommands(scene)
    commands.execute(add_entity_command(scene, "a", {"x": 0, "y": 0, "z": 0, "transform3d": {"rotation": [0, 0, 0], "scale": [1, 1, 1]}}))

    commands.execute(move_entity_command(scene, "a", (0, 0, 0), (10, 5, -3)))
    check("move: applied", (scene.entities["a"]["x"], scene.entities["a"]["y"], scene.entities["a"]["z"]) == (10, 5, -3))
    commands.undo()
    check("move: undone", (scene.entities["a"]["x"], scene.entities["a"]["y"], scene.entities["a"]["z"]) == (0, 0, 0))

    commands.execute(rotate_entity_command(scene, "a", [0, 0, 0], [0, 1.57, 0]))
    check("rotate: applied", scene.entities["a"]["transform3d"]["rotation"] == [0, 1.57, 0])
    commands.undo()
    check("rotate: undone", scene.entities["a"]["transform3d"]["rotation"] == [0, 0, 0])

    commands.execute(scale_entity_command(scene, "a", [1, 1, 1], [2, 2, 2]))
    check("scale: applied", scene.entities["a"]["transform3d"]["scale"] == [2, 2, 2])
    commands.undo()
    check("scale: undone", scene.entities["a"]["transform3d"]["scale"] == [1, 1, 1])


def test_remove_and_source_preserved() -> None:
    scene = Scene()
    commands = EditorCommands(scene)
    commands.execute(add_entity_command(scene, "a", {"x": 0, "y": 0, "z": 0}, source="authoritative"))

    data = dict(scene.entities["a"])
    source = scene.entity_source("a")
    commands.execute(remove_entity_command(scene, "a", data, source))
    check("remove: gone", "a" not in scene.entities)

    commands.undo()
    check("remove undo: restored", "a" in scene.entities)
    check("remove undo: source preserved", scene.entity_source("a") == "authoritative")


def test_update_entity_generic() -> None:
    scene = Scene()
    commands = EditorCommands(scene)
    commands.execute(add_entity_command(scene, "a", {"x": 0, "render_template": "old-id"}))

    commands.execute(update_entity_command(scene, "a", {"render_template": "old-id"}, {"render_template": "new-id"}))
    check("update: applied", scene.entities["a"]["render_template"] == "new-id")
    commands.undo()
    check("update: undone", scene.entities["a"]["render_template"] == "old-id")


def test_zone_commands() -> None:
    scene = Scene()
    commands = EditorCommands(scene)

    commands.execute(add_zone_command(scene, "z1", {"shape": {"type": "aabb", "min": [0, 0, 0], "max": [1, 1, 1]}, "on_enter": [], "on_exit": []}))
    check("add_zone: present", "z1" in scene.zones)
    commands.undo()
    check("add_zone undo: gone", "z1" not in scene.zones)
    commands.redo()
    check("add_zone redo: back", "z1" in scene.zones)

    commands.execute(update_zone_command(scene, "z1", {"on_enter": []}, {"on_enter": [{"type": "fire_event", "event": "test"}]}))
    check("update_zone: applied", scene.zones["z1"]["on_enter"] == [{"type": "fire_event", "event": "test"}])
    commands.undo()
    check("update_zone undo: reverted", scene.zones["z1"]["on_enter"] == [])

    data = dict(scene.zones["z1"])
    commands.execute(remove_zone_command(scene, "z1", data))
    check("remove_zone: gone", "z1" not in scene.zones)
    commands.undo()
    check("remove_zone undo: restored", "z1" in scene.zones)


def test_start_camera_and_lighting() -> None:
    scene = Scene()
    commands = EditorCommands(scene)
    scene.set_camera({"mode": "3d", "position": [1, 2, 3]})

    commands.execute(set_start_camera_command(scene, scene.start_camera, dict(scene.camera)))
    check("set_start_camera: applied", scene.start_camera["position"] == [1, 2, 3])
    commands.undo()
    check("set_start_camera: undone (back to None)", scene.start_camera is None)

    commands.execute(set_start_lighting_command(scene, dict(scene.lighting), {"ambientColor": [0.5, 0.5, 0.5]}))
    check("set_start_lighting: applied to lighting", scene.lighting["ambientColor"] == [0.5, 0.5, 0.5])
    check("set_start_lighting: dual-written to camera", scene.camera["ambientColor"] == [0.5, 0.5, 0.5])
    commands.undo()
    check("set_start_lighting: undone", scene.lighting.get("ambientColor") is None)


def test_new_action_clears_redo_stack() -> None:
    scene = Scene()
    commands = EditorCommands(scene)
    commands.execute(add_entity_command(scene, "a", {"x": 0}))
    commands.undo()
    check("redo stack has one entry before a new action", len(commands.redo_stack) == 1)

    commands.execute(add_entity_command(scene, "b", {"x": 0}))
    check("a new execute() clears the redo stack", len(commands.redo_stack) == 0)


def test_last_label_and_empty_stack_noops() -> None:
    scene = Scene()
    commands = EditorCommands(scene)
    check("undo on empty stack returns None, does not raise", commands.undo() is None)
    check("redo on empty stack returns None, does not raise", commands.redo() is None)
    check("last_label empty before anything happens", commands.last_label == "")

    commands.execute(add_entity_command(scene, "a", {"x": 0}))
    check("last_label reflects the most recent command", commands.last_label == "Add a")


def main() -> None:
    logger.info("=" * 50)
    logger.info("[DEV ONLY] EditorCommands smoke test")
    logger.info("=" * 50)

    test_add_undo_redo()
    test_move_rotate_scale()
    test_remove_and_source_preserved()
    test_update_entity_generic()
    test_zone_commands()
    test_start_camera_and_lighting()
    test_new_action_clears_redo_stack()
    test_last_label_and_empty_stack_noops()

    logger.info("PASS: EditorCommands undo/redo and every command factory verified.")


if __name__ == "__main__":
    main()
