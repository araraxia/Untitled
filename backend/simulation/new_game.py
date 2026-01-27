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
from backend.simulation.races import get_all_races, get_race_by_id

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

        backgrounds = race.get_backgrounds() if background_name else {}
        background = backgrounds.get(background_name) if background_name else None

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

        # Set basic info
        entity.name = character_name
        entity.race = race_id

        # Apply appearance if provided
        if appearance:
            # Map appearance options to entity attributes
            appearance_mapping = {
                "skinTone": "skin_tone",
                "hairColor": "hair_color",
                "eyeColor": "left_eye_color",
                "bodyType": "body_type",
            }
            for frontend_key, entity_attr in appearance_mapping.items():
                if frontend_key in appearance:
                    setattr(entity, entity_attr, appearance[frontend_key])

            # Set both eyes to same color if eyeColor was provided
            if "eyeColor" in appearance:
                entity.right_eye_color = appearance["eyeColor"]

        # Set stats from race base stats and background modifiers
        if stats:
            # Stats are already calculated on frontend, just store them
            entity.stats.update(stats)
        else:
            # Use race base stats if not provided
            base_stats = {
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
            }

            # Apply background modifiers if available
            if background:
                base_stats["strength"] += background.additional_strength
                base_stats["dexterity"] += background.additional_dexterity
                base_stats["intelligence"] += background.additional_intelligence
                base_stats["willpower"] += background.additional_willpower
                base_stats["charisma"] += background.additional_charisma
                base_stats["perception"] += background.additional_perception
                base_stats["endurance"] += background.additional_endurance
                base_stats["luck"] += background.additional_luck
                base_stats["speed"] += background.additional_speed
                base_stats["soul_power"] += background.additional_soul_power
                base_stats["combat_sense"] += background.additional_combat_sense

            entity.stats.update(base_stats)

        # Apply background-specific attributes if available
        if background:
            # Store fame, virtue, infamy, karma
            entity.stats["fame"] = (
                entity.stats.get("fame", 0) + background.additional_fame
            )
            entity.stats["virtue"] = (
                entity.stats.get("virtue", 0) + background.additional_virtue
            )
            entity.stats["infamy"] = (
                entity.stats.get("infamy", 0) + background.additional_infamy
            )
            entity.stats["karma"] = (
                entity.stats.get("karma", 0) + background.additional_karma
            )

            # Store resistance modifiers for future use
            resistances = {
                "physical_resistance": background.additional_physical_resistance,
                "magical_resistance": background.additional_magical_resistance,
                "mental_resistance": background.additional_mental_resistance,
                "poison_resistance": background.additional_poison_resistance,
                "disease_resistance": background.additional_disease_resistance,
                "fire_resistance_modifier": background.additional_fire_resistance_modifier,
                "ice_resistance_modifier": background.additional_ice_resistance_modifier,
                "lightning_resistance_modifier": background.additional_lightning_resistance_modifier,
                "curse_resistance_modifier": background.additional_curse_resistance_modifier,
                "pain_resistance_modifier": background.additional_pain_resistance_modifier,
            }
            entity.stats["resistances"] = resistances

        # Store personality and background info in entity metadata
        if personality:
            entity.stats["personality"] = personality
        if background_name:
            entity.stats["background"] = background_name

        # Add starting items to equipment
        if items:
            entity.equipment["inventory"] = items

        # Add entity to player's controlled entities
        if self.player_character:
            self.player_character.add_controlled_entity(entity)

            # Set this as the active entity
            self.player_character.set_active_entity_by_id(entity_id)

            # Save entity to file
            from pathlib import Path

            entity.save_to_file()

        return entity
