"""World state manager."""

from typing import Dict, List, Any, Optional
from backend.config import DEF_AREA_WIDTH, DEF_AREA_HEIGHT
from backend.simulation.entity import Entity
from backend.simulation.player import PlayerCharacter
from backend.simulation.spatial import SpatialGrid
from pathlib import Path
import json


class Area:
    """Manages the game world state and entities."""

    def __init__(
        self, area_id: Optional[str] = None, area_name: str = "Untitled Area"
    ):
        self.area_id = area_id
        self.area_name = area_name
        self.width = DEF_AREA_WIDTH  # Default world dimensions
        self.height = DEF_AREA_HEIGHT  # Default world dimensions
        self.entities: Dict[str, Entity] = {}
        self.player_controller: Optional[PlayerCharacter] = None
        self.spatial_grid = SpatialGrid(DEF_AREA_WIDTH, DEF_AREA_HEIGHT)
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
    def load_area(
        cls, data_dir: Path, area_id: str
    ) -> "Area":
        """Load an area from a JSON file.

        Args:
            data_dir: Directory where area files are stored
            area_id: ID of the area to load
            world_id: ID of the world the area belongs to
        """
        area_file = data_dir / f"area-{area_id}.json"
        if not area_file.exists():
            raise FileNotFoundError(f"Area file {area_file} does not exist.")

        with open(area_file, "r") as f:
            data = json.load(f)

        area = cls(area_id=area_id, area_name=data.get("area_name", "Untitled Area"))
        area.width = data.get("width", DEF_AREA_WIDTH)
        area.height = data.get("height", DEF_AREA_HEIGHT)

        # Load entities
        entities_data = data.get("entities", {})
        for entity_id, entity_data in entities_data.items():
            entity = Entity.deserialize(entity_data)
            area.add_entity(entity)

        return area