"""Player character with deep action system."""

from typing import Dict, Any, Optional, List
from backend.simulation.entity import Entity
from backend.simulation.actions import ActionFactory
from pathlib import Path
import json

PLAYER_DIRECTORY = Path("data/players")


class PlayerCharacter(Entity):
    """Player character with deep action control."""

    def __init__(
        self,
        entity_id: str = "00000000-0000-0000-0000-000000000000",
        x: Optional[float] = None,
        y: Optional[float] = None,
        animation_data_paths: Optional[List[str]] = None,
    ):
        # 00000000-0000-0000-0000-000000000000 is the default ID for non-persistent players.
        super().__init__(entity_id, x, y, animation_data_paths=animation_data_paths)

        # Basic info
        self.name = "default"
        self.race = "human"
        self.model_version = "00"

        # Physical attributes
        self.height = 0
        self.weight = 0
        self.age = 0
        self.dob = "01/01/0001"
        self.gender = "unspecified"

        # Appearance
        self.hair_style = 0
        self.hair_color = 0
        self.left_eye_color = 0
        self.left_eye_type = 0
        self.right_eye_color = 0
        self.right_eye_type = 0

        # Progression
        self.experience = 0
        self.level = 1

        # Modifiers
        self.modifiers = {
            "action_speed": 1.0,
            "carrying_capacity": 1.0,
            "walking_speed": 1.0,
            "running_speed": 1.0,
            "crawling_speed": 1.0,
            "jumping_ability": 1.0,
            "strength": {},
            "dexterity": {},
            "intelligence": {},
            "perception": {},
            "willpower": {},
            "charisma": {},
        }

        # Stats
        self.stats = {"fame": 0, "virtue": 0, "infamy": 0}

        # Skills and abilities
        self.skills = {}
        self.abilities = {}

        # Health system
        self.health = {
            "head": {
                "left_eye": {},
                "right_eye": {},
                "mouth": {},
                "tongue": {},
                "skull": {},
                "brain": {},
            },
            "torso": {
                "chest": {},
                "stomach": {},
                "groin": {},
                "left_shoulder": {},
                "right_shoulder": {},
                "upper_back": {},
                "lower_back": {},
                "heart": {},
                "lung_left": {},
                "lung_right": {},
                "neck": {},
            },
            "left_arm": {
                "left_forearm": {},
                "left_upper_arm": {},
                "left_hand": {"left_fingers": {}},
            },
            "right_arm": {
                "right_forearm": {},
                "right_upper_arm": {},
                "right_hand": {"right_fingers": {}},
            },
            "left_hip": {},
            "right_hip": {},
            "left_leg": {
                "left_thigh": {},
                "left_knee": {},
                "left_calf": {},
                "left_foot": {},
            },
            "right_leg": {
                "right_thigh": {},
                "right_knee": {},
                "right_calf": {},
                "right_foot": {},
            },
        }

        # Combat and actions (legacy attributes)
        self.hp = 100
        self.max_hp = 100
        self.action_points = 100
        self.inventory = []
        self.equipment = {}
        self.current_action: Optional[Any] = None

    def execute_action(self, action_data: Dict[str, Any]):
        """Execute a player action."""
        action_type = action_data.get("type")

        if action_type == "move":
            # Simple movement for now
            direction = action_data.get("direction", {})
            speed = 50.0  # units per second
            self.vx = direction.get("x", 0) * speed
            self.vy = direction.get("y", 0) * speed
            self.state = "moving" if (self.vx != 0 or self.vy != 0) else "idle"

            # Update facing direction based on movement
            if self.vy < 0:
                self.facing = "up"
            elif self.vy > 0:
                self.facing = "down"
            elif self.vx < 0:
                self.facing = "left"
            elif self.vx > 0:
                self.facing = "right"

            self.is_dirty = True

        elif action_type == "attack":
            # Placeholder for attack action
            target_id = action_data.get("target_id")
            self.state = "attacking"
            self.is_dirty = True

        elif action_type == "use_item":
            # Placeholder for item use
            item_id = action_data.get("item_id")
            self.state = "using_item"
            self.is_dirty = True

    def consume_action_points(self, cost: int):
        """Consume action points for an action."""
        self.action_points = max(0, self.action_points - cost)
        self.is_dirty = True

    def serialize(self) -> Dict[str, Any]:
        """Serialize player state."""
        base_data = super().serialize()
        base_data.update(
            {
                "name": self.name,
                "race": self.race,
                "model_version": self.model_version,
                "height": self.height,
                "weight": self.weight,
                "age": self.age,
                "dob": self.dob,
                "gender": self.gender,
                "hair_style": self.hair_style,
                "hair_color": self.hair_color,
                "left_eye_color": self.left_eye_color,
                "left_eye_type": self.left_eye_type,
                "right_eye_color": self.right_eye_color,
                "right_eye_type": self.right_eye_type,
                "experience": self.experience,
                "level": self.level,
                "modifiers": self.modifiers,
                "stats": self.stats,
                "skills": self.skills,
                "abilities": self.abilities,
                "health": self.health,
                "hp": self.hp,
                "max_hp": self.max_hp,
                "action_points": self.action_points,
                "inventory": self.inventory,
                "equipment": self.equipment,
            }
        )
        return base_data

    def save_to_file(self, directory: Path = PLAYER_DIRECTORY) -> str:
        """Save player data to a JSON file named with the player UUID.

        Args:
            directory: Directory to save the file in (default: 'data/players')

        Returns:
            str: Path to the saved file
        """
        # Create directory if it doesn't exist
        save_dir = Path(directory)
        save_dir.mkdir(parents=True, exist_ok=True)

        # Prepare data to save (includes all player-specific attributes)
        data = {
            "uuid": self.entity_id,
            "x": self.x,
            "y": self.y,
            "vx": self.vx,
            "vy": self.vy,
            "state": self.state,
            "facing": self.facing,
            "animation_data_paths": self.animation_data_paths,
            "name": self.name,
            "race": self.race,
            "model_version": self.model_version,
            "height": self.height,
            "weight": self.weight,
            "age": self.age,
            "dob": self.dob,
            "gender": self.gender,
            "hair_style": self.hair_style,
            "hair_color": self.hair_color,
            "left_eye_color": self.left_eye_color,
            "left_eye_type": self.left_eye_type,
            "right_eye_color": self.right_eye_color,
            "right_eye_type": self.right_eye_type,
            "experience": self.experience,
            "level": self.level,
            "modifiers": self.modifiers,
            "stats": self.stats,
            "skills": self.skills,
            "abilities": self.abilities,
            "health": self.health,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "action_points": self.action_points,
            "inventory": self.inventory,
            "equipment": self.equipment,
        }

        # Save to file
        file_path = save_dir / f"{self.entity_id}.json"
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)

        return str(file_path)

    @classmethod
    def load_from_file(cls, file_path: Path) -> "PlayerCharacter":
        """Load player data from a JSON file.

        Args:
            file_path: Path to the JSON file containing player data

        Returns:
            PlayerCharacter: A new PlayerCharacter instance with loaded data
        """
        with open(file_path, "r") as f:
            data = json.load(f)

        # Create player with basic parameters (handle both 'uuid' and 'entity_id' keys)
        player = cls(
            entity_id=data.get(
                "uuid", data.get("entity_id", "00000000-0000-0000-0000-000000000000")
            ),
            x=data.get("x"),
            y=data.get("y"),
            animation_data_paths=data.get("animation_data_paths", []),
        )

        # Set Entity attributes
        player.vx = data.get("vx", 0.0)
        player.vy = data.get("vy", 0.0)
        player.state = data.get("state", "idle")
        player.facing = data.get("facing", "down")

        # Set basic info
        player.name = data.get("name", "default")
        player.race = data.get("race", "human")
        player.model_version = data.get("model_version", "00")

        # Set physical attributes
        player.height = data.get("height", 0)
        player.weight = data.get("weight", 0)
        player.age = data.get("age", 0)
        player.dob = data.get("dob", "01/01/0001")
        player.gender = data.get("gender", "unspecified")

        # Set appearance
        player.hair_style = data.get("hair_style", 0)
        player.hair_color = data.get("hair_color", 0)
        player.left_eye_color = data.get("left_eye_color", 0)
        player.left_eye_type = data.get("left_eye_type", 0)
        player.right_eye_color = data.get("right_eye_color", 0)
        player.right_eye_type = data.get("right_eye_type", 0)

        # Set progression
        player.experience = data.get("experience", 0)
        player.level = data.get("level", 1)

        # Set modifiers (merge with defaults)
        if "modifiers" in data:
            player.modifiers.update(data["modifiers"])

        # Set stats (merge with defaults)
        if "stats" in data:
            player.stats.update(data["stats"])

        # Set skills and abilities
        player.skills = data.get("skills", {})
        player.abilities = data.get("abilities", {})

        # Set health system (merge with defaults)
        if "health" in data:
            player.health.update(data["health"])

        # Set combat attributes
        player.hp = data.get("hp", 100)
        player.max_hp = data.get("max_hp", 100)
        player.action_points = data.get("action_points", 100)
        player.inventory = data.get("inventory", [])
        player.equipment = data.get("equipment", {})

        return player

    @classmethod
    def load_by_uuid(
        cls, uuid: str, directory: Path = PLAYER_DIRECTORY
    ) -> "PlayerCharacter":
        """Load player data using UUID to construct the file path.

        Args:
            uuid: The player UUID to load
            directory: Directory to load from (default: 'data/players')

        Returns:
            PlayerCharacter: A new PlayerCharacter instance with loaded data
        """
        file_path = Path(directory) / f"{uuid}.json"
        return cls.load_from_file(file_path)
