"""Zones -- named spatial regions that entities can be inside or
outside of, checked each tick, driving declarative on_enter/on_exit
effects: publish an EventBus event, add/remove a GroupRegistry
membership, or write/clear tag data / an attached Component.

Steps 2-4 of .github/prompts/zones.prompt.md. `Zone`/`ZoneRegistry`/
`contains_point` (Steps 2-3) and `apply_zone_effect` (Step 4) all live
here as engine-layer, generic code -- reclassified during
implementation from the prompt's original `backend/game/area.py`
placement for `apply_zone_effect`: every one of its effect types only
touches generic engine primitives (`GroupRegistry`, `Entity.set_data`/
`add_component`, `EventBus`), nothing game-specific, the same reasoning
that already reclassified `client/engine/area_viewer.py` engine-layer
this session. A game branch's `Area.update()` wiring (Step 5) becomes a
thin one-line call into this module's `ZoneRegistry.update()`, not a
reimplementation.

**The `ecs_world` gap this design deliberately avoids** (see the prompt
file's own Required Reading, confirmed via `grep -rn "ecs_world\\."
backend/`): nothing in this codebase ever populates the ECS `World`
registered `System`s query, so a `ZoneSystem` registered with
`SystemScheduler` would compile, look correct, and never actually run
against real data. `ZoneRegistry` is driven from a plain per-tick
`update()` call instead (a game branch's `Area.update()`), mirroring
`backend/engine/group.py`'s own precedent.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from backend.engine.ecs.component import Component
from backend.engine.ecs.entity import Entity
from backend.engine.events import EventBus
from backend.engine.group import GroupRegistry

logger = logging.getLogger(__name__)

# backend/engine/zone.py -> backend/engine -> backend -> repo root -> frontend.
# Mesh zones read plain project-JSON mesh files directly, the same
# files client/engine/mesh.py reads -- pure geometry, no GPU/wgpu
# involvement needed on this side at all.
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

_warned_unknown_effect_types: Set[str] = set()
_warned_unknown_shape_types: Set[str] = set()


# ---------------------------------------------------------------------------
# Zone / ZoneRegistry (Step 2)
# ---------------------------------------------------------------------------


@dataclass
class Zone:
    """A named spatial region. `shape` is one of two dicts (Step 3);
    `on_enter`/`on_exit` are lists of declarative effect dicts (Step 4);
    `tags` are free-form labels (e.g. for editor filtering).
    """

    zone_id: str
    shape: dict
    on_enter: list = field(default_factory=list)
    on_exit: list = field(default_factory=list)
    tags: list = field(default_factory=list)

    # Lazily populated by _mesh_footprint() for shape["type"] == "mesh"
    # zones only -- computed once at first containment test, not at
    # zone-load time literally, but the effect is the same (cached
    # across every subsequent tick, never recomputed per point).
    _cached_footprint: Optional[List[Tuple[float, float]]] = field(
        default=None, repr=False, compare=False
    )
    _cached_y_range: Optional[Tuple[float, float]] = field(
        default=None, repr=False, compare=False
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shape": self.shape,
            "on_enter": self.on_enter,
            "on_exit": self.on_exit,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, zone_id: str, data: Dict[str, Any]) -> "Zone":
        return cls(
            zone_id=zone_id,
            shape=data.get("shape", {}),
            on_enter=list(data.get("on_enter", [])),
            on_exit=list(data.get("on_exit", [])),
            tags=list(data.get("tags", [])),
        )


class ZoneRegistry:
    """Owns named `Zone`s and per-zone enter/exit de-dup state for one
    Area. Mirrors `GroupRegistry`'s shape: constructor-less
    registration, `to_dict`/`from_dict` pair.
    """

    def __init__(self) -> None:
        self._zones: Dict[str, Zone] = {}
        # zone_id -> set of entity_ids currently inside -- the de-dup
        # state driving enter/exit edge detection, same pattern
        # area-system.prompt.md's Step 10 trigger-collider dedup uses,
        # applied per-zone instead of per-entity-pair.
        self._inside: Dict[str, Set[str]] = {}

    def create_zone(
        self,
        zone_id: str,
        shape: dict,
        on_enter: Optional[list] = None,
        on_exit: Optional[list] = None,
        tags: Optional[list] = None,
    ) -> Zone:
        zone = Zone(
            zone_id=zone_id,
            shape=shape,
            on_enter=list(on_enter or []),
            on_exit=list(on_exit or []),
            tags=list(tags or []),
        )
        self._zones[zone_id] = zone
        self._inside.setdefault(zone_id, set())
        return zone

    def get_zone(self, zone_id: str) -> Optional[Zone]:
        return self._zones.get(zone_id)

    def remove_zone(self, zone_id: str) -> None:
        self._zones.pop(zone_id, None)
        self._inside.pop(zone_id, None)

    def all_zones(self) -> List[Zone]:
        return list(self._zones.values())

    def update(
        self,
        entities: Dict[str, "Entity"],
        effect_dispatcher: Callable[["Zone", str, list], None],
    ) -> None:
        """For each zone, test containment for every entity; diff
        against last tick's inside-set; fire on_enter/on_exit for the
        transitions only (never once per tick while stationary
        inside/outside).

        *effect_dispatcher(zone, entity_id, effects)* is injected, not
        imported directly -- keeps this class free of any dependency
        on `GroupRegistry`/`EventBus`/entity-component internals beyond
        position, matching `group.py`'s own "just data and membership"
        scope. **Corrected from the prompt's original sketch during
        implementation**: `effect_dispatcher` here receives the `Zone`
        itself, not just `(entity_id, effects)` -- the prompt's own
        Step 4 task 8 needs `zone.zone_id` for a `fire_event` effect's
        payload, which is unreachable without it.
        """
        for zone in self._zones.values():
            currently_inside = self._inside.setdefault(zone.zone_id, set())
            now_inside: Set[str] = set()

            for entity_id, entity in entities.items():
                x = getattr(entity, "x", None)
                y = getattr(entity, "y", None)
                z = getattr(entity, "z", 0.0)
                if x is None or y is None:
                    continue
                if contains_point(zone, x, y, z):
                    now_inside.add(entity_id)

            entered = now_inside - currently_inside
            exited = currently_inside - now_inside

            for entity_id in entered:
                effect_dispatcher(zone, entity_id, zone.on_enter)
            for entity_id in exited:
                effect_dispatcher(zone, entity_id, zone.on_exit)

            self._inside[zone.zone_id] = now_inside

    def to_dict(self) -> Dict[str, Any]:
        return {zone_id: zone.to_dict() for zone_id, zone in self._zones.items()}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ZoneRegistry":
        registry = cls()
        for zone_id, payload in (data or {}).items():
            registry.create_zone(
                zone_id,
                payload.get("shape", {}),
                payload.get("on_enter"),
                payload.get("on_exit"),
                payload.get("tags"),
            )
        return registry


# ---------------------------------------------------------------------------
# Containment tests (Step 3)
# ---------------------------------------------------------------------------


def contains_point(zone: Zone, x: float, y: float, z: float) -> bool:
    """Dispatch on `zone.shape["type"]`. Unknown/missing shape type
    logs a warning once and returns False -- never crashes the tick
    loop on bad/hand-authored data.
    """
    shape_type = zone.shape.get("type")
    if shape_type == "aabb":
        return _contains_point_aabb(zone.shape, x, y, z)
    if shape_type == "mesh":
        return _contains_point_mesh(zone, x, y, z)

    if shape_type not in _warned_unknown_shape_types:
        _warned_unknown_shape_types.add(shape_type)
        logger.warning("Zone %r has unknown shape type %r", zone.zone_id, shape_type)
    return False


def _contains_point_aabb(shape: dict, x: float, y: float, z: float) -> bool:
    """`shape = {"type": "aabb", "min": [x,y,z], "max": [x,y,z]}` -- the
    "simple two-coordinate square zone": two corner points, nothing
    else.
    """
    min_pt = shape.get("min", [0.0, 0.0, 0.0])
    max_pt = shape.get("max", [0.0, 0.0, 0.0])
    return (
        min_pt[0] <= x <= max_pt[0]
        and min_pt[1] <= y <= max_pt[1]
        and min_pt[2] <= z <= max_pt[2]
    )


def point_in_polygon(x: float, z: float, polygon: List[Tuple[float, float]]) -> bool:
    """Ray-casting / even-odd rule point-in-polygon test against a 2D
    (X, Z) footprint. Standard, dependency-free algorithm. A point
    exactly on an edge is an accepted ambiguous case (standard
    point-in-polygon edge behaviour), not a bug to fix.
    """
    if len(polygon) < 3:
        return False

    inside = False
    x0, z0 = polygon[-1]
    for x1, z1 in polygon:
        if (z1 > z) != (z0 > z):
            x_intersect = (x0 - x1) * (z - z1) / (z0 - z1) + x1
            if x < x_intersect:
                inside = not inside
        x0, z0 = x1, z1
    return inside


def _resolve_mesh_path(mesh_key: str) -> Path:
    """Resolve a mesh asset key/path the same way any backend code
    resolves an asset path -- a raw relative path (contains a slash)
    passes through unchanged, matching
    `client/engine/asset_loader.py`'s own `resolve()` convention;
    otherwise assumes the standard `mesh-<name>.json` project
    convention under `frontend/assets/data/mesh/`.
    """
    if "/" in mesh_key or "\\" in mesh_key:
        return FRONTEND_DIR / mesh_key
    return FRONTEND_DIR / "assets" / "data" / "mesh" / f"{mesh_key}.json"


def _load_mesh_vertex_positions(mesh_key: str) -> List[List[float]]:
    """Read a mesh JSON file directly (`open()`/`json.load` -- pure
    geometry read, no GPU/wgpu involvement needed here at all) and
    return its vertex positions.
    """
    path = _resolve_mesh_path(mesh_key)
    data = json.loads(path.read_text(encoding="utf-8"))
    return [v["pos"] for v in data.get("vertices", [])]


def _rotation_matrix(rx: float, ry: float, rz: float) -> List[List[float]]:
    """3x3 rotation matrix, row-major, matching
    `client/engine/mat4.py`'s `rotation_xyz()` convention exactly
    (intrinsic Z, then Y, then X -- `Rx * Ry * Rz` applied to a column
    vector). Re-derived here rather than imported from `client/` --
    this is backend Python and must not import the client package --
    but must not diverge from that convention: a zone's `rotation`
    means the same thing regardless of which side of the process
    boundary reads it, same rule `3d-coordinate-mapping.prompt.md`
    Step 2 established for every Euler-rotation consumer in this
    project.
    """
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    return [
        [cy * cz, cy * sz, -sy],
        [sx * sy * cz - cx * sz, sx * sy * sz + cx * cz, sx * cy],
        [cx * sy * cz + sx * sz, cx * sy * sz - sx * cz, cx * cy],
    ]


def _matrix_vector_multiply(
    m: List[List[float]], v: Tuple[float, float, float]
) -> Tuple[float, float, float]:
    return (
        m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
        m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
        m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2],
    )


def _matrix_transpose(m: List[List[float]]) -> List[List[float]]:
    return [[m[c][r] for c in range(3)] for r in range(3)]


def _world_to_local(
    point: Tuple[float, float, float],
    position: List[float],
    rotation: List[float],
    scale: List[float],
) -> Tuple[float, float, float]:
    """Inverse of a position/rotation/scale placement: translate, then
    inverse-rotate (transpose -- the rotation matrix is orthonormal, so
    its transpose is its inverse), then inverse-scale.
    """
    relative = (point[0] - position[0], point[1] - position[1], point[2] - position[2])
    rotation_matrix = _rotation_matrix(rotation[0], rotation[1], rotation[2])
    local_rotated = _matrix_vector_multiply(_matrix_transpose(rotation_matrix), relative)
    sx = scale[0] or 1.0
    sy = scale[1] or 1.0
    sz = scale[2] or 1.0
    return (local_rotated[0] / sx, local_rotated[1] / sy, local_rotated[2] / sz)


def _convex_hull_2d(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Andrew's monotone chain convex hull -- dependency-free, ~20
    lines, same "hand-roll it" spirit as `point_in_polygon`'s ray-
    casting. **Necessary, not optional**: a mesh's stored vertices come
    in triangle/face order, not a perimeter walk -- feeding them to
    `point_in_polygon` directly (found and fixed while verifying this
    module, `run_zone_test.py`) produces a self-intersecting,
    meaningless "polygon" and wrong containment results, since
    ray-casting requires an ordered boundary. Convex hull is the
    simplest correct fix for a point cloud with no inherent order.

    **Documented limitation this introduces**: a genuinely concave mesh
    footprint (an L-shaped room) is flattened to its convex hull --
    same class of approximation as the Y-range check already is for a
    non-uniform ceiling height. Not a bug to fix later; a stated scope
    boundary, same as the mesh-zone approximation generally.
    """
    unique_points = sorted(set(points))
    if len(unique_points) <= 2:
        return unique_points

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: List[Tuple[float, float]] = []
    for p in unique_points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)

    upper: List[Tuple[float, float]] = []
    for p in reversed(unique_points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)

    return lower[:-1] + upper[:-1]


def _mesh_footprint(zone: Zone) -> Tuple[List[Tuple[float, float]], Tuple[float, float]]:
    """Cached (2D XZ-plane footprint polygon, (min_y, max_y)) pair for
    a mesh zone. Computed once, at first use -- invalidated only if the
    zone's shape data changes (i.e. never, for the lifetime of a given
    `Zone` instance; a changed shape means constructing a new `Zone`).
    """
    if zone._cached_footprint is not None and zone._cached_y_range is not None:
        return zone._cached_footprint, zone._cached_y_range

    mesh_key = zone.shape.get("mesh")
    vertices = _load_mesh_vertex_positions(mesh_key)
    projected = [(v[0], v[2]) for v in vertices]  # project onto XZ, drop Y
    footprint = _convex_hull_2d(projected)
    y_values = [v[1] for v in vertices]
    y_range = (min(y_values), max(y_values)) if y_values else (0.0, 0.0)

    zone._cached_footprint = footprint
    zone._cached_y_range = y_range
    return footprint, y_range


def _contains_point_mesh(zone: Zone, x: float, y: float, z: float) -> bool:
    """`shape = {"type": "mesh", "mesh": "<mesh-asset-key>", "position":
    [x,y,z], "rotation": [rx,ry,rz], "scale": [sx,sy,sz]}`. Documented
    approximation, not true volumetric containment: the mesh's vertices
    are projected onto the XZ (ground) plane once, into a 2D polygon;
    per-tick containment is a Y-range check plus a point-in-polygon
    test against that cached footprint. A mesh with an actual 3D
    interior shape (e.g. a dome) is not correctly handled by this --
    an explicit non-goal, not a bug.
    """
    footprint, (min_y, max_y) = _mesh_footprint(zone)
    position = zone.shape.get("position", [0.0, 0.0, 0.0])
    rotation = zone.shape.get("rotation", [0.0, 0.0, 0.0])
    scale = zone.shape.get("scale", [1.0, 1.0, 1.0])

    local_x, local_y, local_z = _world_to_local((x, y, z), position, rotation, scale)

    if not (min_y <= local_y <= max_y):
        return False
    return point_in_polygon(local_x, local_z, footprint)


# ---------------------------------------------------------------------------
# Effects (Step 4)
# ---------------------------------------------------------------------------


def apply_zone_effect(
    entities: Dict[str, "Entity"],
    entity_id: str,
    effect: dict,
    groups: GroupRegistry,
    event_bus: Optional[EventBus] = None,
    zone: Optional[Zone] = None,
) -> None:
    """Apply one declarative effect dict (from a `Zone`'s `on_enter`/
    `on_exit` list) to `entity_id`.

    Engine-layer and generic -- takes `entities`/`groups`/`event_bus`
    as plain parameters rather than a full `Area` object (reclassified
    from the prompt's original `backend/game/area.py` placement; see
    module docstring). A game branch's `Area.update()` calls this the
    same way it would call any other engine-layer helper, passing its
    own `self.entities`/`self.groups`/`self.event_bus`.
    """
    entity = entities.get(entity_id)
    if entity is None:
        return

    effect_type = effect.get("type")

    if effect_type == "add_group":
        groups.add_to_group(entity_id, effect["group"])
    elif effect_type == "remove_group":
        groups.remove_from_group(entity_id, effect["group"])
    elif effect_type == "set_group_attribute":
        groups.set_group_attribute(effect["group"], effect["key"], effect["value"])
    elif effect_type == "set_data":
        entity.set_data(effect["key"], effect["value"])
    elif effect_type == "clear_data":
        entity.clear_data(effect["key"])
    elif effect_type == "add_component":
        # Attaches to the entity's own local component store
        # (Entity.add_component/get_component), NOT World's -- it will
        # not be picked up by any System that queries
        # world.query_with_components(...), because of the ecs_world
        # gap this module's docstring documents. It IS visible to any
        # code calling entity.get_component(SomeType) directly, and
        # DOES persist/round-trip through save files.
        entity.add_component(Component.from_dict(effect["component"]))
    elif effect_type == "remove_component":
        component_cls = Component.lookup(effect.get("component_type", ""))
        if component_cls is None:
            _warn_unknown_effect_type_once(
                f"remove_component:{effect.get('component_type')!r}"
            )
        else:
            entity.remove_component(component_cls)
    elif effect_type == "fire_event":
        if event_bus is not None:
            payload = dict(effect.get("payload", {}))
            payload["entity_id"] = entity_id
            if zone is not None:
                payload["zone_id"] = zone.zone_id
            event_bus.publish(effect["event"], payload)
    else:
        _warn_unknown_effect_type_once(effect_type)


def _warn_unknown_effect_type_once(effect_type: Any) -> None:
    """Log a warning once per unique unknown effect type, not once per
    occurrence -- matches `ScriptMovementSystem`'s own "unknown
    script_type" handling in `area-system.prompt.md` Step 10.
    """
    if effect_type in _warned_unknown_effect_types:
        return
    _warned_unknown_effect_types.add(effect_type)
    logger.warning("Unknown zone effect type: %r", effect_type)
