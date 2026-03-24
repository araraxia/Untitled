"""Game configuration settings — backwards-compatibility re-export.

Import from backend.engine.config or backend.game.config directly where
possible. This module exists so that existing code using
``from backend.config import X`` continues to work unchanged.
"""

from backend.engine.config import (  # noqa: F401,F403
    TICK_RATE,
    TICK_DURATION,
    MAX_ENTITIES,
    HOST,
    PORT,
    DEBUG,
    LOG_DIR,
)
from backend.game.config import (  # noqa: F401,F403
    DEF_AREA_WIDTH,
    DEF_AREA_HEIGHT,
    SPATIAL_GRID_SIZE,
)