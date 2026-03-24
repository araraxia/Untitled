"""
Race definitions for character creation.
Each race has base stats, available backgrounds, and other characteristics.
"""

from dataclasses import dataclass, asdict
from typing import Dict, List


@dataclass
class Race:
    """Base race dataclass"""

    id: str
    name: str
    description: str
    lore_text: str

    # Base stats
    base_strength: int = 10
    base_dexterity: int = 10
    base_intelligence: int = 10
    base_willpower: int = 10
    base_charisma: int = 10
    base_perception: int = 10
    base_endurance: int = 10
    base_luck: int = 10
    base_speed: int = 10
    base_soul_power: int = 20
    base_combat_sense: int = 10

    # Variance ranges
    strength_variance: int = 2
    dexterity_variance: int = 3
    intelligence_variance: int = 4
    willpower_variance: int = 4
    charisma_variance: int = 3
    perception_variance: int = 2
    endurance_variance: int = 2
    luck_variance: int = 5
    speed_variance: int = 2
    soul_power_variance: int = 5
    combat_sense_variance: int = 3

    # Resistances
    base_physical_resistance: int = 10
    physical_resistance_variance: int = 2
    base_stab_resistance_modifier: float = 1.0
    base_slash_resistance_modifier: float = 1.0
    base_blunt_resistance_modifier: float = 1.0

    base_magical_resistance: int = 10
    magical_resistance_variance: int = 2
    fire_resistance_modifier: float = 1.0
    ice_resistance_modifier: float = 1.0
    lightning_resistance_modifier: float = 1.0
    curse_resistance_modifier: float = 1.0
    magic_illusion_resistance_modifier: float = 0.5

    base_mental_resistance: int = 10
    mental_resistance_variance: int = 5
    pain_resistance_modifier: float = 1.0
    mental_illusion_resistance_modifier: float = 0.5

    base_poison_resistance: int = 10
    poison_resistance_variance: int = 1
    base_disease_resistance: int = 10
    disease_resistance_variance: int = 10

    # Other stats
    base_fame: int = 0
    base_virtue: int = 0
    base_infamy: int = 0
    base_karma: int = 0

    def get_backgrounds(self) -> Dict[str, object]:
        """Get available backgrounds for this race"""
        from backend.simulation.backgrounds import get_classes_by_tag as get_bg_by_tag
        return get_bg_by_tag(self.id)

    def generate_attributes(self, max_attempts: int = 100) -> dict:
        """
        Generate race attributes with variance applied.
        Prevents all stats from being outliers by checking total deviation.
        Rerolls if character is too extreme (all high or all low).

        Args:
            max_attempts: Maximum number of reroll attempts (default: 100)

        Returns:
            Dictionary of generated attributes with variance applied
        """
        import random

        base_values = {
            "strength": self.base_strength,
            "dexterity": self.base_dexterity,
            "intelligence": self.base_intelligence,
            "willpower": self.base_willpower,
            "charisma": self.base_charisma,
            "perception": self.base_perception,
            "endurance": self.base_endurance,
            "luck": self.base_luck,
            "speed": self.base_speed,
            "soul_power": self.base_soul_power,
            "combat_sense": self.base_combat_sense,
        }

        variances = {
            "strength": self.strength_variance,
            "dexterity": self.dexterity_variance,
            "intelligence": self.intelligence_variance,
            "willpower": self.willpower_variance,
            "charisma": self.charisma_variance,
            "perception": self.perception_variance,
            "endurance": self.endurance_variance,
            "luck": self.luck_variance,
            "speed": self.speed_variance,
            "soul_power": self.soul_power_variance,
            "combat_sense": self.combat_sense_variance,
        }

        # Calculate acceptable deviation range
        # If all stats rolled max variance in same direction, that's too extreme
        max_possible_deviation = sum(variances.values())
        acceptable_deviation_threshold = (
            max_possible_deviation * 0.6
        )  # Allow 60% of max deviation

        for attempt in range(max_attempts):
            # Roll all attributes
            generated_attributes = {}
            total_deviation = 0

            for stat, base_value in base_values.items():
                variance = variances[stat]
                roll = random.randint(-variance, variance)
                generated_attributes[stat] = max(1, base_value + roll)
                total_deviation += abs(roll)

            # Check if total deviation is reasonable (not all stats are outliers)
            if total_deviation <= acceptable_deviation_threshold:
                return generated_attributes

        # If we exhausted attempts, return the last roll (very unlikely)
        return generated_attributes

    def to_dict(self) -> dict:
        """Convert race to dictionary for JSON serialization"""
        return asdict(self)


@dataclass
class Human(Race):
    """Human race - versatile and adaptable"""

    id: str = "human"
    name: str = "Human"
    description: str = (
        "Versatile and adaptable, humans are the most common race in the world."
    )
    lore_text: str = (
        "Humans are the most diverse and ambitious of all races. "
        "Born without the long lifespans of elves or the hardiness of dwarves, "
        "humans make up for it with determination, adaptability, and an unquenchable drive to leave their mark on the world. "
        "Their short lives burn brightly, and they can be found in every corner of the realm, "
        "pursuing countless paths and destinies."
    )


def get_all_races() -> Dict[str, Race]:
    """Get all available races for character creation"""
    return {
        "human": Human(),
        # Additional races can be added here
    }


def get_race_by_id(race_id: str) -> Race:
    """Get a specific race by its ID"""
    races = get_all_races()
    return races.get(race_id)
