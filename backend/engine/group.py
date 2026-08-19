"""Entity groups.

Named collections of entities whose attributes flow down to members via
layered lookup (entity-level override, then group attribute, then a
caller-supplied default) instead of being copied onto every member. A
system that cares about e.g. gravity can look up one group's "strength"
attribute and apply it to every member, without touching each entity's
own data whenever the group-wide value changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

if TYPE_CHECKING:
    from backend.engine.ecs.entity import Entity

_OVERRIDES_KEY = "overrides"


@dataclass
class Group:
    """A named collection of entity IDs with shared attributes."""

    name: str
    attributes: Dict[str, Any] = field(default_factory=dict)
    members: Set[str] = field(default_factory=set)


class GroupRegistry:
    """Owns named :class:`Group`\\ s and entity membership for one Area."""

    def __init__(self) -> None:
        self._groups: Dict[str, Group] = {}
        # entity_id -> group names, insertion order preserved so
        # multi-group attribute resolution is deterministic.
        self._entity_groups: Dict[str, List[str]] = {}

    def create_group(
        self, name: str, attributes: Optional[Dict[str, Any]] = None
    ) -> Group:
        """Return the group named *name*, creating it if needed.

        If the group already exists and *attributes* is given, those
        attributes are merged into the existing group.
        """
        group = self._groups.get(name)
        if group is None:
            group = Group(name=name, attributes=dict(attributes or {}))
            self._groups[name] = group
        elif attributes:
            group.attributes.update(attributes)
        return group

    def get_group(self, name: str) -> Optional[Group]:
        return self._groups.get(name)

    def add_to_group(self, entity_id: str, group_name: str) -> None:
        """Add *entity_id* to *group_name*, creating the group if needed."""
        group = self.create_group(group_name)
        group.members.add(entity_id)
        names = self._entity_groups.setdefault(entity_id, [])
        if group_name not in names:
            names.append(group_name)

    def remove_from_group(self, entity_id: str, group_name: str) -> None:
        group = self._groups.get(group_name)
        if group is not None:
            group.members.discard(entity_id)
        names = self._entity_groups.get(entity_id)
        if names and group_name in names:
            names.remove(group_name)

    def groups_for_entity(self, entity_id: str) -> List[str]:
        """Group names *entity_id* belongs to, in the order it joined them."""
        return list(self._entity_groups.get(entity_id, ()))

    def members_of(self, group_name: str) -> Set[str]:
        group = self._groups.get(group_name)
        return set(group.members) if group else set()

    def set_group_attribute(self, group_name: str, key: str, value: Any) -> None:
        self.create_group(group_name).attributes[key] = value

    def get_effective_attribute(
        self, entity: "Entity", key: str, default: Any = None
    ) -> Any:
        """Resolve *key* for *entity*.

        Priority: an entity-level override stored via the tag data bag
        under the reserved ``"overrides"`` key, then each group the
        entity belongs to (in join order), then *default*.
        """
        overrides = entity.get_data(_OVERRIDES_KEY, None)
        if overrides and key in overrides:
            return overrides[key]
        for group_name in self._entity_groups.get(entity.entity_id, ()):
            group = self._groups.get(group_name)
            if group is not None and key in group.attributes:
                return group.attributes[key]
        return default

    def to_dict(self) -> Dict[str, Any]:
        return {
            name: {
                "attributes": group.attributes,
                "members": sorted(group.members),
            }
            for name, group in self._groups.items()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GroupRegistry":
        registry = cls()
        for name, payload in (data or {}).items():
            registry.create_group(name, payload.get("attributes", {}))
            for entity_id in payload.get("members", []):
                registry.add_to_group(entity_id, name)
        return registry
