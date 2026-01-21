from dataclasses import dataclass


@dataclass
class BlankBackground:
    """"""

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

    # Resistance variances
    ## Physical
    additional_physical_resistance: int = 0
    physical_resistance_variance: int = 0
    additional_stab_resistance_modifier: float = 0
    additional_slash_resistance_modifier: float = 0
    additional_blunt_resistance_modifier: float = 0

    ## Magical
    additional_magical_resistance: int = 0
    magical_resistance_variance: int = 0
    additional_fire_resistance_modifier: float = 0
    additional_ice_resistance_modifier: float = 0
    additional_lightning_resistance_modifier: float = 0
    additional_curse_resistance_modifier: float = 0
    additional_magic_illusion_resistance_modifier: float = 0

    ## Mental
    additional_mental_resistance: int = 0
    mental_resistance_variance: int = 0
    additional_pain_resistance_modifier: float = 0
    additional_mental_illusion_resistance_modifier: float = 0

    ## Other
    additional_poison_resistance: int = 0
    poison_resistance_variance: int = 0
    additional_disease_resistance: int = 0
    disease_resistance_variance: int = 0

    # Other Stats
    additional_fame: int = 0
    additional_virtue: int = 0
    additional_infamy: int = 0
    additional_karma: int = 0


@dataclass
class TideMarkedOutcast:
    additional_perception: int = 3
    additional_willpower: int = 3
    additional_charisma: int = -3
    additional_magical_resistance: int = 2
    additional_lightning_resistance_modifier: float = 0.7
    additional_infamy: int = 6
    lore_text: str = (
        "Born under the shifting tides, you have always felt a deep connection to the sea. "
        "Your keen perception and strong will have helped you survive the harshest of storms, "
        "but your outsider status has made it difficult to form lasting bonds with others."
    )


@dataclass
class AshenChoirSurvivor:
    additional_intelligence: int = 3
    intelligence_variance: int = 2
    additional_soul_power: int = 2
    additional_fire_resistance_modifier: float = 0.5
    additional_mental_resistance: int = 4
    additional_karma: int = -2


@dataclass
class BrokenBannerHeir:
    additional_charisma: int = 1
    additional_willpower: int = 4
    additional_combat_sense: int = 2
    additional_fame: int = 2
    additional_infamy: int = 4


@dataclass
class ClockmakersCreation:
    additional_intelligence: int = 4
    additional_dexterity: int = 2
    additional_physical_resistance: int = 3
    additional_mental_resistance: int = 1
    additional_pain_resistance_modifier: float = 0.7
    additional_charisma: int = -4


@dataclass
class OrchardWitch:
    additional_intelligence: int = 2
    additional_perception: int = 3
    additional_soul_power: int = 2
    poison_resistance_variance: int = 2
    disease_resistance_variance: int = 2


@dataclass
class OathBoundMercenary:
    additional_strength: int = 2
    additional_combat_sense: int = 3
    additional_willpower: int = 2
    additional_charisma: int = -2
    additional_karma: int = -6


@dataclass
class ChildOfTwoSuns:
    additional_soul_power: int = 4
    additional_charisma: int = 2
    additional_fire_resistance_modifier: float = 0.4
    additional_luck: int = -2


@dataclass
class ForbiddenNameLibrarian:
    additional_intelligence: int = 4
    additional_perception: int = 2
    additional_magic_illusion_resistance_modifier: float = 0.3
    additional_infamy: int = 7


@dataclass
class BoneRiverNomad:
    additional_endurance: int = 3
    additional_willpower: int = 2
    additional_soul_power: int = 1
    additional_poison_resistance: int = 2


@dataclass
class CrownlessPretender:
    additional_charisma: int = 3
    additional_willpower: int = 2
    additional_luck: int = -3
    additional_fame: int = 3
    additional_infamy: int = 3


@dataclass
class EmberMarkedMidwife:
    additional_intelligence: int = 2
    additional_willpower: int = 3
    additional_fire_resistance_modifier: float = 0.6
    additional_virtue: int = 2


@dataclass
class SkyFallenKnight:
    additional_strength: int = 2
    additional_endurance: int = 3
    additional_combat_sense: int = 2
    additional_speed: int = -1
    additional_lightning_resistance_modifier: float = 0.8


@dataclass
class SpiritDebtCollector:
    additional_soul_power: int = 3
    additional_mental_resistance: int = 4
    additional_curse_resistance_modifier: float = 0.6
    additional_karma: int = -8


@dataclass
class PaintedBarbarian:
    additional_strength: int = 3
    additional_endurance: int = 3
    additional_charisma: int = -1
    additional_pain_resistance_modifier: float = 0.6


@dataclass
class AcademyDropout:
    additional_intelligence: int = 2
    additional_dexterity: int = 2
    additional_luck: int = -1
    additional_infamy: int = 4


@dataclass
class HollowEyedOracle:
    additional_perception: int = 4
    additional_intelligence: int = 2
    additional_charisma: int = -3
    additional_mental_illusion_resistance_modifier: float = 0.3


@dataclass
class RuneboundSmith:
    additional_strength: int = 2
    additional_endurance: int = 2
    additional_intelligence: int = 2
    additional_luck: int = -5


@dataclass
class ForgottenGodChampion:
    additional_soul_power: int = 4
    additional_willpower: int = 2
    additional_luck: int = -3
    additional_karma: int = -4


@dataclass
class SewerCrownPrince:
    additional_charisma: int = 2
    additional_perception: int = 3
    additional_dexterity: int = 2
    poison_resistance_variance: int = 2


@dataclass
class LastWeatherBinder:
    additional_soul_power: int = 3
    additional_intelligence: int = 2
    additional_lightning_resistance_modifier: float = 0.6
    additional_ice_resistance_modifier: float = 0.6
    additional_endurance: int = -1
