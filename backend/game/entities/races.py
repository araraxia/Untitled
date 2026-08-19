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

    def get_backgrounds(self) -> Dict[str, object]:
        """Get available backgrounds for this race"""
        from backend.game.backgrounds import get_classes_by_tag as get_bg_by_tag

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
        "Humans are the most diverse and ambitious of all races, found in "
        "every corner of the world, pursuing countless paths and destinies."
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
