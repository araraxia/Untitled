"""Entity base class."""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional

ENTITY_DIR = Path("data/entities")

class Entity:
    """Base class for all entities in the simulation.

    Attributes:
        entity_id (str): Unique identifier for the entity.
        x (Optional[float]): X position of the entity.
        y (Optional[float]): Y position of the entity.
        vx (float): Velocity in the X direction.
        vy (float): Velocity in the Y direction.
        state (str): Current state of the entity (e.g., "idle", "moving").
        facing (str): Direction the entity is facing ("up", "down", "left", "right").
        animation_data_paths (List[str]): List of paths to animation data files.
    """

    def __init__(
        self,
        entity_id: str,
        x: Optional[float] = None,
        y: Optional[float] = None,
        state: str = "idle",
        facing: str = "down",
        animation_data_paths: Optional[List[str]] = None,
    ):
        self.entity_id = entity_id
        self.x = x if x is not None else -10000.0
        self.y = y if y is not None else -10000.0
        self.vx = 0.0  # velocity x
        self.vy = 0.0  # velocity y
        self.state = state # e.g., idle, moving, attacking
        self.facing = facing  # direction entity is facing: up, down, left, right
        self.is_dirty = True
        self.animation_data_paths = animation_data_paths or []

    def update(self, delta_time: float):
        """Update entity state."""
        # Update position based on velocity
        if self.vx != 0 or self.vy != 0:
            self.x += self.vx * delta_time
            self.y += self.vy * delta_time
            self.is_dirty = True

    def serialize(self) -> Dict[str, Any]:
        """Serialize entity state for network transmission."""
        return {
            "id": self.entity_id,
            "x": self.x,
            "y": self.y,
            "vx": self.vx,
            "vy": self.vy,
            "state": self.state,
            "facing": self.facing,
            "animation_data_paths": self.animation_data_paths,
        }

    def save_to_file(self, directory: Path = ENTITY_DIR) -> str:
        """Save entity data to a JSON file named with the entity ID.

        Args:
            directory: Directory to save the file in (default: 'data/entities')

        Returns:
            str: Path to the saved file
        """
        # Create directory if it doesn't exist
        save_dir = Path(directory)
        save_dir.mkdir(parents=True, exist_ok=True)

        # Prepare data to save
        data = {
            "entity_id": self.entity_id,
            "x": self.x,
            "y": self.y,
            "vx": self.vx,
            "vy": self.vy,
            "state": self.state,
            "facing": self.facing,
            "animation_data_paths": self.animation_data_paths,
        }

        # Save to file
        file_path = save_dir / f"{self.entity_id}.json"
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)

        return str(file_path)

    @classmethod
    def load_from_file(cls, file_path: Path) -> "Entity":
        """Load entity data from a JSON file.

        Args:
            file_path: Path to the JSON file containing entity data

        Returns:
            Entity: A new Entity instance with loaded data
        """
        with open(file_path, "r") as f:
            data = json.load(f)

        # Create entity with basic parameters
        entity = cls(
            entity_id=data["entity_id"],
            x=data["x"],
            y=data["y"],
            animation_data_paths=data.get("animation_data_paths", []),
        )

        # Set additional attributes
        entity.vx = data.get("vx", 0.0)
        entity.vy = data.get("vy", 0.0)
        entity.state = data.get("state", "idle")
        entity.facing = data.get("facing", "down")

        return entity

    @classmethod
    def load_by_id(cls, entity_id: str, directory: Path = ENTITY_DIR) -> "Entity":
        """Load entity data using entity ID to construct the file path.

        Args:
            entity_id: The entity ID to load
            directory: Directory to load from (default: 'data/entities')

        Returns:
            Entity: A new Entity instance with loaded data
        """
        file_path = Path(directory) / f"{entity_id}.json"
        return cls.load_from_file(file_path)

    def receive_command(self, command: Dict[str, Any]):
        """Receive a high-level command (for party members/AI entities)."""
        pass  # Override in subclasses
