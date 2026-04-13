"""Engine package — reusable infrastructure."""

from backend.engine.spatial import SpatialGrid  # noqa: F401
from backend.engine.game_loop import GameLoop  # noqa: F401
from backend.engine.events import EventBus  # noqa: F401
from backend.engine.config import (  # noqa: F401
    EngineConfig,
    load_engine_config,
)
