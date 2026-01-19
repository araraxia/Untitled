
from pathlib import Path
import sys

FILE_PATH = Path(__file__).resolve()
ROOT_DIR = FILE_PATH.parent.parent.parent
if not str(ROOT_DIR) in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.game_loop import GameLoop
from backend.simulation.player import PlayerCharacter
from backend.simulation.world import World
from backend.simulation.area import Area
from backend.simulation.entity import Entity

import uuid

class NewGameManager():
    def __init__(self, game_loop: GameLoop):
        self.game_loop = game_loop
        
    def init_new_player(self, player_name: str) -> PlayerCharacter:
        """Initialize a new player character and load into the game loop.

        Args:
            player_name: Name of the new player character
        Returns:
            The initialized PlayerCharacter
        """
        # Create a new player character
        player_id = str(uuid.uuid4())
        player_character = PlayerCharacter(
            player_id=player_id,
        )
        player_character.world_id = "overworld_001"
        player_character.area_id = "character_creation"

        return player_character
