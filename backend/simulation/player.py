"""Player character with deep action system."""

from typing import Dict, Any, Optional, List
from backend.simulation.entity import Entity
from backend.simulation.actions import ActionFactory
from pathlib import Path
import json

FILE_PATH = Path(__file__).resolve()
ROOT_DIRECTORY = FILE_PATH.parent.parent.parent
DATA_DIRECTORY = ROOT_DIRECTORY / "frontend" / "assets" / "data"
PLAYER_DIRECTORY = DATA_DIRECTORY / "player"


class PlayerCharacter:
    """Player controller that can control multiple entities simultaneously.

    This class acts as a shell/controller for entities, translating player inputs
    into actions for controlled entities. The player can manage a party of entities
    and switch focus between them.
    """

    def __init__(
        self,
        player_id: str = "00000000-0000-0000-0000-000000000000",
        player_name: str = "Player",
    ):
        # 00000000-0000-0000-0000-000000000000 is the default ID for non-persistent players.
        self.player_id = player_id
        self.player_name = player_name
        self.world_id: str = ""  # Current world ID the player is in
        self.area_id: str = ""  # Current area ID the player is in
        self.active_entity_index: int = (
            0  # Index of currently active entity for direct manual control
        )
        self.controlled_entity_ids: List[str] = []  # Currently controlled entity IDs
        self.controlled_entity_objs: List[Entity] = (
            []
        )  # Currently controlled entity objects
        self.controlled_entity_history: List[str] = (
            []
        )  # List of entity IDs ever controlled
        self.current_selected_entities: List[str] = []  # Currently selected entity IDs
        self.current_selected_entity_objs: List[Entity] = (
            []
        )  # Currently selected entity objects

        # Player-specific attributes (not tied to any entity)
        self.player_inventory = {}  # Global items by player across entities
        self.player_stats = {
            "total_playtime": 0.0,
            "entities_controlled": 0,
            "achievements": [],
            "last_save_timestamptz": None,
        }
        self.current_action: Optional[Any] = None

    def add_controlled_entity(self, entity: Entity):
        """Add an entity to the player's controlled party.

        Args:
            entity: The Entity to add to control
        """
        if entity and entity.entity_id not in self.controlled_entity_ids:
            self.controlled_entity_ids.append(entity.entity_id)
            self.controlled_entity_objs.append(entity)
            if entity.entity_id not in self.controlled_entity_history:
                self.controlled_entity_history.append(entity.entity_id)
                self.player_stats["entities_controlled"] += 1

    def remove_controlled_entity(self, entity: Entity):
        """Remove an entity from the player's controlled party.

        Args:
            entity: The Entity to remove from control
        """
        if entity.entity_id in self.controlled_entity_ids:
            self.controlled_entity_ids.remove(entity.entity_id)
            self.controlled_entity_objs.remove(entity)
            # Adjust active index if needed
            if self.active_entity_index >= len(self.controlled_entity_objs):
                self.active_entity_index = max(0, len(self.controlled_entity_objs) - 1)

    def get_active_entity(self) -> Optional[Entity]:
        """Get the currently active entity for direct control.

        Returns:
            The active Entity or None
        """
        if 0 <= self.active_entity_index < len(self.controlled_entity_objs):
            return self.controlled_entity_objs[self.active_entity_index]
        return None

    def get_controlled_entities(self) -> List[Entity]:
        """Get all entities currently controlled by this player.

        Returns:
            List of controlled entities
        """
        return self.controlled_entity_objs

    def set_active_entity_by_index(self, index: int):
        """Set the active entity by index in the controlled entities list.

        Args:
            index: Index of the entity to make active
        """
        if 0 <= index < len(self.controlled_entity_objs):
            self.active_entity_index = index

    def set_active_entity_by_id(self, entity_id: str):
        """Set the active entity by entity ID.

        Args:
            entity_id: ID of the entity to make active
        """
        for i, entity in enumerate(self.controlled_entity_objs):
            if entity.entity_id == entity_id:
                self.active_entity_index = i
                break

    def cycle_active_entity(self, direction: int = 1):
        """Cycle through controlled entities.

        Args:
            direction: 1 for next, -1 for previous
        """
        if self.controlled_entity_objs:
            self.active_entity_index = (self.active_entity_index + direction) % len(
                self.controlled_entity_objs
            )

    def execute_action(self, action_data: Dict[str, Any]):
        """Translate player input into an action for the active entity or party.

        Args:
            action_data: Dictionary containing action type and parameters
                        Can include 'target_entity_id' to specify which entity should act,
                        or 'apply_to_party' to apply to all controlled entities
        """
        action_type = action_data.get("type")
        target_entity_id = action_data.get("target_entity_id")
        apply_to_party = action_data.get("apply_to_party", False)

        # Determine which entity(ies) to apply action to
        if apply_to_party:
            target_entities = self.controlled_entity_objs
        elif target_entity_id:
            target_entities = [
                e
                for e in self.controlled_entity_objs
                if e.entity_id == target_entity_id
            ]
        else:
            active = self.get_active_entity()
            target_entities = [active] if active else []

        if not target_entities:
            return

        # Apply action to target entities
        for entity in target_entities:
            if action_type == "move":
                # Translate movement input to entity movement
                direction = action_data.get("direction", {})
                speed = 50.0 * entity.modifiers.get("walking_speed", 1.0)

                entity.vx = direction.get("x", 0) * speed
                entity.vy = direction.get("y", 0) * speed
                entity.state = (
                    "moving" if (entity.vx != 0 or entity.vy != 0) else "idle"
                )

                # Update facing direction based on movement
                if entity.vy < 0:
                    entity.facing = "up"
                elif entity.vy > 0:
                    entity.facing = "down"
                elif entity.vx < 0:
                    entity.facing = "left"
                elif entity.vx > 0:
                    entity.facing = "right"

                entity.is_dirty = True

            elif action_type == "attack":
                # Translate attack input to entity attack
                target_id = action_data.get("target_id")
                entity.state = "attacking"
                entity.is_dirty = True

            elif action_type == "use_item":
                # Translate item use to entity action
                item_id = action_data.get("item_id")
                entity.state = "using_item"
                entity.is_dirty = True

            elif action_type == "interact":
                # Generic interaction
                target_id = action_data.get("target_id")
                entity.state = "interacting"
                entity.is_dirty = True

    def serialize(self) -> Dict[str, Any]:
        """Serialize player controller state.

        Returns:
            Dictionary containing player state (not entity state)
        """
        return {
            "player_id": self.player_id,
            "player_name": self.player_name,
            "controlled_entity_ids": [e.entity_id for e in self.controlled_entity_objs],
            "active_entity_index": self.active_entity_index,
            "controlled_entities_history": self.controlled_entity_history,
            "player_inventory": self.player_inventory,
            "player_stats": self.player_stats,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Alias for serialize() to maintain compatibility.

        Returns:
            Dictionary containing player state (not entity state)
        """
        return self.serialize()

    def save_to_file(self, directory: Path = PLAYER_DIRECTORY) -> str:
        """Save player controller data to a JSON file named with the player ID.

        Args:
            directory: Directory to save the file in (default: 'data/players')

        Returns:
            str: Path to the saved file
        """
        # Create directory if it doesn't exist
        save_dir = Path(directory)
        save_dir.mkdir(parents=True, exist_ok=True)

        # Prepare data to save (player controller data only)
        data = self.serialize()

        # Save to file
        file_path = save_dir / f"player-{self.player_id}.json"
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)

        return str(file_path)

    @classmethod
    def load_from_file(
        cls, file_path: Path, load_entities: bool = True
    ) -> "PlayerCharacter":
        """Load player controller data from a JSON file.

        Args:
            file_path: Path to the JSON file containing player data

        Returns:
            PlayerCharacter: A new PlayerCharacter instance with loaded data
        """
        # Load player data first
        with open(file_path, "r") as f:
            data = json.load(f)

        # Create player controller
        player = cls(
            player_id=data.get("player_id"),
            player_name=data.get("player_name", "Player"),
        )
        player.world_id = data.get("world_id", "")
        player.area_id = data.get("area_id", "")
        player.active_entity_index = data.get("active_entity_index", 0)
        player.controlled_entity_ids = data.get("controlled_entity_ids", [])
        player.controlled_entity_history = data.get("controlled_entity_history", [])
        player.current_selected_entities = data.get("current_selected_entities", [])
        player.player_inventory = data.get("player_inventory", {})
        player.player_stats = data.get(
            "player_stats",
            {"total_playtime": 0.0, "entities_controlled": 0, "achievements": []},
        )
        player.current_action = data.get("current_action", None)

        # Load entities if requested
        if load_entities:
            player.load_controlled_entities()

        return player

    @classmethod
    def load_by_id(
        cls,
        player_id: str,
        directory: Path = PLAYER_DIRECTORY,
        load_entities: bool = True,
    ) -> "PlayerCharacter":
        """Load player controller data using player ID to construct the file path.

        This method will automatically load all controlled entities from their files.

        Args:
            player_id: The player ID to load
            directory: Directory to load from (default: 'data/players')
            load_entities: Whether to automatically load entity objects (default: True)

        Returns:
            PlayerCharacter: A new PlayerCharacter instance with loaded data and entities
        """
        file_path = Path(directory) / f"player-{player_id}.json"
        return cls.load_from_file(file_path, entity_lookup=None)

    def load_controlled_entities(self):
        """Load all controlled entities from their files.

        This method loads Entity objects for all entity IDs in controlled_entity_ids.
        """
        self.controlled_entity_objs = []

        for entity_id in self.controlled_entity_ids:
            try:
                entity = Entity.load_by_id(entity_id)
                self.controlled_entity_objs.append(entity)
            except Exception as e:
                print(f"Warning: Failed to load entity {entity_id}: {e}")
