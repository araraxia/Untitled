"""ECS System — abstract base class for all game systems."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Type

if TYPE_CHECKING:
    from backend.engine.ecs.world import World


class System(ABC):
    """Base class for all ECS systems.

    Concrete systems query the ``World`` for entities that carry the
    component types they care about, then operate on those components.

    Class variable ``dependencies`` lists other ``System`` subclasses
    that must run **before** this system each tick.  The scheduler
    enforces this order via topological sort.

    Example::

        class MovementSystem(System):
            def update(
                self,
                world: World,
                delta_time: float,
            ) -> None:
                for eid, (pos, vel) in world.query_with_components(
                    PositionComponent, VelocityComponent
                ):
                    pos.x += vel.vx * delta_time
                    pos.y += vel.vy * delta_time
    """

    dependencies: List[Type["System"]] = []

    @abstractmethod
    def update(
        self,
        world: "World",
        delta_time: float,
    ) -> None:
        """Process relevant entities for one tick.

        Args:
            world: The ECS World; use ``world.query_with_components()``
                to retrieve only the entities this system needs.
            delta_time: Seconds elapsed since the previous tick.
        """
