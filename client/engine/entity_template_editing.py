"""Shared per-part entity-definition-template editing widgets.

Extracted out of area_viewer.py's `_draw_template_section` (Step 1 task
2 of .github/prompts/entity-builder.prompt.md) so both `area_viewer.py`
(quick in-place tweaks while placing entities in an Area) and
`entity_builder.py` (the primary, full editing surface, with part
CRUD/import/material assignment layered around this same per-part field
set) call one implementation instead of two forks of the same imgui
code drifting apart.

This module never touches disk or the manifest itself -- `draw_part_fields()`
returns the edited part dict when its own "Confirm & Save Template"
button is pressed; the caller splices it back into the full `parts`
array and calls `area_io.save_entity_definition()`, exactly like
`area_viewer.py` already did before this extraction.
"""

from imgui_bundle import imgui


def default_part_buffer(part: dict) -> dict:
    """The in-progress edit-state shape `draw_part_fields()` expects,
    seeded from *part*'s current on-disk values. Callers own where this
    is stored (area_viewer.py and entity_builder.py both key a dict of
    these by a `f"{render_template}:{part_id}"` string, but this
    function doesn't care how its result is cached).
    """
    return {
        "animation_id": part.get("animation_id") or "",
        "dangle": dict(part.get("dangle") or {}),
        "local_offset_position": list((part.get("localOffset") or {}).get("position") or [0, 0, 0]),
        "action_animations": dict(part.get("action_animations") or {}),
    }


def draw_part_fields(part: dict, buffer: dict, action_registry, buffer_key: str) -> "dict | None":
    """Render one part's `animation_id`/`dangle`/`localOffset.position`/
    `action_animations` fields plus a "Confirm & Save Template" button.

    Args:
        part: This part's current, on-disk config dict.
        buffer: In-progress edit state (see `default_part_buffer()`),
            mutated in place across frames the same way every other
            imgui widget in this codebase persists between-frame state.
        action_registry: An object with an `.actions` dict (`area_viewer
            .ActionRegistry` today) -- used to list which action names
            have a per-part clip slot.
        buffer_key: Unique suffix for imgui widget ids (e.g.
            `f"{render_template}:{part_id}"`) so multiple parts/entities
            editing simultaneously don't collide.

    Returns:
        The edited part dict, if "Confirm & Save Template" was pressed
        this frame -- the caller is responsible for splicing it back
        into the full `parts` array and persisting it. `None` otherwise
        (nothing to save yet).
    """
    imgui.text("animation_id (continuous, looping clip)")
    _, buffer["animation_id"] = imgui.input_text(
        f"animation_id##{buffer_key}", buffer["animation_id"]
    )

    imgui.text("dangle (secondary motion)")
    for key, default in (("stiffness", 6.0), ("damping", 0.25), ("maxOffset", 6.0)):
        value = buffer["dangle"].get(key, default)
        _, buffer["dangle"][key] = imgui.input_float(f"dangle.{key}##{buffer_key}", value)

    imgui.text("localOffset.position")
    for i, axis_name in enumerate(("ox", "oy", "oz")):
        _, buffer["local_offset_position"][i] = imgui.input_float(
            f"{axis_name}##{buffer_key}", buffer["local_offset_position"][i]
        )

    # Step 15 (level-editor.prompt.md) task 3: per-part action-clip
    # assignment -- one transform-clip-id text field per registered
    # action, writing/clearing part.action_animations[action_name].
    # Data only, exactly like the dangle/localOffset fields above --
    # deciding *when* an action fires is real gameplay code, never
    # authored here.
    imgui.text("action_animations (per registered action)")
    if not action_registry.actions:
        imgui.text_wrapped("No actions registered yet -- add some in the Action Definitions panel.")
    for action_name in sorted(action_registry.actions.keys()):
        clip_id = buffer["action_animations"].get(action_name, "")
        _, buffer["action_animations"][action_name] = imgui.input_text(
            f"{action_name}##{buffer_key}-actionclip", clip_id
        )
        if not buffer["action_animations"][action_name]:
            buffer["action_animations"].pop(action_name, None)

    if not imgui.button(f"Confirm & Save Template##{buffer_key}"):
        return None

    new_part = dict(part)
    if buffer["animation_id"]:
        new_part["animation_id"] = buffer["animation_id"]
    elif "animation_id" in new_part:
        del new_part["animation_id"]
    new_part["dangle"] = dict(buffer["dangle"])
    local_offset = dict(part.get("localOffset") or {})
    local_offset["position"] = list(buffer["local_offset_position"])
    new_part["localOffset"] = local_offset
    if buffer["action_animations"]:
        new_part["action_animations"] = dict(buffer["action_animations"])
    elif "action_animations" in new_part:
        del new_part["action_animations"]
    return new_part
