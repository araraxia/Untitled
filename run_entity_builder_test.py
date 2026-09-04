"""Headless verification for client/engine/entity_builder.py's pure
data-model logic -- Step 12 of .github/prompts/entity-builder.prompt.md.
Also covers client/engine/orbit_camera.py's zoom math (shared with
asset_preview.py), since entity_builder.py's camera auto-fit is what
surfaced a real bug in it.

No GPU/window needed: this only exercises the plain-Python helpers
(socket reading, socket-to-mesh matching, part-id validation, part
removal/orphaning, material-id round-tripping, bounding-radius/zoom
math) against real project fixtures, the same convention as
run_zone_test.py/run_gametick_test.py.
"""

import json
import math
import sys
from pathlib import Path

from client.engine.area_io import (
    ENTITY_DIR,
    load_entity_definition,
    normalize_entity_id,
    refresh_manifest,
    save_entity_definition,
)
from client.engine.asset_loader import asset_loader
from client.engine.entity_builder import (
    add_keyframe,
    advance_timeline_playback_ms,
    animations_used_by_parts,
    apply_keyframe_preview,
    apply_rigid_group_delta,
    assign_part_to_keyframe,
    asset_id_for_material_id_field,
    compute_group_transform_delta,
    default_keyframe_transform,
    duplicate_keyframe,
    entity_bounding_radius,
    find_unattached_part_for_mesh,
    keyframe_gap,
    MESH_DIR,
    keyframe_preview_reach,
    material_id_field_for_asset,
    mesh_bounding_radius,
    mesh_id_to_part_id,
    meshes_used_by_parts,
    new_animation_clip,
    new_animation_clip_id,
    new_animation_clip_path,
    parts_assigned_in_clip,
    part_attached_to_socket,
    parts_using_animation,
    parts_using_mesh,
    position_drag_speed,
    read_mesh_name,
    read_mesh_sockets,
    remove_keyframe,
    remove_part,
    remove_part_from_keyframe,
    sample_part_pose,
    set_keyframe_gap,
    stamp_animation_id_for_assigned_parts,
    strip_live_animation_fields,
    suggest_socket_match,
    unique_part_id,
    validate_new_part_name,
)
from client.engine.orbit_camera import OrbitCamera
from client.engine.mat4 import compose, compose_with_pivot
from client.engine.transform_clip import (
    cubic_bezier_ease,
    DEFAULT_EASING,
    resolve_easing,
    sample_transform_clip,
)
from client.engine.launcher import (
    _current_display_name,
    _rename_asset,
    filtered_sorted_entity_ids_by_name,
)

# tools/ isn't a package -- importing client.engine.entity_builder above
# already inserted tools/ onto sys.path as a side effect (same trick
# that module's own docstring documents), so this import works without
# repeating that setup here.
import convert_mesh  # noqa: E402

_SCRATCH_ENTITY_ID = "_run_entity_builder_test_scratch"

_FAILURES = []


def check(label: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        _FAILURES.append(label)


def main() -> None:
    asset_loader.load_manifest()
    asset_loader.register(
        "mesh-example-staff-shaft", "assets/data/mesh/mesh-example-staff-shaft.json"
    )
    asset_loader.register(
        "mesh-example-staff-charm", "assets/data/mesh/mesh-example-staff-charm.json"
    )

    # --- read_mesh_sockets ---
    sockets = read_mesh_sockets("mesh-example-staff-shaft")
    check("read_mesh_sockets finds the real charm_socket", sockets == ["charm_socket"])
    check("read_mesh_sockets returns [] for an unregistered mesh id", read_mesh_sockets("no-such-mesh") == [])
    check("read_mesh_sockets returns [] for None", read_mesh_sockets(None) == [])

    # --- read_mesh_name (per direct request: "make it trivial to
    # rename parts, meshes or entities without it breaking relations" --
    # used to give a freshly-auto-added part a sensible name matching
    # its mesh's own) ---
    asset_loader.register("mesh-body", "assets/data/mesh/mesh-body.json")
    check("read_mesh_name finds the real 'name' field on a mesh that has one", read_mesh_name("mesh-body") == "body")
    check(
        "read_mesh_name returns None for a real mesh predating the convert_mesh.py fix (no 'name' field at all)",
        read_mesh_name("mesh-example-staff-shaft") is None,
    )
    check("read_mesh_name returns None for an unregistered mesh id", read_mesh_name("no-such-mesh") is None)
    check("read_mesh_name returns None for None", read_mesh_name(None) is None)

    # --- suggest_socket_match ---
    candidates = ["mesh-example-staff-charm", "mesh-example-crate", "mesh-bird-wing-l"]
    check(
        "suggest_socket_match matches 'charm_socket' -> the charm mesh",
        suggest_socket_match("charm_socket", candidates) == "mesh-example-staff-charm",
    )
    check(
        "suggest_socket_match returns None when nothing matches",
        suggest_socket_match("beak_socket", candidates) is None,
    )

    # Real-data regression: tools/split_glb.py's Blender-object-derived
    # names came out side-then-part ("L_Wing" -> "mesh-bird-l_wing"),
    # while this project's socket convention is part-then-side
    # ("wing_l_socket") -- a plain substring check misses this
    # entirely; the word-set match must not.
    bird_mesh_ids = [
        "mesh-bird-body", "mesh-bird-beak",
        "mesh-bird-l_leg", "mesh-bird-r_leg",
        "mesh-bird-l_wing", "mesh-bird-r_wing",
    ]
    check(
        "suggest_socket_match handles reversed word order (wing_l_socket -> l_wing mesh)",
        suggest_socket_match("wing_l_socket", bird_mesh_ids) == "mesh-bird-l_wing",
    )
    check(
        "suggest_socket_match handles reversed word order (leg_r_socket -> r_leg mesh)",
        suggest_socket_match("leg_r_socket", bird_mesh_ids) == "mesh-bird-r_leg",
    )
    check(
        "suggest_socket_match doesn't cross-match the wrong side (leg_l_socket != r_leg mesh)",
        suggest_socket_match("leg_l_socket", bird_mesh_ids) != "mesh-bird-r_leg",
    )

    # --- validate_new_part_name (per direct request: "make it trivial
    # to rename parts... without it breaking relations" -- a duplicate
    # *name* is no longer an error, only an empty one is, since the
    # actual id a new part gets is independently deduped by
    # unique_part_id and can never collide) ---
    check("validate_new_part_name rejects an empty name", validate_new_part_name("") is not None)
    check("validate_new_part_name rejects a whitespace-only name", validate_new_part_name("   ") is not None)
    check("validate_new_part_name accepts a fresh name", validate_new_part_name("wing_r") is None)
    check("validate_new_part_name allows a name that duplicates an existing part's name (names aren't unique by design)", validate_new_part_name("body") is None)

    # --- remove_part / orphaning ---
    parts = [
        {"id": "root", "mesh": "mesh-a"},
        {"id": "child", "mesh": "mesh-b", "attachTo": {"part": "root", "socket": "s1"}},
        {"id": "grandchild", "mesh": "mesh-c", "attachTo": {"part": "child", "socket": "s2"}},
    ]
    orphaned = remove_part(parts, "root")
    check("remove_part actually removes the part", all(p["id"] != "root" for p in parts))
    check("remove_part orphans (clears attachTo on) the direct child", orphaned == ["child"])
    child = next(p for p in parts if p["id"] == "child")
    check("remove_part clears the orphaned child's attachTo entirely", "attachTo" not in child)
    grandchild = next(p for p in parts if p["id"] == "grandchild")
    check(
        "remove_part leaves an unrelated part's attachTo untouched",
        grandchild.get("attachTo") == {"part": "child", "socket": "s2"},
    )

    # --- part_attached_to_socket (fixes a real reported bug: scaffolding
    # used to add a duplicate, overlapping part at a socket that already
    # had one attached, since it only guarded against *id* collisions) ---
    scaffold_parts = [
        {"id": "body", "mesh": "mesh-bird-body"},
        {"id": "wing_l", "mesh": "mesh-bird-l_wing", "attachTo": {"part": "body", "socket": "wing_l_socket"}},
    ]
    check(
        "part_attached_to_socket finds the existing part at an already-claimed socket",
        part_attached_to_socket(scaffold_parts, "body", "wing_l_socket") == "wing_l",
    )
    check(
        "part_attached_to_socket returns None for a socket nothing is attached to yet",
        part_attached_to_socket(scaffold_parts, "body", "wing_r_socket") is None,
    )
    check(
        "part_attached_to_socket ignores a same-named socket on a different parent",
        part_attached_to_socket(scaffold_parts, "some_other_part", "wing_l_socket") is None,
    )
    check(
        "part_attached_to_socket ignores a part with no attachTo at all",
        part_attached_to_socket(scaffold_parts, "body", "beak_socket") is None,
    )

    # --- mesh_id_to_part_id / unique_part_id / meshes_used_by_parts /
    # parts_using_mesh / find_unattached_part_for_mesh -- support "when
    # a mesh is converted, add it to the entity" and the Meshes sidebar
    # tab ("meshes imported into an entity"), plus the fix that keeps
    # Scaffold from duplicating a part Import Mesh/Split already added.
    check("mesh_id_to_part_id strips the 'mesh-' prefix", mesh_id_to_part_id("mesh-l_wing") == "l_wing")
    check("mesh_id_to_part_id passes through an id with no prefix", mesh_id_to_part_id("l_wing") == "l_wing")

    no_collision = [{"id": "body"}]
    check("unique_part_id returns the candidate unchanged when it's free", unique_part_id("wing_l", no_collision) == "wing_l")
    one_collision = [{"id": "wing_l"}]
    check("unique_part_id appends _2 on a single collision", unique_part_id("wing_l", one_collision) == "wing_l_2")
    two_collisions = [{"id": "wing_l"}, {"id": "wing_l_2"}]
    check("unique_part_id skips past multiple collisions", unique_part_id("wing_l", two_collisions) == "wing_l_3")

    inventory_parts = [
        {"id": "body", "mesh": "mesh-bird-body"},
        {"id": "wing_l", "mesh": "mesh-bird-l_wing", "attachTo": {"part": "body", "socket": "wing_l_socket"}},
        {"id": "wing_r", "mesh": "mesh-bird-l_wing"},  # deliberately shares wing_l's mesh, unattached
        {"id": "no_mesh_yet", "mesh": None},
    ]
    check(
        "meshes_used_by_parts lists distinct meshes in first-seen order",
        meshes_used_by_parts(inventory_parts) == ["mesh-bird-body", "mesh-bird-l_wing"],
    )
    check(
        "parts_using_mesh finds every part referencing a shared mesh",
        parts_using_mesh(inventory_parts, "mesh-bird-l_wing") == ["wing_l", "wing_r"],
    )
    check(
        "parts_using_mesh returns [] for a mesh nothing references",
        parts_using_mesh(inventory_parts, "mesh-bird-beak") == [],
    )
    check(
        "find_unattached_part_for_mesh finds the unattached duplicate, not the attached one",
        find_unattached_part_for_mesh(inventory_parts, "mesh-bird-l_wing", "body") == inventory_parts[2],
    )
    check(
        "find_unattached_part_for_mesh never returns the root part itself",
        find_unattached_part_for_mesh(inventory_parts, "mesh-bird-body", "body") is None,
    )
    check(
        "find_unattached_part_for_mesh returns None when nothing unattached uses that mesh",
        find_unattached_part_for_mesh(inventory_parts, "mesh-bird-beak", "body") is None,
    )

    # --- animations_used_by_parts / parts_using_animation (Animations
    # sidebar tab: "animations imported into an entity") ---
    animated_parts = [
        {"id": "shaft", "mesh": "mesh-example-staff-shaft"},
        {
            "id": "charm",
            "mesh": "mesh-example-staff-charm",
            "animation_id": "anim-transform-charm-spin",
            "action_animations": {
                "activate": "anim-transform-charm-activate-swing",
                "deactivate": "anim-transform-charm-spin",  # deliberately reuses the same clip as animation_id
            },
        },
    ]
    check(
        "animations_used_by_parts lists distinct clips in first-seen order (animation_id before action_animations)",
        animations_used_by_parts(animated_parts) == [
            "anim-transform-charm-spin",
            "anim-transform-charm-activate-swing",
        ],
    )
    check(
        "animations_used_by_parts returns [] for parts with no animations assigned",
        animations_used_by_parts([{"id": "shaft", "mesh": "mesh-example-staff-shaft"}]) == [],
    )
    spin_usages = parts_using_animation(animated_parts, "anim-transform-charm-spin")
    check(
        "parts_using_animation finds both the continuous and one-shot usage of a shared clip",
        {"part": "charm", "role": "animation_id"} in spin_usages
        and {"part": "charm", "role": "action:deactivate"} in spin_usages
        and len(spin_usages) == 2,
    )
    check(
        "parts_using_animation finds the one-shot-only usage of a distinct clip",
        parts_using_animation(animated_parts, "anim-transform-charm-activate-swing")
        == [{"part": "charm", "role": "action:activate"}],
    )
    check(
        "parts_using_animation returns [] for a clip nothing references",
        parts_using_animation(animated_parts, "anim-transform-unused") == [],
    )

    # --- Animation Editor pure helpers (new/edit-mode multi-part rig
    # clips, per direct request) ---
    check("new_animation_clip_id follows the anim-transform-<name> convention", new_animation_clip_id("bird-flap") == "anim-transform-bird-flap")
    check(
        "new_animation_clip_path follows the animation-transform-<name>.json convention",
        new_animation_clip_path("bird-flap").name == "animation-transform-bird-flap.json",
    )
    fresh_clip = new_animation_clip("anim-transform-bird-flap")
    check(
        "new_animation_clip starts empty (id/type/loop set, no keyframes yet)",
        fresh_clip == {"id": "anim-transform-bird-flap", "type": "transform", "loop": True, "keyframes": []},
    )
    check(
        "default_keyframe_transform is identity position/rotation, unit scale",
        default_keyframe_transform() == {"position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0]},
    )

    kfs: "list[dict]" = []
    kf0 = add_keyframe(kfs)
    check("add_keyframe's first keyframe starts at time_ms=0", kf0["time_ms"] == 0.0 and kfs[0] is kf0)
    kf1 = add_keyframe(kfs)
    check("add_keyframe's second keyframe uses the default 500ms gap", kf1["time_ms"] == 500.0)
    kf2 = add_keyframe(kfs, gap_ms=250.0)
    check("add_keyframe honors an explicit gap_ms", kf2["time_ms"] == 750.0)

    check("keyframe_gap for index 0 is its own time_ms", keyframe_gap(kfs, 0) == 0.0)
    check("keyframe_gap for a later index is the delta from the previous keyframe", keyframe_gap(kfs, 1) == 500.0 and keyframe_gap(kfs, 2) == 250.0)

    set_keyframe_gap(kfs, 1, 100.0)
    check("set_keyframe_gap moves only the target keyframe's own time_ms", kfs[1]["time_ms"] == 100.0)
    check("set_keyframe_gap leaves later keyframes' own time_ms untouched (their gap changes instead)", kfs[2]["time_ms"] == 750.0)
    set_keyframe_gap(kfs, 1, -50.0)
    check("set_keyframe_gap clamps a negative gap to 0", kfs[1]["time_ms"] == 0.0)

    assign_part_to_keyframe(kfs[0], "wing_l")
    assign_part_to_keyframe(kfs[0], "wing_r", {"rotation": [0.0, 0.0, 0.5], "position": [0, 0, 0], "scale": [1, 1, 1]})
    check("assign_part_to_keyframe defaults to an identity transform", kfs[0]["parts"]["wing_l"] == default_keyframe_transform())
    check("assign_part_to_keyframe accepts an explicit transform", kfs[0]["parts"]["wing_r"]["rotation"] == [0.0, 0.0, 0.5])
    remove_part_from_keyframe(kfs[0], "wing_r")
    check("remove_part_from_keyframe drops just that part", "wing_r" not in kfs[0]["parts"] and "wing_l" in kfs[0]["parts"])

    assign_part_to_keyframe(kfs[1], "wing_l")
    check(
        "parts_assigned_in_clip lists distinct part ids across every keyframe, first-seen order",
        parts_assigned_in_clip({"keyframes": kfs}) == ["wing_l"],
    )

    remove_keyframe(kfs, 2)
    check("remove_keyframe deletes just that keyframe", len(kfs) == 2)

    # --- compute_group_transform_delta / apply_rigid_group_delta (per
    # direct request: "add another option to the animation editor's
    # keyframe transformer system that allows you to apply
    # transformations to every mesh/part in the entity as one") ---
    delta_pos, delta_rot, scale_ratio = compute_group_transform_delta(
        old_position=[0.0, 0.0, 0.0],
        new_position=[1.0, 2.0, 3.0],
        old_rotation=[0.0, 0.0, 0.0],
        new_rotation=[0.0, 0.1, 0.0],
        old_scale=[1.0, 1.0, 1.0],
        new_scale=[2.0, 1.0, 0.5],
    )
    check("compute_group_transform_delta computes an additive position delta", delta_pos == [1.0, 2.0, 3.0])
    check("compute_group_transform_delta computes an additive rotation delta", delta_rot == [0.0, 0.1, 0.0])
    check("compute_group_transform_delta computes a multiplicative scale ratio", scale_ratio == [2.0, 1.0, 0.5])

    zero_delta_pos, _, zero_scale_ratio = compute_group_transform_delta(
        old_position=[5.0, 5.0, 5.0],
        new_position=[5.0, 5.0, 5.0],
        old_rotation=[0.0, 0.0, 0.0],
        new_rotation=[0.0, 0.0, 0.0],
        old_scale=[0.0, 1.0, 1.0],
        new_scale=[0.0, 3.0, 1.0],
    )
    check("compute_group_transform_delta reports no position change when old == new", zero_delta_pos == [0.0, 0.0, 0.0])
    check(
        "compute_group_transform_delta guards a near-zero old scale component against divide-by-zero (ratio 1.0)",
        zero_scale_ratio[0] == 1.0 and zero_scale_ratio[1] == 3.0,
    )

    group_kf = add_keyframe([])
    group_kfs = [group_kf]
    assign_part_to_keyframe(group_kfs[0], "body", {"position": [1.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0]})
    assign_part_to_keyframe(group_kfs[0], "wing_l", {"position": [2.0, 0.0, 0.0], "rotation": [0.1, 0.0, 0.0], "scale": [2.0, 1.0, 1.0]})
    apply_rigid_group_delta(
        group_kfs[0],
        ["body", "wing_l"],
        delta_position=[0.0, 5.0, 0.0],
        delta_rotation=[0.0, 0.0, 0.2],
        scale_ratio=[1.0, 1.0, 2.0],
    )
    check(
        "apply_rigid_group_delta shifts every listed part by the same additive position delta",
        group_kfs[0]["parts"]["body"]["position"] == [1.0, 5.0, 0.0]
        and group_kfs[0]["parts"]["wing_l"]["position"] == [2.0, 5.0, 0.0],
    )
    check(
        "apply_rigid_group_delta preserves each part's own relative position (rigid-body move, not identical positions)",
        group_kfs[0]["parts"]["body"]["position"] != group_kfs[0]["parts"]["wing_l"]["position"],
    )
    check(
        "apply_rigid_group_delta adds the same rotation delta to every listed part, on top of its own existing rotation",
        group_kfs[0]["parts"]["body"]["rotation"] == [0.0, 0.0, 0.2]
        and group_kfs[0]["parts"]["wing_l"]["rotation"] == [0.1, 0.0, 0.2],
    )
    check(
        "apply_rigid_group_delta multiplies every listed part's own scale by the same ratio, component-wise",
        group_kfs[0]["parts"]["body"]["scale"] == [1.0, 1.0, 2.0]
        and group_kfs[0]["parts"]["wing_l"]["scale"] == [2.0, 1.0, 2.0],
    )

    # --- duplicate_keyframe (per direct request: "add a button to
    # duplicate the current selected keyframe. This clones all part
    # transformations") ---
    dup_kfs: "list[dict]" = []
    add_keyframe(dup_kfs)  # kf0 @ 0ms
    add_keyframe(dup_kfs, gap_ms=1000.0)  # kf1 @ 1000ms
    assign_part_to_keyframe(dup_kfs[0], "wing_l", {"position": [1.0, 2.0, 3.0], "rotation": [0.1, 0.2, 0.3], "scale": [1.0, 1.0, 1.0]})
    assign_part_to_keyframe(dup_kfs[0], "wing_r", {"position": [4.0, 5.0, 6.0], "rotation": [0.4, 0.5, 0.6], "scale": [2.0, 2.0, 2.0]})

    new_kf = duplicate_keyframe(dup_kfs, 0)
    check("duplicate_keyframe returns the newly-appended keyframe", new_kf is dup_kfs[-1] and len(dup_kfs) == 3)
    check("duplicate_keyframe places the clone after the current last keyframe (add_keyframe's own placement rule)", new_kf["time_ms"] == 1500.0)
    check(
        "duplicate_keyframe clones every assigned part's transform exactly",
        new_kf["parts"]["wing_l"] == {"position": [1.0, 2.0, 3.0], "rotation": [0.1, 0.2, 0.3], "scale": [1.0, 1.0, 1.0]}
        and new_kf["parts"]["wing_r"] == {"position": [4.0, 5.0, 6.0], "rotation": [0.4, 0.5, 0.6], "scale": [2.0, 2.0, 2.0]},
    )

    new_kf["parts"]["wing_l"]["position"][0] = 999.0
    check(
        "duplicate_keyframe's clone is a real deep copy -- editing it never mutates the source keyframe",
        dup_kfs[0]["parts"]["wing_l"]["position"] == [1.0, 2.0, 3.0],
    )

    check("duplicate_keyframe returns None for an out-of-range index (nothing selected)", duplicate_keyframe(dup_kfs, 99) is None)
    check("duplicate_keyframe returns None for a negative index", duplicate_keyframe(dup_kfs, -1) is None)

    # Real gap found and fixed while adding per-part "easing" (Step 17):
    # this function used to hardcode exactly position/rotation/scale,
    # which would have silently dropped a custom transition curve back
    # to default the moment its keyframe was duplicated.
    dup_kfs[0]["parts"]["wing_l"]["easing"] = [0.4, 0.0, 0.6, 1.0]
    eased_dup_kf = duplicate_keyframe(dup_kfs, 0)
    check(
        "duplicate_keyframe carries over a part's own easing curve",
        eased_dup_kf["parts"]["wing_l"]["easing"] == [0.4, 0.0, 0.6, 1.0],
    )
    check(
        "duplicate_keyframe doesn't invent an easing field for a part that never had one",
        "easing" not in eased_dup_kf["parts"]["wing_r"],
    )
    eased_dup_kf["parts"]["wing_l"]["easing"][0] = 999.0
    check(
        "duplicate_keyframe's easing clone is a real deep copy too",
        dup_kfs[0]["parts"]["wing_l"]["easing"] == [0.4, 0.0, 0.6, 1.0],
    )

    rig_parts = [{"id": "wing_l", "mesh": "mesh-example-staff-shaft"}, {"id": "wing_r", "mesh": "mesh-example-staff-shaft", "animation_id": "anim-transform-existing"}]
    stamped = stamp_animation_id_for_assigned_parts(rig_parts, ["wing_l", "wing_r", "no-such-part"], "anim-transform-bird-flap")
    check("stamp_animation_id_for_assigned_parts stamps a part with no animation_id yet", rig_parts[0]["animation_id"] == "anim-transform-bird-flap")
    check("stamp_animation_id_for_assigned_parts never overwrites an existing animation_id", rig_parts[1]["animation_id"] == "anim-transform-existing")
    check("stamp_animation_id_for_assigned_parts returns only ids actually changed", stamped == ["wing_l"])

    # --- apply_keyframe_preview (live "mesh follows the keyframe
    # you're editing" feedback in the orbit preview, per direct request) ---
    preview_parts = [
        {"id": "shaft", "mesh": "mesh-example-staff-shaft", "localOffset": {"position": [1, 1, 1]}},
        {
            "id": "charm", "mesh": "mesh-example-staff-charm",
            "localOffset": {"position": [0, -8, 0]},
            "animation_id": "anim-transform-charm-spin",
            "action_animations": {"activate": "anim-transform-charm-activate-swing"},
        },
    ]
    check("apply_keyframe_preview is a no-op (same list) for None keyframe", apply_keyframe_preview(preview_parts, None) is preview_parts)
    check("apply_keyframe_preview is a no-op (same list) for a keyframe with no parts assigned", apply_keyframe_preview(preview_parts, {"time_ms": 0, "parts": {}}) is preview_parts)

    posed_keyframe = {"time_ms": 500, "parts": {"charm": {"position": [9, 9, 9], "rotation": [0, 1, 0], "scale": [2, 2, 2]}}}
    posed = apply_keyframe_preview(preview_parts, posed_keyframe)
    posed_charm = next(p for p in posed if p["id"] == "charm")
    posed_shaft = next(p for p in posed if p["id"] == "shaft")
    check("apply_keyframe_preview overrides localOffset for the assigned part", posed_charm["localOffset"] == {"position": [9, 9, 9], "rotation": [0, 1, 0], "scale": [2, 2, 2]})
    check("apply_keyframe_preview strips animation_id from the previewed part (so it can't override the pose right back)", "animation_id" not in posed_charm)
    check("apply_keyframe_preview strips action_animations from the previewed part", "action_animations" not in posed_charm)
    check("apply_keyframe_preview leaves an unassigned part completely untouched", posed_shaft is preview_parts[0])
    check("apply_keyframe_preview never mutates the original parts list", preview_parts[1]["localOffset"] == {"position": [0, -8, 0]} and preview_parts[1].get("animation_id") == "anim-transform-charm-spin")

    # --- strip_live_animation_fields (per direct request: "return the
    # entity model state to default when an animation is not selected --
    # such as when deselecting or the default state when loading/opening
    # an entity") ---
    stripped = strip_live_animation_fields(preview_parts)
    stripped_shaft = next(p for p in stripped if p["id"] == "shaft")
    stripped_charm = next(p for p in stripped if p["id"] == "charm")
    check("strip_live_animation_fields removes animation_id", "animation_id" not in stripped_charm)
    check("strip_live_animation_fields removes action_animations", "action_animations" not in stripped_charm)
    check(
        "strip_live_animation_fields leaves localOffset (the default rest pose) untouched",
        stripped_charm["localOffset"] == {"position": [0, -8, 0]},
    )
    check(
        "strip_live_animation_fields doesn't touch a part with neither field to begin with",
        stripped_shaft == preview_parts[0],
    )
    check(
        "strip_live_animation_fields never mutates the original parts list",
        "animation_id" in preview_parts[1] and "action_animations" in preview_parts[1],
    )

    # --- transform_clip.sample_transform_clip's multi-part "parts" path
    # (the runtime half of the same feature -- entity_renderer.py now
    # threads part_id through to here) ---
    rig_clip = {
        "id": "anim-transform-bird-flap", "type": "transform", "loop": True,
        "keyframes": [
            {"time_ms": 0, "parts": {"wing_l": {"rotation": [0.0, 0.0, 0.0]}, "wing_r": {"rotation": [0.0, 0.0, 0.0]}}},
            {"time_ms": 1000, "parts": {"wing_l": {"rotation": [0.0, 0.0, 2.0]}}},
        ],
    }
    check(
        "sample_transform_clip samples wing_l's own track at the midpoint",
        sample_transform_clip(rig_clip, 500.0, part_id="wing_l")["rotation"] == [0.0, 0.0, 1.0],
    )
    check(
        "sample_transform_clip holds wing_r at its only keyframe (not present at time_ms=1000)",
        sample_transform_clip(rig_clip, 1000.0, part_id="wing_r")["rotation"] == [0.0, 0.0, 0.0],
    )
    check(
        "sample_transform_clip returns {} for a part_id no keyframe names",
        sample_transform_clip(rig_clip, 500.0, part_id="tail") == {},
    )
    flat_clip = {
        "id": "anim-transform-charm-spin", "type": "transform", "loop": True,
        "keyframes": [{"time_ms": 0, "rotation": [0, 0, 0]}, {"time_ms": 1000, "rotation": [0, 2.0, 0]}],
    }
    check(
        "sample_transform_clip ignores part_id for a plain flat clip (backward compatible)",
        sample_transform_clip(flat_clip, 500.0, part_id="whatever")["rotation"] == [0.0, 1.0, 0.0],
    )

    # --- cubic_bezier_ease / resolve_easing (per direct request: "edit
    # the transition formula for each part in a keyframe" -> "I'd
    # rather expose a more flexible curve" than a fixed named set) ---
    check("resolve_easing defaults to a straight line when absent", resolve_easing({}) == DEFAULT_EASING)
    check(
        "resolve_easing reads a well-formed easing field",
        resolve_easing({"easing": [0.1, 0.2, 0.3, 0.4]}) == (0.1, 0.2, 0.3, 0.4),
    )
    check("resolve_easing falls back to default for a malformed field", resolve_easing({"easing": "nonsense"}) == DEFAULT_EASING)
    check("resolve_easing falls back to default for the wrong length", resolve_easing({"easing": [0.1, 0.2]}) == DEFAULT_EASING)

    check("cubic_bezier_ease(0, ...) is always exactly 0.0 regardless of curve", cubic_bezier_ease(0.0, 0.9, 0.1, 0.1, 0.9) == 0.0)
    check("cubic_bezier_ease(1, ...) is always exactly 1.0 regardless of curve", cubic_bezier_ease(1.0, 0.9, 0.1, 0.1, 0.9) == 1.0)
    check(
        "cubic_bezier_ease with linear control points (0,0,1,1) reduces to plain t (no curve at all)",
        abs(cubic_bezier_ease(0.37, 0.0, 0.0, 1.0, 1.0) - 0.37) < 1e-6,
    )
    check(
        "cubic_bezier_ease's standard CSS ease-in-out curve is symmetric -- exactly 0.5 at t=0.5",
        abs(cubic_bezier_ease(0.5, 0.42, 0.0, 0.58, 1.0) - 0.5) < 1e-6,
    )
    check(
        "cubic_bezier_ease's ease-in curve (slow start) is behind linear at the midpoint",
        cubic_bezier_ease(0.5, 0.42, 0.0, 1.0, 1.0) < 0.5,
    )
    check(
        "cubic_bezier_ease's ease-out curve (fast start) is ahead of linear at the midpoint",
        cubic_bezier_ease(0.5, 0.0, 0.0, 0.58, 1.0) > 0.5,
    )
    check(
        "cubic_bezier_ease allows an overshoot/back curve -- y briefly exceeds 1.0 mid-transition",
        max(cubic_bezier_ease(t / 20, 0.2, 1.6, 0.8, 1.0) for t in range(21)) > 1.0,
    )

    eased_clip = {
        "id": "anim-transform-eased", "type": "transform", "loop": False,
        "keyframes": [
            {"time_ms": 0, "position": [0.0, 0.0, 0.0]},
            {"time_ms": 1000, "position": [10.0, 0.0, 0.0], "easing": [0.42, 0.0, 1.0, 1.0]},
        ],
    }
    check(
        "sample_transform_clip actually applies a keyframe's own easing curve, not just raw linear t",
        sample_transform_clip(eased_clip, 500.0)["position"][0] < 5.0,
    )
    linear_clip = {**eased_clip, "keyframes": [eased_clip["keyframes"][0], {**eased_clip["keyframes"][1]}]}
    del linear_clip["keyframes"][1]["easing"]
    check(
        "sample_transform_clip is plain linear at the midpoint when no easing is authored (unchanged old behavior)",
        abs(sample_transform_clip(linear_clip, 500.0)["position"][0] - 5.0) < 1e-6,
    )
    check(
        "sample_transform_clip's easing has no effect outside the clip's own time range (still holds exactly at the endpoint)",
        sample_transform_clip(eased_clip, 5000.0)["position"] == [10.0, 0.0, 0.0],
    )

    # --- keyframe_preview_reach / position_drag_speed (real reported
    # bug: "I'm applying transformations to parts in the animation but
    # the mesh render is not updating" -- a ~0.13-unit bird's l_wing was
    # posed to position [0, 50, 2] by a real authored keyframe and was
    # actually rendering correctly, just ~240x past the edge of the
    # camera's tightly auto-fitted view frustum) ---
    check(
        "keyframe_preview_reach is 0.0 (a no-op via max()) for no keyframe",
        keyframe_preview_reach(None, base_radius=0.13) == 0.0,
    )
    check(
        "keyframe_preview_reach is 0.0 for a keyframe with no parts assigned",
        keyframe_preview_reach({"time_ms": 0, "parts": {}}, base_radius=0.13) == 0.0,
    )
    reach = keyframe_preview_reach(
        {"time_ms": 0, "parts": {"l_wing": {"position": [0.0, 50.0, 2.0], "scale": [1.0, 4.9, 4.6]}}},
        base_radius=0.13,
    )
    check(
        "keyframe_preview_reach captures the real flap clip's actual far-flung position (~50 units, not the ~0.13-unit rest radius)",
        reach > 49.0,
    )
    check(
        "keyframe_preview_reach picks the largest scale component to widen the reach, not just position magnitude",
        keyframe_preview_reach({"time_ms": 0, "parts": {"p": {"position": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 10.0]}}}, base_radius=1.0) == 10.0,
    )
    check(
        "position_drag_speed scales down for a tiny entity (a bird, not the old fixed 0.01/px)",
        position_drag_speed(0.13) < 0.01,
    )
    check(
        "position_drag_speed never drops to (near) zero for a vanishingly small entity",
        position_drag_speed(0.0) >= 0.0005,
    )
    check(
        "position_drag_speed scales up for a large, old-scale entity",
        position_drag_speed(200.0) > 0.01,
    )

    # --- advance_timeline_playback_ms / sample_part_pose (real reported
    # bug: "unpausing does not start the playback" -- state.paused used
    # to only gate the unrelated runtime animation_id clock, never the
    # Animation Editor's own static per-keyframe preview, so nothing
    # ever actually played) ---
    check(
        "advance_timeline_playback_ms wraps modulo duration when looping",
        advance_timeline_playback_ms(900.0, 300.0, 1000.0, loop=True) == 200.0,
    )
    check(
        "advance_timeline_playback_ms clamps to duration when not looping (holds the last pose)",
        advance_timeline_playback_ms(900.0, 300.0, 1000.0, loop=False) == 1000.0,
    )
    check(
        "advance_timeline_playback_ms doesn't wrap/clamp when nothing to wrap against (duration <= 0)",
        advance_timeline_playback_ms(50.0, 16.0, 0.0, loop=True) == 66.0,
    )
    check(
        "advance_timeline_playback_ms handles an exact-boundary advance correctly",
        advance_timeline_playback_ms(0.0, 1000.0, 1000.0, loop=True) == 0.0,
    )

    rig_clip_for_playback = {
        "id": "anim-transform-playback-check", "type": "transform", "loop": True,
        "keyframes": [
            {"time_ms": 0, "parts": {"wing": {"position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0]}}},
            {"time_ms": 1000, "parts": {"wing": {"position": [0.0, 0.0, 0.0], "rotation": [0.0, 1.0, 0.0]}}},
        ],
    }
    midpoint_pose = sample_part_pose(rig_clip_for_playback, "wing", 500.0)
    check(
        "sample_part_pose samples the clip's mid-playback rotation correctly",
        midpoint_pose["rotation"] == [0.0, 0.5, 0.0],
    )
    check(
        "sample_part_pose fills in scale as identity when the clip never defines it",
        midpoint_pose["scale"] == [1.0, 1.0, 1.0],
    )
    no_track_pose = sample_part_pose(rig_clip_for_playback, "tail", 500.0, fallback_local_offset={"position": [9.0, 9.0, 9.0]})
    check(
        "sample_part_pose falls back to the part's own localOffset for a part_id the clip doesn't track at all",
        no_track_pose == {"position": [9.0, 9.0, 9.0], "rotation": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0], "origin": [0.0, 0.0, 0.0]},
    )

    # --- origin/pivot point, per direct request ("expand the animation
    # editor to allow setting an origin point to apply the animation
    # transformation from") ---
    clip_with_origin = {**rig_clip_for_playback, "origins": {"wing": [0.5, 0.25, 0.0]}}
    origin_pose = sample_part_pose(clip_with_origin, "wing", 500.0)
    check(
        "sample_part_pose carries the clip's own origins entry through for a matching part_id",
        origin_pose["origin"] == [0.5, 0.25, 0.0],
    )
    check(
        "sample_part_pose falls back to the part's own localOffset origin when the clip defines none",
        sample_part_pose(rig_clip_for_playback, "wing", 500.0, fallback_local_offset={"origin": [1.0, 2.0, 3.0]})["origin"] == [1.0, 2.0, 3.0],
    )
    check(
        "sample_transform_clip attaches origin alongside the interpolated fields",
        sample_transform_clip(clip_with_origin, 500.0, part_id="wing").get("origin") == [0.5, 0.25, 0.0],
    )
    check(
        "sample_transform_clip omits origin for a part_id the clip's origins map doesn't name",
        "origin" not in sample_transform_clip(clip_with_origin, 500.0, part_id="tail-not-in-clip-at-all"),
    )

    origin_preview_parts = [{"id": "wing", "mesh": "mesh-example-staff-shaft"}]
    origin_kf = {"time_ms": 0, "parts": {"wing": {"position": [1.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0]}}}
    previewed = apply_keyframe_preview(origin_preview_parts, origin_kf, origins={"wing": [0.5, 0.0, 0.0]})
    check(
        "apply_keyframe_preview writes the clip's origin into the previewed part's localOffset",
        previewed[0]["localOffset"]["origin"] == [0.5, 0.0, 0.0],
    )
    check(
        "apply_keyframe_preview omits origin when the clip's origins map has nothing for this part",
        "origin" not in apply_keyframe_preview(origin_preview_parts, origin_kf, origins={})[0]["localOffset"],
    )

    check(
        "mat4.compose_with_pivot with pivot=[0,0,0] matches plain compose() exactly",
        compose_with_pivot([1.0, 2.0, 3.0], [0.0, 0.5, 0.0], [1.0, 1.0, 1.0], [0.0, 0.0, 0.0])
        == compose([1.0, 2.0, 3.0], [0.0, 0.5, 0.0], [1.0, 1.0, 1.0]),
    )
    # A 180-degree spin (pi radians) around Y, pivoting at [1, 0, 0] with
    # no additional position offset, must land the pivot's own point back
    # on itself and send local-space origin (0,0,0) to [2, 0, 0] -- basic
    # "rotate a point 180 degrees about an off-center pivot" geometry,
    # confirming the pivot -- not the mesh's own local origin -- is what
    # actually gets rotated around.
    spin_pivot = compose_with_pivot([0.0, 0.0, 0.0], [0.0, math.pi, 0.0], [1.0, 1.0, 1.0], [1.0, 0.0, 0.0])
    origin_after_spin = [spin_pivot[12], spin_pivot[13], spin_pivot[14]]
    check(
        "mat4.compose_with_pivot actually rotates around the pivot, not the local origin",
        abs(origin_after_spin[0] - 2.0) < 1e-9 and abs(origin_after_spin[1]) < 1e-9 and abs(origin_after_spin[2]) < 1e-9,
    )

    # --- mesh_bounding_radius / entity_bounding_radius (camera auto-fit) ---
    # Real reported bug: the orbit camera's fixed ~200-unit default
    # radius (this engine's old pixel-tile-scale legacy) made a
    # realistically-scaled "1 unit = 1 meter" model render correctly
    # but be effectively invisible -- far too small on screen to see.
    # These lock in the fix's core measurement against real fixtures at
    # two very different native scales.
    crate_radius = mesh_bounding_radius("mesh-example-crate")
    check("mesh_bounding_radius measures the real crate mesh (old pixel-tile scale)", crate_radius > 10.0)
    check("mesh_bounding_radius returns 0.0 for an unregistered mesh id", mesh_bounding_radius("no-such-mesh") == 0.0)
    check("mesh_bounding_radius returns 0.0 for None", mesh_bounding_radius(None) == 0.0)
    check(
        "entity_bounding_radius falls back to its default when no part has a mesh yet",
        entity_bounding_radius([{"id": "a", "mesh": None}]) == 50.0,
    )
    check(
        "entity_bounding_radius picks up a real assigned mesh",
        entity_bounding_radius([{"id": "a", "mesh": "mesh-example-crate"}]) == crate_radius,
    )

    # --- OrbitCamera zoom (shared with asset_preview.py) -- fixes a real
    # reported bug: the old fixed 20.0-2000.0 clamp meant a camera
    # auto-fit to a small (<1.0) radius for meter-scale content snapped
    # up to 20.0 on the very first scroll and could never zoom back in.
    cam = OrbitCamera(radius=0.5)
    cam._on_wheel({"dy": -100.0})
    check("OrbitCamera zoom-in from a small radius doesn't snap to the old 20.0 floor", cam.radius < 1.0)
    for _ in range(30):
        cam._on_wheel({"dy": -100.0})
    check("OrbitCamera can zoom in far below the old hardcoded floor", cam.radius < 0.1)
    for _ in range(50):
        cam._on_wheel({"dy": 100.0})
    check(
        "OrbitCamera can zoom back out again after zooming in close (the actual reported bug)",
        cam.radius > 1.0,
    )

    # --- OrbitCamera invert_yaw (per direct request: flip entity_builder
    # .py's left/right drag-pan direction only -- asset_preview.py's
    # camera, constructed with no args, must keep its original feel) ---
    cam_default = OrbitCamera()
    cam_default._dragging = True
    cam_default._last_x, cam_default._last_y = 0.0, 0.0
    default_start_yaw = cam_default.yaw
    cam_default._on_pointer_move({"x": 10.0, "y": 0.0})
    default_delta = cam_default.yaw - default_start_yaw

    cam_inverted = OrbitCamera(invert_yaw=True)
    cam_inverted._dragging = True
    cam_inverted._last_x, cam_inverted._last_y = 0.0, 0.0
    inverted_start_yaw = cam_inverted.yaw
    cam_inverted._on_pointer_move({"x": 10.0, "y": 0.0})
    inverted_delta = cam_inverted.yaw - inverted_start_yaw

    check("OrbitCamera default (asset_preview.py) yaw direction unaffected by invert_yaw", default_delta != 0.0)
    check(
        "OrbitCamera invert_yaw=True (entity_builder.py) flips the same drag to the opposite yaw direction",
        inverted_delta == -default_delta,
    )

    # --- material_id_field_for_asset / asset_id_for_material_id_field round-trip ---
    materials = asset_loader.list_category("materials")
    check("real manifest has at least one material to test against", len(materials) > 0)
    if materials:
        asset_id = next(iter(materials))
        field = material_id_field_for_asset(asset_id)
        check(
            f"material_id_field_for_asset('{asset_id}') strips the 'assets/data/' prefix",
            field is not None and not field.startswith("assets/data/"),
        )
        round_tripped = asset_id_for_material_id_field(field)
        check(
            "asset_id_for_material_id_field round-trips back to the same asset id",
            round_tripped == asset_id,
        )
    check(
        "material_id_field_for_asset returns None for an unknown asset id",
        material_id_field_for_asset("no-such-material") is None,
    )
    check(
        "asset_id_for_material_id_field returns None for None/empty input",
        asset_id_for_material_id_field(None) is None and asset_id_for_material_id_field("") is None,
    )

    # --- save/load round-trip (real filesystem write, via the same
    # area_io.save_entity_definition()/load_entity_definition() the
    # Save Entity panel calls) -- uses a scratch id, cleaned up after.
    scratch_path = ENTITY_DIR / f"entity-{_SCRATCH_ENTITY_ID}.json"
    try:
        built_parts = [
            {"id": "root", "mesh": "mesh-example-staff-shaft"},
            {
                "id": "charm",
                "mesh": "mesh-example-staff-charm",
                "attachTo": {"part": "root", "socket": "charm_socket"},
                "animation_id": "anim-transform-charm-spin",
            },
        ]
        save_entity_definition({"parts": built_parts}, _SCRATCH_ENTITY_ID)
        reloaded = load_entity_definition(_SCRATCH_ENTITY_ID)
        check("save_entity_definition/load_entity_definition round-trip the parts list", reloaded is not None and reloaded.get("parts") == built_parts)
        check(
            "save_entity_definition stamps a correct, matching 'id' field",
            reloaded is not None and reloaded.get("id") == f"entity-{_SCRATCH_ENTITY_ID}",
        )

        # --- normalize_entity_id / the real reported bug: a manifest-
        # derived id (e.g. from the launcher's "Edit" button) is the
        # "entity-<id>" *prefixed* form, not the bare form "Save As"
        # produces -- feeding it back into save/load must not double
        # the prefix, and must not silently fail to find the real file.
        check("normalize_entity_id strips an existing 'entity-' prefix", normalize_entity_id(f"entity-{_SCRATCH_ENTITY_ID}") == _SCRATCH_ENTITY_ID)
        check("normalize_entity_id passes a bare id through unchanged", normalize_entity_id(_SCRATCH_ENTITY_ID) == _SCRATCH_ENTITY_ID)

        prefixed_id = f"entity-{_SCRATCH_ENTITY_ID}"
        reloaded_via_prefixed = load_entity_definition(prefixed_id)
        check(
            "load_entity_definition finds the real file when given the prefixed id (the actual reported failure)",
            reloaded_via_prefixed is not None and reloaded_via_prefixed.get("parts") == built_parts,
        )

        double_prefixed_path = ENTITY_DIR / f"entity-entity-{_SCRATCH_ENTITY_ID}.json"
        save_entity_definition({"parts": built_parts}, prefixed_id)
        check(
            "re-saving with the prefixed id does not create a double-prefixed file",
            not double_prefixed_path.exists(),
        )
        check("re-saving with the prefixed id overwrites the same original file", scratch_path.exists())
    finally:
        if scratch_path.exists():
            scratch_path.unlink()
        double_prefixed_path = ENTITY_DIR / f"entity-entity-{_SCRATCH_ENTITY_ID}.json"
        if double_prefixed_path.exists():
            double_prefixed_path.unlink()

    # --- _save_animation_editor's entity auto-save-on-stamp (real
    # reported bug: "flap" animation's clip file was correctly written
    # and its part correctly stamped in memory, but entity-bird.json on
    # disk never got that stamp because only a separate File > Save
    # persisted the entity -- that step was never taken, so the next
    # reload silently lost the wiring even though the clip was still on
    # disk and in the manifest). Per direct decision, Save in the
    # Animation Editor now also persists the entity immediately when it
    # stamps a part -- verified here end-to-end, not just the in-memory
    # stamp already covered by stamp_animation_id_for_assigned_parts above.
    from client.engine.entity_builder import (
        BuilderState,
        _open_animation_editor,
        _save_animation_editor,
    )
    from client.engine.scene import Scene

    autosave_entity_id = "_run_entity_builder_test_autosave_entity"
    autosave_entity_path = ENTITY_DIR / f"entity-{autosave_entity_id}.json"
    autosave_clip_path = new_animation_clip_path("_run_entity_builder_test_autosave_clip")
    autosave_clip_id = new_animation_clip_id("_run_entity_builder_test_autosave_clip")
    try:
        save_entity_definition({"parts": [{"id": "wing", "mesh": "mesh-example-staff-shaft"}]}, autosave_entity_id)

        autosave_clip_path.parent.mkdir(parents=True, exist_ok=True)
        autosave_clip_path.write_text(json.dumps(new_animation_clip(autosave_clip_id), indent=2) + "\n", encoding="utf-8")
        refresh_manifest()
        asset_loader.load_manifest()

        scene = Scene()
        state = BuilderState(autosave_entity_id, list(load_entity_definition(autosave_entity_id)["parts"]))
        _open_animation_editor(scene, state, autosave_clip_id)
        keyframes = state.animation_editor_clip["keyframes"]
        add_keyframe(keyframes)
        assign_part_to_keyframe(keyframes[0], "wing", {"position": [1, 2, 3], "rotation": [0, 0, 0], "scale": [1, 1, 1]})

        before = load_entity_definition(autosave_entity_id)
        check(
            "before Save, the on-disk entity file has no animation_id yet (only state.parts in memory does)",
            before["parts"][0].get("animation_id") is None,
        )

        _save_animation_editor(scene, state)

        after = load_entity_definition(autosave_entity_id)
        check(
            "Save in the Animation Editor persists the stamped animation_id to the entity file itself, not just state.parts (the actual reported bug)",
            after["parts"][0].get("animation_id") == autosave_clip_id,
        )
    finally:
        if autosave_entity_path.exists():
            autosave_entity_path.unlink()
        if autosave_clip_path.exists():
            autosave_clip_path.unlink()

    # --- convert_mesh.py's id/name derivation (real bug: used to
    # derive from the *source* file's stem instead of the caller's
    # chosen output filename -- confirmed as the exact cause of the
    # real mesh-bird.json/mesh-body.json id collision already in the
    # asset tree, both converted from a source file literally named
    # body.glb into two different output names but both stamped
    # "id": "mesh-body") ---
    import tempfile

    source_glb = Path("frontend/assets/pending/models/bird/body.glb")
    if source_glb.exists():
        with tempfile.TemporaryDirectory() as tmp_dir:
            mismatched_output = Path(tmp_dir) / "mesh-totally-different-name.json"
            convert_mesh.convert(str(source_glb), str(mismatched_output))
            converted = json.loads(mismatched_output.read_text(encoding="utf-8"))
            check(
                "convert_mesh.convert derives id from the output filename, not the source file's name (the actual reported collision's root cause)",
                converted["id"] == "mesh-totally-different-name",
            )
            check(
                "convert_mesh.convert derives name from the same output filename, with the 'mesh-' prefix stripped",
                converted["name"] == "totally-different-name",
            )
    else:
        check("convert_mesh.convert id/name derivation (skipped -- source fixture missing)", True)

    # --- launcher.py's _rename_asset / _current_display_name (per
    # direct request: "make it trivial to rename parts, meshes or
    # entities without it breaking relations") -- the old version of
    # this function rewrote the id/filename/manifest key; the new one
    # only ever touches "name", so nothing referencing this asset by
    # id can be affected by a rename ---
    rename_test_id = "mesh-_run_entity_builder_test_rename_scratch"
    rename_test_path = MESH_DIR / f"{rename_test_id}.json"
    try:
        rename_test_path.parent.mkdir(parents=True, exist_ok=True)
        rename_test_path.write_text(
            json.dumps({"id": rename_test_id, "name": "original name", "vertices": [], "indices": []}, indent=2),
            encoding="utf-8",
        )
        asset_loader.register(rename_test_id, f"assets/data/mesh/{rename_test_id}.json")

        check(
            "_current_display_name reads the asset's real current name",
            _current_display_name(rename_test_id) == "original name",
        )

        error = _rename_asset("meshes", rename_test_id, "")
        check("_rename_asset rejects an empty name", error is not None)

        error = _rename_asset("meshes", rename_test_id, "renamed display name")
        check("_rename_asset succeeds renaming a real asset's display name", error is None)

        after_rename = json.loads(rename_test_path.read_text(encoding="utf-8"))
        check("_rename_asset writes the new name to the file", after_rename.get("name") == "renamed display name")
        check(
            "_rename_asset never touches the id -- the frozen reference every other file points at",
            after_rename.get("id") == rename_test_id,
        )
        check(
            "_rename_asset never renames the file on disk (the same path still resolves through asset_loader)",
            asset_loader.resolve(rename_test_id) == f"assets/data/mesh/{rename_test_id}.json",
        )
        check(
            "_current_display_name reflects the freshly-renamed name on a second read",
            _current_display_name(rename_test_id) == "renamed display name",
        )
    finally:
        if rename_test_path.exists():
            rename_test_path.unlink()
        asset_loader.remove_entry("meshes", rename_test_id)

    # --- launcher.py's filtered_sorted_entity_ids_by_name (per direct
    # request: "have the entity list display the entities by their
    # name, rather than ID") -- sorts/filters by display name, not id,
    # since id is now frozen at creation and no longer tracks a
    # renamed entity's alphabetical position ---
    sort_test_ids = [
        "entity-_run_entity_builder_test_sort_a",
        "entity-_run_entity_builder_test_sort_b",
        "entity-_run_entity_builder_test_sort_c",
    ]
    sort_test_names = {
        sort_test_ids[0]: "Zebra",
        sort_test_ids[1]: "apple",
        sort_test_ids[2]: "Mango",
    }
    sort_test_paths = [ENTITY_DIR / f"{entity_id}.json" for entity_id in sort_test_ids]
    try:
        ENTITY_DIR.mkdir(parents=True, exist_ok=True)
        for entity_id, path in zip(sort_test_ids, sort_test_paths):
            path.write_text(
                json.dumps({"id": entity_id, "name": sort_test_names[entity_id], "parts": []}, indent=2),
                encoding="utf-8",
            )
            asset_loader.register(entity_id, f"assets/data/entity/{entity_id}.json")

        fake_entries = {entity_id: {} for entity_id in sort_test_ids}

        pairs = filtered_sorted_entity_ids_by_name(fake_entries, "")
        pairs = [pair for pair in pairs if pair[0] in sort_test_ids]
        check(
            "filtered_sorted_entity_ids_by_name sorts by display name (case-insensitive), not id",
            [pair[1] for pair in pairs] == ["apple", "Mango", "Zebra"],
        )

        filtered = filtered_sorted_entity_ids_by_name(fake_entries, "man")
        filtered = [pair for pair in filtered if pair[0] in sort_test_ids]
        check(
            "filtered_sorted_entity_ids_by_name filters by display name (substring, case-insensitive)",
            filtered == [(sort_test_ids[2], "Mango")],
        )

        filtered_by_id = filtered_sorted_entity_ids_by_name(fake_entries, "sort_a")
        filtered_by_id = [pair for pair in filtered_by_id if pair[0] in sort_test_ids]
        check(
            "filtered_sorted_entity_ids_by_name also matches against the id (for anyone searching by habit)",
            filtered_by_id == [(sort_test_ids[0], "Zebra")],
        )

        # Rename "Zebra" to "aardvark" -- it should now sort first,
        # proving sort tracks the live name, not a stale snapshot.
        renamed_path = sort_test_paths[0]
        renamed_path.write_text(
            json.dumps({"id": sort_test_ids[0], "name": "aardvark", "parts": []}, indent=2),
            encoding="utf-8",
        )
        pairs_after_rename = filtered_sorted_entity_ids_by_name(fake_entries, "")
        pairs_after_rename = [pair for pair in pairs_after_rename if pair[0] in sort_test_ids]
        check(
            "filtered_sorted_entity_ids_by_name re-sorts a renamed entity by its new name, not its old one",
            [pair[1] for pair in pairs_after_rename] == ["aardvark", "apple", "Mango"],
        )
    finally:
        for path in sort_test_paths:
            if path.exists():
                path.unlink()
        for entity_id in sort_test_ids:
            asset_loader.remove_entry("entities", entity_id)

    print()
    if _FAILURES:
        print(f"{len(_FAILURES)} FAILURE(S):")
        for label in _FAILURES:
            print(f"  - {label}")
        sys.exit(1)
    print("All entity_builder data-model checks passed.")


if __name__ == "__main__":
    main()
