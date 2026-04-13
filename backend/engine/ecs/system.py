"""ECS System — abstract base class for all game systems."""

from abc import ABC, abstractmethod
from typing import List

from backend.engine.ecs.entity import Entity


class System(ABC):
    """Base class for all ECS systems.

    Concrete systems process a list of entities each tick.
    Override ``update`` to implement game logic.

    Example::

        class MovementSystem(System):
            def update(
                self,
                entities: List[Entity],
                delta_time: float,
            ) -> None:
                for e in entities:
                    e.x += e.vx * delta_time
                    e.y += e.vy * delta_time
    """

    @abstractmethod
    def update(
        self,
        entities: List[Entity],
        delta_time: float,
    ) -> None:
        """Process all relevant entities for one tick.

        Args:
            entities: Full list of active entities from the World.
            delta_time: Seconds elapsed since the previous tick.
        """
