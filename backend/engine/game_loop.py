"""Engine game loop. Manages tick scheduling and lifecycle."""

import time
import threading
from typing import Optional

from backend.engine.config import TICK_DURATION
from backend.independant_logger import Logger

logger = Logger(
    log_name="backend.engine.game_loop",
    log_file="game_loop.log",
    log_level=20,  # INFO
).get_logger()


class GameLoop:
    """Manages the main simulation loop timing and lifecycle.

    Subclass and override ``_do_tick`` to add game-specific work.
    """

    def __init__(self, socketio):
        self.socketio = socketio
        self.running = False
        self.paused = False
        self.tick_count = 0
        self.current_thread: Optional[threading.Thread] = None

    def _do_tick(self, tick_start: float) -> None:
        """Execute one simulation tick. Override in subclasses."""

    def _after_tick(self) -> None:
        """Called after tick_count is incremented. Override in subclasses."""

    def run(self) -> None:
        """Main loop. Runs until stop() is called."""
        self.running = True
        logger.info("Game loop started")

        while self.running:
            while self.paused:
                time.sleep(0.1)

            tick_start = time.time()
            self._do_tick(tick_start)
            self.tick_count += 1
            self._after_tick()

            elapsed = time.time() - tick_start
            sleep_time = max(0, TICK_DURATION - elapsed)
            time.sleep(sleep_time)

    def start(self) -> threading.Thread:
        """Start the loop in a daemon background thread."""
        if self.running:
            logger.warning("Game loop is already running")
            if self.current_thread and self.current_thread.is_alive():
                return self.current_thread

        self.running = True
        self.tick_count = 0
        game_thread = threading.Thread(target=self.run, daemon=True)
        game_thread.start()
        self.current_thread = game_thread
        return self.current_thread

    def stop(self) -> None:
        """Stop the loop."""
        self.running = False

    def pause(self) -> None:
        """Pause the loop."""
        self.paused = True

    def resume(self) -> None:
        """Resume the loop after pausing."""
        self.paused = False
