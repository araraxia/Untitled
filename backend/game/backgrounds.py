from dataclasses import dataclass, field


@dataclass
class BlankBackground:
    """Base background class with all default attributes.

    Games built on this engine define their own backgrounds; this file
    keeps a neutral default plus one populated example to demonstrate
    the stat-bonus pattern new_game.py and character_creation.py expect.
    """

    tags: list = field(default_factory=lambda: ["human", "common"])

    # Base attributes and their variances
    additional_strength: int = 0
    strength_variance: int = 0

    additional_dexterity: int = 0
    dexterity_variance: int = 0

    additional_intelligence: int = 0
    intelligence_variance: int = 0

    additional_willpower: int = 0
    willpower_variance: int = 0

    additional_charisma: int = 0
    charisma_variance: int = 0

    additional_perception: int = 0
    perception_variance: int = 0

    additional_endurance: int = 0
    endurance_variance: int = 0

    additional_luck: int = 0
    luck_variance: int = 0

    additional_speed: int = 0
    speed_variance: int = 0

    additional_soul_power: int = 0
    soul_power_variance: int = 0

    additional_combat_sense: int = 0
    combat_sense_variance: int = 0

    lore_text: str = (
        "You come from a humble background with no notable history or traits. "
        "Your life has been ordinary, and you possess no special advantages or disadvantages. "
        "You are a blank slate, ready to carve your own path in the world."
    )


@dataclass
class Wanderer(BlankBackground):
    tags: list = field(default_factory=lambda: ["human", "traveler"])
    additional_endurance: int = 2
    additional_perception: int = 2
    additional_charisma: int = -1
    lore_text: str = (
        "You have spent years on the road, relying on sharp senses and a "
        "hardy constitution rather than a settled life."
    )


def get_classes_by_tag(tag):
    """Get background classes filtered by a specific tag.

    Args:
        tag: The tag to filter by (e.g., "human", "common")

    Returns:
        A dict mapping display names to background class instances that have the specified tag.
    """
    all_backgrounds = {
        "Blank Background": BlankBackground(),
        "Wanderer": Wanderer(),
    }

    return {name: bg for name, bg in all_backgrounds.items() if tag in bg.tags}
