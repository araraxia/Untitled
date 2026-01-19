

from typing import Optional
import uuid, json
from pathlib import Path

class World:
    def __init__(self, world_id: Optional[str] = None, world_name: str = "Untitled World"):
        self.world_id = world_id
        self.world_name = world_name
    
    @classmethod
    def load_world(cls, data_dir: Path, world_id: str) -> "World":
        """Load world data from a JSON file.

        Args:
            data_dir: Directory where world data is stored
            world_id: ID of the world to load
        """
        world_file = data_dir / f"world-{world_id}.json"
        if not world_file.exists():
            raise FileNotFoundError(f"World file {world_file} does not exist.")

        with open(world_file, "r") as f:
            data = json.load(f)

        world = cls(world_id=world_id, world_name=data.get("world_name", "Untitled World"))
        # Load additional world attributes as needed

        return world

    def save_to_file(self, data_dir: Path, file_name: str = "current_world_data.json"):
        """Save the world to a JSON file.

        Args:
            data_dir: Directory where world data should be saved
            file_name: Name of the file to save the world data
                - use "{world_id}" in the file name to include the world ID
        """
        world_file = data_dir / file_name.replace("{world_id}", self.world_id or "unknown")
        world_file.parent.mkdir(parents=True, exist_ok=True)

        with open(world_file, "w") as f:
            json.dump(self.to_dict(), f, indent=4)
            
    def to_dict(self) -> dict:
        """Serialize the world to a dictionary."""
        return {
            "world_id": self.world_id,
            "world_name": self.world_name,
            # Add additional world attributes as needed
        }