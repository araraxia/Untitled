"""Game tick. Processes queued actions, updates simulation, and
broadcasts state deltas over SocketIO.
"""

import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from backend.engine.config import TICK_DURATION, load_engine_config
from backend.engine.events import EventBus
from backend.engine.game_loop import GameLoop
from backend.engine.ecs.world import World
from backend.engine.ecs.scheduler import SystemScheduler
from backend.game.area import Area
from backend.game.systems.systems import (
    AISystem,
    CombatSystem,
    MovementSystem,
    PathfindingSystem,
    PhysicsSystem,
)


class GameTick(GameLoop):
    """Extends GameLoop with game-specific tick processing.

    Handles player action queues, area simulation updates, and
    client state broadcasting via SocketIO.

    A :class:`SystemScheduler` drives ECS systems each tick in
    dependency order.  Systems operate on the shared :attr:`ecs_world`.
    """

    def __init__(self, socketio):
        super().__init__(socketio)
        self.current_world = None
        self.current_area: Optional[Area] = None
        self.player_instance = None
        self.player_action_queue: List[Dict[str, Any]] = []
        self.party_command_queue: List[Dict[str, Any]] = []

        self.ecs_world: World = World()
        self.event_bus: EventBus = EventBus()
        movement = MovementSystem(self.event_bus)
        physics = PhysicsSystem(event_bus=self.event_bus)
        pathfinding = PathfindingSystem(event_bus=self.event_bus)
        ai = AISystem(event_bus=self.event_bus)
        combat = CombatSystem(event_bus=self.event_bus)
        self._scheduler: SystemScheduler = SystemScheduler()
        self._scheduler.register(physics)
        self._scheduler.register(pathfinding)
        self._scheduler.register(movement)
        self._scheduler.register(ai)
        self._scheduler.register(combat)
        self._scheduler.build()

        # Update the spatial grid whenever an entity moves.
        self.event_bus.subscribe("entity_moved", self._on_entity_moved)

        # Auto-save executor (single worker keeps saves serialised).
        _engine_cfg = load_engine_config()
        self._autosave_interval: int = _engine_cfg.autosave_interval_ticks
        self._autosave_executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=1)

    def _on_entity_moved(self, payload: Dict[str, Any]) -> None:
        """Update the spatial grid when an entity moves."""
        if not self.current_area:
            return
        entity_id = payload.get("id")
        if entity_id is None:
            return
        entity = self.current_area.entities.get(entity_id)
        if entity is not None:
            self.current_area.spatial_grid.update(entity)

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

        self._scheduler.run(self.ecs_world, TICK_DURATION)
        self.current_area.update(TICK_DURATION)
        state_delta = self.current_area.get_state_delta()
        if state_delta:
            self.socketio.emit(
                "state_update",
                {"tick": self.tick_count, "delta": state_delta},
            )

    def _run_autosave(self) -> None:
        """Execute a save in the background executor thread."""
        from backend.save_manager import SaveManager

        if not self.player_instance:
            return
        try:
            sm = SaveManager(
                self.socketio,
                player_id=self.player_instance.player_id,
            )
            sm.save_game(self.player_instance, self)
            self.socketio.emit(
                "autosave_complete",
                {"tick": self.tick_count, "status": "ok"},
            )
        except Exception:  # pragma: no cover
            self.socketio.emit(
                "autosave_complete",
                {"tick": self.tick_count, "status": "error"},
            )

    def _after_tick(self) -> None:
        """Submit an auto-save if the interval has elapsed."""
        interval = self._autosave_interval
        if interval > 0 and self.tick_count % interval == 0:
            self._autosave_executor.submit(self._run_autosave)

    def start(self) -> object:
        """Start the game loop, resetting action queues first."""
        self.player_action_queue = []
        self.party_command_queue = []
        return super().start()
