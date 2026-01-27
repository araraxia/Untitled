from dataclasses import dataclass, field


@dataclass
class BlankBackground:
    """Base background class with all default attributes."""

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

    lore_text: str = (
        "You come from a humble background with no notable history or traits. "
        "Your life has been ordinary, and you possess no special advantages or disadvantages. "
        "You are a blank slate, ready to carve your own path in the world."
    )


@dataclass
class TideMarkedOutcast(BlankBackground):
    tags: list = field(default_factory=lambda: ["human", "outcast", "sea"])
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
class AshenChoirSurvivor(BlankBackground):
    tags: list = field(default_factory=lambda: ["human", "survivor", "fire"])
    additional_intelligence: int = 3
    intelligence_variance: int = 2
    additional_soul_power: int = 2
    additional_fire_resistance_modifier: float = 0.5
    additional_mental_resistance: int = 4
    additional_karma: int = -2
    lore_text: str = (
        "You are one of the few who escaped the burning of the Grand Choir. "
        "The flames that consumed your sanctuary tempered your mind and soul, "
        "leaving you with heightened mental fortitude and resistance to fire's touch, "
        "but also with scars that karma will not forget."
    )


@dataclass
class BrokenBannerHeir(BlankBackground):
    tags: list = field(default_factory=lambda: ["human", "noble", "warrior"])
    additional_charisma: int = 1
    additional_willpower: int = 4
    additional_combat_sense: int = 2
    additional_fame: int = 2
    additional_infamy: int = 4
    lore_text: str = (
        "Once you bore a proud standard of a now-fallen house. "
        "Your family's legacy weighs heavily upon you, fueling an indomitable will "
        "and tactical prowess on the battlefield. Though your name carries both renown and shame, "
        "you refuse to let the banner fall again."
    )


@dataclass
class ClockmakersCreation(BlankBackground):
    tags: list = field(
        default_factory=lambda: ["construct", "mechanical", "artificial"]
    )
    additional_intelligence: int = 4
    additional_dexterity: int = 2
    additional_physical_resistance: int = 3
    additional_mental_resistance: int = 1
    additional_pain_resistance_modifier: float = 0.7
    additional_charisma: int = -4
    lore_text: str = (
        "Forged in brass and bound by arcane gears, you are the masterwork of a forgotten artisan. "
        "Your mechanical precision and dulled nerves make you a formidable presence, "
        "though your inhuman nature makes social graces nearly impossible to grasp."
    )


@dataclass
class OrchardWitch(BlankBackground):
    tags: list = field(default_factory=lambda: ["human", "witch", "nature"])
    additional_intelligence: int = 2
    additional_perception: int = 3
    additional_soul_power: int = 2
    poison_resistance_variance: int = 2
    disease_resistance_variance: int = 2
    lore_text: str = (
        "You tend to ancient groves where fruit and fungi grow in strange patterns. "
        "Your keen senses and deep understanding of nature's darker gifts "
        "have granted you immunity to many toxins and ailments that would fell lesser folk."
    )


@dataclass
class OathBoundMercenary(BlankBackground):
    tags: list = field(default_factory=lambda: ["human", "mercenary", "warrior"])
    additional_strength: int = 2
    additional_combat_sense: int = 3
    additional_willpower: int = 2
    additional_charisma: int = -2
    additional_karma: int = -6
    lore_text: str = (
        "Bound by an unbreakable oath to serve, you have become a weapon honed through countless battles. "
        "Your martial prowess is undeniable, but the deeds you've committed in service "
        "have left your soul stained and your reputation grim."
    )


@dataclass
class ChildOfTwoSuns(BlankBackground):
    tags: list = field(default_factory=lambda: ["human", "blessed", "celestial"])
    additional_soul_power: int = 4
    additional_charisma: int = 2
    additional_fire_resistance_modifier: float = 0.4
    additional_luck: int = -2
    lore_text: str = (
        "Born during the rare alignment when both celestial orbs blazed overhead, "
        "you radiate an otherworldly presence that draws others to you. "
        "Your soul burns with intense power, though fate seems to conspire against you in subtle ways."
    )


@dataclass
class ForbiddenNameLibrarian(BlankBackground):
    tags: list = field(default_factory=lambda: ["human", "scholar", "forbidden"])
    additional_intelligence: int = 4
    additional_perception: int = 2
    additional_magic_illusion_resistance_modifier: float = 0.3
    additional_infamy: int = 7
    lore_text: str = (
        "You have read the names that should not be spoken and catalogued the texts that should not exist. "
        "Your vast knowledge has made you invaluable to those who seek dark wisdom, "
        "and your reputation as a trafficker of forbidden lore precedes you wherever you go."
    )


@dataclass
class BoneRiverNomad(BlankBackground):
    tags: list = field(default_factory=lambda: ["human", "nomad", "cursed"])
    additional_endurance: int = 3
    additional_willpower: int = 2
    additional_soul_power: int = 1
    additional_poison_resistance: int = 2
    lore_text: str = (
        "You were born to wander the ashen banks of the Bone River, where death flows eternal. "
        "The harsh journey has hardened your body and spirit, "
        "granting you resilience to the toxins that seep from the cursed waters."
    )


@dataclass
class CrownlessPretender(BlankBackground):
    tags: list = field(default_factory=lambda: ["human", "noble", "pretender"])
    additional_charisma: int = 3
    additional_willpower: int = 2
    additional_luck: int = -3
    additional_fame: int = 3
    additional_infamy: int = 3
    lore_text: str = (
        "You claim rightful ownership of a throne that no longer exists. "
        "Your magnetic personality and unwavering conviction have drawn followers and enemies alike, "
        "though fortune itself seems to mock your aspirations at every turn."
    )


@dataclass
class EmberMarkedMidwife(BlankBackground):
    tags: list = field(default_factory=lambda: ["human", "healer", "blessed"])
    additional_intelligence: int = 2
    additional_willpower: int = 3
    additional_fire_resistance_modifier: float = 0.6
    additional_virtue: int = 2
    lore_text: str = (
        "Marked by sacred embers during your first delivery, you have brought countless souls into the world. "
        "Your hands, blessed and burned, possess an uncanny warmth that soothes both mother and child. "
        "Your selfless service has earned you a reputation of virtue among your people."
    )


@dataclass
class SkyFallenKnight(BlankBackground):
    tags: list = field(default_factory=lambda: ["human", "knight", "fallen"])
    additional_strength: int = 2
    additional_endurance: int = 3
    additional_combat_sense: int = 2
    additional_speed: int = -1
    additional_lightning_resistance_modifier: float = 0.8
    lore_text: str = (
        "You plummeted from the floating citadels above, cast down for crimes real or imagined. "
        "The fall should have killed you, but instead you were struck by lightning and survived. "
        "Now your body carries the scars of heaven's wrath, slower but more resilient than before."
    )


@dataclass
class SpiritDebtCollector(BlankBackground):
    tags: list = field(default_factory=lambda: ["human", "cursed", "spirit"])
    additional_soul_power: int = 3
    additional_mental_resistance: int = 4
    additional_curse_resistance_modifier: float = 0.6
    additional_karma: int = -8
    lore_text: str = (
        "You enforce contracts that extend beyond the grave, claiming what is owed from the living and the dead. "
        "Your dealings with restless spirits have fortified your mind against supernatural influence, "
        "but the work you do for coin has damned your soul beyond redemption."
    )


@dataclass
class PaintedBarbarian(BlankBackground):
    tags: list = field(default_factory=lambda: ["human", "barbarian", "warrior"])
    additional_strength: int = 3
    additional_endurance: int = 3
    additional_charisma: int = -1
    additional_pain_resistance_modifier: float = 0.6
    lore_text: str = (
        "Adorned with the sacred warpaint of your tribe, you are a living weapon of ancient traditions. "
        "Years of brutal combat have made you nearly immune to pain and incredibly resilient, "
        "though civilized folk often mistake your warrior's demeanor for savagery."
    )


@dataclass
class AcademyDropout(BlankBackground):
    tags: list = field(default_factory=lambda: ["human", "scholar", "dropout"])
    additional_intelligence: int = 2
    additional_dexterity: int = 2
    additional_luck: int = -1
    additional_infamy: int = 4
    lore_text: str = (
        "You walked away from prestigious halls of learning, either by choice or necessity. "
        "Though you retained some knowledge and nimbleness of mind, "
        "your abrupt departure left a stain on your reputation and luck seems to elude you."
    )


@dataclass
class HollowEyedOracle(BlankBackground):
    tags: list = field(default_factory=lambda: ["human", "oracle", "seer"])
    additional_perception: int = 4
    additional_intelligence: int = 2
    additional_charisma: int = -3
    additional_mental_illusion_resistance_modifier: float = 0.3
    lore_text: str = (
        "You have gazed into the void between moments and seen truths not meant for mortal eyes. "
        "Your heightened perception pierces through deception with ease, "
        "but the visions have hollowed you out, leaving little room for warmth or charm."
    )


@dataclass
class RuneboundSmith(BlankBackground):
    tags: list = field(default_factory=lambda: ["human", "smith", "crafter"])
    additional_strength: int = 2
    additional_endurance: int = 2
    additional_intelligence: int = 2
    additional_luck: int = -5
    lore_text: str = (
        "You forge weapons and armor inscribed with ancient runes of power. "
        "The craft demands both physical strength and intellectual mastery, "
        "but the runic bindings you create have a terrible cost—fortune itself turns against you."
    )


@dataclass
class ForgottenGodChampion(BlankBackground):
    tags: list = field(default_factory=lambda: ["human", "champion", "divine"])
    additional_soul_power: int = 4
    additional_willpower: int = 2
    additional_luck: int = -3
    additional_karma: int = -4
    lore_text: str = (
        "You serve a deity whose name has been erased from history and memory. "
        "Your faith grants you immense spiritual power and unbreakable resolve, "
        "but championing a forgotten god comes at a price—both luck and karma abandon you."
    )


@dataclass
class SewerCrownPrince(BlankBackground):
    tags: list = field(default_factory=lambda: ["human", "underworld", "leader"])
    additional_charisma: int = 2
    additional_perception: int = 3
    additional_dexterity: int = 2
    poison_resistance_variance: int = 2
    lore_text: str = (
        "You rule the forgotten underbelly of the city, commanding loyalty from those who dwell in darkness. "
        "Your time navigating treacherous tunnels has sharpened your senses and reflexes, "
        "and exposure to countless toxins has built an unusual resistance in your blood."
    )


@dataclass
class LastWeatherBinder(BlankBackground):
    tags: list = field(default_factory=lambda: ["human", "mage", "elemental"])
    additional_soul_power: int = 3
    additional_intelligence: int = 2
    additional_lightning_resistance_modifier: float = 0.6
    additional_ice_resistance_modifier: float = 0.6
    additional_endurance: int = -1
    lore_text: str = (
        "You are the final practitioner of an ancient art that commands storms and seasons. "
        "Your intimate connection with elemental forces grants you protection from lightning and frost, "
        "though channeling such raw power takes a toll on your physical stamina."
    )


def get_classes_by_tag(tag):
    """Get background classes filtered by a specific tag.

    Args:
        tag: The tag to filter by (e.g., "human", "warrior", "mage")

    Returns:
        A dict mapping display names to background class instances that have the specified tag.
    """
    all_backgrounds = {
        "Blank Background": BlankBackground(),
        "Tide-Marked Outcast": TideMarkedOutcast(),
        "Ashen Choir Survivor": AshenChoirSurvivor(),
        "Broken Banner Heir": BrokenBannerHeir(),
        "Clockmaker's Creation": ClockmakersCreation(),
        "Orchard Witch": OrchardWitch(),
        "Oath-Bound Mercenary": OathBoundMercenary(),
        "Child of Two Suns": ChildOfTwoSuns(),
        "Forbidden Name Librarian": ForbiddenNameLibrarian(),
        "Bone River Nomad": BoneRiverNomad(),
        "Crownless Pretender": CrownlessPretender(),
        "Ember-Marked Midwife": EmberMarkedMidwife(),
        "Sky-Fallen Knight": SkyFallenKnight(),
        "Spirit Debt Collector": SpiritDebtCollector(),
        "Painted Barbarian": PaintedBarbarian(),
        "Academy Dropout": AcademyDropout(),
        "Hollow-Eyed Oracle": HollowEyedOracle(),
        "Runebound Smith": RuneboundSmith(),
        "Forgotten God Champion": ForgottenGodChampion(),
        "Sewer Crown Prince": SewerCrownPrince(),
        "Last Weather Binder": LastWeatherBinder(),
    }

    return {name: bg for name, bg in all_backgrounds.items() if tag in bg.tags}
