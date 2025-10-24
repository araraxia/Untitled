"""Action system for player character."""

from typing import Dict, Any, Optional
from abc import ABC, abstractmethod


class Action(ABC):
    """Base class for player actions."""

    def __init__(self, cost: int = 10):
        self.cost = cost
        self.result: Optional[Any] = None

    @abstractmethod
    def can_execute(self, player) -> bool:
        """Check if the action can be executed."""
        pass

    @abstractmethod
    def execute(self, player):
        """Execute the action."""
        pass


class MoveAction(Action):
    """Movement action."""

    def __init__(self, target_x: float, target_y: float):
        super().__init__(cost=5)
        self.target_x = target_x
        self.target_y = target_y

    def can_execute(self, player) -> bool:
        return player.action_points >= self.cost

    def execute(self, player):
        # Simple teleport for now (should be gradual movement)
        player.x = self.target_x
        player.y = self.target_y
        player.is_dirty = True


class AttackAction(Action):
    """Attack action."""

    def __init__(self, target_id: str):
        super().__init__(cost=20)
        self.target_id = target_id

    def can_execute(self, player) -> bool:
        return player.action_points >= self.cost

    def execute(self, player):
        # Placeholder for attack logic
        player.state = "attacking"
        player.is_dirty = True


class UseItemAction(Action):
    """Use item action."""

    def __init__(self, item_id: str):
        super().__init__(cost=10)
        self.item_id = item_id

    def can_execute(self, player) -> bool:
        return player.action_points >= self.cost and self.item_id in player.inventory

    def execute(self, player):
        # Placeholder for item use logic
        player.state = "using_item"
        player.is_dirty = True


class ActionFactory:
    """Factory for creating actions."""

    @staticmethod
    def create(action_type: str, **kwargs) -> Optional[Action]:
        """Create an action based on type."""
        if action_type == "move":
            return MoveAction(kwargs.get("x"), kwargs.get("y"))
        elif action_type == "attack":
            return AttackAction(kwargs.get("target_id"))
        elif action_type == "use_item":
            return UseItemAction(kwargs.get("item_id"))
        return None
