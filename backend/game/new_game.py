from backend.engine.game_loop import GameLoop
from backend.game.entities.player import PlayerCharacter
from backend.game.world import World
from backend.game.area import Area
from backend.engine.ecs.entity import Entity
from backend.game.entities.races import get_all_races, get_race_by_id

import uuid
from dataclasses import asdict


class NewGameManager:
    def __init__(self, game_loop: GameLoop):
        self.game_loop = game_loop
        self.player_character = None

    def init_new_game(self, save_name: str):
        """Initialize a new save file for a new game.

        Args:
            save_name: Name of the new save file

        """
        player_id = str(uuid.uuid4())
        player_character = PlayerCharacter(player_id=player_id)
        player_character.world_id = "overworld_001"
        player_character.area_id = "character_creation"
        player_character.player_name = save_name
        self.player_character = player_character

    def get_available_races(self) -> dict:
        """Get all available races for character creation.

        Returns:
            Dict with race IDs as keys and race data as values (serializable)
        """
        races = get_all_races()
        return {
            race_id: {
                "id": race.id,
                "name": race.name,
                "description": race.description,
                "lore_text": race.lore_text,
                "base_stats": {
                    "strength": race.base_strength,
                    "dexterity": race.base_dexterity,
                    "intelligence": race.base_intelligence,
                    "willpower": race.base_willpower,
                    "charisma": race.base_charisma,
                    "perception": race.base_perception,
                    "endurance": race.base_endurance,
                    "luck": race.base_luck,
                    "speed": race.base_speed,
                    "soul_power": race.base_soul_power,
                    "combat_sense": race.base_combat_sense,
                },
            }
            for race_id, race in races.items()
        }

    def get_backgrounds_for_race(self, race_id: str) -> dict:
        """Get available backgrounds for a specific race.

        Args:
            race_id: The ID of the race

        Returns:
            Dict with background names as keys and background data as values (serializable)
        """
        race = get_race_by_id(race_id)
        if not race:
            return {}

        backgrounds = race.get_backgrounds()
        result = {}

        for bg_name, bg_instance in backgrounds.items():
            bg_data = asdict(bg_instance)
            # Add the display name
            bg_data["display_name"] = bg_name
            result[bg_name] = bg_data

        return result

    def init_new_character(
        self,
        character_name: str,
        race_id: str = "human",
        background_name: str = None,
        personality: list = None,
        appearance: dict = None,
        stats: dict = None,
        items: list = None,
    ) -> Entity:
        """Initialize a new character entity and add to the player's control.

        Args:
            character_name: Name of the new character
            race_id: ID of the selected race (default: "human")
            background_name: Name of the selected background (optional)
            personality: List of personality traits
            appearance: Dict of appearance options
            stats: Dict of character stats
            items: List of starting items

        Returns:
            The created Entity
        """
        # Get race and background data
        race = get_race_by_id(race_id)
        if not race:
            raise ValueError(f"Race {race_id} not found")

        # Generate entity ID
        entity_id = str(uuid.uuid4())

        # Create entity
        entity = Entity(
            entity_id=entity_id,
            x=500.0,  # Default spawn position
            y=300.0,
            state="idle",
            facing="down",
        )

        # character_name/race_id/background_name/personality/appearance/
        # stats/items are accepted (client still sends them) but not
        # persisted onto the entity: Entity no longer carries ad-hoc
        # RPG/appearance fields (backend/engine/ecs/entity.py), and this
        # data isn't read by anything downstream yet. Once a real
        # consumer exists, store it via entity.set_data(...) instead of
        # reintroducing hardcoded fields.

        # Add entity to player's controlled entities
        if self.player_character:
            self.player_character.add_controlled_entity(entity)

            # Set this as the active entity
            self.player_character.set_active_entity_by_id(entity_id)

            # Save entity to file
            from pathlib import Path

            entity.save_to_file()

        return entity
