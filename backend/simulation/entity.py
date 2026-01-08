"""Entity base class."""

from typing import Dict, Any


class Entity:
    """Base class for all entities in the simulation.
    
    Attributes:
        entity_id (str): Unique identifier for the entity.
        x (float): X position of the entity.
        y (float): Y position of the entity.
        vx (float): Velocity in the X direction.
        vy (float): Velocity in the Y direction.
        state (str): Current state of the entity (e.g., "idle", "moving").
        facing (str): Direction the entity is facing ("up", "down", "left", "right").
    """

    def __init__(self, entity_id: str, x: float, y: float):
        self.entity_id = entity_id
        self.x = x
        self.y = y
        self.vx = 0.0  # velocity x
        self.vy = 0.0  # velocity y
        self.state = "idle"
        self.facing = "down"  # direction entity is facing: up, down, left, right
        self.is_dirty = True

    def update(self, delta_time: float):
        """Update entity state."""
        # Update position based on velocity
        if self.vx != 0 or self.vy != 0:
            self.x += self.vx * delta_time
            self.y += self.vy * delta_time
            self.is_dirty = True

    def serialize(self) -> Dict[str, Any]:
        """Serialize entity state for network transmission."""
        return {
            "id": self.entity_id,
            "x": self.x,
            "y": self.y,
            "vx": self.vx,
            "vy": self.vy,
            "state": self.state,
            "facing": self.facing,
        }

    def receive_command(self, command: Dict[str, Any]):
        """Receive a high-level command (for party members/AI entities)."""
        pass  # Override in subclasses
