"""Player character with deep action system."""

from typing import Dict, Any, Optional
from backend.simulation.entity import Entity
from backend.simulation.actions import ActionFactory


class PlayerCharacter(Entity):
    """Player character with deep action control."""

    def __init__(self, entity_id: str, x: float, y: float):
        super().__init__(entity_id, x, y)
        self.hp = 100
        self.max_hp = 100
        self.action_points = 100
        self.inventory = []
        self.equipment = {}
        self.current_action: Optional[Any] = None

    def execute_action(self, action_data: Dict[str, Any]):
        """Execute a player action."""
        action_type = action_data.get("type")

        if action_type == "move":
            # Simple movement for now
            direction = action_data.get("direction", {})
            speed = 50.0  # units per second
            self.vx = direction.get("x", 0) * speed
            self.vy = direction.get("y", 0) * speed
            self.state = "moving" if (self.vx != 0 or self.vy != 0) else "idle"

            # Update facing direction based on movement
            if self.vy < 0:
                self.facing = "up"
            elif self.vy > 0:
                self.facing = "down"
            elif self.vx < 0:
                self.facing = "left"
            elif self.vx > 0:
                self.facing = "right"

            self.is_dirty = True

        elif action_type == "attack":
            # Placeholder for attack action
            target_id = action_data.get("target_id")
            self.state = "attacking"
            self.is_dirty = True

        elif action_type == "use_item":
            # Placeholder for item use
            item_id = action_data.get("item_id")
            self.state = "using_item"
            self.is_dirty = True

    def consume_action_points(self, cost: int):
        """Consume action points for an action."""
        self.action_points = max(0, self.action_points - cost)
        self.is_dirty = True

    def serialize(self) -> Dict[str, Any]:
        """Serialize player state."""
        base_data = super().serialize()
        base_data.update(
            {
                "hp": self.hp,
                "max_hp": self.max_hp,
                "action_points": self.action_points,
                "inventory": self.inventory,
                "equipment": self.equipment,
            }
        )
        return base_data
