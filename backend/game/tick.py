"""GameTick -- Milestone 1's concrete `GameLoop` subclass.

Drains queued `player_action` payloads, advances the current `Area`
one tick, then broadcasts the resulting dirty-entity delta. Deliberately
thin compared to `legacy`'s own `GameTick` (which additionally drove an
abandoned `ecs_world`/`SystemScheduler` stack and save/party-command
handling) -- none of that exists in this milestone's scope.
"""

from __future__ import annotations

import queue
from typing import Any, Dict, Optional

from backend.engine.config import TICK_DURATION
from backend.engine.game_loop import GameLoop
from backend.game.area import Area


class GameTick(GameLoop):
    """One area, one action queue, one dirty-delta broadcast per tick."""

    def __init__(self, socketio) -> None:
        super().__init__(socketio)
        self.current_area: Optional[Area] = None
        # queue.Queue, not a plain list: player_action arrives on
        # whichever thread Flask-SocketIO dispatches the event handler
        # on (this app runs async_mode="threading", so that's a real,
        # separate OS thread from this loop's own daemon thread, not
        # just cooperative scheduling) -- put_nowait()/get_nowait() is
        # the correct, cheap, actually-thread-safe handoff for that
        # producer/consumer split.
        self._action_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()

    def queue_player_action(self, action: Dict[str, Any]) -> None:
        self._action_queue.put_nowait(action)

    def _do_tick(self, tick_start: float) -> None:
        if self.current_area is None:
            return

        while True:
            try:
                action = self._action_queue.get_nowait()
            except queue.Empty:
                break
            self.current_area.process_player_action(action)

        self.current_area.update(TICK_DURATION)

        delta = self.current_area.get_state_delta()
        if delta and self.socketio is not None:
            payload = {"tick": self.tick_count, "delta": delta}
            self.socketio.emit("state_update", payload)
