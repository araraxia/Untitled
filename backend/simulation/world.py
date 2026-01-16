

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