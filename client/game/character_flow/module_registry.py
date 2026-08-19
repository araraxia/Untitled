"""Character-flow module registry.

Port of frontend/js/game/characterFlow/moduleRegistry.js:
register_character_flow_module(), get_character_flow_module(),
list_character_flow_modules() -- Step 14 (checkpoint 2 of 4). JS's
`window.CharacterFlow` namespace object has no Python equivalent
needed; this module's own top-level functions, imported directly,
serve the same purpose.

**One check dropped, not ported**: JS's `registerCharacterFlowModule`
first checks `typeof module !== 'object'`, throwing if not. There is
no meaningful Python equivalent -- everything passed here is an
object -- so only the genuinely meaningful checks (non-empty string
`id`, no duplicate registration) are ported.
"""

from client.game.character_flow.module_types import CharacterFlowModule

_modules: dict = {}


def register_character_flow_module(module: CharacterFlowModule) -> None:
    """Register a character flow module."""
    module_id = getattr(module, "id", None)
    if not isinstance(module_id, str) or module_id.strip() == "":
        raise ValueError("[CharacterFlow] Module must have a non-empty string id.")

    if module_id in _modules:
        raise ValueError(
            f'[CharacterFlow] Module with id "{module_id}" is already registered.'
        )

    _modules[module_id] = module


def get_character_flow_module(module_id: str) -> "CharacterFlowModule | None":
    """Get a character flow module by id."""
    return _modules.get(module_id)


def list_character_flow_modules() -> list:
    """List all registered character flow modules."""
    return list(_modules.values())
