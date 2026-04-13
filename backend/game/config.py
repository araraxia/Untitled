"""Game-specific configuration — defaults and injectable schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional
import json

# ---------------------------------------------------------------------------
# Module-level constants — backward-compatible defaults
# ---------------------------------------------------------------------------

DEF_AREA_WIDTH: int = 1000
DEF_AREA_HEIGHT: int = 1000
SPATIAL_GRID_SIZE: int = 32

# ---------------------------------------------------------------------------
# Injectable config schema
# ---------------------------------------------------------------------------


@dataclass
class GameConfig:
    """Injectable game configuration.

    Attributes:
        default_area_width: Default area width in world units.
        default_area_height: Default area height in world units.
        spatial_grid_size: Grid cell size for spatial queries.
        starting_world_id: World ID loaded on a new game.
        starting_area_id: Area ID spawned into on a new game.
        default_base_stats: Stat baseline used when no race
            definition overrides a value.
    """

    default_area_width: int = DEF_AREA_WIDTH
    default_area_height: int = DEF_AREA_HEIGHT
    spatial_grid_size: int = SPATIAL_GRID_SIZE
    starting_world_id: str = "overworld_001"
    starting_area_id: str = "town_start"
    default_base_stats: Dict[str, int] = field(
        default_factory=lambda: {
            "strength": 10,
            "dexterity": 10,
            "intelligence": 10,
            "willpower": 10,
            "charisma": 10,
            "perception": 10,
            "endurance": 10,
            "luck": 10,
            "speed": 10,
            "soul_power": 10,
            "combat_sense": 10,
        }
    )


_SCHEMA: Dict[str, type] = {
    "default_area_width": int,
    "default_area_height": int,
    "spatial_grid_size": int,
    "starting_world_id": str,
    "starting_area_id": str,
    "default_base_stats": dict,
}

_DEFAULT_PATH: Path = (
    Path(__file__).resolve().parent.parent.parent / "config" / "game.json"
)


def _validate(data: Dict[str, Any], schema: Dict[str, type]) -> None:
    """Raise TypeError on schema mismatch."""
    for key, expected in schema.items():
        if key in data and not isinstance(data[key], expected):
            raise TypeError(
                f"GameConfig '{key}': expected"
                f" {expected.__name__},"
                f" got {type(data[key]).__name__}"
            )


def load_game_config(
    path: Optional[str] = None,
) -> GameConfig:
    """Load GameConfig from a JSON file.

    Falls back to all defaults when the file does not exist.

    Args:
        path: Optional path to a JSON config file.
              Defaults to ``config/game.json`` at project root.

    Returns:
        Populated GameConfig instance.
    """
    config_path = Path(path) if path else _DEFAULT_PATH
    if not config_path.exists():
        return GameConfig()
    with config_path.open("r", encoding="utf-8") as fh:
        data: Dict[str, Any] = json.load(fh)
    _validate(data, _SCHEMA)
    return GameConfig(**{k: v for k, v in data.items() if k in _SCHEMA})
