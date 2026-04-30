"""Engine configuration — defaults and injectable schema."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import json

# ---------------------------------------------------------------------------
# Module-level constants — backward-compatible defaults
# ---------------------------------------------------------------------------

TICK_RATE: int = 20
TICK_DURATION: float = 1.0 / TICK_RATE
MAX_ENTITIES: int = 1000

HOST: str = "0.0.0.0"
PORT: int = 5000
DEBUG: bool = True
LOG_DIR: str = "logs"
AUTOSAVE_INTERVAL_TICKS: int = 300
SAVE_DIR: str = "saves"

# ---------------------------------------------------------------------------
# Injectable config schema
# ---------------------------------------------------------------------------


@dataclass
class EngineConfig:
    """Injectable engine configuration.

    Attributes:
        tick_rate: Simulation ticks per second.
        max_entities: Hard cap on tracked entities.
        world_width: Default world width in world units.
        world_height: Default world height in world units.
        grid_cell_size: Spatial grid cell size in world units.
        host: Server bind address.
        port: Server port.
        debug: Enable Flask debug mode.
        log_dir: Directory for log files.
    """

    tick_rate: int = TICK_RATE
    max_entities: int = MAX_ENTITIES
    world_width: int = 1000
    world_height: int = 1000
    grid_cell_size: int = 32
    host: str = HOST
    port: int = PORT
    debug: bool = DEBUG
    log_dir: str = LOG_DIR
    autosave_interval_ticks: int = AUTOSAVE_INTERVAL_TICKS
    save_dir: str = SAVE_DIR


_SCHEMA: Dict[str, type] = {
    "tick_rate": int,
    "max_entities": int,
    "world_width": int,
    "world_height": int,
    "grid_cell_size": int,
    "host": str,
    "port": int,
    "debug": bool,
    "log_dir": str,
    "autosave_interval_ticks": int,
    "save_dir": str,
}

_DEFAULT_PATH: Path = (
    Path(__file__).resolve().parent.parent.parent / "config" / "engine.json"
)


def _validate(data: Dict[str, Any], schema: Dict[str, type]) -> None:
    """Raise TypeError on schema mismatch."""
    for key, expected in schema.items():
        if key in data and not isinstance(data[key], expected):
            raise TypeError(
                f"EngineConfig '{key}': expected"
                f" {expected.__name__},"
                f" got {type(data[key]).__name__}"
            )


def load_engine_config(
    path: Optional[str] = None,
) -> EngineConfig:
    """Load EngineConfig from a JSON file.

    Falls back to all defaults when the file does not exist.

    Args:
        path: Optional path to a JSON config file.
              Defaults to ``config/engine.json`` at project root.

    Returns:
        Populated EngineConfig instance.
    """
    config_path = Path(path) if path else _DEFAULT_PATH
    if not config_path.exists():
        return EngineConfig()
    with config_path.open("r", encoding="utf-8") as fh:
        data: Dict[str, Any] = json.load(fh)
    _validate(data, _SCHEMA)
    return EngineConfig(**{k: v for k, v in data.items() if k in _SCHEMA})
