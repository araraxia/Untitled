"""ECS Component — base class and built-in concrete components."""

from dataclasses import dataclass, field
from typing import Dict, List


class Component:
    """Base class for all ECS components.

    Every concrete component subclass is assigned a unique integer
    type ID automatically via __init_subclass__.  The ID is stable
    within a process lifetime and used as a storage key.
    """

    _next_id: int = 0
    type_id: int  # set by __init_subclass__

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        cls.type_id = Component._next_id
        Component._next_id += 1


@dataclass
class PositionComponent(Component):
    """Stores the world-space position of an entity."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass
class VelocityComponent(Component):
    """Stores the velocity of an entity."""

    vx: float = 0.0
    vy: float = 0.0


@dataclass
class StateComponent(Component):
    """Stores the behavioural state and facing direction of an entity."""

    state: str = "idle"
    facing: str = "down"


@dataclass
class AnimationComponent(Component):
    """Stores paths to animation data files for an entity."""

    animation_data_paths: List[str] = field(default_factory=list)


@dataclass
class LightComponent(Component):
    """Stores light emission properties for an entity."""

    color: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    radius: float = 1.0


@dataclass
class EmitterComponent(Component):
    """Stores particle emitter configuration for an entity."""

    config: Dict = field(default_factory=dict)


@dataclass
class PathComponent(Component):
    """Stores a pre-computed movement path for an entity."""

    waypoints: List[tuple] = field(default_factory=list)
    current_index: int = 0


@dataclass
class AIComponent(Component):
    """Links an entity to a behaviour tree definition."""

    behaviour_tree_id: str = ""
    active_node_path: List[str] = field(default_factory=list)


@dataclass
class StatsComponent(Component):
    """Stores combat and movement statistics for an entity."""

    max_hp: int = 100
    hp: int = 100
    attack: int = 10
    defence: int = 5
    action_points: int = 0
    max_action_points: int = 100
    speed: float = 1.0


@dataclass
class StatusComponent(Component):
    """Tracks active status effects on an entity.

    Each effect is a dict with keys ``type`` (str),
    ``duration`` (int ticks remaining), and
    ``magnitude`` (float strength of the effect).
    """

    effects: List[Dict] = field(default_factory=list)


@dataclass
class ColliderComponent(Component):
    """Defines an axis-aligned bounding box for collision detection."""

    width: float = 1.0
    height: float = 1.0
    solid: bool = True


@dataclass
class FactionComponent(Component):
    """Assigns an entity to a named faction for AI targeting."""

    faction: str = "neutral"
