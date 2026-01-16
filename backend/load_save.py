
from pathlib import Path
import sys
from typing import Optional
from backend import game_loop
from backend.simulation.player import PlayerCharacter
from backend.simulation.entity import Entity
from backend.simulation.world import World
from backend.simulation.area import Area
from backend.game_loop import GameLoop
import threading

FILE_PATH = Path(__file__).resolve()
PROJECT_ROOT = FILE_PATH.parent.parent
DATA_PATH = PROJECT_ROOT / "frontend" / "assets" / "data"
PLAYER_DIR = DATA_PATH / "player"

class SaveManager():
    """Class to handle loading and saving game data."""
    def __init__(self, socketio, player_id: Optional[str] = None):
        self.socketio = socketio
        self.game_loop = None
        
        import uuid
        self.player_id = player_id
        if self.player_id is None:
            self.player_id = str(uuid.uuid4())
        
            
        self.player_data_dir: Path | None = None
        self.player = None
        self.player_controlled_entity_ids: list[str] = []
        self.player_controlled_entities: list[Entity] = []
        self.world_id = None
        self.world = None
        self.current_area_id = None
        self.current_area = None

    def load_game(self) -> PlayerCharacter:
        """Load a player from a JSON file."""
        self._verify_files()

        # Get player object, load attributes from file. 
        self.player = PlayerCharacter.load_from_file(
            file_path=self.player_file, load_entities=False
        )
        self.player_controlled_entity_ids = self.player.controlled_entity_ids
        
        self.world_id = self.player.world_id
        self.world = World.load_world(self.player_data_dir, self.world_id)
        
        self.current_area_id = self.player.area_id
        self.current_area = Area.load_area(
            self.player_data_dir, area_id=self.current_area_id
        )

        return self.game_loop

    def _verify_files(self):
        """Verify that necessary files and directories exist."""
        PLAYER_DIR.mkdir(parents=True, exist_ok=True)
        self.player_file = PLAYER_DIR / f"player-{self.player_id}.json"
        if not self.player_file.exists():
            raise FileNotFoundError(f"Player file {self.player_file} does not exist.")
        self.player_data_dir = PLAYER_DIR / f"player-{self.player_id}"

    @staticmethod
    def save_player(player: PlayerCharacter):
        """Save a player to a JSON file."""
        player_file = PLAYER_DIR / f"player-{player.player_id}.json"
        player_file.parent.mkdir(parents=True, exist_ok=True)

        with open(player_file, "w") as f:
            import json

            json.dump(player.to_dict(), f, indent=4)