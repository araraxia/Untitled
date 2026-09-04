"""Entity Builder -- assembles rigid-part-hierarchy entity definitions
from Blender exports. Steps 3-10 of .github/prompts/entity-builder.prompt.md.

Houses the Blender-export conversion scripts (tools/convert_mesh.py,
tools/convert_animation.py, tools/pack_param_map.py -- called in-process,
never via subprocess) behind one launcher-reachable window: import a
mesh/animation export, add/remove parts, wire attachTo/socket references
(validated against a parent part's real, loaded sockets -- never free
text), scaffold a root mesh's sockets into a suggested parts list,
assign materials, and preview the live result with an orbit camera.

Deliberately NOT built by extending asset_preview.py in place -- that
module is explicitly read-only (see its own docstring) -- or by adding
a fourth mode to area_viewer.py, which is already large and mixes in
Area/zone concerns this tool has no use for. Shared code
(`OrbitCamera`, the per-part `dangle`/`localOffset`/`animation_id`/
`action_animations` editing widgets) is imported from
`orbit_camera.py`/`entity_template_editing.py`, not duplicated.

Top/bottom menu bars (`_draw_menu_bar`/`_draw_bottom_bar`, F11 to
toggle the top one) mirror area_viewer.py's own of the same name --
same File/View shape (plus a "Parts" menu for Parts-related actions --
currently just Scaffold), same "Save/Save As fold into File menu"
pattern, same always-on-foreground-draw-list bottom strip. This tool
has no Edit menu/undo stack, unlike area_viewer.py: template edits here
are buffer-then-explicit-save, not undo-tracked (see entity-builder
.prompt.md's own note on this). The Parts list itself and Materials
both live as tabs in the right-side sidebar, not their own windows --
see `_SIDEBAR_TABS`.

Animation editing splits across two windows, per direct request:
`_draw_timeline_window` (full width, docked just above the bottom bar)
owns the keyframe strip itself -- add/select/loop -- while
`_draw_animation_editor_window` (a normal floating window) shows only
whichever keyframe is currently selected there. Both share one
visibility gate (`_timeline_visible`), so they always appear and
disappear together; `_draw_sidebar` reads that same gate to shrink its
own height and avoid sitting underneath the full-width Timeline.

Forward-looking note, not built in this pass (Step 11 of the prompt
file): a live in-editor param-map channel painter (paint roughness/
emission/palette/alpha directly on the mesh preview) would remove the
current external-image-editor round-trip, but is a materially larger
scope -- effectively a small raster editor with brush strokes written
into an in-memory buffer, live-uploaded to the preview texture, and
only written to disk (via the same pack_param_map.pack() call this
file's Materials panel already uses) on an explicit save. If ever
undertaken, it should still bottom out in the same material-<id>.json/
<id>_params.png files the Materials panel below produces -- a painting
UI is a different way to *produce* the four channel images, not a
different material format. UV-space painting (projected onto each
part's actual mesh UVs) is materially harder than screen-space
painting and would need its own scoping pass, not be assumed. This
file's plain "pick existing images, pack, save" flow remains useful
even after a painting surface exists -- not every texture originates
from in-tool painting.
"""

import contextlib
import io
import json
import math
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.independant_logger import Logger

logger = Logger(
    log_name="entity_builder",
    log_file="entity_builder.log",
    log_level=20,
).get_logger()

import glfw
from imgui_bundle import imgui
from wgpu.utils.imgui import ImguiRenderer

from client.engine import imgui_wgpu_compat  # noqa: F401
from client.engine import interpolation, renderer, transform_clip
from client.engine.area_io import (
    ENTITY_DIR,
    load_entity_definition,
    normalize_entity_id,
    refresh_manifest,
    save_entity_definition,
)
from client.engine.asset_loader import asset_loader
from client.engine.entity_template_editing import default_part_buffer, draw_part_fields
from client.engine.orbit_camera import OrbitCamera
from client.engine.scene import Scene

import client.main as client_main

# tools/*.py aren't a package (no tools/__init__.py) -- same sys.path
# trick area_io.py already uses for tools/build_manifest.py.
_TOOLS_DIR = str(REPO_ROOT / "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import convert_animation  # noqa: E402 -- must follow the sys.path insert above
import convert_mesh  # noqa: E402
import pack_param_map  # noqa: E402
import split_glb  # noqa: E402

FRONTEND_DIR = REPO_ROOT / "frontend"
PENDING_DIR = FRONTEND_DIR / "assets" / "pending"
PENDING_MODELS_DIR = PENDING_DIR / "models"
PENDING_ANIMATIONS_DIR = PENDING_DIR / "animations"
MESH_DIR = FRONTEND_DIR / "assets" / "data" / "mesh"
ANIMATION_DIR = FRONTEND_DIR / "assets" / "data" / "animation"
MATERIAL_DIR = FRONTEND_DIR / "assets" / "data" / "material"
TEXTURES_DIR = FRONTEND_DIR / "assets" / "images" / "textures"
PARAM_MAPS_DIR = FRONTEND_DIR / "assets" / "images" / "param_maps"

# Scratch entity-definition id the live preview is rewritten into on
# every edit -- same non-manifest-registered "throwaway, reused every
# launch" status asset_preview.py's own _PREVIEW_TEMPLATE_KEY has, kept
# under a different name so the two tools never collide if a future
# change runs them in the same process.
_BUILDER_SCRATCH_ID = "_entity_builder_tmp"
_PREVIEW_ENTITY_ID = "preview"


# ---------------------------------------------------------------------
# Pure data helpers -- no imgui/GPU, headlessly testable
# (run_entity_builder_test.py, Step 12).
# ---------------------------------------------------------------------


def read_mesh_sockets(mesh_asset_id: "str | None") -> "list[str]":
    """Socket names a mesh asset defines, read straight off its JSON
    file -- deliberately not via a live `Mesh`/GPU device (Mesh.load()
    couples socket parsing to GPU buffer upload; this only needs the
    names, and needs to work before a GPU mesh object necessarily
    exists for this particular part, e.g. while scaffolding suggestions
    for parts that aren't added yet).
    """
    if not mesh_asset_id or not asset_loader.has(mesh_asset_id):
        return []
    path = FRONTEND_DIR / asset_loader.resolve(mesh_asset_id)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [s["name"] for s in data.get("sockets", []) if s.get("name")]


def read_mesh_name(mesh_asset_id: "str | None") -> "str | None":
    """A mesh asset's own `"name"` field, read straight off its JSON
    file (same no-GPU-needed approach as `read_mesh_sockets`) -- `None`
    if the mesh can't be resolved/read or has no `"name"` field (an
    older mesh converted before `tools/convert_mesh.py`'s id/name
    derivation bug was fixed). Used to give a freshly-auto-added part a
    sensible display name matching its mesh's own, per direct request
    ("make it trivial to rename parts... without it breaking relations").
    """
    if not mesh_asset_id or not asset_loader.has(mesh_asset_id):
        return None
    path = FRONTEND_DIR / asset_loader.resolve(mesh_asset_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    name = data.get("name")
    return name if isinstance(name, str) and name else None


def mesh_bounding_radius(mesh_asset_id: "str | None") -> float:
    """Max distance from local-space origin across a mesh's vertices --
    a cheap, order-of-magnitude "how big is this thing" estimate (not a
    true bounding sphere), read straight off the mesh JSON, same
    no-GPU-needed approach as read_mesh_sockets(). 0.0 if the mesh
    can't be resolved/read or has no vertices.
    """
    if not mesh_asset_id or not asset_loader.has(mesh_asset_id):
        return 0.0
    path = FRONTEND_DIR / asset_loader.resolve(mesh_asset_id)
    if not path.exists():
        return 0.0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0.0
    max_dist = 0.0
    for v in data.get("vertices", []):
        pos = v.get("pos", [0.0, 0.0, 0.0])
        dist = math.sqrt(pos[0] ** 2 + pos[1] ** 2 + pos[2] ** 2)
        if dist > max_dist:
            max_dist = dist
    return max_dist


def entity_bounding_radius(parts: "list[dict]", default: float = 50.0) -> float:
    """Overall bounding radius across every part's mesh (each mesh's
    own local-space extent, not composed through attachTo/socket
    transforms -- an approximation, but a large improvement over a
    single fixed constant for content authored at a very different
    scale than this engine's legacy defaults). Falls back to *default*
    when no part has a mesh assigned yet, so a fresh/empty entity still
    gets a sane starting camera distance.

    Fixes a real reported bug: the preview's orbit camera defaulted to
    a fixed ~200-unit radius (OrbitCamera's own default, inherited from
    this engine's old pixel-tile-scale content -- MOVE_SPEED=200, a
    64-unit crate mesh, etc.). A realistically-scaled "1 unit = 1
    meter" model (e.g. a ~0.3m bird) rendered correctly but was
    effectively invisible at that distance -- far too small on screen
    to see, indistinguishable from "nothing is rendering."
    """
    radii = [r for r in (mesh_bounding_radius(p.get("mesh")) for p in parts if p.get("mesh")) if r > 0]
    return max(radii) if radii else default


def keyframe_preview_reach(keyframe: "dict | None", base_radius: float) -> float:
    """How far the currently-previewed keyframe's posed parts extend
    from the origin -- widens the auto-fit camera (see
    _sync_preview_definition) so a keyframe transform that moves a part
    far from its rest position doesn't silently exceed the camera's
    tightly-zoomed view frustum while still rendering correctly.

    Fixes a real reported bug ("I'm applying transformations to parts
    in the animation but the mesh render is not updating"): a bird
    measuring ~0.13 units across (entity_bounding_radius) auto-fits the
    orbit camera to sit only ~0.5 units away -- a ~0.2-unit-tall visible
    area at 45 degrees FOV. A keyframe posing a part to position
    `[0, 50, 2]` (confirmed against the user's own real `flap` clip) was
    ~240x past the edge of that frame: still being drawn every frame
    with the correct world transform (verified directly against
    `EntityRenderer._draw_mesh_part`'s actual argument), just nowhere
    near visible, indistinguishable from "not updating" to a user
    watching the preview.

    Deliberately approximate, not an exact world-space bound (an exact
    one needs the full attachTo/socket parent chain, which isn't
    available from this pure, headlessly-tested helper) -- each posed
    part's raw local position magnitude plus *base_radius* scaled by
    that part's largest scale component is enough to keep a far-flung
    or dramatically resized pose in frame without needing to reproduce
    entity_renderer.py's full transform composition here. Returns 0.0
    (a no-op when combined with entity_bounding_radius via max()) for
    no keyframe, an empty keyframe, or one with no parts assigned.
    """
    assigned = (keyframe or {}).get("parts") or {}
    if not assigned:
        return 0.0
    reach = 0.0
    for transform in assigned.values():
        position = transform.get("position") or [0.0, 0.0, 0.0]
        distance = math.sqrt(sum(v * v for v in position))
        scale = transform.get("scale") or [1.0, 1.0, 1.0]
        max_scale = max(abs(v) for v in scale) if scale else 1.0
        reach = max(reach, distance + base_radius * max_scale)
    return reach


def position_drag_speed(entity_radius: float) -> float:
    """Drag speed (units per pixel of mouse movement) for the Animation
    Editor's position field, scaled to how physically big the entity
    actually is -- part of the same real reported bug as
    keyframe_preview_reach ("the mesh render is not updating"): a fixed
    0.01-per-pixel speed is coarse enough that, on a ~0.13-unit bird, a
    short drag could fling a part dozens of units away -- correctly
    rendered, just far outside the tightly auto-fitted camera's view.

    Deliberately position-only, not applied to rotation/scale: an
    angle (radians) and a scale multiplier are already unit-independent
    of the entity's physical size, so their existing fixed speed is
    equally sensible at any scale -- only a *position* offset's
    reasonable range is tied to how big the mesh actually is.
    """
    return max(entity_radius * 0.02, 0.0005)


def material_id_field_for_asset(material_asset_id: str) -> "str | None":
    """Map a `"materials"` manifest asset id to the `material_id`
    string a part actually stores (a path fragment appended to
    `"assets/data/"` by entity_renderer.py's `_draw_mesh_part`, e.g.
    `"material/material-example-crate.json"` -- not the manifest asset
    id itself, e.g. `"mat-crate-001"`, which is a different string).
    """
    path = asset_loader.list_category("materials").get(material_asset_id)
    if not path:
        return None
    prefix = "assets/data/"
    return path[len(prefix) :] if path.startswith(prefix) else path


def asset_id_for_material_id_field(material_id_field: "str | None") -> "str | None":
    """Inverse of material_id_field_for_asset() -- given a part's
    stored `material_id`, find which manifest asset id (if any) that
    corresponds to, for pre-selecting a combo box.
    """
    if not material_id_field:
        return None
    for asset_id in asset_loader.list_category("materials"):
        if material_id_field_for_asset(asset_id) == material_id_field:
            return asset_id
    return None


def _words(text: str) -> "set[str]":
    return {w for w in re.split(r"[_\-]+", text.lower()) if w}


def suggest_socket_match(socket_name: str, mesh_ids: "list[str]") -> "str | None":
    """Best-guess a mesh asset id for a socket by naming convention.

    Word-set match, not substring: strip a trailing '_socket', split
    what's left into '_'/'-'-delimited words, and match any mesh id
    whose own word set is a superset of those words -- order-
    independent, so `wing_l_socket` matches a mesh id however its
    words are arranged (`mesh-bird-l_wing`, `mesh-bird-wing_l`, etc.).
    A plain substring check (the first version of this function) fails
    exactly this case: 'wing_l' is not a substring of 'l_wing' even
    though they mean the same thing -- found via a real split-glb
    export (tools/split_glb.py) whose Blender object names happened to
    be side-then-part ('L_Wing'), while this project's socket-naming
    convention is part-then-side ('wing_l_socket').

    Never auto-applied -- the scaffolding panel (Step 6) always shows
    this as an editable, user-confirmed suggestion, never writes
    anything on its own. When multiple mesh ids match, prefers the one
    with the fewest extra words (the tightest match), then
    alphabetical, for a deterministic default.
    """
    needle = socket_name[:-7] if socket_name.endswith("_socket") else socket_name
    needle_words = _words(needle)
    if not needle_words:
        return None
    scored = []
    for mesh_id in mesh_ids:
        mesh_words = _words(mesh_id)
        if needle_words <= mesh_words:
            scored.append((len(mesh_words), mesh_id))
    if not scored:
        return None
    scored.sort()
    return scored[0][1]


def validate_new_part_name(new_name: str) -> "str | None":
    """Return an error message if *new_name* can't be used for a new
    part's display name, else None. Only checks non-empty -- unlike
    the old `validate_new_part_id` this replaces, a duplicate name is
    no longer an error: names aren't unique by design (that's the
    whole point of separating them from the id), and the actual `id`
    a new part gets is independently deduped by `unique_part_id`,
    which can never collide.
    """
    if not new_name or not new_name.strip():
        return "Part name can't be empty."
    return None


def remove_part(parts: "list[dict]", part_id: str) -> "list[str]":
    """Remove the part with id *part_id* and clear any other part's
    `attachTo` that pointed at it. Mutates *parts* in place. Returns
    the ids of any parts that were orphaned (their attachTo cleared) so
    the caller can warn about it.
    """
    orphaned = []
    parts[:] = [p for p in parts if p.get("id") != part_id]
    for p in parts:
        attach_to = p.get("attachTo")
        if attach_to and attach_to.get("part") == part_id:
            del p["attachTo"]
            orphaned.append(p.get("id"))
    return orphaned


def part_attached_to_socket(parts: "list[dict]", parent_id: "str | None", socket_name: str) -> "str | None":
    """Id of the existing part (if any) already attached to
    (parent_id, socket_name), else None. Used by the scaffold panel to
    never offer -- or add -- a second part at a socket that's already
    claimed, whether that existing part arrived from a previous
    scaffold pass or was added/attached by hand. Fixes a real reported
    bug: Add Selected Parts used to only guard against *id* collisions
    (renaming wing_l -> wing_l_2), never against a socket that already
    had a part attached, so re-running it created a second, overlapping
    part at the same socket instead of recognizing it was covered.
    """
    for p in parts:
        attach_to = p.get("attachTo")
        if attach_to and attach_to.get("part") == parent_id and attach_to.get("socket") == socket_name:
            return p.get("id")
    return None


def mesh_id_to_part_id(mesh_id: str) -> str:
    """Strip a mesh asset id's 'mesh-' prefix to get a reasonable
    default part id (e.g. 'mesh-l_wing' -> 'l_wing') -- used when a
    freshly-converted mesh is auto-added as a part.
    """
    return mesh_id[len("mesh-") :] if mesh_id.startswith("mesh-") else mesh_id


def unique_part_id(candidate: str, existing_parts: "list[dict]") -> str:
    """*candidate*, or candidate_2/candidate_3/... on collision -- the
    same dedup rule "Scaffold Parts from Sockets" already used inline,
    shared here so mesh-conversion auto-part-creation follows it too.
    """
    existing_ids = {p.get("id") for p in existing_parts}
    if candidate not in existing_ids:
        return candidate
    suffix = 2
    new_id = f"{candidate}_{suffix}"
    while new_id in existing_ids:
        suffix += 1
        new_id = f"{candidate}_{suffix}"
    return new_id


def meshes_used_by_parts(parts: "list[dict]") -> "list[str]":
    """Distinct mesh ids referenced by any part, in first-seen order --
    the sidebar's Meshes tab ("meshes imported into an entity").
    """
    seen = []
    for p in parts:
        mesh_id = p.get("mesh")
        if mesh_id and mesh_id not in seen:
            seen.append(mesh_id)
    return seen


def parts_using_mesh(parts: "list[dict]", mesh_id: str) -> "list[str]":
    """Ids of every part currently referencing *mesh_id*."""
    return [p.get("id") for p in parts if p.get("mesh") == mesh_id]


def find_unattached_part_for_mesh(parts: "list[dict]", mesh_id: str, root_id: "str | None") -> "dict | None":
    """An existing, non-root part already using *mesh_id* with no
    `attachTo` yet, if any. "Scaffold Parts from Sockets" reuses
    (attaches) this instead of creating a duplicate part when Import
    Mesh/Split Multi-Mesh GLB already auto-added it, unattached, for
    the same mesh -- without this, scaffolding after an auto-converted
    multi-part import would silently double every part (one unattached
    from import, one newly-created and attached from scaffolding).
    """
    for p in parts:
        if p.get("id") == root_id:
            continue
        if p.get("mesh") == mesh_id and "attachTo" not in p:
            return p
    return None


def animations_used_by_parts(parts: "list[dict]") -> "list[str]":
    """Distinct animation clip ids referenced by any part, in
    first-seen order -- the sidebar's Animations tab ("animations
    imported into an entity"). Combines each part's `animation_id`
    (continuous, looping) and every value in its `action_animations`
    map (one-shot, triggered) -- both fields reference the same kind of
    transform-clip id, just played differently at runtime.
    """
    seen = []
    for p in parts:
        animation_id = p.get("animation_id")
        if animation_id and animation_id not in seen:
            seen.append(animation_id)
        for clip_id in (p.get("action_animations") or {}).values():
            if clip_id and clip_id not in seen:
                seen.append(clip_id)
    return seen


def parts_using_animation(parts: "list[dict]", animation_id: str) -> "list[dict]":
    """Every (part, role) usage of *animation_id* -- role is
    `"animation_id"` (continuous loop) or `"action:<name>"` (one-shot,
    triggered when `entity.state == "<name>"`). A single part can use
    the same clip both ways, or two different clips.
    """
    usages = []
    for p in parts:
        if p.get("animation_id") == animation_id:
            usages.append({"part": p.get("id"), "role": "animation_id"})
        for action_name, clip_id in (p.get("action_animations") or {}).items():
            if clip_id == animation_id:
                usages.append({"part": p.get("id"), "role": f"action:{action_name}"})
    return usages


def new_animation_clip_id(name: str) -> str:
    """Clip id for a brand-new animation named *name* -- same
    "anim-transform-<name>" convention tools/convert_animation.py's own
    imported clips already use, so a from-scratch clip and an imported
    one are indistinguishable to every other part of this tool.
    """
    return f"anim-transform-{name}"


def new_animation_clip_path(name: str) -> Path:
    """On-disk path for a brand-new animation named *name* -- same
    "animation-transform-<name>.json" filename convention the Import
    Animation panel's own output_path already uses.
    """
    return ANIMATION_DIR / f"animation-transform-{name}.json"


def new_animation_clip(clip_id: str) -> dict:
    """An empty, from-scratch multi-part rig clip -- "New Animation",
    per direct request. Starts with zero keyframes (Add Keyframe in the
    Animation Editor creates the first one) rather than a single
    default keyframe, so an untouched new clip has no opinion yet about
    what it should hold.
    """
    return {"id": clip_id, "type": "transform", "loop": True, "keyframes": []}


def default_keyframe_transform() -> dict:
    """Rest-pose transform assigned to a part the moment it's added to
    a keyframe -- identity position/rotation, unit scale, so a freshly
    assigned part doesn't visibly jump before it's actually been edited.
    """
    return {"position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0]}


def add_keyframe(keyframes: "list[dict]", gap_ms: float = 500.0) -> dict:
    """Append and return a new, empty (no parts yet) keyframe -- the
    first keyframe always starts at time_ms=0; every keyframe after
    that starts *gap_ms* after the previous one's own time_ms (the
    Animation Editor's "Add Keyframe" button uses the default gap;
    the per-keyframe gap field, see set_keyframe_gap, adjusts it after
    the fact).
    """
    time_ms = 0.0 if not keyframes else keyframes[-1]["time_ms"] + gap_ms
    keyframe = {"time_ms": time_ms, "parts": {}}
    keyframes.append(keyframe)
    return keyframe


def duplicate_keyframe(keyframes: "list[dict]", index: int, gap_ms: float = 500.0) -> "dict | None":
    """Clone keyframes[index]'s part transforms into a brand new
    keyframe, per direct request ("duplicate the current selected
    keyframe. This clones all part transformations"). Placed the same
    way `add_keyframe` places any new keyframe -- appended at the end,
    `gap_ms` after the current last keyframe's own time -- rather than
    inserted mid-timeline, so duplicating never needs to renumber/shift
    any other keyframe's time_ms (same reasoning `remove_keyframe`
    already documents for deletion). Returns the new keyframe dict, or
    None if *index* is out of range (nothing selected to duplicate).

    Each assigned part's transform is a genuine deep copy -- fresh
    position/rotation/scale lists, not shared references back to the
    source keyframe's own lists -- so editing the duplicate afterward
    (e.g. via the Animation Editor's drag_float3 fields) can never also
    silently change the original keyframe it was cloned from. Also
    carries over each part's own `"easing"` curve, if it has one --
    real gap found and fixed while adding that field (Step 17): this
    function used to hardcode exactly position/rotation/scale into the
    rebuilt dict, which would have silently dropped any other per-part
    field (a custom transition curve included) back to its default the
    moment a keyframe was duplicated.
    """
    if not (0 <= index < len(keyframes)):
        return None
    source_parts = keyframes[index].get("parts") or {}
    new_keyframe = add_keyframe(keyframes, gap_ms=gap_ms)
    new_keyframe["parts"] = {
        part_id: {
            "position": list(transform.get("position", [0.0, 0.0, 0.0])),
            "rotation": list(transform.get("rotation", [0.0, 0.0, 0.0])),
            "scale": list(transform.get("scale", [1.0, 1.0, 1.0])),
            **({"easing": list(transform["easing"])} if "easing" in transform else {}),
        }
        for part_id, transform in source_parts.items()
    }
    return new_keyframe


def remove_keyframe(keyframes: "list[dict]", index: int) -> None:
    """Delete keyframe *index* in place. Does not renumber/shift any
    other keyframe's own time_ms -- gaps for keyframes after the
    removed one are simply larger now, same as deleting a frame from
    the middle of a hand-authored clip would be.
    """
    if 0 <= index < len(keyframes):
        del keyframes[index]


def keyframe_gap(keyframes: "list[dict]", index: int) -> float:
    """Time since the previous keyframe (or since t=0 for keyframe 0)
    -- what the Animation Editor's "gap from previous" field displays,
    since authoring relative spacing is more natural than editing raw
    absolute time_ms directly.
    """
    if index <= 0:
        return keyframes[0]["time_ms"] if keyframes else 0.0
    return keyframes[index]["time_ms"] - keyframes[index - 1]["time_ms"]


def set_keyframe_gap(keyframes: "list[dict]", index: int, gap_ms: float) -> None:
    """Set keyframe *index*'s time_ms from a "gap from previous" value
    (clamped non-negative). Only *this* keyframe's own time_ms moves --
    every later keyframe keeps its own stored time_ms, so its gap from
    (the now-shifted) *index* changes instead, rather than the whole
    tail of the clip silently shifting too.
    """
    gap_ms = max(0.0, gap_ms)
    prev_time = keyframes[index - 1]["time_ms"] if index > 0 else 0.0
    keyframes[index]["time_ms"] = prev_time + gap_ms


def assign_part_to_keyframe(keyframe: dict, part_id: str, transform: "dict | None" = None) -> None:
    """Add *part_id* to *keyframe*'s "parts" map with *transform* (or a
    fresh identity transform -- see default_keyframe_transform).
    Overwrites if already assigned, so this also serves as the "reset
    to identity" path if ever needed.
    """
    keyframe.setdefault("parts", {})[part_id] = transform or default_keyframe_transform()


def remove_part_from_keyframe(keyframe: dict, part_id: str) -> None:
    """Drop *part_id* from *keyframe*'s "parts" map, if present."""
    keyframe.get("parts", {}).pop(part_id, None)


def compute_group_transform_delta(
    old_position: "list[float]",
    new_position: "list[float]",
    old_rotation: "list[float]",
    new_rotation: "list[float]",
    old_scale: "list[float]",
    new_scale: "list[float]",
) -> "tuple[list[float], list[float], list[float]]":
    """Pure delta math behind the Animation Editor's "All Parts" rigid-
    group transform control -- per direct request ("apply
    transformations to every mesh/part in the entity as one"). The
    group control's own fields are a running total since it was last
    reset (see `_draw_animation_editor_window`'s per-keyframe reset),
    so each widget edit is applied to every part as the *delta* between
    the control's previous and new value: additive for position/
    rotation, a per-component ratio for scale (guarding a near-zero old
    value against a divide-by-zero -- dragging a scale field to exactly
    0 is a legal, if unusual, widget state).
    """
    delta_position = [new_position[i] - old_position[i] for i in range(3)]
    delta_rotation = [new_rotation[i] - old_rotation[i] for i in range(3)]
    scale_ratio = [
        (new_scale[i] / old_scale[i]) if abs(old_scale[i]) > 1e-6 else 1.0
        for i in range(3)
    ]
    return delta_position, delta_rotation, scale_ratio


def apply_rigid_group_delta(
    keyframe: dict,
    part_ids: "list[str]",
    delta_position: "list[float]",
    delta_rotation: "list[float]",
    scale_ratio: "list[float]",
) -> None:
    """Applies *delta_position*/*delta_rotation* additively and
    *scale_ratio* multiplicatively (component-wise) to every part in
    *part_ids*' own transform inside *keyframe* -- the actual "move/
    rotate/scale every part together, rigidly, preserving each part's
    pose relative to the others" effect behind the "All Parts" group
    control. Assumes every id in *part_ids* is already assigned to
    *keyframe* (see `assign_part_to_keyframe`) -- callers must assign
    any missing part first, since "every mesh/part in the entity" per
    the direct request means literally every part, not just whichever
    ones happened to already be in this keyframe.
    """
    for part_id in part_ids:
        transform = keyframe["parts"][part_id]
        position = transform.get("position", [0.0, 0.0, 0.0])
        rotation = transform.get("rotation", [0.0, 0.0, 0.0])
        scale = transform.get("scale", [1.0, 1.0, 1.0])
        transform["position"] = [position[i] + delta_position[i] for i in range(3)]
        transform["rotation"] = [rotation[i] + delta_rotation[i] for i in range(3)]
        transform["scale"] = [scale[i] * scale_ratio[i] for i in range(3)]


def parts_assigned_in_clip(clip: dict) -> "list[str]":
    """Distinct part ids referenced by any keyframe's "parts" map, in
    first-seen order -- used on Save to decide which of this entity's
    parts should have their own animation_id stamped to this clip (see
    stamp_animation_id_for_assigned_parts). Empty for a clip with no
    "parts" map anywhere (a plain single-part/imported clip).
    """
    seen = []
    for kf in clip.get("keyframes", []):
        for part_id in (kf.get("parts") or {}).keys():
            if part_id not in seen:
                seen.append(part_id)
    return seen


def stamp_animation_id_for_assigned_parts(
    entity_parts: "list[dict]", assigned_part_ids: "list[str]", clip_id: str
) -> "list[str]":
    """For every part in *assigned_part_ids* that exists in
    *entity_parts* and doesn't already have its own animation_id, set
    `part["animation_id"] = clip_id` -- so assigning a part to a
    keyframe in the Animation Editor is enough on its own to make that
    part actually play the clip, without a separate trip to the Parts
    tab. Never overwrites a part's existing animation_id (continuous-
    loop role stays whatever it was explicitly set to, e.g. a different
    clip, or this same clip already) -- returns only the ids actually
    changed, for the Save toast message.
    """
    stamped = []
    for part_id in assigned_part_ids:
        part = next((p for p in entity_parts if p.get("id") == part_id), None)
        if part is not None and not part.get("animation_id"):
            part["animation_id"] = clip_id
            stamped.append(part_id)
    return stamped


def apply_keyframe_preview(
    parts: "list[dict]", keyframe: "dict | None", origins: "dict | None" = None
) -> "list[dict]":
    """Live "watch the mesh follow the values you're editing" feedback
    for the Animation Editor's selected keyframe, per direct request.
    Returns *parts* completely unchanged (same list, not a copy) when
    *keyframe* is None/empty, so this is a no-op call whenever the
    editor isn't open or has nothing selected.

    For every part *keyframe* assigns a transform to, returns a shallow
    copy of that part with `localOffset` replaced by the keyframe's own
    transform -- entity_renderer.py's `_draw_entity` already reads
    `localOffset` as the position/rotation/scale baseline before
    layering any live animation sample on top (see that function's own
    comments), so this reuses that exact existing mechanism rather than
    adding a second, parallel transform-application path. `animation_id`/
    `action_animations` are stripped from the copy too -- without that,
    a part that already has a real running animation (e.g. a continuous
    spin) would have its own live-sampled pose silently override this
    keyframe's static preview pose the very next frame, exactly like it
    already overrides localOffset at runtime. Parts *not* named in this
    keyframe are returned unchanged (same dict, not copied) -- their
    ordinary animation/localOffset keeps rendering normally alongside
    the part(s) being previewed.

    *origins* -- the open clip's own top-level `"origins"` map (`{part_id:
    [x,y,z]}`, see transform_clip.py's own docstring) -- is per direct
    request ("allow setting an origin point to apply the animation
    transformation from"): when a previewed part has an entry there, it's
    written into the override's `localOffset.origin` alongside
    position/rotation/scale, so `entity_renderer.py` pivots that part's
    rotation/scale around it instead of the mesh's own local origin,
    exactly matching what real playback would do (see
    `_update_playback_pose`/`sample_part_pose` for the same lookup on
    the playing side).
    """
    assigned = (keyframe or {}).get("parts") or {}
    if not assigned:
        return parts
    origins = origins or {}
    result = []
    for part in parts:
        part_id = part.get("id")
        if part_id in assigned:
            overridden = dict(part)
            local_offset = dict(assigned[part_id])
            if part_id in origins:
                local_offset["origin"] = origins[part_id]
            overridden["localOffset"] = local_offset
            overridden.pop("animation_id", None)
            overridden.pop("action_animations", None)
            result.append(overridden)
        else:
            result.append(part)
    return result


def strip_live_animation_fields(parts: "list[dict]") -> "list[dict]":
    """Default-state preview, per direct request ("return the entity
    model state to default when an animation is not selected -- such as
    when deselecting or the default state when loading/opening an
    entity"). Returns a shallow copy of *parts* with every part's own
    `animation_id`/`action_animations` removed, so nothing keeps playing
    in the background -- each part renders at its plain, authored
    `localOffset` rest pose (untouched here, unlike apply_keyframe_preview,
    which actively overrides it with a specific keyframe's transform).

    Used by `_sync_preview_definition` exactly when no clip is currently
    open in the Animation Editor (`state.animation_editor_clip is None`)
    -- true both the moment an entity is first loaded (before anything's
    ever been selected) and right after deselecting/closing whatever was
    open, per the direct request's own two examples. Once a clip *is*
    open, `apply_keyframe_preview` takes back over as before -- this
    function only governs the "nothing selected at all" state.
    """
    return [
        {k: v for k, v in part.items() if k not in ("animation_id", "action_animations")}
        for part in parts
    ]


def advance_timeline_playback_ms(current_ms: float, delta_ms: float, duration_ms: float, loop: bool) -> float:
    """Advance the Timeline's playback clock by *delta_ms* -- real
    playback for the Play/Pause button (see _toggle_timeline_playback/
    _update_playback_pose), fixing the reported "unpausing does not
    start the playback" bug: nothing previously advanced any clock at
    all while a clip was open, since `state.paused` only ever gated the
    unrelated runtime animation_id clock.

    Wraps modulo *duration_ms* when *loop* is true (matching
    transform_clip.sample_transform_clip's own loop-wrap rule, so the
    displayed pose and the wrapped clock never disagree); otherwise
    clamps to *duration_ms* so a one-shot clip holds its final pose
    instead of running past the end forever. *duration_ms* <= 0 (no
    keyframes yet, or a single keyframe at time_ms 0) has nothing to
    wrap or clamp against -- returns the unwrapped advance.
    """
    new_ms = current_ms + delta_ms
    if duration_ms <= 0:
        return new_ms
    if loop:
        return new_ms % duration_ms
    return min(new_ms, duration_ms)


def sample_part_pose(clip: dict, part_id: str, elapsed_ms: float, fallback_local_offset: "dict | None" = None) -> dict:
    """Sample *clip* for *part_id* at *elapsed_ms*, filling in whichever
    of position/rotation/scale the clip doesn't define at this moment
    (see transform_clip.sample_transform_clip's own "omitted fields
    hold the part's rest value" rule) from *fallback_local_offset* --
    the part's own currently-authored localOffset, or identity if not
    given -- so `_update_playback_pose` always has a complete transform
    to write, never a partial one that would leave a stale value from
    a previous pose sitting in an untouched field.

    Also carries "origin" through unchanged when the clip's own
    `"origins"` map (transform_clip.py's own docstring) names *part_id*
    -- a rotation/scale pivot point, per direct request ("allow setting
    an origin point to apply the animation transformation from"),
    falling back to *fallback_local_offset*'s own origin (or `[0,0,0]`)
    when the clip doesn't define one, same fallback shape as the other
    three fields.
    """
    sampled = transform_clip.sample_transform_clip(clip, elapsed_ms, part_id=part_id)
    fallback = fallback_local_offset or {}
    return {
        "position": sampled.get("position", fallback.get("position", [0.0, 0.0, 0.0])),
        "rotation": sampled.get("rotation", fallback.get("rotation", [0.0, 0.0, 0.0])),
        "scale": sampled.get("scale", fallback.get("scale", [1.0, 1.0, 1.0])),
        "origin": sampled.get("origin", fallback.get("origin", [0.0, 0.0, 0.0])),
    }


# ---------------------------------------------------------------------
# Builder state
# ---------------------------------------------------------------------


class BuilderState:
    def __init__(self, entity_id: "str | None", parts: "list[dict]", entity_name: "str | None" = None) -> None:
        self.entity_id = entity_id
        self.parts = parts
        self.status_message = ""

        # Per direct request ("make it trivial to rename parts, meshes
        # or entities without it breaking relations"): entity_id is the
        # frozen reference every render_template/launcher lookup is
        # keyed on; entity_name is the freely-editable display label
        # (see _draw_entity_info_window). Defaults to entity_id so a
        # never-renamed entity shows the same string everywhere, same
        # "id and name start identical, diverge only once explicitly
        # renamed" pattern parts already use.
        self.entity_name = entity_name or entity_id or ""

        # Bottom-left toast -- transient, timed feedback for whatever
        # action just ran (see _show_toast()/_draw_toast()). Separate
        # from status_message above, which persists (no expiry) in the
        # hidden-by-default Entity Information window as a running
        # "last thing that happened" -- the toast is the same text,
        # just also shown immediately without opening that window.
        self.toast_message = ""
        self.toast_expires_at = 0.0

        # Set once in run() -- lets _sync_preview_definition() auto-fit
        # the orbit distance to whatever's actually loaded (see
        # entity_bounding_radius()) instead of assuming a fixed scale.
        self.orbit: "OrbitCamera | None" = None

        self.new_part_name = ""
        self.template_edit_buffers: dict = {}  # part_id -> draw_part_fields() buffer

        # Step 6 -- scaffold-from-sockets. socket_name -> {"mesh_id": str|None, "include": bool}.
        self.scaffold_state: dict = {}

        # Step 4 -- import panels.
        self.import_mesh_selected: "str | None" = None
        self.import_mesh_output_id = ""
        self.import_mesh_error = ""
        self.import_anim_selected: "str | None" = None
        self.import_anim_output_id = ""
        self.import_anim_name = ""
        self.import_anim_no_loop = False
        self.import_anim_error = ""

        # Step 7 -- materials panel.
        self.material_id_text = ""
        self.material_albedo_selected: "str | None" = None
        self.material_r_selected: "str | None" = None
        self.material_g_selected: "str | None" = None
        self.material_b_selected: "str | None" = None
        self.material_a_selected: "str | None" = None
        self.material_error = ""

        # Step 8 -- playback, folded into the Timeline window per direct
        # request (see _draw_timeline_window) -- no standalone Playback
        # window/state.show_playback_panel anymore. Defaults to paused,
        # per direct request -- a freshly-opened entity no longer starts
        # animating immediately.
        self.paused = True

        # Step 9 -- save. Save/Save As live in the File menu (_draw_menu_bar),
        # mirroring area_viewer.py's own fold of its standalone Save
        # window into File > Save[/Save As] -- no separate Save Entity
        # window in this tool either.
        self.save_as_name = entity_id or ""

        # Top/bottom menu bar (mirrors area_viewer.py's _draw_menu_bar/
        # _draw_bottom_bar) -- F11 toggles the top bar; the bottom bar
        # is always visible. want_exit/want_back_to_launcher are
        # deferred-close flags, same reasoning as area_viewer.py's own
        # want_exit: closing the canvas must happen in draw(), after
        # imgui_renderer.render() has actually finished, never from
        # inside a menu-item click handler (which runs inside that same
        # frame bracket) -- see that module's own note on the exact
        # crash this avoids.
        self.menu_bar_visible = True
        self.want_exit = False
        self.want_back_to_launcher = False
        self.show_entity_info = False  # hidden by default, like area_viewer.py's "Area Information"

        # Sidebar (Parts, Materials, and whatever else gets folded in later).
        self.show_sidebar = True

        # View > Mesh -- wireframe vs. solid (EntityRenderer.set_wireframe(),
        # applied to the live preview renderer each frame in run()'s
        # draw(), since _sync_preview_definition() destroys/recreates
        # that renderer on every parts-list edit -- reapplying here
        # means the toggle survives that).
        self.wireframe = False

        # Animations tab -- "New Animation" + the Animation Editor
        # window, per direct request. animation_editor_clip is the
        # in-memory buffer for whichever clip is currently open (loaded
        # fresh off disk by _open_animation_editor, not read from
        # EntityRenderer's own permanent clip cache -- see that
        # function's docstring); animation_editor_path is where Save
        # writes it back. None/None when no editor is open.
        self.new_animation_name = ""
        self.new_animation_error = ""
        self.editing_animation_id: "str | None" = None
        self.animation_editor_clip: "dict | None" = None
        self.animation_editor_path: "Path | None" = None
        self.animation_editor_selected_kf = -1
        self.animation_editor_assign_part = ""

        # "All Parts" rigid-group transform control, per direct request
        # ("apply transformations to every mesh/part in the entity as
        # one") -- these three fields are a running total *since the
        # control was last reset*, not a real transform read from any
        # part; each widget edit is applied to every part as the delta
        # from the previous value (see compute_group_transform_delta/
        # apply_rigid_group_delta), so the control must reset back to
        # identity whenever the selected keyframe changes (tracked via
        # animation_editor_group_kf_index -- an already-reset value
        # never matches the initial -2 sentinel, so the first draw
        # always resets once before use).
        self.animation_editor_group_position = [0.0, 0.0, 0.0]
        self.animation_editor_group_rotation = [0.0, 0.0, 0.0]
        self.animation_editor_group_scale = [1.0, 1.0, 1.0]
        self.animation_editor_group_kf_index = -2

        # Timeline playback clock -- real bug fixed, reported directly
        # as "unpausing does not start the playback": state.paused used
        # to only gate the real runtime animation_id/action_animations
        # clock (entity_renderer.py's own sampling), which has nothing
        # to do with the Animation Editor's static per-keyframe preview
        # override (apply_keyframe_preview) -- so toggling it never did
        # anything while a clip was open. This clock (elapsed ms within
        # the open clip) drives actual playback instead -- see
        # _toggle_timeline_playback/_update_playback_pose.
        self.timeline_playback_ms = 0.0


def _pending_files(directory: Path) -> "list[str]":
    if not directory.exists():
        return []
    return sorted(
        p.name for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in (".glb", ".gltf")
    )


def _pending_model_files() -> "list[str]":
    """Files offered in the Import Mesh panel: plain single-mesh
    exports at the top level of pending/models/, plus, one (or more)
    levels deeper, whatever tools/split_glb.py has split a multi-mesh
    export into -- its default output directory is
    `pending/models/<source stem>/`. Returned as paths relative to
    PENDING_MODELS_DIR (forward-slash), both for display and for
    resolving back to a real path (`PENDING_MODELS_DIR / result`).
    """
    if not PENDING_MODELS_DIR.exists():
        return []
    return sorted(
        p.relative_to(PENDING_MODELS_DIR).as_posix()
        for p in PENDING_MODELS_DIR.rglob("*")
        if p.is_file() and p.suffix.lower() in (".glb", ".gltf")
    )


def _pending_images() -> "list[str]":
    if not PENDING_DIR.exists():
        return []
    return sorted(
        p.name for p in PENDING_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg")
    )


def _browse_for_file(type_label: str, patterns: "tuple[str, ...]") -> "str | None":
    """Open the native OS file-open dialog (Explorer/Finder/whatever
    the platform's file manager is), filtered to *patterns*. Returns
    the chosen absolute path, or None if cancelled.

    `tkinter.filedialog` -- stdlib, no new pip dependency -- rather
    than a hand-rolled per-OS dialog. This does reintroduce `tkinter`
    into this one module, reversing this tool's original "no native
    file dialog" decision, but that decision's actual justification
    (`distribution.prompt.md` excludes `tkinter` from the *packaged
    game* build) doesn't apply here: `entity_builder.py` is a dev-only
    authoring tool, never part of any shipped game executable, and that
    prompt file is itself written entirely against the old, now-deleted
    PyWebView/JS client (`main.py`'s PyWebView entry point) -- see its
    own "Not started" status in ROADMAP.md. A throwaway hidden Tk root
    is created and destroyed per call rather than kept alive, since
    this dialog is opened rarely (once per file pick), not per-frame.
    """
    import tkinter
    from tkinter import filedialog

    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)  # otherwise the dialog can open behind the GLFW window
    try:
        path = filedialog.askopenfilename(
            title=f"Select a {type_label} file",
            filetypes=[(type_label, patterns), ("All files", "*.*")],
        )
    finally:
        root.destroy()
    return path or None


def _copy_into_pending(src: Path, dest_dir: Path) -> Path:
    """Copy *src* (picked via _browse_for_file, likely from anywhere on
    disk) into *dest_dir* (PENDING_MODELS_DIR/PENDING_ANIMATIONS_DIR),
    so the rest of the Import panel's existing pending/-relative-path
    logic (`_pending_model_files()`, `_pending_files()`, the Convert/
    Split buttons) doesn't need a second code path for "a file that
    isn't actually in pending/ yet." Renames on collision (`name_2.glb`,
    `name_3.glb`, ...) rather than overwriting an unrelated existing
    file of the same name; a no-op if *src* already resolves to
    somewhere inside *dest_dir*.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if dest.resolve() == src.resolve():
        return dest
    if dest.exists():
        stem, suffix, n = src.stem, src.suffix, 2
        while dest.exists():
            dest = dest_dir / f"{stem}_{n}{suffix}"
            n += 1
    shutil.copyfile(src, dest)
    return dest


def _sync_preview_definition(scene: Scene, state: BuilderState) -> None:
    """Write the in-progress `parts` list to a scratch entity-
    definition file and force the preview EntityRenderer to reload from
    scratch. Called after every edit that changes what should render.

    EntityRenderer caches definitions/meshes/materials *permanently*
    once loaded (`_render_templates`/`_meshes`/`_material_handles` --
    there is no cache-invalidation path anywhere in that class, by
    design, since real gameplay entities never change their own
    render_template's on-disk contents out from under a running
    client). That's exactly wrong for a live builder tool, so this
    reaches into `client.main.entity_renderers` directly to destroy and
    drop the preview entity's renderer -- a targeted, builder-only
    mechanism, the same kind of direct-internals reach
    asset_preview.py's own `_apply_material_overrides` already uses for
    a different field set.

    If the Animation Editor is open with a keyframe selected, the parts
    it assigns a transform to are rendered posed exactly at that
    keyframe (see apply_keyframe_preview) instead of their normal
    localOffset/live-animation pose -- per direct request, so dragging
    a keyframe's position/rotation/scale fields visibly moves the real
    mesh right away. This only ever affects the *scratch preview copy*
    written below, never `state.parts` itself, so it can't leak into a
    real Save.

    No keyframe actually selected/previewable -- either no clip open at
    all (`state.animation_editor_clip is None`, true both the moment an
    entity is first loaded and right after deselecting/closing whatever
    was open), or a clip *is* open but nothing in it is currently
    selected (a brand-new clip with zero keyframes yet, per
    `_draw_animations_tab`'s "New Animation" -- `_open_animation_editor`
    leaves `animation_editor_selected_kf` at `-1` until a first keyframe
    exists to auto-select) -- is its own case, per direct request
    ("return the entity model state to default when an animation is not
    selected"): every part's `animation_id`/`action_animations` is
    stripped from the preview copy (see strip_live_animation_fields) so
    nothing keeps playing in the background, leaving every part at its
    plain authored localOffset rest pose.

    **Real bug found and fixed here**, reported directly ("Creating
    another new animation for the bird entity ... instead starts
    playing the flap-test animation"): the original version of this
    fix only checked `clip is None`, so opening the editor for a
    brand-new *empty* clip (`clip` is a real dict, just with no
    keyframes) fell into the `apply_keyframe_preview` branch below with
    `preview_keyframe` already `None` -- and that function is a
    documented no-op whenever its keyframe argument is `None`, so every
    other part's own real, already-running `animation_id` (a bird's
    wing flap, say) kept animating completely undisturbed, with nothing
    in the visibly-empty Animation Editor window suggesting why. Keying
    directly off `preview_keyframe is None` instead of `clip is None`
    covers both "no clip open" and "clip open but nothing selected"
    with the one same default-state rule.

    This is the *paused* preview only -- while the Timeline is actively
    playing (`state.paused` is False), `_update_playback_pose` takes
    over on every frame instead, mutating the already-loaded render
    template directly rather than rewriting this file and recreating
    the renderer 60 times a second (see that function's own docstring
    on why). Pressing Pause calls this function once to snap back to
    the statically-selected keyframe.
    """
    preview_keyframe = None
    clip = state.animation_editor_clip
    if clip is not None:
        keyframes = clip.get("keyframes", [])
        index = state.animation_editor_selected_kf
        if 0 <= index < len(keyframes):
            preview_keyframe = keyframes[index]

    if preview_keyframe is None:
        render_parts = strip_live_animation_fields(state.parts)
    else:
        render_parts = apply_keyframe_preview(state.parts, preview_keyframe, clip.get("origins"))

    ENTITY_DIR.mkdir(parents=True, exist_ok=True)
    path = ENTITY_DIR / f"entity-{_BUILDER_SCRATCH_ID}.json"
    path.write_text(json.dumps({"parts": render_parts}, indent=2), encoding="utf-8")
    asset_loader.register(_BUILDER_SCRATCH_ID, f"assets/data/entity/entity-{_BUILDER_SCRATCH_ID}.json")

    renderer_ = client_main.entity_renderers.get(_PREVIEW_ENTITY_ID)
    if renderer_ is not None:
        renderer_.destroy()
        del client_main.entity_renderers[_PREVIEW_ENTITY_ID]

    entity = scene.entities.get(_PREVIEW_ENTITY_ID)
    if state.parts:
        if entity is None:
            scene.add_entity(
                _PREVIEW_ENTITY_ID,
                {
                    "x": 0.0, "y": 0.0, "z": 0.0,
                    "state": "idle",
                    "facing": "down",
                    "render_template": _BUILDER_SCRATCH_ID,
                    "transform3d": {"rotation": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0]},
                    "animation_data_paths": ["assets/data/example_human_animations.json"],
                },
                "local",
            )
        else:
            entity["render_template"] = _BUILDER_SCRATCH_ID
    elif entity is not None:
        scene.remove_entity(_PREVIEW_ENTITY_ID)

    # Auto-frame the orbit camera to whatever's actually loaded, per
    # direct report: OrbitCamera's fixed ~200-unit default radius
    # (inherited from this engine's old pixel-tile-scale content)
    # rendered a realistically-scaled "1 unit = 1 meter" model
    # correctly but far too small on screen to see -- indistinguishable
    # from not rendering at all. Runs on every parts-list edit, not
    # just once at load, so it stays sane as meshes get assigned/
    # swapped -- overwriting any manual scroll-zoom is an accepted
    # tradeoff for a dev tool that's actively being edited, not a
    # precious authored camera.
    #
    # Widened by keyframe_preview_reach() when a keyframe pose is
    # currently being previewed (see above) -- per direct report ("I'm
    # applying transformations to parts in the animation but the mesh
    # render is not updating"), the rest-pose-only radius left the
    # camera fitted so tightly (e.g. ~0.5 units for a ~0.13-unit bird)
    # that a keyframe moving a part any real distance from the origin
    # rendered correctly but immediately exceeded the visible frustum --
    # not a rendering bug, a framing one.
    if state.orbit is not None:
        radius = entity_bounding_radius(state.parts)
        radius = max(radius, keyframe_preview_reach(preview_keyframe, radius))
        _fit_camera_to_radius(scene, state, radius)


def _fit_camera_to_radius(scene: Scene, state: BuilderState, radius: float) -> None:
    """Apply the same orbit-distance/near/far formula `_sync_preview_definition`
    uses, factored out so `_toggle_timeline_playback` can fit the camera
    once up front (to the whole clip's max reach) when playback starts,
    without needing a full `_sync_preview_definition` call every frame
    during playback (see `_update_playback_pose`'s own docstring for why
    that would be too expensive to do 60 times a second).
    """
    if state.orbit is None:
        return
    state.orbit.radius = max(radius * 3.0, 0.5)
    scene.camera["near"] = max(radius * 0.01, 0.001)
    scene.camera["far"] = max(radius * 50.0, 100.0)


def _update_playback_pose(state: BuilderState) -> None:
    """Per-frame pose update while the Timeline is actively playing
    (state.paused is False) -- called from run()'s draw() every frame,
    unlike `_sync_preview_definition` (called only on discrete edits).

    Deliberately does *not* call `_sync_preview_definition`: that
    function rewrites the scratch entity JSON to disk and destroys/
    recreates the whole preview `EntityRenderer` -- correct and cheap
    enough for a single edit, but calling it 60 times a second during
    smooth playback would mean disk I/O plus a full mesh/material
    reload every frame, purely to advance a clock. Instead, this reaches
    directly into the already-loaded, cached render_template
    (`EntityRenderer._render_templates`, the same object `_draw_entity`
    reads from every frame with no re-parsing) and mutates each
    clip-assigned part's `localOffset` in place from
    `transform_clip.sample_transform_clip` -- the same sampling
    function `entity_renderer.py` uses at real gameplay time, just
    driven by `state.timeline_playback_ms` instead of a live game clock.
    A no-op if the preview renderer/definition hasn't loaded yet (e.g.
    the very first frame after opening the editor).
    """
    clip = state.animation_editor_clip
    if clip is None:
        return
    assigned_ids = parts_assigned_in_clip(clip)
    if not assigned_ids:
        return

    renderer_ = client_main.entity_renderers.get(_PREVIEW_ENTITY_ID)
    if renderer_ is None:
        return
    definition = renderer_._render_templates.get(_BUILDER_SCRATCH_ID)
    if not definition:
        return

    parts_by_id = {p.get("id"): p for p in definition.get("parts", [])}
    for part_id in assigned_ids:
        part = parts_by_id.get(part_id)
        if part is None:
            continue
        part["localOffset"] = sample_part_pose(
            clip, part_id, state.timeline_playback_ms, part.get("localOffset")
        )


def _toggle_timeline_playback(scene: Scene, state: BuilderState) -> None:
    """Play/Pause button handler (see _draw_timeline_window). Real bug
    fixed here, reported directly as "unpausing does not start the
    playback": `state.paused` used to only gate the real runtime
    animation_id/action_animations clock (entity_renderer.py's own
    sampling) -- but while the Animation Editor has a keyframe selected,
    the preview is statically pinned to that one keyframe's pose
    (apply_keyframe_preview), which has nothing to do with that clock,
    so toggling Paused there never visibly did anything.

    Pausing now explicitly snaps back to that static per-keyframe
    preview (_sync_preview_definition). Starting playback resumes the
    clip's own clock from wherever the currently selected keyframe sits
    in time (or 0.0 if none is selected -- natural "scrub then play
    from here" behavior), fits the camera once to the *whole* clip's
    max reach across every keyframe (not just whichever one happens to
    be selected right now, since playback will visit all of them) so
    a dramatic pose later in the clip doesn't silently exceed the
    frustum mid-playback the way the underlying rest-pose-only fit
    already once did (see keyframe_preview_reach's own docstring), and
    lets `_update_playback_pose` take over every frame after that.
    """
    state.paused = not state.paused
    if state.paused:
        _sync_preview_definition(scene, state)
        return

    clip = state.animation_editor_clip
    keyframes = (clip or {}).get("keyframes", [])
    index = state.animation_editor_selected_kf
    state.timeline_playback_ms = keyframes[index]["time_ms"] if 0 <= index < len(keyframes) else 0.0

    if state.orbit is not None:
        radius = entity_bounding_radius(state.parts)
        radius = max(radius, max((keyframe_preview_reach(kf, radius) for kf in keyframes), default=0.0))
        _fit_camera_to_radius(scene, state, radius)


def _add_part_for_converted_mesh(scene: Scene, state: BuilderState, mesh_id: str) -> "str | None":
    """Auto-create an unattached part for a freshly-converted mesh, per
    direct request ("when a mesh is converted, add it to the entity").
    A no-op (returns None) if a part already references this exact
    mesh id -- treated as a re-conversion (e.g. re-exporting after a
    Blender fix), not a request for a second, duplicate part every time
    the same mesh is reconverted.
    """
    if any(p.get("mesh") == mesh_id for p in state.parts):
        return None
    part_id = unique_part_id(mesh_id_to_part_id(mesh_id), state.parts)
    name = read_mesh_name(mesh_id) or mesh_id_to_part_id(mesh_id)
    state.parts.append({"id": part_id, "name": name, "mesh": mesh_id})
    _sync_preview_definition(scene, state)
    return part_id


# ---------------------------------------------------------------------
# Toast feedback -- every discrete action in this tool (add/remove a
# part, import/split/convert, pack a material, save) reports itself
# here, per direct request: brief, visible confirmation without having
# to open the (hidden-by-default) Entity Information window.
# ---------------------------------------------------------------------

_TOAST_DURATION_S = 3.0


def _show_toast(state: BuilderState, message: str) -> None:
    """Set both the transient bottom-left toast and the persistent
    status_message (still shown in Entity Information) from one call --
    every action in this file reports through this single function
    rather than assigning state.status_message directly, so nothing can
    silently skip the toast half.
    """
    state.status_message = message
    state.toast_message = message
    state.toast_expires_at = time.perf_counter() + _TOAST_DURATION_S


def _capture_stdout(fn, *args, **kwargs):
    """Run *fn* with stdout captured, returning (result, printed_text).

    convert_mesh.convert()/convert_animation.convert()/split_glb
    .split_glb() all report what they did via plain print() (e.g.
    "[convert_mesh] Wrote ... (32 vertices, 42 indices)"), not a return
    value -- this lets the Import panel surface that exact real message
    as the toast (per direct request) without changing any of those
    three already-independently-tested scripts just to make them return
    a string instead of printing one.
    """
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = fn(*args, **kwargs)
    return result, buf.getvalue().strip()


def _draw_toast(state: BuilderState) -> None:
    """Bottom-left, auto-expiring after _TOAST_DURATION_S -- drawn on
    the foreground draw list (not a real window), positioned just above
    the always-on bottom bar so it never overlaps that bar's own
    Mode/Parts text. Same "draw straight onto the foreground list from
    inside gui()'s own frame bracket" mechanism as _draw_bottom_bar.
    """
    if not state.toast_message or time.perf_counter() >= state.toast_expires_at:
        return

    from client.engine.gizmo import pack_color, to_imvec2

    viewport = imgui.get_main_viewport()
    bottom_bar_height = imgui.get_frame_height()
    pad = 8.0
    text_size = imgui.calc_text_size(state.toast_message)
    box_w = text_size.x + pad * 2
    box_h = text_size.y + pad * 2

    left = viewport.work_pos.x + 8.0
    bottom = viewport.work_pos.y + viewport.work_size.y - bottom_bar_height - 8.0
    top = bottom - box_h

    draw_list = imgui.get_foreground_draw_list()
    draw_list.add_rect_filled(
        to_imvec2((left, top)), to_imvec2((left + box_w, top + box_h)), pack_color((30, 90, 40), 235), rounding=4.0
    )
    draw_list.add_text(to_imvec2((left + pad, top + pad)), pack_color((255, 255, 255), 255), state.toast_message)


# ---------------------------------------------------------------------
# Panels
# ---------------------------------------------------------------------


def _draw_parts_tab(scene: Scene, state: BuilderState, action_registry) -> None:
    """Content only -- no imgui.begin()/end() of its own. Folded into
    the right-side sidebar (per direct request) as its first tab,
    same "content-only function, chrome lives in the container" split
    _draw_materials_tab already established.

    Per direct request ("make it trivial to rename parts, meshes or
    entities without it breaking relations"): the header label and the
    editable "name" field show/change a part's `"name"`, never its
    `"id"` -- id is what `attachTo.part` and every animation clip's
    `"parts"`/`"origins"` map keys actually reference, so it stays
    frozen from creation onward, displayed read-only for grep/debug
    visibility. The `##{part_id}` imgui-id suffix on the header and
    every widget below it is deliberately keyed on the immutable id,
    not the display label, so renaming a part never scrambles which
    header is open or loses in-progress edits to its own fields.
    """
    mesh_ids = sorted(asset_loader.list_category("meshes").keys())
    material_asset_ids = sorted(asset_loader.list_category("materials").keys())

    for index, part in enumerate(state.parts):
        part_id = part.get("id") or "?"
        display_name = part.get("name") or part_id
        if not imgui.collapsing_header(f"Part: {display_name}##{part_id}"):
            continue

        changed, new_name = imgui.input_text(f"name##{part_id}", part.get("name") or part_id)
        if changed:
            part["name"] = new_name
            _show_toast(state, f"Renamed part to '{new_name}' (not yet saved to disk)")
        imgui.text(f"id: {part_id}")

        # --- mesh picker ---
        current_mesh = part.get("mesh") or ""
        mesh_index = mesh_ids.index(current_mesh) if current_mesh in mesh_ids else -1
        changed, new_index = imgui.combo(f"mesh##{part_id}", mesh_index, mesh_ids or ["(no meshes imported yet)"])
        if changed and mesh_ids and new_index >= 0:
            part["mesh"] = mesh_ids[new_index]
            _sync_preview_definition(scene, state)

        # --- material picker ---
        current_material_asset = asset_id_for_material_id_field(part.get("material_id"))
        material_index = (
            material_asset_ids.index(current_material_asset)
            if current_material_asset in material_asset_ids
            else -1
        )
        changed, new_index = imgui.combo(
            f"material##{part_id}", material_index, material_asset_ids or ["(no materials yet)"]
        )
        if changed and material_asset_ids and new_index >= 0:
            part["material_id"] = material_id_field_for_asset(material_asset_ids[new_index])
            _sync_preview_definition(scene, state)

        # --- attachTo: part picker ---
        earlier_ids = [p.get("id") for p in state.parts[:index] if p.get("id")]
        attach_options = ["(none -- use entity's own position)"] + earlier_ids
        current_attach = part.get("attachTo") or {}
        current_parent = current_attach.get("part") or ""
        attach_index = attach_options.index(current_parent) if current_parent in attach_options else 0
        changed, new_index = imgui.combo(f"attachTo part##{part_id}", attach_index, attach_options)
        if changed:
            if new_index == 0:
                if "attachTo" in part:
                    del part["attachTo"]
            else:
                parent_id = attach_options[new_index]
                part["attachTo"] = {"part": parent_id, "socket": ""}
            _sync_preview_definition(scene, state)

        # --- attachTo: socket picker (only if a parent is chosen) ---
        attach_to = part.get("attachTo")
        if attach_to:
            parent_part = next((p for p in state.parts if p.get("id") == attach_to.get("part")), None)
            parent_mesh = parent_part.get("mesh") if parent_part else None
            socket_names = read_mesh_sockets(parent_mesh)
            if not socket_names:
                imgui.text_wrapped(
                    f"Parent part '{attach_to.get('part')}' has no loaded sockets yet "
                    "-- assign its mesh first."
                )
            else:
                current_socket = attach_to.get("socket") or ""
                socket_index = socket_names.index(current_socket) if current_socket in socket_names else -1
                changed, new_index = imgui.combo(f"attachTo socket##{part_id}", socket_index, socket_names)
                if changed and new_index >= 0:
                    attach_to["socket"] = socket_names[new_index]
                    _sync_preview_definition(scene, state)

        imgui.separator()

        # --- shared per-part fields (animation_id/dangle/localOffset/action_animations) ---
        buffer = state.template_edit_buffers.setdefault(part_id, default_part_buffer(part))
        edited = draw_part_fields(part, buffer, action_registry, part_id)
        if edited is not None:
            # Defense-in-depth tripwire, not expected to ever fire today
            # (entity_template_editing.py's draw_part_fields never
            # touches "id") -- per direct request that renaming must
            # never break a reference, id has to stay frozen after
            # creation forever, so a future change to that shared,
            # cross-file editor accidentally starting to rewrite it
            # should be loud immediately, not a silently corrupted save.
            if edited.get("id") != part_id:
                wrong_id = edited.get("id")
                edited["id"] = part_id
                _show_toast(state, f"BUG: part id changed from '{part_id}' to '{wrong_id}' -- ignoring")
            else:
                _show_toast(state, f"Updated part '{part_id}' (not yet saved to disk)")
            state.parts[index] = edited
            _sync_preview_definition(scene, state)

        if imgui.button(f"Remove Part##{part_id}"):
            orphaned = remove_part(state.parts, part_id)
            state.template_edit_buffers.pop(part_id, None)
            _sync_preview_definition(scene, state)
            _show_toast(
                state,
                f"Removed part '{part_id}'"
                + (f" -- cleared attachTo on: {', '.join(orphaned)}" if orphaned else ""),
            )

        imgui.separator()

    imgui.text("+ Add Part")
    _, state.new_part_name = imgui.input_text("new part name", state.new_part_name)
    if imgui.button("Add Part"):
        error = validate_new_part_name(state.new_part_name)
        if error:
            _show_toast(state, error)
        else:
            name = state.new_part_name.strip()
            # id is derived from the typed name and frozen from here on
            # -- per direct request ("make it trivial to rename parts...
            # without it breaking relations"), id is what every
            # attachTo.part / animation clip parts-/origins-map reference
            # actually points at, so it must never change after creation;
            # name is what the user is actually free to rename later (see
            # the part header's own "name" field, below).
            new_id = unique_part_id(name, state.parts)
            state.parts.append({"id": new_id, "name": name, "mesh": None})
            state.new_part_name = ""
            _sync_preview_definition(scene, state)
            suffix = f" (id: {new_id})" if new_id != name else ""
            _show_toast(state, f"Added part '{name}'{suffix}")


def _draw_scaffold_content(scene: Scene, state: BuilderState) -> None:
    """Content only -- no imgui.begin()/end() of its own. Folded into
    the menu bar's "Parts" top-level menu as a submenu (per direct
    request), the same "submenu holding real widgets" pattern
    File > Save As / Import Mesh / Import Animation already established.
    """
    root = state.parts[0] if state.parts else None
    if root is None or not root.get("mesh"):
        imgui.text_wrapped("Add a root part with a mesh assigned first.")
        return

    socket_names = read_mesh_sockets(root.get("mesh"))
    if not socket_names:
        imgui.text_wrapped(f"Root mesh '{root.get('mesh')}' has no sockets.")
        return

    mesh_ids = sorted(asset_loader.list_category("meshes").keys())
    root_id = root.get("id")

    # A real bug, reported directly: this loop used to only guard
    # against *id* collisions (renaming wing_l -> wing_l_2), never
    # against a socket that already has a part attached -- so
    # re-running Add Selected Parts (or scaffolding a socket someone
    # had already attached a part to by hand) created a second,
    # overlapping part at the same socket instead of recognizing it was
    # already covered. Sockets already attached are shown, disabled, in
    # the list below rather than silently hidden -- so it's visible
    # *why* a socket isn't offered, not just that it's missing.
    for socket_name in socket_names:
        attached_id = part_attached_to_socket(state.parts, root_id, socket_name)
        if attached_id is not None:
            imgui.text_disabled(f"{socket_name}: already attached (part '{attached_id}')")
            continue

        row = state.scaffold_state.setdefault(
            socket_name,
            {"mesh_id": suggest_socket_match(socket_name, mesh_ids), "include": True},
        )
        _, row["include"] = imgui.checkbox(f"##{socket_name}-include", row["include"])
        imgui.same_line()
        options = ["(skip)"] + mesh_ids
        current = row["mesh_id"] or "(skip)"
        current_index = options.index(current) if current in options else 0
        changed, new_index = imgui.combo(f"{socket_name}##scaffold", current_index, options)
        if changed:
            row["mesh_id"] = None if new_index == 0 else options[new_index]
        # Transparency, per this codebase's own "make behavior visible,
        # not surprising" precedent: with Import Mesh/Split Multi-Mesh
        # GLB now auto-adding an unattached part per converted mesh
        # (see _add_part_for_converted_mesh), this button's action
        # depends on whether one of those already exists for the
        # chosen mesh -- show which it'll be, not just do it silently.
        if row["mesh_id"]:
            existing = find_unattached_part_for_mesh(state.parts, row["mesh_id"], root_id)
            imgui.text_disabled(
                f"  -> will attach existing part '{existing.get('id')}'"
                if existing is not None
                else "  -> will create a new part"
            )

    if imgui.button("Add Selected Parts"):
        added = []
        for socket_name in socket_names:
            # Defensive re-check, not just relying on the UI above
            # having hidden this row -- scaffold_state can carry a
            # stale "include": True from before a part existed here
            # (e.g. added by hand between panel renders).
            if part_attached_to_socket(state.parts, root_id, socket_name) is not None:
                continue
            row = state.scaffold_state.get(socket_name)
            if not row or not row["include"] or not row["mesh_id"]:
                continue

            # Reuse (attach) an existing unattached part for this mesh
            # rather than creating a duplicate -- see
            # find_unattached_part_for_mesh's own docstring for why
            # this matters now that Import Mesh/Split Multi-Mesh GLB
            # auto-add parts too.
            existing = find_unattached_part_for_mesh(state.parts, row["mesh_id"], root_id)
            if existing is not None:
                existing["attachTo"] = {"part": root_id, "socket": socket_name}
                added.append(existing.get("id"))
                continue

            name = socket_name[:-7] if socket_name.endswith("_socket") else socket_name
            new_id = unique_part_id(name, state.parts)
            state.parts.append({
                "id": new_id,
                "name": name,
                "mesh": row["mesh_id"],
                "attachTo": {"part": root_id, "socket": socket_name},
            })
            added.append(new_id)
        if added:
            _sync_preview_definition(scene, state)
            _show_toast(state, f"Scaffolded parts: {', '.join(added)}")
        else:
            _show_toast(state, "No sockets selected/matched -- nothing added.")


def _draw_import_mesh_content(scene: Scene, state: BuilderState) -> None:
    """Content only -- no imgui.begin()/end() of its own. Folded into
    the File menu as an "Import Mesh" submenu (per direct request),
    the same "submenu holding real widgets" pattern the File > Save As
    submenu already established.
    """
    imgui.text("Import Mesh (from frontend/assets/pending/models/)")
    if imgui.button("Search...##import-mesh-browse"):
        picked = _browse_for_file("glTF/GLB", ("*.glb", "*.gltf"))
        if picked:
            dest = _copy_into_pending(Path(picked), PENDING_MODELS_DIR)
            state.import_mesh_selected = dest.relative_to(PENDING_MODELS_DIR).as_posix()
            state.import_mesh_output_id = dest.stem
            _show_toast(state, f"Added '{dest.name}' to pending/models/")
    mesh_files = _pending_model_files()
    if not mesh_files:
        imgui.text_wrapped("No .glb/.gltf files found in pending/models/.")
    else:
        current_index = mesh_files.index(state.import_mesh_selected) if state.import_mesh_selected in mesh_files else 0
        changed, new_index = imgui.combo("mesh file##import", current_index, mesh_files)
        state.import_mesh_selected = mesh_files[new_index]
        if not state.import_mesh_output_id:
            state.import_mesh_output_id = Path(state.import_mesh_selected).stem
        _, state.import_mesh_output_id = imgui.input_text("output mesh id##import", state.import_mesh_output_id)
        if imgui.button("Convert Mesh"):
            try:
                input_path = PENDING_MODELS_DIR / state.import_mesh_selected
                mesh_id = f"mesh-{state.import_mesh_output_id}"
                output_path = MESH_DIR / f"{mesh_id}.json"
                _, printed = _capture_stdout(convert_mesh.convert, str(input_path), str(output_path))
                refresh_manifest()
                asset_loader.load_manifest()
                state.import_mesh_error = ""
                # Per direct request: a converted mesh is auto-added as
                # a part -- see _add_part_for_converted_mesh's own
                # docstring for the "already referenced -> skip" guard.
                added_part_id = _add_part_for_converted_mesh(scene, state, mesh_id)
                if added_part_id:
                    _show_toast(state, f"{printed}\nAdded part '{added_part_id}'" if printed else f"Imported mesh '{mesh_id}' -- added as part '{added_part_id}'")
                else:
                    _show_toast(state, printed or f"Imported mesh '{mesh_id}'")
            except convert_mesh.ConvertError as err:
                state.import_mesh_error = str(err)
        imgui.same_line()
        # Multi-mesh exports (a whole rigid-part rig exported as one
        # file) can't go through Convert Mesh directly -- convert_mesh
        # .py refuses anything but a single mesh, by design. This runs
        # tools/split_glb.py against the currently-selected file first,
        # writing one single-mesh .glb per part into a subfolder here
        # (pending/models/<stem>/). do_convert=True, per direct request
        # ("when splitting meshes, also automatically convert them") --
        # each successfully-converted part is then auto-added as a part
        # too (same as the plain Convert Mesh button above), so
        # splitting a whole rig is a single click from raw export to a
        # full (unattached) parts list; wire up attachTo/sockets
        # afterward via Parts > Scaffold Parts from Sockets, which
        # reuses these same auto-added parts rather than duplicating
        # them (see find_unattached_part_for_mesh).
        if imgui.button("Split Multi-Mesh GLB##import"):
            try:
                input_path = PENDING_MODELS_DIR / state.import_mesh_selected
                written, printed = _capture_stdout(
                    split_glb.split_glb,
                    str(input_path), output_dir=None, mesh_dir=str(MESH_DIR), do_convert=True,
                )
                refresh_manifest()
                asset_loader.load_manifest()
                state.import_mesh_error = ""
                added = []
                for split_path in written:
                    mesh_id = f"mesh-{split_path.stem}"
                    # split_glb.py catches and prints its own per-part
                    # ConvertError rather than raising (so one bad part
                    # doesn't abort the whole split) -- checking the
                    # output file's existence is how this tells which
                    # parts actually converted, since split_glb() itself
                    # doesn't return a per-part success flag.
                    if not (MESH_DIR / f"{mesh_id}.json").exists():
                        continue
                    part_id = _add_part_for_converted_mesh(scene, state, mesh_id)
                    if part_id:
                        added.append(part_id)
                if added:
                    _show_toast(state, (printed + "\n" if printed else "") + f"Added parts: {', '.join(added)}")
                else:
                    _show_toast(state, printed or f"Split '{state.import_mesh_selected}' -- no new parts added")
            except convert_mesh.ConvertError as err:
                state.import_mesh_error = str(err)
    if state.import_mesh_error:
        imgui.text_colored(imgui.ImVec4(1.0, 0.4, 0.4, 1.0), state.import_mesh_error)


def _draw_import_animation_content(state: BuilderState) -> None:
    """Content only -- see _draw_import_mesh_content's docstring."""
    imgui.text("Import Animation (from frontend/assets/pending/animations/)")
    if imgui.button("Search...##import-anim-browse"):
        picked = _browse_for_file("glTF/GLB", ("*.glb", "*.gltf"))
        if picked:
            dest = _copy_into_pending(Path(picked), PENDING_ANIMATIONS_DIR)
            state.import_anim_selected = dest.name
            state.import_anim_output_id = dest.stem
            _show_toast(state, f"Added '{dest.name}' to pending/animations/")
    anim_files = _pending_files(PENDING_ANIMATIONS_DIR)
    if not anim_files:
        imgui.text_wrapped("No .glb/.gltf files found in pending/animations/.")
    else:
        current_index = anim_files.index(state.import_anim_selected) if state.import_anim_selected in anim_files else 0
        changed, new_index = imgui.combo("animation file##import", current_index, anim_files)
        state.import_anim_selected = anim_files[new_index]
        if not state.import_anim_output_id:
            state.import_anim_output_id = Path(state.import_anim_selected).stem
        _, state.import_anim_output_id = imgui.input_text("output clip id##import", state.import_anim_output_id)
        _, state.import_anim_name = imgui.input_text(
            "animation name (blank if only one)##import", state.import_anim_name
        )
        _, state.import_anim_no_loop = imgui.checkbox("no loop##import", state.import_anim_no_loop)
        if imgui.button("Convert Animation"):
            try:
                input_path = PENDING_ANIMATIONS_DIR / state.import_anim_selected
                output_path = ANIMATION_DIR / f"animation-transform-{state.import_anim_output_id}.json"
                _, printed = _capture_stdout(
                    convert_animation.convert,
                    str(input_path), str(output_path),
                    clip_id=f"anim-transform-{state.import_anim_output_id}",
                    animation_name=state.import_anim_name or None,
                    loop=not state.import_anim_no_loop,
                )
                refresh_manifest()
                asset_loader.load_manifest()
                state.import_anim_error = ""
                _show_toast(state, printed or f"Imported animation '{state.import_anim_output_id}'")
            except convert_animation.ConvertError as err:
                state.import_anim_error = str(err)
    if state.import_anim_error:
        imgui.text_colored(imgui.ImVec4(1.0, 0.4, 0.4, 1.0), state.import_anim_error)


def _draw_meshes_tab(scene: Scene, state: BuilderState, action_registry) -> None:
    """Content only -- no imgui.begin()/end() of its own. Sidebar tab,
    per direct request: lists meshes imported into this entity (i.e.
    referenced by any of its parts) -- not a global project-wide mesh
    browser (that's the Parts tab's mesh combo, or the launcher's View
    Asset tab). Read-only: change which mesh a part uses from the
    Parts tab, not here.
    """
    mesh_ids = meshes_used_by_parts(state.parts)
    if not mesh_ids:
        imgui.text_wrapped(
            "No meshes imported into this entity yet -- "
            "File > Import Mesh, or Parts > Scaffold Parts from Sockets."
        )
        return

    for mesh_id in mesh_ids:
        used_by = parts_using_mesh(state.parts, mesh_id)
        socket_names = read_mesh_sockets(mesh_id)
        imgui.text(mesh_id)
        imgui.text_wrapped(f"  used by: {', '.join(used_by)}")
        if socket_names:
            imgui.text_wrapped(f"  sockets: {', '.join(socket_names)}")
        imgui.separator()


def _open_animation_editor(scene: Scene, state: BuilderState, animation_id: str) -> None:
    """Load *animation_id*'s clip JSON fresh off disk into the editor's
    in-memory buffer and open the Animation Editor window for it.
    Always reloads from disk rather than reusing EntityRenderer's own
    permanent per-clip cache (`_get_transform_clip`) -- that cache is
    correct for gameplay but, per this file's own established pattern
    (see _sync_preview_definition's docstring), wrong for a live-
    editing tool that needs to see the clip's actual current contents.
    """
    try:
        rel_path = asset_loader.resolve(animation_id)
        full_path = FRONTEND_DIR / rel_path
        clip = json.loads(full_path.read_text(encoding="utf-8"))
    except (ValueError, OSError, json.JSONDecodeError) as err:
        _show_toast(state, f"Could not open animation '{animation_id}': {err}")
        return

    state.editing_animation_id = animation_id
    state.animation_editor_path = full_path
    state.animation_editor_clip = clip
    state.animation_editor_selected_kf = 0 if clip.get("keyframes") else -1
    state.animation_editor_assign_part = ""
    # Immediately pose the preview at whatever keyframe just got
    # auto-selected above, per direct request (see apply_keyframe_preview).
    _sync_preview_definition(scene, state)


def _close_animation_editor(scene: Scene, state: BuilderState) -> None:
    """Deselect whatever animation is currently open, per direct request
    ("make it possible to deselect a currently selected entity['s
    animation]"). Shared by the Animation Editor window's own close (X)
    button and the Animations tab's table (clicking the already-active
    row toggles it off, see _draw_animations_tab) -- previously only the
    window's own close button reached this, so deselecting from the
    Animations tab itself wasn't possible without first finding and
    closing that separate floating window.

    Reverts the live preview back to every part's default rest pose
    (see strip_live_animation_fields, called from _sync_preview_definition
    whenever animation_editor_clip is None) -- otherwise the last-
    previewed keyframe's pose, or whatever was mid-playback, would keep
    overriding the assigned part(s) forever.
    """
    state.editing_animation_id = None
    state.animation_editor_clip = None
    state.animation_editor_path = None
    state.animation_editor_selected_kf = -1
    _sync_preview_definition(scene, state)


def _save_animation_editor(scene: Scene, state: BuilderState) -> None:
    """Write the in-progress clip buffer back to
    state.animation_editor_path, then stamp animation_id onto any
    newly-assigned part that doesn't already have one (see
    stamp_animation_id_for_assigned_parts) -- so assigning a part to a
    keyframe here is enough by itself to make it actually play, no
    separate trip to the Parts tab required.

    **Real reported bug, fixed here**: stamping only ever updated
    `state.parts` in memory -- the entity's own saved file
    (`entity-<id>.json`) was untouched, so the stamp survived only
    until the next reload. A user created a clip, assigned a part,
    edited it, and clicked Save here -- the clip file itself was
    written correctly (confirmed live in `frontend/assets/data/
    animation/`) -- but never did a separate File > Save on the entity
    afterward, so the *next* session's `load_entity_definition()`
    reloaded that part with no animation_id, and `animations_used_by_parts`
    (what the Animations tab's table actually reads) silently lost the
    clip -- it was still on disk and still in the manifest, just no
    longer referenced by anything. Per direct decision, this is fixed
    by persisting the entity immediately whenever a part actually gets
    newly stamped (mirroring `save_entity_definition`'s own "Save"
    exactly) rather than only warning about the missing step --
    deliberately breaking from this tool's usual "nothing but File >
    Save touches entity-<id>.json" rule for this one case, since
    leaving the stamp unpersisted is what caused the bug. Only fires
    when `state.entity_id` is already set (an entity that's never been
    saved at all has nowhere to persist to yet -- same gate File >
    Save's own Save/Save As split already uses); this also persists
    whatever else is currently sitting in `state.parts` from other,
    unrelated in-progress edits, an accepted tradeoff of the decision
    to auto-save here rather than only warn.
    """
    clip = state.animation_editor_clip
    animation_id = state.editing_animation_id
    path = state.animation_editor_path
    if clip is None or animation_id is None or path is None:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clip, indent=2) + "\n", encoding="utf-8")

    assigned_ids = parts_assigned_in_clip(clip)
    stamped = stamp_animation_id_for_assigned_parts(state.parts, assigned_ids, animation_id)

    entity_saved = False
    if stamped:
        _sync_preview_definition(scene, state)
        if state.entity_id is not None:
            save_entity_definition({"parts": state.parts, "name": state.entity_name}, state.entity_id)
            entity_saved = True

    message = f"Saved animation '{animation_id}'"
    if stamped:
        message += f" (assigned to part(s): {', '.join(stamped)}"
        message += ", entity saved)" if entity_saved else ", entity NOT saved yet -- use File > Save As first)"
    _show_toast(state, message)


def _draw_animations_tab(scene: Scene, state: BuilderState, action_registry) -> None:
    """Content only -- no imgui.begin()/end() of its own. Sidebar tab,
    per direct request: lists animation clips imported into this
    entity (i.e. referenced by any part's `animation_id`/
    `action_animations`) -- same shape as the Meshes tab, not a global
    project-wide animation browser. Mostly read-only (assign/change a
    part's `animation_id`/`action_animations` from the Parts tab,
    preview playback from the Playback panel), except for two actions
    added per direct request: "New Animation" (creates an empty
    multi-part rig clip -- see new_animation_clip) and a table of this
    entity's existing animations where selecting a row makes it
    "active" -- confirmed with the user this means opening it in the
    Animation Editor (see _draw_animation_editor_window), the same
    action the previous per-row "Edit" button performed; the table's
    selected row simply tracks whichever clip is currently open
    (`state.editing_animation_id`) instead of needing a separate
    button per row. A brand-new clip has no part usage yet, so it
    won't itself appear in this table until Save actually assigns it
    to a part -- "New Animation" opens its editor immediately, which is
    the intended way to reach it before then.

    Deselecting, per direct request ("make it possible to deselect a
    currently selected entity['s animation]"): clicking the already-
    active row, or the "Deselect Animation" button shown whenever one is
    active, both call `_close_animation_editor` -- the same path the
    Animation Editor window's own close (X) button uses -- which returns
    every part to its default rest pose (see strip_live_animation_fields).
    """
    imgui.text("New Animation")
    _, state.new_animation_name = imgui.input_text("name##new-animation", state.new_animation_name)
    if imgui.button("Create##new-animation"):
        name = state.new_animation_name.strip()
        if not name:
            state.new_animation_error = "Name can't be empty."
        else:
            path = new_animation_clip_path(name)
            if path.exists():
                state.new_animation_error = f"'{path.name}' already exists."
            else:
                clip_id = new_animation_clip_id(name)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(new_animation_clip(clip_id), indent=2) + "\n", encoding="utf-8")
                refresh_manifest()
                asset_loader.load_manifest()
                state.new_animation_name = ""
                state.new_animation_error = ""
                _show_toast(state, f"Created animation '{clip_id}'")
                _open_animation_editor(scene, state, clip_id)
    if state.new_animation_error:
        imgui.text_colored(imgui.ImVec4(1.0, 0.4, 0.4, 1.0), state.new_animation_error)
    imgui.separator()

    animation_ids = animations_used_by_parts(state.parts)
    if not animation_ids:
        imgui.text_wrapped(
            "No animations assigned to this entity yet -- "
            "assign animation_id/action_animations per part in the Parts tab, "
            "or File > Import Animation to convert a new clip."
        )
        return

    imgui.text_wrapped(
        "Select a row to make it active (opens it in the Animation Editor); "
        "click the active row again to deselect it and return every part "
        "to its default rest pose."
    )
    if state.editing_animation_id is not None and imgui.button("Deselect Animation##anim-deselect"):
        _close_animation_editor(scene, state)
    table_flags = imgui.TableFlags_.borders | imgui.TableFlags_.row_bg | imgui.TableFlags_.resizable
    if imgui.begin_table("AnimationsTable", 2, table_flags):
        imgui.table_setup_column("Animation")
        imgui.table_setup_column("Used By")
        imgui.table_headers_row()

        for animation_id in animation_ids:
            imgui.table_next_row()
            imgui.table_next_column()
            is_active = state.editing_animation_id == animation_id
            selected, _ = imgui.selectable(
                f"{animation_id}##anim-row-{animation_id}",
                is_active,
                imgui.SelectableFlags_.span_all_columns,
            )
            if selected:
                if is_active:
                    _close_animation_editor(scene, state)
                else:
                    _open_animation_editor(scene, state, animation_id)

            imgui.table_next_column()
            usage_labels = []
            for usage in parts_using_animation(state.parts, animation_id):
                role = usage["role"]
                if role == "animation_id":
                    usage_labels.append(f"{usage['part']} (loop)")
                else:
                    usage_labels.append(f"{usage['part']} (action: {role.split(':', 1)[1]})")
            imgui.text_wrapped(", ".join(usage_labels))

        imgui.end_table()


_TIMELINE_HEIGHT = 130.0

# Fixed sidebar width, per direct request -- used to track the
# now-removed standalone Playback window's own current width (see
# _draw_sidebar's own docstring); with that window gone (its controls
# folded into the Timeline, below), there's nothing left to size
# against, so this is just a plain constant now.
_SIDEBAR_WIDTH = 400.0


def _timeline_visible(state: BuilderState) -> bool:
    """Whether the full-width Timeline window (see
    _draw_timeline_window) is currently showing -- same visibility gate
    as the Animation Editor window itself, since the timeline has
    nothing to manage without an open clip. Also read by _draw_sidebar
    to shrink its own height so the two never overlap, per direct
    request -- a plain function (not inlined at both call sites) so the
    two windows' visibility can never drift out of sync with each other.
    """
    return state.animation_editor_clip is not None


def _draw_timeline_window(scene: Scene, state: BuilderState) -> None:
    """Full-width window docked just above the always-on bottom bar,
    per direct request ("make the timeline menu the full width of the
    screen, slightly above the bottom menu bar"). Split out of the
    Animation Editor window itself (which used to hold this same strip
    in a cramped, fixed-size child region) so the timeline gets the
    full screen width to lay out keyframes in -- a no-op when no clip
    is open (`_timeline_visible`), the same gate `_draw_animation_editor_window`
    uses, so the two windows always appear/disappear together.

    Pinned to position/size every frame (`Cond_.always`, matching
    `_draw_sidebar`'s own reasoning) rather than just on first use, so
    it can't be dragged or resized away from where it belongs.
    `_draw_sidebar` shrinks its own height to stop just above this
    window whenever `_timeline_visible` is true, per direct request
    ("make the sidebar window conform so it doesn't overlap") --  see
    that function's own note.

    Also houses every control that used to live in the now-removed
    standalone Playback window, per direct request ("move the options
    from the playback window to the timeline window") -- Play/Pause,
    and the action_animations trigger/revert-to-idle buttons.
    `state.paused` defaults to True now (per that same direct request),
    so a freshly-opened entity doesn't start animating before anyone's
    looked at it. `_TIMELINE_HEIGHT` was widened (90 -> 130) to fit the
    extra row without cramming the keyframe strip below it.

    Per direct follow-up request, the plain "Paused" checkbox is now a
    single button that swaps its own label between "> Play" and
    "|| Pause" (ASCII, not the Unicode ▶/⏸ glyphs -- this codebase loads
    no custom/icon font, only Dear ImGui's default one, which doesn't
    include those code points; they'd render as missing-glyph boxes)
    depending on `state.paused`, always showing the action a click will
    perform -- the standard media-player convention. See
    `_toggle_timeline_playback` for the real playback-not-actually-
    starting bug this click handler also fixes.
    """
    if not _timeline_visible(state):
        return

    from client.engine.gizmo import to_imvec2

    viewport = imgui.get_main_viewport()
    bottom_bar_height = imgui.get_frame_height()
    pos_x = viewport.work_pos.x
    pos_y = viewport.work_pos.y + viewport.work_size.y - bottom_bar_height - _TIMELINE_HEIGHT
    width = viewport.work_size.x

    imgui.set_next_window_pos(to_imvec2((pos_x, pos_y)), imgui.Cond_.always)
    imgui.set_next_window_size(to_imvec2((width, _TIMELINE_HEIGHT)), imgui.Cond_.always)
    imgui.begin(
        f"Timeline - {state.editing_animation_id}###Timeline",
        None,
        imgui.WindowFlags_.no_move | imgui.WindowFlags_.no_resize,
    )

    clip = state.animation_editor_clip
    keyframes = clip.setdefault("keyframes", [])

    if imgui.button("Add Keyframe##timeline"):
        add_keyframe(keyframes)
        state.animation_editor_selected_kf = len(keyframes) - 1
        _sync_preview_definition(scene, state)
    imgui.same_line()
    if imgui.button("Duplicate Keyframe##timeline"):
        new_keyframe = duplicate_keyframe(keyframes, state.animation_editor_selected_kf)
        if new_keyframe is None:
            _show_toast(state, "No keyframe selected to duplicate.")
        else:
            state.animation_editor_selected_kf = len(keyframes) - 1
            state.animation_editor_assign_part = ""
            state.timeline_playback_ms = new_keyframe["time_ms"]
            _sync_preview_definition(scene, state)
            _show_toast(state, f"Duplicated keyframe to {new_keyframe['time_ms']:.0f}ms")
    imgui.same_line()
    _, clip["loop"] = imgui.checkbox("loop##timeline", clip.get("loop", True))
    imgui.same_line()
    play_pause_label = "> Play##timeline" if state.paused else "|| Pause##timeline"
    if imgui.button(play_pause_label):
        _toggle_timeline_playback(scene, state)

    entity = scene.entities.get(_PREVIEW_ENTITY_ID)
    action_names = sorted(
        {name for part in state.parts for name in (part.get("action_animations") or {}).keys()}
    )
    if action_names:
        imgui.text("Trigger action_animations (sets entity.state):")
        imgui.same_line()
        for name in action_names:
            if imgui.button(f"Trigger '{name}'##timeline") and entity is not None:
                entity["state"] = name
                _show_toast(state, f"Triggered '{name}'")
            imgui.same_line()
        if imgui.button("Revert to idle##timeline") and entity is not None:
            entity["state"] = "idle"
            _show_toast(state, "Reverted to idle")

    imgui.begin_child(
        "TimelineKeyframeStrip",
        imgui.ImVec2(0, 0),
        imgui.ChildFlags_.borders,
        imgui.WindowFlags_.horizontal_scrollbar,
    )
    for index, kf in enumerate(keyframes):
        if index > 0:
            imgui.same_line()
        selected = index == state.animation_editor_selected_kf
        if selected:
            imgui.push_style_color(imgui.Col_.button, imgui.ImVec4(0.2, 0.5, 0.9, 1.0))
        if imgui.button(f"{kf['time_ms']:.0f}ms##timeline-kf{index}"):
            state.animation_editor_selected_kf = index
            state.animation_editor_assign_part = ""
            # Also seeks playback to this keyframe's own time, so
            # clicking a keyframe acts as a scrubber whether paused
            # (shows this exact pose, via _sync_preview_definition
            # below) or already playing (_update_playback_pose picks
            # up the new time_ms on the very next frame).
            state.timeline_playback_ms = kf["time_ms"]
            _sync_preview_definition(scene, state)
        if selected:
            imgui.pop_style_color()
    if not keyframes:
        imgui.text_wrapped("No keyframes yet -- Add Keyframe above.")
    imgui.end_child()

    imgui.end()


_EASING_PREVIEW_SIZE = 90.0
_EASING_PREVIEW_Y_MIN = -0.4
_EASING_PREVIEW_Y_MAX = 1.4


def _draw_easing_curve_preview(x1: float, y1: float, x2: float, y2: float) -> None:
    """Small live-updating plot of the cubic-bezier easing curve
    currently dialed in for a part's keyframe transition -- per direct
    request ("[I'd rather expose a more flexible curve] ... same
    numbers plus a live curve preview"), since four raw control-point
    numbers with no visual feedback is a rough way to actually author a
    curve's shape. Hand-samples the curve and draws it with plain
    `ImDrawList.add_line` calls -- the same technique `client/engine/
    gizmo.py`'s own overlay already uses -- rather than imgui's built-in
    `plot_lines`, which needs a numpy `ndarray` and this codebase's own
    "nothing should import numpy directly" rule (requirements.txt) rules
    that out.

    The plotted y-range is padded beyond [0, 1] (see
    _EASING_PREVIEW_Y_MIN/_MAX) so an overshoot/"back"-style curve
    (y1/y2 outside [0, 1], intentionally left unclamped -- see
    transform_clip.py's own docstring) stays visible instead of
    clipping flat against the box edges.
    """
    size = _EASING_PREVIEW_SIZE
    origin = imgui.get_cursor_screen_pos()
    draw_list = imgui.get_window_draw_list()
    y_span = _EASING_PREVIEW_Y_MAX - _EASING_PREVIEW_Y_MIN

    def to_screen(t: float, y: float):
        screen_x = origin.x + t * size
        screen_y = origin.y + size * (1.0 - (y - _EASING_PREVIEW_Y_MIN) / y_span)
        return imgui.ImVec2(screen_x, screen_y)

    top_left = imgui.ImVec2(origin.x, origin.y)
    bottom_right = imgui.ImVec2(origin.x + size, origin.y + size)
    draw_list.add_rect_filled(top_left, bottom_right, imgui.IM_COL32(30, 30, 30, 255))
    draw_list.add_rect(top_left, bottom_right, imgui.IM_COL32(90, 90, 90, 255))
    # Faint reference diagonal -- what this transition would look like
    # with no easing at all (the pre-this-feature, always-linear behavior).
    draw_list.add_line(to_screen(0.0, 0.0), to_screen(1.0, 1.0), imgui.IM_COL32(70, 70, 70, 255))

    steps = 24
    previous = to_screen(0.0, transform_clip.cubic_bezier_ease(0.0, x1, y1, x2, y2))
    for i in range(1, steps + 1):
        t = i / steps
        point = to_screen(t, transform_clip.cubic_bezier_ease(t, x1, y1, x2, y2))
        draw_list.add_line(previous, point, imgui.IM_COL32(255, 200, 60, 255), 2.0)
        previous = point

    # Control-point handles, so it's visible *why* the curve bends the
    # way it does, not just the resulting shape.
    draw_list.add_circle_filled(to_screen(x1, y1), 3.0, imgui.IM_COL32(90, 170, 255, 255))
    draw_list.add_circle_filled(to_screen(x2, y2), 3.0, imgui.IM_COL32(90, 170, 255, 255))

    imgui.dummy(imgui.ImVec2(size, size))


def _draw_animation_editor_window(scene: Scene, state: BuilderState) -> None:
    """Selected-keyframe detail editor, per direct request -- opened
    via the Animations tab's "New Animation"/"Edit". A no-op (draws
    nothing) when no clip is currently open. Keyframe selection/
    creation itself lives in the separate, full-width `_draw_timeline_window`
    (see that function's own docstring for why); this window shows only
    whichever keyframe is currently selected there: its gap-from-
    previous field, its assigned-parts list (each part editable via
    drag_float3 position/rotation/scale), an "All Parts" rigid-group
    transform control that applies a shared position/rotation/scale
    delta to every part in the entity at once (per direct request --
    see compute_group_transform_delta/apply_rigid_group_delta), a combo
    to assign one more of this entity's parts into it, and Save. Nothing
    here touches disk
    until "Save" (_save_animation_editor) -- same buffer-then-explicit-
    save shape as the Parts tab's own per-part fields, since this tool
    has no undo stack (see the module docstring).

    Every action that changes a previewed part's transform calls
    `_sync_preview_definition` (see apply_keyframe_preview) so the real
    orbit-preview mesh visibly tracks whatever's being edited, per
    direct request -- the same "any edit re-syncs the live preview"
    convention every other panel in this file already follows for its
    own fields.
    """
    if state.animation_editor_clip is None:
        return

    clip = state.animation_editor_clip
    keyframes = clip.setdefault("keyframes", [])

    expanded, keep_open = imgui.begin(f"Animation Editor - {state.editing_animation_id}###AnimationEditor", True)
    if expanded:
        index = state.animation_editor_selected_kf
        if not (0 <= index < len(keyframes)):
            imgui.text_wrapped("No keyframe selected -- pick one in the Timeline below.")
        if 0 <= index < len(keyframes):
            keyframe = keyframes[index]
            imgui.separator()
            imgui.text(f"Keyframe {index} -- {keyframe['time_ms']:.0f}ms")

            gap = keyframe_gap(keyframes, index)
            changed, new_gap = imgui.drag_float(f"gap from previous (ms)##kf{index}", gap, 10.0, 0.0, 100000.0)
            if changed:
                set_keyframe_gap(keyframes, index, new_gap)

            if imgui.button(f"Delete Keyframe##kf{index}"):
                remove_keyframe(keyframes, index)
                state.animation_editor_selected_kf = -1
                _sync_preview_definition(scene, state)
            else:
                imgui.separator()
                imgui.text("Parts in this keyframe")
                assigned_ids = sorted((keyframe.get("parts") or {}).keys())
                if not assigned_ids:
                    imgui.text_wrapped("No parts assigned to this keyframe yet.")
                position_speed = position_drag_speed(entity_bounding_radius(state.parts))

                # "All Parts" rigid-group transform, per direct request
                # ("apply transformations to every mesh/part in the
                # entity as one") -- moves/rotates/scales every part in
                # the entity together, rigidly, preserving each part's
                # pose relative to the others (not the same as setting
                # every part to the same absolute transform, which would
                # visually collapse them together). Any part not yet
                # assigned to this keyframe is auto-assigned (identity
                # transform) the moment this control is touched, since
                # "every mesh/part in the entity" means literally every
                # part, not just whichever ones happened to already be
                # in this keyframe.
                #
                # The three fields below are a running total *since
                # this control was last reset*, not a real transform
                # read off any part -- each edit is applied to every
                # part as the delta from the control's previous value
                # (see compute_group_transform_delta). The control
                # resets to identity whenever the selected keyframe
                # changes, since a stale running total from a different
                # keyframe would be meaningless here.
                if state.animation_editor_group_kf_index != index:
                    state.animation_editor_group_position = [0.0, 0.0, 0.0]
                    state.animation_editor_group_rotation = [0.0, 0.0, 0.0]
                    state.animation_editor_group_scale = [1.0, 1.0, 1.0]
                    state.animation_editor_group_kf_index = index

                if imgui.collapsing_header(f"All Parts (apply to every part together)##kf{index}group"):
                    imgui.text_wrapped(
                        "Moves/rotates/scales every part in the entity together, as one -- "
                        "each part keeps its pose relative to the others."
                    )
                    group_changed = False

                    changed, new_value = imgui.drag_float3(
                        f"position##kf{index}-group", state.animation_editor_group_position, position_speed
                    )
                    new_group_position = list(new_value)
                    group_changed = group_changed or changed

                    changed, new_value = imgui.drag_float3(
                        f"rotation##kf{index}-group", state.animation_editor_group_rotation, 0.01
                    )
                    new_group_rotation = list(new_value)
                    group_changed = group_changed or changed

                    changed, new_value = imgui.drag_float3(
                        f"scale##kf{index}-group", state.animation_editor_group_scale, 0.01
                    )
                    new_group_scale = list(new_value)
                    group_changed = group_changed or changed

                    if group_changed:
                        delta_position, delta_rotation, scale_ratio = compute_group_transform_delta(
                            state.animation_editor_group_position,
                            new_group_position,
                            state.animation_editor_group_rotation,
                            new_group_rotation,
                            state.animation_editor_group_scale,
                            new_group_scale,
                        )
                        for part in state.parts:
                            part_id = part.get("id")
                            if part_id and part_id not in (keyframe.get("parts") or {}):
                                assign_part_to_keyframe(keyframe, part_id)
                        all_part_ids = [p.get("id") for p in state.parts if p.get("id")]
                        apply_rigid_group_delta(keyframe, all_part_ids, delta_position, delta_rotation, scale_ratio)

                        state.animation_editor_group_position = new_group_position
                        state.animation_editor_group_rotation = new_group_rotation
                        state.animation_editor_group_scale = new_group_scale
                        assigned_ids = sorted((keyframe.get("parts") or {}).keys())
                        _sync_preview_definition(scene, state)

                for part_id in assigned_ids:
                    transform = keyframe["parts"][part_id]
                    if imgui.collapsing_header(f"{part_id}##kf{index}part"):
                        position = transform.get("position", [0.0, 0.0, 0.0])
                        changed, new_value = imgui.drag_float3(f"position##kf{index}-{part_id}", position, position_speed)
                        if changed:
                            transform["position"] = list(new_value)
                            _sync_preview_definition(scene, state)

                        rotation = transform.get("rotation", [0.0, 0.0, 0.0])
                        changed, new_value = imgui.drag_float3(f"rotation##kf{index}-{part_id}", rotation, 0.01)
                        if changed:
                            transform["rotation"] = list(new_value)
                            _sync_preview_definition(scene, state)

                        scale = transform.get("scale", [1.0, 1.0, 1.0])
                        changed, new_value = imgui.drag_float3(f"scale##kf{index}-{part_id}", scale, 0.01)
                        if changed:
                            transform["scale"] = list(new_value)
                            _sync_preview_definition(scene, state)

                        # Transition curve into this keyframe, per direct
                        # request ("edit the transition formula for each
                        # part in a keyframe" / "I'd rather expose a more
                        # flexible curve" than a fixed named-easing set) --
                        # a cubic-bezier control-point pair, the same
                        # cubic-bezier(x1,y1,x2,y2) convention CSS/After
                        # Effects use (see transform_clip.py's own
                        # docstring/cubic_bezier_ease). Governs the
                        # segment from the *previous* keyframe up to this
                        # one -- "ease into this pose" -- which is why
                        # it's stored per-part on this keyframe's own
                        # transform dict, right alongside position/
                        # rotation/scale, not on the segment's other end.
                        easing_changed = False
                        x1, y1, x2, y2 = transform_clip.resolve_easing(transform)
                        imgui.text_wrapped("Transition curve (cubic-bezier, eases into this pose):")
                        changed, new_value = imgui.drag_float2(f"P1##kf{index}-{part_id}-easing", [x1, y1], 0.01, -2.0, 2.0)
                        if changed:
                            x1, y1 = new_value
                            easing_changed = True
                        changed, new_value = imgui.drag_float2(f"P2##kf{index}-{part_id}-easing", [x2, y2], 0.01, -2.0, 2.0)
                        if changed:
                            x2, y2 = new_value
                            easing_changed = True
                        if easing_changed:
                            # x stays a valid function of time; y is
                            # deliberately left unclamped so an overshoot/
                            # "back"-style curve is still possible.
                            x1 = min(1.0, max(0.0, x1))
                            x2 = min(1.0, max(0.0, x2))
                            transform["easing"] = [x1, y1, x2, y2]
                            _sync_preview_definition(scene, state)
                        _draw_easing_curve_preview(x1, y1, x2, y2)

                        # Rotation/scale pivot, per direct request ("allow
                        # setting an origin point to apply the animation
                        # transformation from") -- clip-level, not
                        # per-keyframe (shared across every keyframe this
                        # part appears in, since a hinge/pivot point is a
                        # property of how the part is rigged, not
                        # something that would sensibly change keyframe to
                        # keyframe within one clip -- see transform_clip
                        # .py's own "origins" map docstring).
                        origins = clip.setdefault("origins", {})
                        origin = origins.get(part_id, [0.0, 0.0, 0.0])
                        imgui.text_wrapped("Origin (pivot point, shared across every keyframe for this part):")
                        changed, new_value = imgui.drag_float3(f"origin##kf{index}-{part_id}", origin, position_speed)
                        if changed:
                            origins[part_id] = list(new_value)
                            _sync_preview_definition(scene, state)

                        if imgui.button(f"Remove from keyframe##kf{index}-{part_id}"):
                            remove_part_from_keyframe(keyframe, part_id)
                            _sync_preview_definition(scene, state)

                unassigned = [p.get("id") for p in state.parts if p.get("id") and p.get("id") not in assigned_ids]
                if unassigned:
                    imgui.separator()
                    if state.animation_editor_assign_part not in unassigned:
                        state.animation_editor_assign_part = unassigned[0]
                    combo_index = unassigned.index(state.animation_editor_assign_part)
                    changed, new_index = imgui.combo("assign part##kf-assign", combo_index, unassigned)
                    if changed:
                        state.animation_editor_assign_part = unassigned[new_index]
                    imgui.same_line()
                    if imgui.button("Assign to Keyframe##kf-assign"):
                        assign_part_to_keyframe(keyframe, state.animation_editor_assign_part)
                        state.animation_editor_assign_part = ""
                        _sync_preview_definition(scene, state)

        imgui.separator()
        if imgui.button("Save##animation-editor"):
            _save_animation_editor(scene, state)

    imgui.end()
    if not keep_open:
        _close_animation_editor(scene, state)


def _draw_materials_tab(scene: Scene, state: BuilderState, action_registry) -> None:
    """Content only -- no imgui.begin()/end() of its own. Originally a
    standalone "Materials" window; folded into the right-side sidebar
    (`_draw_sidebar`) as a tab, per direct request. Any window chrome
    (title, sizing, position) is the sidebar's job now, not this
    function's -- keeps this reusable if a future tab needs the same
    content elsewhere. Takes the same `(scene, state, action_registry)`
    signature every sidebar tab does, even though this one only needs
    `state` -- see `_SIDEBAR_TABS`' own note on why.
    """
    images = _pending_images()
    if not images:
        imgui.text_wrapped("No .png/.jpg files found in pending/.")
        return

    def _picker(label: str, current: "str | None") -> "str | None":
        options = ["(none)"] + images
        current_index = options.index(current) if current in options else 0
        changed, new_index = imgui.combo(label, current_index, options)
        return None if new_index == 0 else options[new_index]

    _, state.material_id_text = imgui.input_text("material id##material", state.material_id_text)
    state.material_albedo_selected = _picker("albedo##material", state.material_albedo_selected)
    state.material_r_selected = _picker("roughness (R)##material", state.material_r_selected)
    state.material_g_selected = _picker("emission mask (G)##material", state.material_g_selected)
    state.material_b_selected = _picker("palette index (B)##material", state.material_b_selected)
    state.material_a_selected = _picker("alpha mask (A)##material", state.material_a_selected)

    if imgui.button("Pack & Save Material"):
        if not state.material_id_text.strip():
            state.material_error = "Material id can't be empty."
        elif not state.material_albedo_selected:
            state.material_error = "Albedo image is required."
        else:
            try:
                _save_material(
                    state.material_id_text.strip(),
                    PENDING_DIR / state.material_albedo_selected,
                    PENDING_DIR / state.material_r_selected if state.material_r_selected else None,
                    PENDING_DIR / state.material_g_selected if state.material_g_selected else None,
                    PENDING_DIR / state.material_b_selected if state.material_b_selected else None,
                    PENDING_DIR / state.material_a_selected if state.material_a_selected else None,
                )
                state.material_error = ""
                _show_toast(state, f"Saved material '{state.material_id_text}'")
            except Exception as err:  # noqa: BLE001 -- surface any packing/IO failure to the panel
                state.material_error = str(err)
    if state.material_error:
        imgui.text_colored(imgui.ImVec4(1.0, 0.4, 0.4, 1.0), state.material_error)


# Sidebar tabs -- (label, content-drawing function) pairs, each function
# taking the uniform `(scene, state, action_registry)` signature and
# drawing directly into whatever tab item is currently active (no
# imgui.begin()/end() of its own -- see _draw_materials_tab's
# docstring). The uniform signature means a tab that doesn't need
# `scene`/`action_registry` (Materials) just ignores them, rather than
# _draw_sidebar() needing per-tab special-casing. Append future
# folded-in panels here; _draw_sidebar() itself never needs to change
# to gain a new tab.
_SIDEBAR_TABS = [
    ("Parts", _draw_parts_tab),
    ("Meshes", _draw_meshes_tab),
    ("Animations", _draw_animations_tab),
    ("Materials", _draw_materials_tab),
]


def _draw_sidebar(scene: Scene, state: BuilderState, action_registry) -> None:
    """Right-docked, tabbed panel -- generic container for "any menu
    that gets put in this side bar" (currently Parts and Materials).
    Pinned to the right edge every frame (`Cond_.always`, not just on
    first use) so it can't drift or be resized away from where it
    belongs, same reasoning as launcher.py's fixed-size window. Width
    is a fixed constant (`_SIDEBAR_WIDTH`) -- it used to track the
    now-removed standalone Playback window's own current width (per an
    earlier direct request), but that window's controls folded into the
    Timeline window (see _draw_timeline_window), leaving no other
    window left to size against.

    Height additionally shrinks by `_TIMELINE_HEIGHT` whenever the
    Timeline window is showing (`_timeline_visible`), per direct
    request ("make the sidebar window conform so it doesn't overlap")
    -- the Timeline is full-width (see its own docstring), so without
    this the sidebar's bottom-right corner would sit underneath it.
    """
    if not state.show_sidebar:
        return

    from client.engine.gizmo import to_imvec2

    viewport = imgui.get_main_viewport()
    width = _SIDEBAR_WIDTH
    bottom_bar_height = imgui.get_frame_height()
    timeline_height = _TIMELINE_HEIGHT if _timeline_visible(state) else 0.0
    pos_x = viewport.work_pos.x + viewport.work_size.x - width
    pos_y = viewport.work_pos.y
    height = viewport.work_size.y - bottom_bar_height - timeline_height

    imgui.set_next_window_pos(to_imvec2((pos_x, pos_y)), imgui.Cond_.always)
    imgui.set_next_window_size(to_imvec2((width, height)), imgui.Cond_.always)
    imgui.begin("Sidebar", None, imgui.WindowFlags_.no_move | imgui.WindowFlags_.no_resize)

    if imgui.begin_tab_bar("SidebarTabs"):
        for label, draw_content in _SIDEBAR_TABS:
            selected, _ = imgui.begin_tab_item(label)
            if selected:
                draw_content(scene, state, action_registry)
                imgui.end_tab_item()
        imgui.end_tab_bar()

    imgui.end()


def _save_material(
    material_id: str,
    albedo_src: Path,
    r_src: "Path | None",
    g_src: "Path | None",
    b_src: "Path | None",
    a_src: "Path | None",
) -> Path:
    """Copy the picked albedo image and pack the (optional) four
    channel images into a param map, then write material-<id>.json in
    the shape material_loader.py's MaterialLoader.load() reads.
    Import-and-run only -- see this module's docstring for why live
    painting is deliberately not built here.
    """
    TEXTURES_DIR.mkdir(parents=True, exist_ok=True)
    albedo_dest = TEXTURES_DIR / f"{material_id}_albedo{albedo_src.suffix.lower()}"
    shutil.copyfile(albedo_src, albedo_dest)

    param_map_rel = None
    if any((r_src, g_src, b_src, a_src)):
        PARAM_MAPS_DIR.mkdir(parents=True, exist_ok=True)
        param_map_dest = PARAM_MAPS_DIR / f"{material_id}_params.png"
        pack_param_map.pack(
            str(r_src) if r_src else None,
            str(g_src) if g_src else None,
            str(b_src) if b_src else None,
            str(a_src) if a_src else None,
            str(param_map_dest),
        )
        param_map_rel = param_map_dest.relative_to(FRONTEND_DIR).as_posix()

    material_json = {
        "id": f"material-{material_id}",
        "name": material_id,
        "atlas": albedo_dest.relative_to(FRONTEND_DIR).as_posix(),
        "param_map": param_map_rel,
        "overlays": [],
    }
    MATERIAL_DIR.mkdir(parents=True, exist_ok=True)
    out_path = MATERIAL_DIR / f"material-{material_id}.json"
    out_path.write_text(json.dumps(material_json, indent=2) + "\n", encoding="utf-8")
    refresh_manifest()
    asset_loader.load_manifest()
    return out_path


def _make_key_handler(state: BuilderState):
    """F11 toggles the top menu bar -- same key, same guard against
    stealing focus from an active imgui text field, as area_viewer.py's
    own `_make_key_handler`. Z toggles solid/wireframe mesh display,
    mirroring the View > Mesh > Solid/Wireframe menu items above.
    Deliberately minimal otherwise: this tool has no undo stack, gizmo
    modes, or grid to bind shortcuts for.
    """

    def on_key(event: dict) -> None:
        if event["event_type"] != "key_down":
            return
        if imgui.get_io().want_capture_keyboard or imgui.get_io().want_text_input:
            return
        if event["key"].lower() == "f11":
            state.menu_bar_visible = not state.menu_bar_visible
        elif event["key"].lower() == "z":
            state.wireframe = not state.wireframe

    return on_key


def _draw_menu_bar(scene: Scene, state: BuilderState) -> None:
    """File/Parts/View menu bar, toggled by F11 -- mirrors area_viewer
    .py's `_draw_menu_bar` shape (Save/Save As fold, right-aligned id
    label, per-panel View toggles, "Hide Menu Bar" self-reference). No
    Edit menu: this tool has no undo stack (see entity-builder
    .prompt.md's own note that template edits here are
    buffer-then-explicit-save, not undo-tracked, matching
    area_viewer.py's template-edit precedent).
    """
    if not state.menu_bar_visible:
        return
    if not imgui.begin_main_menu_bar():
        return

    if imgui.begin_menu("File"):
        if state.entity_id is not None:
            if imgui.menu_item_simple("Save", "Ctrl+S", False, True):
                save_entity_definition({"parts": state.parts, "name": state.entity_name}, state.entity_id)
                _show_toast(state, f"Saved entity '{state.entity_id}'")
        else:
            # No entity_id yet (brand-new, never-saved definition) --
            # "Save As" needs a name first, so it's a submenu holding an
            # inline text field instead of a plain menu_item.
            if imgui.begin_menu("Save As"):
                _, state.save_as_name = imgui.input_text("Name", state.save_as_name)
                if imgui.button("Save") and state.save_as_name.strip():
                    # id and name both start identical to the typed text
                    # (same "diverge only once explicitly renamed" pattern
                    # parts use) -- entity_name stays freely editable
                    # afterward via the Entity Information window, entity_id
                    # never changes again.
                    state.entity_id = state.save_as_name.strip()
                    state.entity_name = state.save_as_name.strip()
                    save_entity_definition({"parts": state.parts, "name": state.entity_name}, state.entity_id)
                    _show_toast(state, f"Saved entity '{state.entity_id}'")
                    imgui.close_current_popup()
                imgui.end_menu()
        imgui.separator()
        # Folded in from the old standalone "Import" window, per direct
        # request -- same "submenu holding real widgets" pattern Save
        # As already established just above, not a plain menu_item
        # (both need file combos/text fields/buttons, not a single
        # click action).
        if imgui.begin_menu("Import Mesh"):
            _draw_import_mesh_content(scene, state)
            imgui.end_menu()
        if imgui.begin_menu("Import Animation"):
            _draw_import_animation_content(state)
            imgui.end_menu()
        imgui.separator()
        if imgui.menu_item_simple("Back to Launcher"):
            state.want_back_to_launcher = True
        if imgui.menu_item_simple("Exit"):
            state.want_exit = True
        imgui.end_menu()

    # New top-level menu, per direct request: houses "Scaffold Parts
    # from Sockets" (formerly its own standalone window), the same
    # "submenu holding real widgets" pattern as File's own submenus.
    # The Parts *list* itself lives in the sidebar now (below), not
    # here -- this menu is for Parts-related *actions*, not the list.
    if imgui.begin_menu("Parts"):
        if imgui.begin_menu("Scaffold Parts from Sockets"):
            _draw_scaffold_content(scene, state)
            imgui.end_menu()
        imgui.end_menu()

    if imgui.begin_menu("View"):
        _, state.show_entity_info = imgui.menu_item("Entity Information", "", state.show_entity_info)
        _, state.show_sidebar = imgui.menu_item("Sidebar (Parts/Materials)", "", state.show_sidebar)
        # Solid/Wireframe as two mutually-exclusive items (each sets an
        # explicit value on click, not a toggle) rather than one
        # checkbox, so the currently-active mode always shows a
        # checkmark -- WebGPU has no native polygon wireframe fill mode
        # (see Mesh.wireframe_index_buffer's docstring for how this is
        # actually drawn: a real line-list over the mesh's edges). "Z"
        # shortcut (handled in `_make_key_handler`) toggles between the
        # two rather than picking one explicitly, same as it would via
        # these menu items in sequence.
        if imgui.begin_menu("Mesh"):
            if imgui.menu_item_simple("Solid", "Z", not state.wireframe, True):
                state.wireframe = False
            if imgui.menu_item_simple("Wireframe", "Z", state.wireframe, True):
                state.wireframe = True
            imgui.end_menu()
        imgui.separator()
        if imgui.menu_item_simple("Hide Menu Bar", "F11"):
            state.menu_bar_visible = False
        imgui.end_menu()

    # Right-aligned entity-id label -- replaces the standalone Save
    # Entity window's own id display, same reasoning as area_viewer.py's
    # "Area id" label (no other reason for that window to exist once
    # Save/Save As moved into this menu).
    label = f"Entity: {state.entity_id}" if state.entity_id else "Entity: (unsaved)"
    label_width = imgui.calc_text_size(label).x
    available_width = imgui.get_window_width()
    imgui.set_cursor_pos_x(max(imgui.get_cursor_pos_x(), available_width - label_width - 16))
    imgui.text(label)

    imgui.end_main_menu_bar()


def _draw_bottom_bar(scene: Scene, state: BuilderState) -> None:
    """A second, bottom-docked strip -- always visible regardless of
    `menu_bar_visible`/panel-visibility settings, identical mechanism
    to area_viewer.py's own `_draw_bottom_bar`: drawn straight onto the
    foreground draw list (not a real window) so it always composites
    above every floating panel with no z-order fight, and must be
    called from inside `gui()`'s own imgui frame bracket -- see that
    function's docstring for the crash this avoids.
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
    mode_text = "Mode: entity builder"
    draw_list.add_text(to_imvec2((cursor_x, text_y)), text_color, mode_text)
    cursor_x += imgui.calc_text_size(mode_text).x + 16.0

    parts_text = f"Parts: {len(state.parts)}"
    draw_list.add_text(to_imvec2((cursor_x, text_y)), text_color, parts_text)

    pos = [round(v, 1) for v in scene.camera.get("position", [0, 0, 0])]
    camera_text = f"camera.position = {pos}"
    camera_text_width = imgui.calc_text_size(camera_text).x
    draw_list.add_text(to_imvec2((left + width - camera_text_width - pad_x, text_y)), text_color, camera_text)


def _draw_entity_info_window(state: BuilderState) -> None:
    """Hidden by default (View > Entity Information) -- mirrors
    area_viewer.py's "Area Information" window, the status-message/
    last-action home left behind once Save moved into the menu bar.

    Also this entity's one editable "Name" field, per direct request
    ("make it trivial to rename parts, meshes or entities without it
    breaking relations") -- `state.entity_id` (shown just below, read-
    only) is the frozen reference `render_template`/the manifest/the
    launcher's asset browser all key on; renaming here only ever
    touches the separate, freely-editable display name, never that id,
    so nothing referencing this entity can break. Buffer-then-explicit-
    save like every other edit in this tool -- File > Save actually
    persists it.
    """
    if not state.show_entity_info:
        return
    imgui.begin("Entity Information", None, imgui.WindowFlags_.always_auto_resize)
    changed, state.entity_name = imgui.input_text("Name##entity-info", state.entity_name)
    if changed:
        _show_toast(state, f"Renamed entity to '{state.entity_name}' (not yet saved to disk)")
    imgui.text(f"Entity: {state.entity_id or '(new, unsaved)'}")
    imgui.text(f"Parts: {len(state.parts)}")
    if state.status_message:
        imgui.separator()
        imgui.text_wrapped(state.status_message)
    imgui.end()


class _ActionRegistryStub:
    """entity_template_editing.draw_part_fields() needs an
    `action_registry` with an `.actions` dict -- area_viewer.py's real
    `ActionRegistry` class lives in that file (a circular import away
    from here). This tool doesn't author actions itself (that's
    area_viewer.py's Action Definitions panel); it only needs to *read*
    the same actions.json so per-part action_animations fields list the
    same registered names. A fresh instance per `run()` call -- this
    tool doesn't need actions.json edits made *during* one editing
    session to hot-reload mid-session, only to reflect whatever was
    registered the last time this tool (or area_viewer.py) started.
    """

    def __init__(self) -> None:
        self.actions: dict = {}
        path = FRONTEND_DIR / "assets" / "data" / "actions.json"
        if path.exists():
            try:
                self.actions = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self.actions = {}


# ---------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------


def run(entity_id: "Optional[str]") -> bool:
    """Show the Entity Builder for *entity_id* (None starts a blank,
    unsaved definition). Blocks until the window closes. Returns True
    if closed via "Back to Launcher" (the caller should show the
    launcher again), False on a plain window-close.
    """
    logger.info(f"Entity builder -- entity_id={entity_id}")

    asset_loader.load_manifest()
    action_registry = _ActionRegistryStub()

    # Normalize to the bare id immediately, regardless of which form
    # *entity_id* arrived in -- the launcher's "Edit" button passes a
    # manifest-derived id, which (per normalize_entity_id()'s own
    # docstring) is the "entity-<id>" prefixed form, not the bare form
    # "Save As" produces. Keeping state.entity_id consistently bare
    # means every display site (bottom bar, menu bar label, Entity
    # Information) and every save call reads/writes the same string
    # regardless of how this entity was opened.
    entity_id = normalize_entity_id(entity_id) if entity_id else entity_id

    if entity_id:
        definition = load_entity_definition(entity_id)
        parts = list((definition or {}).get("parts") or [])
        entity_name = (definition or {}).get("name")
    else:
        parts = []
        entity_name = None

    scene = Scene()
    state = BuilderState(entity_id, parts, entity_name)

    renderer.init_renderer()
    # Launch maximized -- this tool's window is dense enough (menu bar,
    # part list, sidebar, import/playback panels all at once) that the
    # default launch size leaves everything cramped. `canvas._window`
    # is the same private GLFW handle renderer.py's own init_renderer()
    # already reaches into for its min-size constraint -- reused here
    # rather than changing that shared function, which every other
    # tool (launcher/area_viewer/asset_preview) also calls and none of
    # which asked to launch maximized.
    glfw.maximize_window(renderer.canvas._window)
    imgui_renderer = ImguiRenderer(renderer.device, renderer.canvas)

    # invert_yaw=True: flips the left/right drag-pan direction, per
    # direct request -- scoped to this tool's own camera only (see
    # OrbitCamera's own docstring on why this is a constructor arg,
    # not a shared-class-wide change; asset_preview.py's camera keeps
    # its original direction).
    orbit = OrbitCamera(invert_yaw=True)
    orbit.bind(renderer.canvas)
    state.orbit = orbit
    renderer.canvas.add_event_handler(_make_key_handler(state), "key_down")

    # _sync_preview_definition() auto-fits orbit.radius/scene.camera's
    # near/far to whatever's loaded (see entity_bounding_radius()) --
    # called before the first orbit.apply() so the very first rendered
    # frame already uses the fitted distance, not one frame of the
    # camera's raw ~200-unit default.
    _sync_preview_definition(scene, state)
    orbit.apply(scene.camera)

    render_state = {"entities": scene.entities, "camera": scene.camera}
    result = [False]

    def gui() -> None:
        _draw_menu_bar(scene, state)
        _draw_bottom_bar(scene, state)
        _draw_toast(state)
        _draw_entity_info_window(state)
        _draw_animation_editor_window(scene, state)
        _draw_timeline_window(scene, state)
        _draw_sidebar(scene, state, action_registry)

    imgui_renderer.set_gui(gui)

    last_time = [None]

    def draw() -> None:
        now = time.perf_counter()
        delta_ms = 0.0 if last_time[0] is None else (now - last_time[0]) * 1000.0
        last_time[0] = now

        orbit.apply(scene.camera)
        effective_delta_ms = 0.0 if state.paused else delta_ms
        interpolation.update_interpolation(scene.entities, effective_delta_ms / 1000.0)

        # Advance the Timeline's own playback clock and re-pose every
        # clip-assigned part from it -- see _update_playback_pose's own
        # docstring for why this bypasses _sync_preview_definition
        # (too expensive to call every frame). Real bug fixed: this is
        # the actual "unpausing does not start the playback" fix --
        # before this, nothing here ever advanced state.timeline_playback_ms
        # or resampled the clip at all, regardless of state.paused.
        if _timeline_visible(state) and not state.paused:
            clip = state.animation_editor_clip
            keyframes = clip.get("keyframes", [])
            if keyframes:
                duration = keyframes[-1]["time_ms"]
                state.timeline_playback_ms = advance_timeline_playback_ms(
                    state.timeline_playback_ms, delta_ms, duration, clip.get("loop", True)
                )
            _update_playback_pose(state)

        # Reapplied every frame, not just on toggle: _sync_preview_definition()
        # destroys/recreates the preview entity's EntityRenderer on every
        # parts-list edit (see that function's own docstring), which
        # would otherwise silently reset wireframe back to its off
        # default the next time any part changes.
        preview_renderer = client_main.entity_renderers.get(_PREVIEW_ENTITY_ID)
        if preview_renderer is not None:
            preview_renderer.set_wireframe(state.wireframe)
        client_main.draw_game_scene(render_state, effective_delta_ms)
        imgui_renderer.render()
        # Deferred close -- must happen here, after imgui_renderer.render()
        # has actually finished submitting this frame, never from inside
        # a menu-item click handler (which runs inside that same frame
        # bracket). Same crash area_viewer.py's own want_exit avoids.
        if state.want_back_to_launcher:
            result[0] = True
            renderer.canvas.close()
        elif state.want_exit:
            result[0] = False
            renderer.canvas.close()

    renderer.run(draw)
    logger.info("Entity builder closed.")
    return result[0]


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--entity", default=None, help="Existing entity id to edit, omit for a new one")
    args = parser.parse_args()
    run(entity_id=args.entity)


if __name__ == "__main__":
    main()
