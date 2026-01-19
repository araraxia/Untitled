from dataclasses import dataclass
from email.mime import base


@dataclass
class Human:
    """
    Docstring for Human
    """

    # Base attributes and their variances
    base_strength: int = 10
    strength_variance: int = 2

    base_dexterity: int = 10
    dexterity_variance: int = 3

    base_intelligence: int = 10
    intelligence_variance: int = 4

    base_willpower: int = 10
    willpower_variance: int = 4

    base_charisma: int = 10
    charisma_variance: int = 3

    base_perception: int = 10
    perception_variance: int = 2

    base_endurance: int = 10
    endurance_variance: int = 2

    base_luck: int = 10
    luck_variance: int = 5

    base_speed: int = 10
    speed_variance: int = 2

    base_soul_power: int = 20
    soul_power_variance: int = 5

    base_combat_sense: int = 10
    combat_sense_variance: int = 3

    # Resistance variances
    ## Physical
    base_physical_resistance: int = 10
    physical_resistance_variance: int = 2
    base_stab_resistance_modifier: int = 1
    base_slash_resistance_modifier: int = 1
    base_blunt_resistance_modifier: int = 1

    ## Magical
    base_magical_resistance: int = 10
    magical_resistance_variance: int = 2
    fire_resistance_modifier: int = 1
    ice_resistance_modifier: int = 1
    lightning_resistance_modifier: int = 1
    curse_resistance_modifier: int = 1
    magic_illusion_resistance_modifier: int = 0.5

    ## Mental
    base_mental_resistance: int = 10
    mental_resistance_variance: int = 5
    pain_resistance_modifier: int = 1
    mental_illusion_resistance_modifier: int = 0.5

    ## Other
    base_poison_resistance: int = 10
    poison_resistance_variance: int = 1
    base_disease_resistance: int = 10
    disease_resistance_variance: int = 10

    def generate_attributes(self, max_attempts: int = 100) -> dict:
        """
        Generate human attributes with variance applied.
        Prevents all stats from being outliers by checking total deviation.
        Rerolls if character is too extreme (all high or all low).
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


if __name__ == "__main__":
    human = Human()

    # Test multiple generations to see distribution
    print("Testing 10 human attribute generations:\n")
    for i in range(10):
        attrs = human.generate_attributes()
        total = sum(attrs.values())
        print(f"Character {i+1} (total: {total}):")
        for attr, value in attrs.items():
            print(f"  {attr}: {value}")
