"""Example: a generic entity + timed action-trigger pattern, and a
minimal concrete GameLoop demonstrating a real 20 TPS tick loop.

`backend/engine/game_loop.py`'s `GameLoop` is an abstract base with no
concrete engine-layer subclass otherwise (see `CLAUDE.md`'s Running
section) -- every real tick loop lives on a game branch (`legacy`'s
`GameTick`, `backend/game/tick.py`). This file is example/reference
content only, not a game: it exists to (a) prove `GameLoop`'s own
20 TPS pacing (`TICK_DURATION`, `backend/engine/config.py`) actually
works once subclassed, and (b) demonstrate the "an action sets a
state, a duration later it auto-reverts" pattern
`.github/prompts/3d-coordinate-mapping.prompt.md`'s Step 12 describes
against game-layer files that don't exist on this branch
(`backend/game/entities/player.py`, `systems/actions.py`, `tick.py`,
all `legacy`-branch-only) -- generalised here so the pattern itself is
verifiable without depending on any real game's action set.

Uses `Entity.set_data`/`get_data` (this session's tag data bag,
`backend/engine/ecs/entity.py`) for the action's start timestamp
rather than adding a bespoke field to `Entity` -- exactly the kind of
ad hoc, optional, entity-specific data that API exists for.

See `run_gametick_test.py` for a standalone verification script.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

from backend.engine.ecs.entity import Entity
from backend.engine.game_loop import GameLoop

# Milliseconds. A single example action -- "activate" is a placeholder,
# the same way a "Hello World" string is a placeholder, not real game
# content. A real game defines its own action set (see
# 3d-coordinate-mapping.prompt.md Step 12's ACTION_DURATIONS, on
# whichever game branch implements it).
ACTION_DURATIONS: Dict[str, float] = {"activate": 400.0}

DEFAULT_IDLE_STATE = "idle"

_STATE_STARTED_AT_KEY = "state_started_at"


def trigger_action(entity: Entity, action_type: str) -> None:
    """Set entity.state to action_type and record when it started via
    the tag data bag -- mirrors Step 12's
    `entity.state = "attacking"/"using_item"/"interacting"` pattern,
    one level more generic (any action_type, not a hardcoded set).
    """
    entity.state = action_type
    entity.set_data(_STATE_STARTED_AT_KEY, time.monotonic())
    entity.is_dirty = True


def revert_expired_actions(
    entities: Dict[str, Entity],
    action_durations: Optional[Dict[str, float]] = None,
    idle_state: str = DEFAULT_IDLE_STATE,
) -> List[str]:
    """Revert any entity whose current state is a timed action and
    whose duration has elapsed back to idle_state.

    Args:
        entities: entity_id -> Entity, checked every call (cheap for
            the entity counts this example targets; a real game with
            many entities would want this driven by the same
            dirty/active-entity bookkeeping its tick loop already has,
            not a new concern this example needs to solve).
        action_durations: Defaults to this module's ACTION_DURATIONS.
        idle_state: The state to revert to. Step 12's real version
            picks "idle" vs "moving" based on current velocity; this
            example only has one idle state, since it has no movement
            system of its own.

    Returns:
        Ids of entities reverted this call, for callers that want to
        log/broadcast the change (matching Step 12's "reuses the
        existing state_update delta broadcast" note).
    """
    durations = ACTION_DURATIONS if action_durations is None else action_durations
    reverted = []
    now = time.monotonic()
    for entity_id, entity in entities.items():
        duration_ms = durations.get(entity.state)
        if duration_ms is None:
            continue
        started_at = entity.get_data(_STATE_STARTED_AT_KEY)
        if started_at is None:
            continue
        elapsed_ms = (now - started_at) * 1000.0
        if elapsed_ms >= duration_ms:
            entity.state = idle_state
            entity.is_dirty = True
            reverted.append(entity_id)
    return reverted


class ExampleGameLoop(GameLoop):
    """Minimal concrete GameLoop: drains one queued action per tick,
    then reverts any expired timed action. Real 20 TPS pacing comes
    entirely from the inherited run()/TICK_DURATION (GameLoop.run(),
    backend/engine/config.py) -- nothing here reinvents tick timing.

    Not tied to SocketIO/a real client -- socketio may be None, since
    this example never calls self.socketio.emit(...). A real game's
    concrete GameLoop (legacy's GameTick) broadcasts state_update
    deltas from _do_tick(); this one only demonstrates the action/
    revert mechanism itself.
    """

    def __init__(self, socketio=None):
        super().__init__(socketio)
        self.entities: Dict[str, Entity] = {}
        self._action_queue: List[Tuple[str, str]] = []
        self.last_reverted: List[str] = []

    def add_entity(self, entity: Entity) -> None:
        self.entities[entity.entity_id] = entity

    def queue_action(self, entity_id: str, action_type: str) -> None:
        """Queue an action to be applied on the next tick -- mirrors
        GameTick.queue_player_action's queue-then-drain shape."""
        self._action_queue.append((entity_id, action_type))

    def _do_tick(self, tick_start: float) -> None:
        while self._action_queue:
            entity_id, action_type = self._action_queue.pop(0)
            entity = self.entities.get(entity_id)
            if entity is not None:
                trigger_action(entity, action_type)

        self.last_reverted = revert_expired_actions(self.entities)
