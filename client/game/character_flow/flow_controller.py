"""Character-flow controller.

Port of frontend/js/game/characterFlow/flowController.js:
init_character_flow_controller(), activate_character_flow_module(),
dispatch_character_flow_event(), get_active_character_flow_module_id()
-- Step 14 (checkpoint 2 of 4). Synchronous throughout -- see
module_types.py's docstring for why this port doesn't carry over JS's
async-capable module lifecycle hooks. Duck-types optional module
methods via `callable(getattr(module, 'name', None))`, mirroring the
JS original's `typeof x.method === "function"` guards exactly.
"""

from client.game.character_flow.module_registry import get_character_flow_module
from client.game.character_flow.module_types import CharacterFlowModule

_controller_config: dict = {"default_module_id": None}
_controller_context: dict = {}
_active_module_id: "str | None" = None
_active_module: "CharacterFlowModule | None" = None


def init_character_flow_controller(config: "dict | None", context: "dict | None") -> None:
    """Initialize the character flow controller."""
    global _controller_config, _controller_context

    default_module_id = None
    if config and isinstance(config.get("default_module_id"), str):
        default_module_id = config["default_module_id"]
    _controller_config = {"default_module_id": default_module_id}
    _controller_context = context or {}

    if _controller_config["default_module_id"]:
        activate_character_flow_module(_controller_config["default_module_id"])


def activate_character_flow_module(module_id: str) -> None:
    """Activate a character flow module by id."""
    global _active_module_id, _active_module

    if not isinstance(module_id, str) or module_id.strip() == "":
        raise ValueError(
            "[CharacterFlow] activate_character_flow_module requires a module id."
        )

    next_module = get_character_flow_module(module_id)
    if next_module is None:
        raise ValueError(f'[CharacterFlow] Unknown module id "{module_id}".')

    if _active_module_id == module_id:
        return

    if _active_module is not None and callable(getattr(_active_module, "unmount", None)):
        _active_module.unmount(_controller_context)

    # Ported as-is: given the early return above already guarantees
    # `_active_module_id != module_id`, and a registered module's `.id`
    # always equals its registry key, `_active_module_id != next_module.id`
    # is always true by the time execution reaches here -- redundant in
    # the JS original too, kept for fidelity rather than "corrected"
    # during a mechanical port.
    if (
        _active_module is not None
        and callable(getattr(_active_module, "destroy", None))
        and isinstance(getattr(next_module, "id", None), str)
        and _active_module_id != next_module.id
    ):
        _active_module.destroy(_controller_context)

    _active_module = next_module
    _active_module_id = module_id

    if callable(getattr(_active_module, "init", None)):
        _active_module.init(_controller_context)

    if callable(getattr(_active_module, "mount", None)):
        _active_module.mount(_controller_context)


def dispatch_character_flow_event(event_name: str, payload: "dict | None") -> bool:
    """Dispatch an event to the active character flow module."""
    if _active_module is None or not callable(
        getattr(_active_module, "handle_event", None)
    ):
        return False

    handled = _active_module.handle_event(event_name, payload or {}, _controller_context)
    return handled is True


def get_active_character_flow_module_id() -> "str | None":
    """Get the currently active character flow module id."""
    return _active_module_id
