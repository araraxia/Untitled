"""Main simulation loop."""

import time
from typing import List, Dict, Any
from backend.config import TICK_RATE, TICK_DURATION
from backend.simulation.area import Area
from backend.independant_logger import Logger
import threading

# Initialize logger
logger = Logger(
    log_name="backend.game_loop",
    log_file="game_loop.log",
    log_level=20,  # INFO
).get_logger()

class GameLoop:
    """Manages the main game simulation loop."""

    def __init__(self, socketio):
        self.socketio = socketio
        self.current_world = None
        self.current_area = None
        self.player_instance = None
        self.running = False
        self.paused = False
        self.tick_count = 0
        self.player_action_queue: List[Dict[str, Any]] = []
        self.party_command_queue: List[Dict[str, Any]] = []

    def queue_player_action(self, action: Dict[str, Any]):
        """Queue a player action to be processed."""
        if not self.current_area: return
        
        while self.running and not self.paused:
            self.player_action_queue.append(action)

    def queue_party_command(self, command: Dict[str, Any]):
        """Queue a party command to be processed."""
        if not self.current_area: return
        
        while self.running and not self.paused:
            self.party_command_queue.append(command)

    def process_player_actions(self):
        """Process all queued player actions."""
        if not self.current_area: return

        while self.player_action_queue and self.running and not self.paused:
            if self.tick_start + TICK_DURATION < time.time():
                break
            action = self.player_action_queue.pop(0)
            self.current_area.process_player_action(action)

    def process_party_commands(self):
        """Process all queued party commands."""
        if not self.current_area: return

        while self.party_command_queue and self.running and not self.paused:
            if self.tick_start + TICK_DURATION < time.time():
                break
            command = self.party_command_queue.pop(0)
            self.current_area.process_party_command(command)

    def run(self):
        """Main game loop."""
        self.running = True
        logger.info("Game loop started")

        while self.running:
            # Wait while paused
            while self.paused:
                time.sleep(0.1)

            tick_start = time.time()
            self.tick_start = tick_start

            # Process input
            self.process_player_actions()
            self.process_party_commands()

            # Update world simulation
            self.current_area.update(TICK_DURATION)

            # Broadcast state to clients
            state_delta = self.current_area.get_state_delta()
            if state_delta:
                self.socketio.emit(
                    "state_update", {"tick": self.tick_count, "delta": state_delta}
                )

            self.tick_count += 1

            # Sleep until next tick
            tick_end = time.time()
            elapsed = tick_end - tick_start
            sleep_time = max(0, TICK_DURATION - elapsed)
            time.sleep(sleep_time)
            
    def start(self):
        """Start the game loop."""
        if self.running:
            logger.warning("Game loop is already running")
            if self.current_thread and self.current_thread.is_alive():
                return self.current_thread
        
        self.running = True
        self.tick_count = 0
        self.player_action_queue: List[Dict[str, Any]] = []
        self.party_command_queue: List[Dict[str, Any]] = []
        game_thread = threading.Thread(target=self.run, daemon=True)
        game_thread.start()
        self.current_thread = game_thread
        return self.current_thread
            

    def stop(self):
        """Stop the game loop."""
        self.running = False

    def pause(self):
        """Pause the game loop."""
        self.paused = True
        
    def resume(self):
        """Resume the game loop."""
        self.paused = False
