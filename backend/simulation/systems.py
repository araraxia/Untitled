"""ECS-style systems for entity processing."""

from typing import List
from backend.simulation.entity import Entity


class MovementSystem:
    """Handles entity movement."""

    @staticmethod
    def update(entities: List[Entity], delta_time: float):
        """Update entity positions based on velocity."""
        for entity in entities:
            if entity.vx != 0 or entity.vy != 0:
                entity.x += entity.vx * delta_time
                entity.y += entity.vy * delta_time
                entity.is_dirty = True


class AISystem:
    """Handles AI behavior."""

    @staticmethod
    def update(entities: List[Entity], delta_time: float):
        """Update AI-controlled entities."""
        # Placeholder for AI logic
        pass


class CombatSystem:
    """Handles combat resolution."""

    @staticmethod
    def resolve_attack(attacker: Entity, defender: Entity):
        """Resolve an attack between entities."""
        # Placeholder for combat logic
        pass
