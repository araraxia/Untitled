"""Game tick. Processes queued actions, updates simulation, and
broadcasts state deltas over SocketIO.
"""

import time
from typing import Any, Dict, List, Optional

from backend.engine.config import TICK_DURATION
from backend.engine.game_loop import GameLoop
from backend.game.area import Area


class GameTick(GameLoop):
    """Extends GameLoop with game-specific tick processing.

    Handles player action queues, area simulation updates, and
    client state broadcasting via SocketIO.
    """

    def __init__(self, socketio):
        super().__init__(socketio)
        self.current_world = None
        self.current_area: Optional[Area] = None
        self.player_instance = None
        self.player_action_queue: List[Dict[str, Any]] = []
        self.party_command_queue: List[Dict[str, Any]] = []

    def queue_player_action(self, action: Dict[str, Any]) -> None:
        """Queue a player action to be processed on the next tick."""
        if not self.current_area:
            return
        self.player_action_queue.append(action)

    def queue_party_command(self, command: Dict[str, Any]) -> None:
        """Queue a party command to be processed on the next tick."""
        if not self.current_area:
            return
        self.party_command_queue.append(command)

    def _process_player_actions(self, tick_start: float) -> None:
        """Drain the player action queue within the tick budget."""
        if not self.current_area:
            return
        while self.player_action_queue and self.running and not self.paused:
            if tick_start + TICK_DURATION < time.time():
                break
            action = self.player_action_queue.pop(0)
            self.current_area.process_player_action(action)

    def _process_party_commands(self, tick_start: float) -> None:
        """Drain the party command queue within the tick budget."""
        if not self.current_area:
            return
        while self.party_command_queue and self.running and not self.paused:
            if tick_start + TICK_DURATION < time.time():
                break
            command = self.party_command_queue.pop(0)
            self.current_area.process_party_command(command)

    def _do_tick(self, tick_start: float) -> None:
        """Process one game tick."""
        self._process_player_actions(tick_start)
        self._process_party_commands(tick_start)

        if not self.current_area:
            return

        self.current_area.update(TICK_DURATION)
        state_delta = self.current_area.get_state_delta()
        if state_delta:
            self.socketio.emit(
                "state_update",
                {"tick": self.tick_count, "delta": state_delta},
            )

    def start(self) -> object:
        """Start the game loop, resetting action queues first."""
        self.player_action_queue = []
        self.party_command_queue = []
        return super().start()
