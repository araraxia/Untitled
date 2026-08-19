"""World state manager."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import json

from backend.engine.ecs.entity import Entity
from backend.engine.group import GroupRegistry
from backend.engine.save_format import SAVE_VERSION, migrate
from backend.engine.spatial import SpatialGrid
from backend.game.config import DEF_AREA_WIDTH, DEF_AREA_HEIGHT
from backend.game.entities.player import PlayerCharacter


class Area:
    """Manages the game world state and entities."""

    def __init__(self, area_id: Optional[str] = None, area_name: str = "Untitled Area"):
        self.area_id = area_id
        self.area_name = area_name
        self.width = DEF_AREA_WIDTH  # Default world dimensions
        self.height = DEF_AREA_HEIGHT  # Default world dimensions
        self.entities: Dict[str, Entity] = {}
        self.player_controller: Optional[PlayerCharacter] = None
        self.spatial_grid = SpatialGrid(DEF_AREA_WIDTH, DEF_AREA_HEIGHT)
        self.groups = GroupRegistry()
        self.dirty_entities: set = set()
        self.removed_entities: set = set()

        # Don't auto-initialize player - wait for player selection from menu

    def load_player_controller(self, player_controller: PlayerCharacter):
        """Load a player controller and their controlled entities into the world.

        Args:
            player_controller: The PlayerCharacter controller to load
        """
        self.player_controller = player_controller

        # Add all controlled entities to the world
        for entity in player_controller.get_controlled_entities():
            if entity.entity_id not in self.entities:
                self.add_entity(entity)

    def get_active_player_entity(self) -> Optional[Entity]:
        """Get the currently active player-controlled entity.

        Returns:
            The active Entity being controlled, or None
        """
        if self.player_controller:
            return self.player_controller.get_active_entity()
        return None

    def add_entity(self, entity: Entity):
        """Add an entity to the world."""
        self.entities[entity.entity_id] = entity
        self.spatial_grid.insert(entity)
        self.dirty_entities.add(entity.entity_id)

    def remove_entity(self, entity_id: str):
        """Remove an entity from the world."""
        if entity_id in self.entities:
            entity = self.entities[entity_id]
            self.spatial_grid.remove(entity)
            del self.entities[entity_id]
            self.removed_entities.add(entity_id)

    def process_player_action(self, action: Dict[str, Any]):
        """Process a player action."""
        if self.player_controller:
            self.player_controller.execute_action(action)
            # Mark controlled entities as dirty
            for entity in self.player_controller.get_controlled_entities():
                if entity.entity_id in self.entities:
                    self.dirty_entities.add(entity.entity_id)

    def process_party_command(self, command: Dict[str, Any]):
        """Process a party command."""
        member_id = command.get("member_id")
        if member_id in self.entities:
            entity = self.entities[member_id]
            entity.receive_command(command)
            self.dirty_entities.add(member_id)

    def update(self, delta_time: float):
        """Update all entities in the world."""
        for entity in self.entities.values():
            entity.update(delta_time)
            if entity.is_dirty:
                self.dirty_entities.add(entity.entity_id)
                entity.is_dirty = False

    def get_state_delta(self) -> Dict[str, Any]:
        """Get the state changes since last call."""
        if not self.dirty_entities and not self.removed_entities:
            return {}

        delta = {"entities": {}, "removed": list(self.removed_entities)}

        for entity_id in self.dirty_entities:
            if entity_id in self.entities:
                delta["entities"][entity_id] = self.entities[entity_id].serialize()

        # Clear dirty flags
        self.dirty_entities.clear()
        self.removed_entities.clear()

        return delta

    def get_full_state(self) -> Dict[str, Any]:
        """Get the complete world state."""
        return {
            "entities": {
                eid: entity.serialize() for eid, entity in self.entities.items()
            },
            "world": {"width": self.width, "height": self.height},
        }

    def save_from_file(self, file_path: str):
        """Load world state from a file."""
        pass  # Implementation depends on file format

    def load_from_file(self, file_path: str):
        """Save world state to a file."""
        pass  # Implementation depends on file format

    @classmethod
    def load_area(cls, data_dir: Path, area_id: str) -> Area:
        """Load an area from a JSON file.

        Tries ``data_dir/area-<area_id>.json`` first, then falls back
        to ``data_dir/current_area_data.json`` for legacy saves.
        Runs :func:`~backend.engine.save_format.migrate` on the raw
        data before deserialising.

        Args:
            data_dir: Directory where area files are stored.
            area_id: ID of the area to load.

        Returns:
            Populated Area instance.

        Raises:
            FileNotFoundError: If neither file path exists.
        """
        primary = data_dir / f"area-{area_id}.json"
        legacy = data_dir / "current_area_data.json"

        if primary.exists():
            area_file = primary
        elif legacy.exists():
            area_file = legacy
        else:
            raise FileNotFoundError(
                f"Area file not found for area_id={area_id!r} " f"in {data_dir}"
            )

        with open(area_file, "r", encoding="utf-8") as fh:
            raw = json.load(fh)

        data = migrate(raw)
        return cls.from_dict(data)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the area to a dictionary."""
        return {
            "save_version": SAVE_VERSION,
            "area_id": self.area_id,
            "area_name": self.area_name,
            "width": self.width,
            "height": self.height,
            "entities": [entity.to_dict() for entity in self.entities.values()],
            "groups": self.groups.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Area:
        """Reconstruct an Area from a serialised dict.

        Rebuilds the spatial grid from loaded entity positions.

        Args:
            data: Dict produced by :meth:`to_dict`, already migrated.

        Returns:
            Populated Area instance.
        """
        area = cls(
            area_id=data.get("area_id"),
            area_name=data.get("area_name", "Untitled Area"),
        )
        area.width = data.get("width", DEF_AREA_WIDTH)
        area.height = data.get("height", DEF_AREA_HEIGHT)
        area.spatial_grid = SpatialGrid(area.width, area.height)

        entities_raw = data.get("entities", [])
        # Support both list (new format) and dict (legacy format).
        if isinstance(entities_raw, dict):
            entity_iter = entities_raw.values()
        else:
            entity_iter = entities_raw
        for entity_data in entity_iter:
            entity = Entity.deserialize(entity_data)
            area.add_entity(entity)

        area.groups = GroupRegistry.from_dict(data.get("groups", {}))

        return area

    def save_to_file(self, save_dir: Path) -> None:
        """Save the area to ``save_dir/area-<area_id>.json``.

        Args:
            save_dir: Target directory (e.g. ``saves/<player_id>/``).
        """
        save_dir.mkdir(parents=True, exist_ok=True)
        area_file = save_dir / f"area-{self.area_id or 'unknown'}.json"
        with open(area_file, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=4)

    def save_area_to_file(
        self, data_dir: Path, file_name: str = "current_area_data.json"
    ):
        """Save the area to a JSON file.

        Args:
            data_dir: Directory where area files are stored
            file_name: Name of the area file to save
                - Defaults to "current_area_data.json"
                - Can include "{area_id}" placeholder to insert area ID
        """
        file_name = file_name.replace("{area_id}", self.area_id or "unknown")
        area_file = data_dir / file_name
        area_file.parent.mkdir(parents=True, exist_ok=True)

        with open(area_file, "w") as f:
            json.dump(self.to_dict(), f, indent=4)
