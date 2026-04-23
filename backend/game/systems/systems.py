"""ECS-style systems for entity processing."""

import math
from typing import TYPE_CHECKING, Optional

from backend.engine.ecs.system import System
from backend.engine.ecs.world import World
from backend.engine.ecs.component import (
    PathComponent,
    PositionComponent,
    StatsComponent,
    StateComponent,
    VelocityComponent,
)
from backend.engine.ecs.entity import Entity
from backend.engine.events import EventBus

if TYPE_CHECKING:
    from backend.engine.spatial import SpatialGrid


class MovementSystem(System):
    """Applies velocity components to position components each tick."""

    def __init__(self, event_bus: Optional[EventBus] = None) -> None:
        self._bus = event_bus

    def update(self, world: World, delta_time: float) -> None:
        """Update entity positions based on their velocity components."""
        for eid, (pos, vel) in world.query_with_components(
            PositionComponent, VelocityComponent
        ):
            if vel.vx != 0 or vel.vy != 0:
                pos.x += vel.vx * delta_time
                pos.y += vel.vy * delta_time
                entity = world.get(eid)
                if entity is not None:
                    entity.x = pos.x
                    entity.y = pos.y
                    entity.is_dirty = True
                if self._bus is not None:
                    self._bus.publish(
                        "entity_moved",
                        {"id": eid, "x": pos.x, "y": pos.y},
                    )


class PathfindingSystem(System):
    """Advances entities along pre-computed movement paths.

    Each tick, pathing entities move toward the next waypoint in
    their ``PathComponent`` at a speed derived from their
    ``StatsComponent`` (if present) or a default fallback speed.
    The ``PathComponent`` is removed when all waypoints are reached.
    """

    # Multiplier: StatsComponent.speed * _STEP_SPEED = world units/s
    _STEP_SPEED: float = 50.0

    def __init__(
        self,
        spatial_grid: Optional["SpatialGrid"] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self._grid = spatial_grid
        self._bus = event_bus

    def update(self, world: World, delta_time: float) -> None:
        """Move each entity one step along its PathComponent."""
        for eid, (pos, path) in world.query_with_components(
            PositionComponent, PathComponent
        ):
            if path.current_index >= len(path.waypoints):
                world.remove_component(eid, PathComponent)
                continue

            stats: Optional[StatsComponent] = world.get_component(eid, StatsComponent)
            speed = (
                stats.speed * self._STEP_SPEED
                if stats is not None
                else self._STEP_SPEED
            )

            wx, wy = path.waypoints[path.current_index]
            dx = wx - pos.x
            dy = wy - pos.y
            dist = math.sqrt(dx * dx + dy * dy)
            step = speed * delta_time

            if step >= dist:
                pos.x = wx
                pos.y = wy
                path.current_index += 1
            else:
                factor = step / dist
                pos.x += dx * factor
                pos.y += dy * factor

            entity = world.get(eid)
            if entity is not None:
                entity.x = pos.x
                entity.y = pos.y
                entity.is_dirty = True

            if self._bus is not None:
                self._bus.publish(
                    "entity_moved",
                    {"id": eid, "x": pos.x, "y": pos.y},
                )

            if path.current_index >= len(path.waypoints):
                world.remove_component(eid, PathComponent)


class AISystem(System):
    """Handles AI behaviour for entities that have a StateComponent."""

    dependencies = [MovementSystem]

    def update(self, world: World, delta_time: float) -> None:
        """Update AI-controlled entities."""
        for _eid, (_state,) in world.query_with_components(StateComponent):
            # Placeholder for AI logic.
            pass


class CombatSystem:
    """Handles combat resolution."""

    def __init__(self, event_bus: Optional[EventBus] = None) -> None:
        self._bus = event_bus

    def resolve_attack(self, attacker: Entity, defender: Entity) -> None:
        """Resolve an attack between entities."""
        # Placeholder for combat logic.
        if self._bus is not None:
            self._bus.publish(
                "entity_attacked",
                {
                    "attacker": attacker.entity_id,
                    "defender": defender.entity_id,
                },
            )
