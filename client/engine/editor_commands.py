"""Undo/redo command stack for the level editor. Step 5 of
.github/prompts/level-editor.prompt.md.

Explicitly lifting `area-system.prompt.md`'s "no undo stack --
explicitly out of scope" now that this task's whole point is polish.
Wraps `Scene`'s existing API; `Scene` itself stays unaware undo exists
-- every command factory below calls `Scene.add_entity`/`update_entity`/
`remove_entity`/`set_camera`/`set_lighting`/`set_start_camera`/
`add_zone`/`update_zone`/`remove_zone`, never reaches into `Scene`'s
internals.

Every editor mutation from Step 6 onward goes through
`EditorCommands.execute()` -- never call a `Scene` mutator directly from
UI code once this module is in use.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from client.engine.scene import Scene


@dataclass
class Command:
    """A single undoable editor action: `do()`/`undo()` plus a `label`
    for display (Step 12's "last action" HUD line). Callers should use
    the factory functions below rather than constructing this directly
    -- they exist so call sites read as intent ("move this entity"),
    not "build a Command with these two closures."
    """

    do: Callable[[], None]
    undo: Callable[[], None]
    label: str = ""


class EditorCommands:
    """`__init__(self, scene)` -- holds a reference to the target
    `Scene`, an `undo_stack`, a `redo_stack`. A new `execute()` clears
    `redo_stack` (a new action invalidates any redo history -- standard
    editor behaviour; branching history is explicitly out of scope).
    """

    def __init__(self, scene: Scene) -> None:
        self.scene = scene
        self.undo_stack: list[Command] = []
        self.redo_stack: list[Command] = []

    def execute(self, command: Command) -> None:
        command.do()
        self.undo_stack.append(command)
        self.redo_stack.clear()

    def undo(self) -> Optional[str]:
        """Undo the most recent command. Returns its label, or None if
        there was nothing to undo.
        """
        if not self.undo_stack:
            return None
        command = self.undo_stack.pop()
        command.undo()
        self.redo_stack.append(command)
        return command.label

    def redo(self) -> Optional[str]:
        """Redo the most recently undone command. Returns its label, or
        None if there was nothing to redo.
        """
        if not self.redo_stack:
            return None
        command = self.redo_stack.pop()
        command.do()
        self.undo_stack.append(command)
        return command.label

    @property
    def last_label(self) -> str:
        """The most recently executed/redone command's label, for
        Step 12's always-visible "last action" HUD line. Empty string
        if nothing has happened yet.
        """
        return self.undo_stack[-1].label if self.undo_stack else ""


# ---------------------------------------------------------------------
# Command factories -- small, explicit constructors rather than
# hand-building Command(do=..., undo=...) at every call site.
# ---------------------------------------------------------------------


def move_entity_command(
    scene: Scene, entity_id: str, old_pos: tuple, new_pos: tuple
) -> Command:
    ox, oy, oz = old_pos
    nx, ny, nz = new_pos

    def do():
        scene.update_entity(entity_id, {"x": nx, "y": ny, "z": nz})

    def undo():
        scene.update_entity(entity_id, {"x": ox, "y": oy, "z": oz})

    return Command(do=do, undo=undo, label=f"Move {entity_id}")


def rotate_entity_command(
    scene: Scene, entity_id: str, old_rotation: list, new_rotation: list
) -> Command:
    old_rotation = list(old_rotation)
    new_rotation = list(new_rotation)

    def _apply(rotation):
        entity = scene.entities.get(entity_id)
        if entity is None:
            return
        transform3d = dict(entity.get("transform3d") or {})
        transform3d["rotation"] = list(rotation)
        scene.update_entity(entity_id, {"transform3d": transform3d})

    return Command(
        do=lambda: _apply(new_rotation),
        undo=lambda: _apply(old_rotation),
        label=f"Rotate {entity_id}",
    )


def scale_entity_command(
    scene: Scene, entity_id: str, old_scale: list, new_scale: list
) -> Command:
    old_scale = list(old_scale)
    new_scale = list(new_scale)

    def _apply(scale):
        entity = scene.entities.get(entity_id)
        if entity is None:
            return
        transform3d = dict(entity.get("transform3d") or {})
        transform3d["scale"] = list(scale)
        scene.update_entity(entity_id, {"transform3d": transform3d})

    return Command(
        do=lambda: _apply(new_scale),
        undo=lambda: _apply(old_scale),
        label=f"Scale {entity_id}",
    )


def add_entity_command(scene: Scene, entity_id: str, data: dict, source: str = "local") -> Command:
    data = dict(data)

    return Command(
        do=lambda: scene.add_entity(entity_id, dict(data), source),
        undo=lambda: scene.remove_entity(entity_id),
        label=f"Add {entity_id}",
    )


def remove_entity_command(scene: Scene, entity_id: str, data: dict, source: str) -> Command:
    """Capture *data*/*source* before removal so `undo()` can restore
    it exactly -- callers must read `scene.entities[entity_id]` and
    `scene.entity_source(entity_id)` before calling `scene.remove_entity`
    to build this command's inputs, not after.
    """
    data = dict(data)

    return Command(
        do=lambda: scene.remove_entity(entity_id),
        undo=lambda: scene.add_entity(entity_id, dict(data), source),
        label=f"Remove {entity_id}",
    )


def update_entity_command(scene: Scene, entity_id: str, old_patch: dict, new_patch: dict) -> Command:
    """The generic fallback for property-panel field edits that aren't
    one of the three transform-specific commands above. *old_patch*
    must carry the pre-edit value of every key present in *new_patch*,
    so undo can restore them exactly.
    """
    old_patch = dict(old_patch)
    new_patch = dict(new_patch)

    return Command(
        do=lambda: scene.update_entity(entity_id, dict(new_patch)),
        undo=lambda: scene.update_entity(entity_id, dict(old_patch)),
        label=f"Edit {entity_id}",
    )


def add_zone_command(scene: Scene, zone_id: str, data: dict) -> Command:
    data = dict(data)

    return Command(
        do=lambda: scene.add_zone(zone_id, dict(data)),
        undo=lambda: scene.remove_zone(zone_id),
        label=f"Add zone {zone_id}",
    )


def remove_zone_command(scene: Scene, zone_id: str, data: dict) -> Command:
    data = dict(data)

    return Command(
        do=lambda: scene.remove_zone(zone_id),
        undo=lambda: scene.add_zone(zone_id, dict(data)),
        label=f"Remove zone {zone_id}",
    )


def update_zone_command(scene: Scene, zone_id: str, old_patch: dict, new_patch: dict) -> Command:
    """Covers both shape-transform edits and effect-list edits alike --
    same generic old/new patch shape as `update_entity_command`.
    """
    old_patch = dict(old_patch)
    new_patch = dict(new_patch)

    return Command(
        do=lambda: scene.update_zone(zone_id, dict(new_patch)),
        undo=lambda: scene.update_zone(zone_id, dict(old_patch)),
        label=f"Edit zone {zone_id}",
    )


def set_start_camera_command(scene: Scene, old_camera: "dict | None", new_camera: dict) -> Command:
    """Step 11 task 7's "Set Start Camera to Current View" -- the one
    and only call site allowed to invoke `scene.set_start_camera()`.
    Undo restores the entire prior `start_camera` value (a full
    replace, not a merge -- `Scene.set_start_camera` only merges, so
    undo must reset the dict wholesale to undo a merge correctly).
    """
    old_camera = dict(old_camera) if old_camera is not None else None
    new_camera = dict(new_camera)

    def _do():
        scene.set_start_camera(dict(new_camera))

    def _undo():
        scene.start_camera = dict(old_camera) if old_camera is not None else None

    return Command(do=_do, undo=_undo, label="Set start camera")


_LIGHTING_CAMERA_KEYS = ("ambientColor", "fogColor", "fogNear", "fogFar")


def set_start_lighting_command(scene: Scene, old_lighting: dict, new_lighting: dict) -> Command:
    """Step 11 task 8's "Set Start Lighting" button.

    **Deliberately does not call `scene.set_lighting()`** -- that
    method only *merges*, which cannot correctly undo a change: undoing
    back to a dict that's missing a key `set_lighting` previously added
    would leave the added value behind (found while verifying this
    module, `run_editor_commands_test.py`). Both `do`/`undo` here do a
    full wholesale replace of `scene.lighting` and the dual-written
    `scene.camera` fog/ambient keys instead -- clearing a key from
    `scene.camera` if the target lighting dict doesn't have it, not
    just leaving stale merged-in values in place.
    """
    old_lighting = dict(old_lighting)
    new_lighting = dict(new_lighting)

    def _apply(lighting_dict):
        scene.lighting = dict(lighting_dict)
        for key in _LIGHTING_CAMERA_KEYS:
            if key in lighting_dict:
                scene.camera[key] = lighting_dict[key]
            else:
                scene.camera.pop(key, None)

    return Command(
        do=lambda: _apply(new_lighting),
        undo=lambda: _apply(old_lighting),
        label="Set start lighting",
    )
