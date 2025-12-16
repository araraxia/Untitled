"""World state manager."""

from typing import Dict, List, Any, Optional
from backend.config import WORLD_WIDTH, WORLD_HEIGHT
from backend.simulation.entity import Entity
from backend.simulation.player import PlayerCharacter
from backend.simulation.spatial import SpatialGrid


class World:
    """Manages the game world state and entities."""

    def __init__(self):
        self.width = WORLD_WIDTH
        self.height = WORLD_HEIGHT
        self.entities: Dict[str, Entity] = {}
        self.player: Optional[PlayerCharacter] = None
        self.spatial_grid = SpatialGrid(WORLD_WIDTH, WORLD_HEIGHT)
        self.dirty_entities: set = set()
        self.removed_entities: set = set()

        # Initialize with a player character
        self._initialize_player()

    def _initialize_player(self, x_pos: float = -1, y_pos: float = -1):
        """Create the initial player character."""
        # Spawn player in the center of the world if no position provided
        if x_pos < 0:
            x_pos = WORLD_WIDTH // 2
        if y_pos < 0:
            y_pos = WORLD_HEIGHT // 2
        
        self.player = PlayerCharacter(
            entity_id="player_1", x=x_pos, y=y_pos
        )
        self.add_entity(self.player)

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
        if self.player:
            self.player.execute_action(action)
            self.dirty_entities.add(self.player.entity_id)

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
