"""[DEV ONLY] Standalone smoke test for backend/engine/zone.py --
Zone/ZoneRegistry, both containment shapes, and all 8 effect types plus
the unknown-type catch-all. No GPU, no backend server, no game branch
involvement. Steps 2-4 of .github/prompts/zones.prompt.md.

Mirrors run_gametick_test.py/run_scene_test.py's no-GPU verification
pattern: a real, permanent script, not a one-off manual check.

Usage:
    python run_zone_test.py
"""

import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.independant_logger import Logger

logger = Logger(
    log_name="run_zone_test",
    log_file="zone_test.log",
    log_level=20,  # INFO
).get_logger()

from backend.engine.ecs.component import ColliderComponent, Component
from backend.engine.ecs.entity import Entity
from backend.engine.events import EventBus
from backend.engine.group import GroupRegistry
from backend.engine.zone import (
    ZoneRegistry,
    apply_zone_effect,
    contains_point,
    point_in_polygon,
)


def check(label: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    logger.info(f"[{status}] {label}")
    if not condition:
        raise AssertionError(label)


def make_entity(entity_id: str, x: float, y: float, z: float = 0.0) -> Entity:
    return Entity(entity_id=entity_id, x=x, y=y, z=z)


def test_aabb_contains() -> None:
    zone = ZoneRegistry().create_zone(
        "box", {"type": "aabb", "min": [0, 0, 0], "max": [10, 10, 10]}
    )
    check("aabb: inside point contained", contains_point(zone, 5, 5, 5))
    check("aabb: outside point not contained", not contains_point(zone, 50, 5, 5))
    check("aabb: on-boundary point contained (inclusive)", contains_point(zone, 0, 0, 0))


def test_unknown_shape_type_does_not_crash() -> None:
    zone = ZoneRegistry().create_zone("weird", {"type": "sphere"})
    check("unknown shape type: returns False, doesn't raise", contains_point(zone, 0, 0, 0) is False)


def test_aabb_enter_exit_dedup() -> None:
    """zones.prompt.md Step 2's own verify: enter fires once when an
    entity moves inside, exit fires once when it moves back out, and
    repeated update() calls while stationary fire neither.
    """
    registry = ZoneRegistry()
    registry.create_zone("box", {"type": "aabb", "min": [0, 0, 0], "max": [10, 10, 10]})

    calls = []

    def dispatcher(zone, entity_id, effects):
        calls.append((zone.zone_id, entity_id, "enter" if effects is zone.on_enter else "exit"))

    entities = {"a": make_entity("a", -5, 5, 5)}  # starts outside

    registry.update(entities, dispatcher)
    check("dedup: no transition on first tick (outside, stays outside)", calls == [])

    entities["a"].x = 5  # move inside
    registry.update(entities, dispatcher)
    check("dedup: enter fires exactly once on the crossing tick", calls == [("box", "a", "enter")])

    registry.update(entities, dispatcher)
    registry.update(entities, dispatcher)
    check("dedup: no repeat firing while stationary inside", calls == [("box", "a", "enter")])

    entities["a"].x = -5  # move back outside
    registry.update(entities, dispatcher)
    check(
        "dedup: exit fires exactly once on the crossing tick",
        calls == [("box", "a", "enter"), ("box", "a", "exit")],
    )


def test_mesh_footprint_translation() -> None:
    """Real mesh-file loading path (frontend/assets/data/mesh/
    mesh-example-crate.json, a 64x64x64 box centered at its own local
    origin), translated to a world position -- proves the load/project/
    position path works. (Rotation-sensitivity is tested separately,
    below, with a synthetic non-square footprint -- a square footprint
    is rotation-invariant at 90 degree steps and can't demonstrate a
    flip, so it's the wrong shape to test rotation against.)
    """
    zone = ZoneRegistry().create_zone(
        "crate_zone",
        {
            "type": "mesh",
            "mesh": "mesh-example-crate",
            "position": [100, 0, 0],
            "rotation": [0, 0, 0],
            "scale": [1, 1, 1],
        },
    )
    check("mesh: point at zone center contained", contains_point(zone, 100, 0, 0))
    check("mesh: point near zone center, inside 64-unit box, contained", contains_point(zone, 110, 5, -10))
    check("mesh: point far from zone not contained", not contains_point(zone, 100, 0, 500))
    check("mesh: point outside Y range not contained", not contains_point(zone, 100, 100, 0))


def test_mesh_footprint_rotation_flip() -> None:
    """point_in_polygon + _world_to_local's rotation math, isolated
    from mesh-file loading: a synthetic non-square (10 wide x 40 deep)
    rectangular footprint, injected directly via the Zone's cache
    fields rather than a real mesh file. zones.prompt.md's own verify:
    "Rotating the zone 90 degrees and re-testing the same world-space
    point flips the expected result correctly."
    """
    rect_footprint = [(-5, -20), (5, -20), (5, 20), (-5, 20)]  # 10 wide (X), 40 deep (Z)

    zone = ZoneRegistry().create_zone(
        "rect_zone",
        {"type": "mesh", "mesh": "unused", "position": [0, 0, 0], "rotation": [0, 0, 0], "scale": [1, 1, 1]},
    )
    zone._cached_footprint = rect_footprint
    zone._cached_y_range = (-10.0, 10.0)

    # contains_point(zone, x, y, z) -- world (x=8, y=0, z=0). (8, z=0)
    # is outside the un-rotated 10-wide-in-X rect (half-width 5) but
    # would be inside if the rectangle were rotated 90 degrees (its
    # long axis, half-length 20, now spans X).
    check("mesh rotation: (x=8,z=0) outside un-rotated rect", not contains_point(zone, 8, 0, 0))

    zone.shape["rotation"] = [0, math.pi / 2, 0]
    check("mesh rotation: same point (x=8,z=0) inside after 90-degree rotation", contains_point(zone, 8, 0, 0))

    # And the inverse: a point inside the un-rotated rect should move
    # outside once rotated (a genuine flip both directions, not just
    # "rotation makes everything true"). world (x=0, y=0, z=15) -- z=15
    # is within the un-rotated rect's 40-deep-in-Z span (half-depth 20).
    zone.shape["rotation"] = [0, 0, 0]
    check("mesh rotation: (x=0,z=15) inside un-rotated rect", contains_point(zone, 0, 0, 15))
    zone.shape["rotation"] = [0, math.pi / 2, 0]
    check(
        "mesh rotation: same point (x=0,z=15) outside after 90-degree rotation",
        not contains_point(zone, 0, 0, 15),
    )


def test_point_in_polygon_directly() -> None:
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    check("point_in_polygon: center inside", point_in_polygon(5, 5, square))
    check("point_in_polygon: far outside", not point_in_polygon(50, 50, square))
    check("point_in_polygon: degenerate (<3 points) is False, not a crash", not point_in_polygon(0, 0, [(0, 0), (1, 1)]))


def test_zone_round_trip() -> None:
    registry = ZoneRegistry()
    registry.create_zone(
        "z1",
        {"type": "aabb", "min": [0, 0, 0], "max": [1, 1, 1]},
        on_enter=[{"type": "fire_event", "event": "test_event"}],
        on_exit=[{"type": "clear_data", "key": "in_zone"}],
        tags=["water"],
    )
    data = registry.to_dict()
    reloaded = ZoneRegistry.from_dict(data)
    zone = reloaded.get_zone("z1")
    check("round-trip: zone present", zone is not None)
    check("round-trip: shape preserved", zone.shape == {"type": "aabb", "min": [0, 0, 0], "max": [1, 1, 1]})
    check("round-trip: on_enter preserved", zone.on_enter == [{"type": "fire_event", "event": "test_event"}])
    check("round-trip: tags preserved", zone.tags == ["water"])


def test_effect_add_remove_group() -> None:
    entities = {"a": make_entity("a", 0, 0)}
    groups = GroupRegistry()

    apply_zone_effect(entities, "a", {"type": "add_group", "group": "gravity"}, groups)
    check("effect add_group: membership applied", "a" in groups.members_of("gravity"))

    apply_zone_effect(entities, "a", {"type": "remove_group", "group": "gravity"}, groups)
    check("effect remove_group: membership removed", "a" not in groups.members_of("gravity"))

    apply_zone_effect(
        entities, "a", {"type": "set_group_attribute", "group": "gravity", "key": "strength", "value": 9.8}, groups
    )
    check("effect set_group_attribute: applied", groups.get_group("gravity").attributes["strength"] == 9.8)


def test_effect_set_clear_data() -> None:
    entities = {"a": make_entity("a", 0, 0)}
    groups = GroupRegistry()

    apply_zone_effect(entities, "a", {"type": "set_data", "key": "wet", "value": True}, groups)
    check("effect set_data: applied", entities["a"].get_data("wet") is True)

    apply_zone_effect(entities, "a", {"type": "clear_data", "key": "wet"}, groups)
    check("effect clear_data: removed", entities["a"].get_data("wet") is None)


def test_effect_add_remove_component() -> None:
    entities = {"a": make_entity("a", 0, 0)}
    groups = GroupRegistry()

    apply_zone_effect(
        entities,
        "a",
        {"type": "add_component", "component": {"type": "ColliderComponent", "width": 2.0, "height": 2.0, "solid": True}},
        groups,
    )
    collider = entities["a"].get_component(ColliderComponent)
    check("effect add_component: attached", collider is not None and collider.width == 2.0)

    # Round-trips through to_dict/from_dict, per Step 4 task 6.
    round_tripped = Entity.from_dict(entities["a"].to_dict())
    check(
        "effect add_component: round-trips through Entity.to_dict/from_dict",
        round_tripped.get_component(ColliderComponent) is not None,
    )

    apply_zone_effect(entities, "a", {"type": "remove_component", "component_type": "ColliderComponent"}, groups)
    check("effect remove_component: detached", entities["a"].get_component(ColliderComponent) is None)


def test_effect_fire_event() -> None:
    entities = {"a": make_entity("a", 0, 0)}
    groups = GroupRegistry()
    bus = EventBus()

    received = []
    bus.subscribe("test_event", lambda payload: received.append(payload))

    zone = ZoneRegistry().create_zone("z1", {"type": "aabb", "min": [0, 0, 0], "max": [1, 1, 1]})
    apply_zone_effect(
        entities, "a", {"type": "fire_event", "event": "test_event", "payload": {"extra": 1}}, groups, bus, zone
    )
    check("effect fire_event: published", len(received) == 1)
    check(
        "effect fire_event: payload carries entity_id/zone_id plus the effect's own payload",
        received[0] == {"extra": 1, "entity_id": "a", "zone_id": "z1"},
    )


def test_unknown_effect_type_does_not_crash() -> None:
    entities = {"a": make_entity("a", 0, 0)}
    groups = GroupRegistry()
    # Should log a warning once and return -- not raise.
    apply_zone_effect(entities, "a", {"type": "teleport_to_moon"}, groups)
    apply_zone_effect(entities, "a", {"type": "teleport_to_moon"}, groups)
    check("unknown effect type: no exception raised (twice, to prove the once-per-type warning path)", True)


def test_full_tick_through_dispatcher() -> None:
    """End-to-end: ZoneRegistry.update() -> apply_zone_effect, the
    exact wiring shape a game branch's Area.update() would use.
    """
    entities = {"a": make_entity("a", -5, 5, 5)}
    groups = GroupRegistry()
    bus = EventBus()
    registry = ZoneRegistry()
    registry.create_zone(
        "box",
        {"type": "aabb", "min": [0, 0, 0], "max": [10, 10, 10]},
        on_enter=[{"type": "add_group", "group": "inside_box"}],
        on_exit=[{"type": "remove_group", "group": "inside_box"}],
    )

    def dispatcher(zone, entity_id, effects):
        for effect in effects:
            apply_zone_effect(entities, entity_id, effect, groups, bus, zone)

    registry.update(entities, dispatcher)
    check("full tick: not yet in group (still outside)", "a" not in groups.members_of("inside_box"))

    entities["a"].x = 5
    registry.update(entities, dispatcher)
    check("full tick: entering the zone adds group membership", "a" in groups.members_of("inside_box"))

    entities["a"].x = -5
    registry.update(entities, dispatcher)
    check("full tick: exiting the zone removes group membership", "a" not in groups.members_of("inside_box"))


def main() -> None:
    logger.info("=" * 50)
    logger.info("[DEV ONLY] Zone/ZoneRegistry/apply_zone_effect smoke test")
    logger.info("=" * 50)

    test_aabb_contains()
    test_unknown_shape_type_does_not_crash()
    test_aabb_enter_exit_dedup()
    test_mesh_footprint_translation()
    test_mesh_footprint_rotation_flip()
    test_point_in_polygon_directly()
    test_zone_round_trip()
    test_effect_add_remove_group()
    test_effect_set_clear_data()
    test_effect_add_remove_component()
    test_effect_fire_event()
    test_unknown_effect_type_does_not_crash()
    test_full_tick_through_dispatcher()

    logger.info(
        "PASS: Zone/ZoneRegistry (both shapes, enter/exit dedup), all 8 effect "
        "types plus the unknown-type catch-all, and the full "
        "ZoneRegistry.update() -> apply_zone_effect wiring all verified."
    )


if __name__ == "__main__":
    main()
