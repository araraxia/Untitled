"""ECS World — entity registry and component query hub."""

from typing import Dict, List, Optional

from backend.engine.ecs.entity import Entity


class World:
    """Entity registry providing CRUD and attribute-based queries.

    This is the stable API through which game code creates,
    retrieves, updates, and deletes entities.  Component storage
    layouts and typed queries will be extended in Phase 3.

    Example::

        world = World()
        e = Entity(entity_id='abc', x=0.0, y=0.0)
        world.add(e)
        entity = world.get('abc')
        world.remove('abc')
    """

    def __init__(self) -> None:
        self._entities: Dict[str, Entity] = {}

    # ------------------------------------------------------------------
    # Entity CRUD
    # ------------------------------------------------------------------

    def add(self, entity: Entity) -> Entity:
        """Register *entity* and return it."""
        self._entities[entity.entity_id] = entity
        return entity

    def get(self, entity_id: str) -> Optional[Entity]:
        """Return the entity for *entity_id*, or ``None``."""
        return self._entities.get(entity_id)

    def remove(self, entity_id: str) -> Optional[Entity]:
        """Unregister and return the entity, or ``None`` if absent."""
        return self._entities.pop(entity_id, None)

    def all(self) -> List[Entity]:
        """Return all registered entities."""
        return list(self._entities.values())

    def __len__(self) -> int:
        return len(self._entities)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def query(self, *attribute_names: str) -> List[Entity]:
        """Return entities that have all *attribute_names* non-None.

        This is a placeholder for the full archetype-based query
        system that will be implemented in Phase 3 (ECS Overhaul).

        Args:
            *attribute_names: Entity attribute names to filter on.

        Returns:
            List of entities possessing all requested attributes.
        """
        results = []
        for entity in self._entities.values():
            if all(getattr(entity, attr, None) is not None for attr in attribute_names):
                results.append(entity)
        return results
