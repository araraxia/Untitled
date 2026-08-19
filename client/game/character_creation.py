"""Character creation flow (imgui-bundle).

Port of frontend/js/game/characterCreation.js (735 JS lines -- the
largest single file in this task) -- Step 14 (checkpoint 4 of 4) of
.github/prompts/wgpu-py-migration.prompt.md. Race/background/
personality/appearance/item/name/summary steps, driven by
races_list/backgrounds_list/new_player_initialized/character_created
SocketIO events, rebuilt as imgui widgets rather than DOM -- the
biggest DOM-to-imgui rewrite in Step 14, exactly as that step's intro
warns.

**Two honest findings from actually reading the whole 735-line source,
not just skimming signatures**: this file's own step machine
(`character_creation_state['current_step']` + a switch in
`renderCurrentStep`) never calls anything in
`characterFlow/flowController.js`/`moduleRegistry.js` (checkpoint 2) --
and a full-tree grep of frontend/js confirms `CharacterFlow.*` and
`setCharacterFlowCallbacks()` are defined but genuinely never invoked
anywhere in the current JS client. That machinery is real, working,
unused scaffolding in the JS source itself -- checkpoint 2 ported it
faithfully as such; it is *not* used here, matching the JS original's
actual (not aspirational) structure. Separately: `initCharacterCreation()`
itself has no caller anywhere in frontend/js either -- character
creation is orphaned/unreachable from the current client's actual UI
flow (nothing in playerSelect.js's "Create New Player" button leads
here). Same class of pre-existing gap as Step 7's missing
`lantern_atlas` texture -- ported as real, working, callable code;
not wired to an auto-trigger, since inventing that wiring would be new
behavior beyond a mechanical port.

**One deliberate adaptation, not a straight port**: JS registers
one-shot `socket.once('races_list', cb)`/`socket.once('backgrounds_list',
cb)` listeners inline, bypassing network.js's own
`characterFlowCallbacks` plumbing entirely (itself part of the unused-
scaffolding finding above). This file uses
`network.set_character_flow_callbacks()` instead -- the *only* clean
integration point available: `client/engine/network.py` (Step 11)
already registers exactly one persistent `@sio.on('races_list')` (and
one each for `backgrounds_list`/`error`/`character_created`) that
forwards through `_invoke_character_flow_callback()`; there is no
equivalent in `python-socketio`'s `Client` to stacking a second,
competing one-shot handler for the same event name the way the browser
socket.io client's `.once()` does from an arbitrary call site --
re-registering the same event name would simply replace network.py's
own handler. Using the callback slot network.py already exposes (built
in Step 11, never actually invoked by anything until now) is the
closest available equivalent, not a new design.

**Free simplification from immediate-mode rendering**: JS explicitly
re-invokes `renderCurrentStep(container)` from inside every click
handler, because each step is otherwise-static DOM that only updates
when poked. `render_character_creation_screen()` here is called once
per frame unconditionally (by whichever code owns the main render
loop, Step 15) and always reflects current state -- no explicit
re-render call is needed after a selection changes state. Same class
of "immediate mode gives this for free" adaptation as `ui.py`'s
popups closing on outside-click.

**`alert()` has no native equivalent** -- error conditions
(`init_character_creation()`'s "socket not available",
`backgrounds_list`'s fetch failure) are stored in `_error_message` and
rendered as text instead of a blocking browser dialog.

**Appearance option keys stay JS's original camelCase strings**
(`skinTone`, `hairColor`, `eyeColor`, `bodyType`), not converted to
snake_case, because they flow straight into `character_data['appearance']`
sent to the (unmodified, per this task's Constraints) backend via
`new_character` -- these are wire-format field names, not Python
identifiers, so CLAUDE.md's snake_case style guide doesn't apply to
them, the same way entity dict keys elsewhere in this port
(`entity['x']` etc.) keep their original JSON names.
"""

import re

from imgui_bundle import imgui

from client.engine import network
from client.game import player_select

character_creation_state: dict = {
    "current_step": "race",
    "selected_race": None,
    "selected_background": None,
    "personality": {},
    "appearance": {},
    "stats": {},
    "items": [],
    "character_name": "",
    "available_races": {},
    "available_backgrounds": {},
}

_active = False
_creating = False
_error_message: "str | None" = None

_PERSONALITY_TRAITS = [
    "ambitious",
    "curious",
    "stubborn",
    "loyal",
    "cautious",
    "brave",
    "cunning",
    "compassionate",
]

# Keys are wire-format field names, not Python identifiers -- see
# module docstring.
_APPEARANCE_OPTIONS = {
    "skinTone": ["pale", "fair", "olive", "tan", "brown", "dark"],
    "hairColor": ["black", "brown", "blonde", "red", "gray", "white"],
    "eyeColor": ["brown", "blue", "green", "hazel", "gray"],
    "bodyType": ["slim", "average", "athletic", "stocky", "heavy"],
}

_STARTING_ITEMS = ["basic_clothes", "water_flask", "travel_rations"]

_STAT_BONUS_FIELDS = [
    "additional_strength",
    "additional_dexterity",
    "additional_intelligence",
    "additional_willpower",
    "additional_charisma",
    "additional_perception",
    "additional_endurance",
    "additional_luck",
    "additional_speed",
    "additional_soul_power",
    "additional_combat_sense",
]


def _humanize_camel_case(value: str) -> str:
    """"skinTone" -> "Skin Tone". Direct port of JS's
    `s.charAt(0).toUpperCase() + s.slice(1).replace(/([A-Z])/g, ' $1')`.
    """
    spaced = re.sub(r"(?<!^)([A-Z])", r" \1", value)
    return spaced[:1].upper() + spaced[1:]


def init_character_creation() -> None:
    """Start character creation: register response handlers and
    request available races from the server.
    """
    global _active, _creating, _error_message
    print("[CharacterCreation] Starting character creation")
    character_creation_state["current_step"] = "race"
    _active = True
    _creating = False
    _error_message = None

    # Preserve whatever's already registered (e.g. client/main.py's
    # on_new_player_initialized/on_save_list, set once at startup) --
    # set_character_flow_callbacks() overwrites *every* key each call
    # (unregistered ones become None, matching the JS original's own
    # setCharacterFlowCallbacks() behavior exactly), so calling it here
    # with only this module's 4 keys would silently wipe out any other
    # module's registrations. Found while wiring Step 15's full app --
    # see that step's notes.
    preserved_callbacks = dict(network.character_flow_callbacks)
    preserved_callbacks.update(
        {
            "on_races_list": _handle_races_list,
            "on_backgrounds_list": _handle_backgrounds_list,
            "on_character_flow_error": _handle_character_flow_error,
            "on_character_created": _handle_character_created,
        }
    )
    network.set_character_flow_callbacks(preserved_callbacks)

    if network.sio is not None and network.sio.connected:
        network.sio.emit("request_races")
    else:
        print("[CharacterCreation] Socket not available")
        _error_message = "Critical Error in init_character_creation()."


def _handle_races_list(data: dict) -> None:
    print(f"[CharacterCreation] Received races: {data.get('races')}")
    character_creation_state["available_races"] = data.get("races", {})


def _handle_backgrounds_list(data: dict) -> None:
    print(f"[CharacterCreation] Received backgrounds: {data.get('backgrounds')}")
    character_creation_state["available_backgrounds"] = data.get("backgrounds", {})


def _handle_character_flow_error(data: dict) -> None:
    global _error_message
    print(f"[CharacterCreation] Error fetching races: {data}")
    _error_message = "Failed to load character creation data. Please refresh."


def _handle_character_created(data: dict) -> None:
    """Closes this screen and hands off to player_select.select_player()
    to actually load the newly created character into gameplay.

    Not a straight JS port: characterCreation.js never reacts to
    `character_created` at all (confirmed by a full-tree grep -- no
    `character_created`/`onCharacterCreated` handling anywhere in that
    file), so `finalizeCharacterCreation()`'s "Creating Character..."
    loading state never actually clears in the JS client -- a real,
    pre-existing gap in the JS original (see this module's docstring
    for the similar orphaned-flow finding), not something to leave
    unfixed here: without this, Step 14's own Step-14-declared verify
    condition ("the full player-select -> character-creation -> in-game
    flow completes end to end") would be false. player_select.py is a
    sibling client/game/ module (no engine/game boundary concern), and
    `select_player()` is exactly the mechanism that already loads a
    player's game state via the same `load_player`/`player_loaded`
    round trip an existing save uses -- the natural, already-built path
    for a just-created character too.
    """
    global _active, _creating
    print(f"[CharacterCreation] Character created successfully: {data}")
    _active = False
    _creating = False

    player_id = data.get("player_id")
    if player_id:
        player_select.select_player(player_id)


def check_step_complete(step: str) -> bool:
    """Check if the given step is complete (i.e. the wizard may
    proceed past it).
    """
    if step == "race":
        return character_creation_state["selected_race"] is not None
    if step == "background":
        return character_creation_state["selected_background"] is not None
    if step == "personality":
        return any(character_creation_state["personality"].values())
    if step == "appearance":
        return True
    if step == "items":
        return True
    if step == "name":
        return len(character_creation_state["character_name"]) > 0
    return False


def finalize_character_creation() -> None:
    """Send the assembled character data to the server."""
    global _creating
    print(f"[CharacterCreation] Finalizing character: {character_creation_state}")

    character_data = {
        "player_name": character_creation_state["character_name"],
        "race_id": character_creation_state["selected_race"],
        "background_name": character_creation_state["selected_background"],
        "personality": [
            trait for trait, v in character_creation_state["personality"].items() if v
        ],
        "appearance": character_creation_state["appearance"],
        "items": character_creation_state["items"],
    }

    if network.sio is not None and network.sio.connected:
        _creating = True
        network.sio.emit("new_character", character_data)
        print(f"[CharacterCreation] Sent character data to server: {character_data}")
    else:
        print("[CharacterCreation] Socket not connected")
        global _error_message
        _error_message = "Connection error. Please refresh and try again."


# ------------------------------------------------------------------
# imgui rendering -- call render_character_creation_screen() once per
# frame; it no-ops unless init_character_creation() has been called
# and hasn't finished/errored out.
# ------------------------------------------------------------------


def render_character_creation_screen() -> None:
    if not _active:
        return

    imgui.begin("Character Creation")

    if _error_message:
        imgui.text_colored(imgui.ImVec4(1.0, 0.3, 0.3, 1.0), _error_message)
        imgui.end()
        return

    if _creating:
        imgui.text("Creating Character...")
        imgui.text_disabled("Please wait while your character is being created.")
        imgui.end()
        return

    step = character_creation_state["current_step"]
    if step == "race":
        _render_race_selection()
    elif step == "background":
        _render_background_selection()
    elif step == "personality":
        _render_personality_selection()
    elif step == "appearance":
        _render_appearance_selection()
    elif step == "items":
        _render_item_selection()
    elif step == "name":
        _render_name_input()
    elif step == "summary":
        _render_summary()

    imgui.end()


def _render_race_selection() -> None:
    imgui.text("Choose Your Race")
    imgui.text_disabled("Select a race for your character")
    imgui.separator()

    for race_id, race in character_creation_state["available_races"].items():
        selected = character_creation_state["selected_race"] == race_id
        imgui.push_id(race_id)
        clicked, _ = imgui.selectable(race.get("name", race_id), selected)
        imgui.text_wrapped(race.get("description", ""))
        imgui.text_disabled(race.get("lore_text", ""))
        imgui.spacing()
        imgui.pop_id()

        if clicked:
            character_creation_state["selected_race"] = race_id
            if network.sio is not None and network.sio.connected:
                network.sio.emit("request_backgrounds", {"race_id": race_id})

    imgui.separator()
    can_proceed = (
        character_creation_state["selected_race"] is not None
        and len(character_creation_state["available_backgrounds"]) > 0
    )
    if can_proceed and imgui.button("Next: Background"):
        character_creation_state["current_step"] = "background"


def _render_background_selection() -> None:
    race = character_creation_state["available_races"].get(
        character_creation_state["selected_race"], {}
    )
    imgui.text("Choose Your Background")
    imgui.text_disabled(f"As a {race.get('name', '')}, select your background")
    imgui.separator()

    for bg_name, bg in character_creation_state["available_backgrounds"].items():
        selected = character_creation_state["selected_background"] == bg_name
        imgui.push_id(bg_name)
        clicked, _ = imgui.selectable(bg.get("display_name", bg_name), selected)
        imgui.text_wrapped(bg.get("lore_text", "A mysterious background."))

        stat_bonuses = []
        for field in _STAT_BONUS_FIELDS:
            value = bg.get(field)
            if value:
                stat_name = field.replace("additional_", "").replace("_", " ")
                sign = "+" if value > 0 else ""
                stat_bonuses.append(f"{stat_name} {sign}{value}")
        if stat_bonuses:
            imgui.text_disabled("Bonuses: " + ", ".join(stat_bonuses))
        imgui.spacing()
        imgui.pop_id()

        if clicked:
            character_creation_state["selected_background"] = bg_name

    _render_navigation_buttons("race", "personality")


def _render_personality_selection() -> None:
    imgui.text("Define Personality")
    imgui.text_disabled("Select up to 3 personality traits")
    imgui.separator()

    for trait in _PERSONALITY_TRAITS:
        is_selected = character_creation_state["personality"].get(trait) is True

        if is_selected:
            imgui.push_style_color(imgui.Col_.button.value, imgui.ImVec4(0.298, 0.686, 0.314, 1.0))
        clicked = imgui.button(trait.capitalize())
        if is_selected:
            imgui.pop_style_color()
        imgui.same_line()

        if clicked:
            selected_count = sum(1 for v in character_creation_state["personality"].values() if v)
            if is_selected:
                character_creation_state["personality"][trait] = False
            elif selected_count < 3:
                character_creation_state["personality"][trait] = True

    imgui.new_line()
    _render_navigation_buttons("background", "appearance")


def _render_appearance_selection() -> None:
    imgui.text("Customize Appearance")
    imgui.text_disabled("Choose your character's appearance")
    imgui.separator()

    for category, options in _APPEARANCE_OPTIONS.items():
        label = _humanize_camel_case(category)
        imgui.text(label)
        current = character_creation_state["appearance"].get(category, "")
        preview = current.capitalize() if current else f"Select {label}..."

        imgui.push_id(category)
        if imgui.begin_combo("##combo", preview):
            for option in options:
                clicked, _ = imgui.selectable(option.capitalize(), current == option)
                if clicked:
                    character_creation_state["appearance"][category] = option
            imgui.end_combo()
        imgui.pop_id()
        imgui.spacing()

    _render_navigation_buttons("personality", "items")


def _render_item_selection() -> None:
    imgui.text("Starting Equipment")
    imgui.text_disabled("These items will be in your inventory")
    imgui.separator()

    character_creation_state["items"] = list(_STARTING_ITEMS)
    for item in _STARTING_ITEMS:
        imgui.bullet_text(item.replace("_", " ").title())

    _render_navigation_buttons("appearance", "name")


def _render_name_input() -> None:
    imgui.text("Name Your Character")
    imgui.text_disabled("Choose a name for your character")
    imgui.separator()

    imgui.text("Character Name:")
    changed, new_value = imgui.input_text(
        "##character_name", character_creation_state["character_name"]
    )
    if len(new_value) > 30:
        new_value = new_value[:30]
    if changed:
        character_creation_state["character_name"] = new_value.strip()

    enter_pressed = imgui.is_item_focused() and imgui.is_key_pressed(imgui.Key.enter)

    imgui.text_disabled(
        "Note: This is your character's name, not your player name. Maximum 30 characters."
    )

    if enter_pressed and len(character_creation_state["character_name"]) > 0:
        character_creation_state["current_step"] = "summary"
        return

    _render_navigation_buttons("items", "summary")


def _render_summary() -> None:
    race = character_creation_state["available_races"].get(
        character_creation_state["selected_race"], {}
    )
    background = character_creation_state["available_backgrounds"].get(
        character_creation_state["selected_background"], {}
    )

    imgui.text("Character Summary")
    imgui.text_disabled("Review your character before creation")
    imgui.separator()

    imgui.text(f"Name: {character_creation_state['character_name']}")
    imgui.text(f"Race: {race.get('name', '')}")
    imgui.text(
        f"Background: {background.get('display_name', character_creation_state['selected_background'])}"
    )

    selected_traits = [t for t, v in character_creation_state["personality"].items() if v]
    imgui.text("Personality: " + (", ".join(selected_traits) or "None selected"))

    imgui.text("Appearance:")
    if character_creation_state["appearance"]:
        for k, v in character_creation_state["appearance"].items():
            imgui.bullet_text(f"{_humanize_camel_case(k)}: {v}")
    else:
        imgui.text_disabled("Default appearance")

    imgui.text("Stats:")
    for k, v in character_creation_state["stats"].items():
        display_name = " ".join(w.capitalize() for w in k.replace("_", " ").split(" "))
        imgui.bullet_text(f"{display_name}: {v}")

    imgui.separator()
    if imgui.button("Back"):
        character_creation_state["current_step"] = "name"
    imgui.same_line()
    if imgui.button("Create Character"):
        finalize_character_creation()


def _render_navigation_buttons(prev_step: str, next_step: str) -> None:
    can_proceed = check_step_complete(character_creation_state["current_step"])

    imgui.separator()
    if imgui.button("Back"):
        character_creation_state["current_step"] = prev_step

    imgui.same_line()
    imgui.begin_disabled(not can_proceed)
    if imgui.button(f"Next: {next_step.capitalize()}") and can_proceed:
        character_creation_state["current_step"] = next_step
    imgui.end_disabled()
