"""[DEV ONLY] Standalone verification for backend/game/area.py and
backend/game/tick.py -- Milestone 1's Area/GameTick, proving movement,
the XZ-axis mapping, dirty-delta tracking, and the queue.Queue
cross-thread handoff all actually work. No GPU/window/network
involved -- mirrors run_gametick_test.py's own no-GPU pattern.

Usage:
    python run_area_gametick_test.py
"""

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.engine.config import TICK_DURATION, TICK_RATE
from backend.game.area import create_milestone1_area
from backend.game.tick import GameTick
from backend.independant_logger import Logger

logger = Logger(
    log_name="run_area_gametick_test",
    log_file="area_gametick_test.log",
    log_level=20,  # INFO
).get_logger()


def test_x_movement() -> None:
    """direction.x=1 is input.py's "right" action -- confirmed via a
    real hands-on run that this must land on world -X (right = cross
    (forward, up) = (-1, 0, 0)), not +X as originally (incorrectly)
    assumed. Signs here are corrected to match, not just described.
    """
    area = create_milestone1_area()
    player = area.entities[area.player_entity_id]

    action = {"type": "move", "direction": {"x": 1, "y": 0}, "facing": "right"}
    area.process_player_action(action)
    for _ in range(10):
        area.update(TICK_DURATION)

    assert player.x < 0, f"expected x < 0 (screen-right = -X), got {player.x}"
    assert player.z == 0.0, f"expected z unchanged, got {player.z}"
    assert player.state == "moving"
    logger.info(
        f"x-movement: x={player.x} z={player.z} state={player.state!r}"
    )

    delta = area.get_state_delta()
    assert player.entity_id in delta.get("entities", {}), "player missing"
    assert area.dirty_entities == set(), "dirty set not cleared"
    logger.info("dirty-delta tracking: player in delta, dirty set cleared")


def test_z_movement() -> None:
    """direction.y=1 is input.py's "down"/backward action -- must land
    on world -Z (backward, toward the camera), not +Z. Proves the XZ
    mapping is actually implemented with the corrected sign, not just
    described.
    """
    area = create_milestone1_area()
    player = area.entities[area.player_entity_id]

    area.process_player_action({"type": "move", "direction": {"x": 0, "y": 1}})
    for _ in range(10):
        area.update(TICK_DURATION)

    assert player.z < 0, f"expected z < 0 (backward), got {player.z}"
    assert player.x == 0.0, f"expected x unchanged, got {player.x}"
    assert player.y == 0.0, f"expected y unchanged, got {player.y}"
    logger.info(
        f"z-movement: x={player.x} y={player.y} z={player.z} (XZ confirmed)"
    )


def test_facing_preserved_on_stop() -> None:
    area = create_milestone1_area()
    player = area.entities[area.player_entity_id]

    move = {"type": "move", "direction": {"x": 1, "y": 0}, "facing": "right"}
    area.process_player_action(move)
    area.update(TICK_DURATION)
    area.process_player_action({"type": "move", "direction": {"x": 0, "y": 0}})
    area.update(TICK_DURATION)

    assert player.state == "idle"
    assert player.facing == "right", "facing clobbered on the facing-less stop"
    logger.info(f"stop: state={player.state!r} facing={player.facing!r}")


def test_real_tick_thread() -> None:
    """Same 'real 20 TPS pacing' sanity check run_gametick_test.py
    already does, plus exercising the queue.Queue cross-thread handoff:
    queue actions from this (main) thread while GameTick's own daemon
    thread ticks concurrently.
    """
    tick = GameTick(socketio=None)
    tick.current_area = create_milestone1_area()
    player = tick.current_area.entities[tick.current_area.player_entity_id]

    logger.info(f"Starting tick loop ({TICK_DURATION}s = {TICK_RATE} TPS)...")
    tick.start()

    move = {"type": "move", "direction": {"x": 1, "y": 0}, "facing": "right"}
    tick.queue_player_action(move)
    time.sleep(0.3)
    tick.queue_player_action({"type": "move", "direction": {"x": 0, "y": 0}})
    time.sleep(0.2)
    tick.stop()
    time.sleep(0.1)

    assert tick.tick_count > 0, "no ticks ran"
    assert player.x < 0, f"expected x < 0 after real ticking, got {player.x}"
    assert player.state == "idle"
    logger.info(
        f"real-thread test: tick_count={tick.tick_count} final_x={player.x} "
        f"state={player.state!r} (as expected)"
    )


def main() -> None:
    logger.info("=" * 50)
    logger.info("[DEV ONLY] backend/game/area.py + tick.py smoke test")
    logger.info("=" * 50)

    test_x_movement()
    test_z_movement()
    test_facing_preserved_on_stop()
    test_real_tick_thread()

    logger.info(
        "PASS: X/Z movement mapping, dirty-delta tracking, facing "
        "preservation, and the real-thread queue.Queue handoff all "
        "verified."
    )


if __name__ == "__main__":
    main()
