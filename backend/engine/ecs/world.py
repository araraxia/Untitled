"""ECS World — entity registry and component query hub."""

from typing import Dict, List, Optional, Set, Tuple, Type

from backend.engine.ecs.component import Component
from backend.engine.ecs.entity import Entity


class World:
    """Entity registry providing CRUD and component-based queries.

    Two parallel structures are maintained per component type:

    * ``_component_ids``  — ``type_id → set[entity_id]`` for fast
      set-intersection queries.
    * ``_components``     — ``type_id → {entity_id → Component}`` for
      O(1) instance retrieval.

    Example::

        world = World()
        e = Entity(entity_id='abc', x=0.0, y=0.0)
        world.add(e)
        entity = world.get('abc')
        world.remove('abc')
    """

    def __init__(self) -> None:
        self._entities: Dict[str, Entity] = {}
        # type_id -> set of entity IDs (for set-intersection queries)
        self._component_ids: Dict[int, Set[str]] = {}
        # type_id -> {entity_id -> Component instance}
        self._components: Dict[int, Dict[str, Component]] = {}

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
    # Component storage
    # ------------------------------------------------------------------

    def add_component(self, entity_id: str, component: Component) -> None:
        """Attach *component* to the entity identified by *entity_id*."""
        type_id = type(component).type_id
        if type_id not in self._components:
            self._components[type_id] = {}
            self._component_ids[type_id] = set()
        self._components[type_id][entity_id] = component
        self._component_ids[type_id].add(entity_id)

    def remove_component(self, entity_id: str, component_type: Type[Component]) -> None:
        """Remove the component of *component_type* from *entity_id*."""
        type_id = component_type.type_id
        bucket = self._components.get(type_id)
        if bucket:
            bucket.pop(entity_id, None)
        id_set = self._component_ids.get(type_id)
        if id_set:
            id_set.discard(entity_id)

    def get_component(
        self, entity_id: str, component_type: Type[Component]
    ) -> Optional[Component]:
        """Return the *component_type* component for *entity_id*, or None."""
        bucket = self._components.get(component_type.type_id)
        if bucket is None:
            return None
        return bucket.get(entity_id)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def query(self, *component_types: Type[Component]) -> List[str]:
        """Return entity IDs that possess all *component_types*.

        Intersects the per-type ID sets so the cost is
        O(min-set-size) rather than O(all-entities).

        Args:
            *component_types: Component subclasses to filter on.

        Returns:
            List of entity IDs possessing every requested component.
        """
        if not component_types:
            return list(self._entities.keys())

        id_sets: List[Set[str]] = []
        for ct in component_types:
            s = self._component_ids.get(ct.type_id)
            if not s:
                return []
            id_sets.append(s)

        if len(id_sets) == 1:
            return list(id_sets[0])

        # Intersect smallest → largest to minimise work.
        id_sets.sort(key=len)
        result: Set[str] = id_sets[0].copy()
        for s in id_sets[1:]:
            result &= s
            if not result:
                return []
        return list(result)

    def query_with_components(
        self, *component_types: Type[Component]
    ) -> List[Tuple[str, Tuple[Component, ...]]]:
        """Return matching entities paired with their component instances.

        Args:
            *component_types: Component subclasses to filter on.

        Returns:
            List of ``(entity_id, (comp_a, comp_b, ...))`` tuples for
            each entity that possesses all requested component types.
        """
        entity_ids = self.query(*component_types)
        buckets = [self._components[ct.type_id] for ct in component_types]
        out: List[Tuple[str, Tuple[Component, ...]]] = []
        for eid in entity_ids:
            components = tuple(b[eid] for b in buckets)
            out.append((eid, components))
        return out
