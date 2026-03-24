# Engine configuration defaults. Override by passing EngineConfig at startup.
TICK_RATE: int = 20            # Simulation ticks per second
TICK_DURATION: float = 1.0 / TICK_RATE
MAX_ENTITIES: int = 1000

HOST: str = '0.0.0.0'
PORT: int = 5000
DEBUG: bool = True
LOG_DIR: str = 'logs'
