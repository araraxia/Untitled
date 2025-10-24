"""Party management and AI."""

from typing import Dict, Any, List, Optional
from backend.simulation.entity import Entity


class PartyMember(Entity):
    """A party member with AI and command system."""

    def __init__(self, entity_id: str, x: float, y: float):
        super().__init__(entity_id, x, y)
        self.hp = 100
        self.max_hp = 100
        self.ai_mode = "follow"  # follow, hold_position, defend, etc.
        self.follow_target: Optional[str] = None
        self.defend_position: Optional[tuple] = None
        self.action_queue: List[Any] = []

    def receive_command(self, command: Dict[str, Any]):
        """Process a high-level command."""
        command_type = command.get("type")

        if command_type == "follow":
            self.ai_mode = "follow"
            self.follow_target = command.get("target_id")
            self.state = "following"
            self.is_dirty = True

        elif command_type == "hold_position":
            self.ai_mode = "hold_position"
            self.vx = 0
            self.vy = 0
            self.state = "idle"
            self.is_dirty = True

        elif command_type == "attack_target":
            target_id = command.get("target_id")
            self.ai_mode = "attack"
            self.state = "attacking"
            self.is_dirty = True

        elif command_type == "move_to":
            target = command.get("target", {})
            # Simple direct movement for now (pathfinding to be added)
            self.ai_mode = "move_to"
            self.state = "moving"
            self.is_dirty = True

    def update(self, delta_time: float):
        """Update party member AI and state."""
        super().update(delta_time)

        # AI behavior based on mode
        if self.ai_mode == "follow" and self.follow_target:
            # Simple follow logic (to be enhanced with pathfinding)
            pass

    def serialize(self) -> Dict[str, Any]:
        """Serialize party member state."""
        base_data = super().serialize()
        base_data.update(
            {"hp": self.hp, "max_hp": self.max_hp, "ai_mode": self.ai_mode}
        )
        return base_data


class PartyManager:
    """Manages the player's party."""

    def __init__(self):
        self.members: Dict[str, PartyMember] = {}

    def add_member(self, member: PartyMember):
        """Add a party member."""
        self.members[member.entity_id] = member

    def remove_member(self, member_id: str):
        """Remove a party member."""
        if member_id in self.members:
            del self.members[member_id]

    def get_member(self, member_id: str) -> Optional[PartyMember]:
        """Get a party member by ID."""
        return self.members.get(member_id)
