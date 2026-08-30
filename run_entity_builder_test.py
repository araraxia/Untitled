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
import sys

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
    animations_used_by_parts,
    apply_keyframe_preview,
    assign_part_to_keyframe,
    asset_id_for_material_id_field,
    default_keyframe_transform,
    entity_bounding_radius,
    find_unattached_part_for_mesh,
    keyframe_gap,
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
    read_mesh_sockets,
    remove_keyframe,
    remove_part,
    remove_part_from_keyframe,
    set_keyframe_gap,
    stamp_animation_id_for_assigned_parts,
    suggest_socket_match,
    unique_part_id,
    validate_new_part_id,
)
from client.engine.orbit_camera import OrbitCamera
from client.engine.transform_clip import sample_transform_clip

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

    # --- validate_new_part_id ---
    existing = [{"id": "body"}, {"id": "wing_l"}]
    check("validate_new_part_id rejects empty id", validate_new_part_id("", existing) is not None)
    check("validate_new_part_id rejects a duplicate id", validate_new_part_id("body", existing) is not None)
    check("validate_new_part_id accepts a fresh id", validate_new_part_id("wing_r", existing) is None)

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

    print()
    if _FAILURES:
        print(f"{len(_FAILURES)} FAILURE(S):")
        for label in _FAILURES:
            print(f"  - {label}")
        sys.exit(1)
    print("All entity_builder data-model checks passed.")


if __name__ == "__main__":
    main()
