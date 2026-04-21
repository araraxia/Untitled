"""ECS-style systems for entity processing."""

from typing import Optional

from backend.engine.ecs.system import System
from backend.engine.ecs.world import World
from backend.engine.ecs.component import (
    PositionComponent,
    VelocityComponent,
    StateComponent,
)
from backend.engine.ecs.entity import Entity
from backend.engine.events import EventBus


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
