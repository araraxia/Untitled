"""ECS Component — base class and built-in concrete components."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Type


class Component:
    """Base class for all ECS components.

    Every concrete component subclass is assigned a unique integer
    type ID automatically via __init_subclass__.  The ID is stable
    within a process lifetime and used as a storage key.  Subclasses
    are also registered in ``_COMPONENT_REGISTRY`` for deserialisation.
    """

    _next_id: int = 0
    type_id: int  # set by __init_subclass__

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        cls.type_id = Component._next_id
        Component._next_id += 1
        _COMPONENT_REGISTRY[cls.__name__] = cls  # type: ignore[assignment]

    def to_dict(self) -> Dict[str, Any]:
        """Serialise this component to a JSON-compatible dict.

        The returned dict includes ``"type"`` set to the component's
        class name so that :meth:`from_dict` can reconstruct the
        correct subclass.  Concrete subclasses override this method
        to include their field data.
        """
        return {"type": type(self).__name__}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Component:
        """Reconstruct a component from a serialised dict.

        When called on the base ``Component`` class, dispatches to the
        correct concrete subclass via ``_COMPONENT_REGISTRY``.

        Args:
            data: Dict produced by :meth:`to_dict`.

        Returns:
            Reconstructed component instance.

        Raises:
            ValueError: If ``"type"`` is missing or unregistered.
        """
        type_name = data.get("type")
        if not type_name:
            raise ValueError("Component data is missing the 'type' key.")
        component_cls = _COMPONENT_REGISTRY.get(type_name)
        if component_cls is None:
            raise ValueError(f"Unknown component type: {type_name!r}")
        # Avoid infinite recursion when called on the base class.
        if component_cls is Component:
            raise ValueError("Cannot instantiate abstract Component base class.")
        return component_cls.from_dict(data)


# Populated automatically by Component.__init_subclass__ above.
_COMPONENT_REGISTRY: Dict[str, Type[Component]] = {}


# ---------------------------------------------------------------------------
# Concrete components
# ---------------------------------------------------------------------------


@dataclass
class DataComponent(Component):
    """Arbitrary namespaced data bag for entity-specific information
    that doesn't warrant its own typed component (e.g. game-specific
    stats, appearance, or any other modular payload)."""

    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "DataComponent", "data": self.data}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DataComponent":
        return cls(data=dict(data.get("data", {})))


@dataclass
class PositionComponent(Component):
    """Stores the world-space position of an entity."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "PositionComponent", "x": self.x, "y": self.y, "z": self.z}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PositionComponent:
        return cls(
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            z=float(data.get("z", 0.0)),
        )


@dataclass
class VelocityComponent(Component):
    """Stores the velocity of an entity."""

    vx: float = 0.0
    vy: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "VelocityComponent", "vx": self.vx, "vy": self.vy}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> VelocityComponent:
        return cls(
            vx=float(data.get("vx", 0.0)),
            vy=float(data.get("vy", 0.0)),
        )


@dataclass
class StateComponent(Component):
    """Stores the behavioural state and facing direction of an entity."""

    state: str = "idle"
    facing: str = "down"

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "StateComponent", "state": self.state, "facing": self.facing}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> StateComponent:
        return cls(
            state=data.get("state", "idle"),
            facing=data.get("facing", "down"),
        )


@dataclass
class AnimationComponent(Component):
    """Stores paths to animation data files for an entity."""

    animation_data_paths: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "AnimationComponent",
            "animation_data_paths": list(self.animation_data_paths),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AnimationComponent:
        return cls(
            animation_data_paths=list(data.get("animation_data_paths", [])),
        )


@dataclass
class LightComponent(Component):
    """Stores light emission properties for an entity."""

    color: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    radius: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "LightComponent",
            "color": list(self.color),
            "radius": self.radius,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LightComponent:
        return cls(
            color=[float(v) for v in data.get("color", [1.0, 1.0, 1.0])],
            radius=float(data.get("radius", 1.0)),
        )


@dataclass
class EmitterComponent(Component):
    """Stores particle emitter configuration for an entity."""

    config: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "EmitterComponent", "config": dict(self.config)}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EmitterComponent:
        return cls(config=dict(data.get("config", {})))


@dataclass
class PathComponent(Component):
    """Stores a pre-computed movement path for an entity."""

    waypoints: List[tuple] = field(default_factory=list)
    current_index: int = 0

    def to_dict(self) -> Dict[str, Any]:
        # Tuples are not JSON-native; store as lists.
        return {
            "type": "PathComponent",
            "waypoints": [list(wp) for wp in self.waypoints],
            "current_index": self.current_index,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PathComponent:
        return cls(
            waypoints=[tuple(wp) for wp in data.get("waypoints", [])],
            current_index=int(data.get("current_index", 0)),
        )


@dataclass
class AIComponent(Component):
    """Links an entity to a behaviour tree definition."""

    behaviour_tree_id: str = ""
    active_node_path: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "AIComponent",
            "behaviour_tree_id": self.behaviour_tree_id,
            "active_node_path": list(self.active_node_path),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AIComponent:
        return cls(
            behaviour_tree_id=data.get("behaviour_tree_id", ""),
            active_node_path=list(data.get("active_node_path", [])),
        )


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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "StatsComponent",
            "max_hp": self.max_hp,
            "hp": self.hp,
            "attack": self.attack,
            "defence": self.defence,
            "action_points": self.action_points,
            "max_action_points": self.max_action_points,
            "speed": self.speed,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> StatsComponent:
        return cls(
            max_hp=int(data.get("max_hp", 100)),
            hp=int(data.get("hp", 100)),
            attack=int(data.get("attack", 10)),
            defence=int(data.get("defence", 5)),
            action_points=int(data.get("action_points", 0)),
            max_action_points=int(data.get("max_action_points", 100)),
            speed=float(data.get("speed", 1.0)),
        )


@dataclass
class StatusComponent(Component):
    """Tracks active status effects on an entity.

    Each effect is a dict with keys ``type`` (str),
    ``duration`` (int ticks remaining), and
    ``magnitude`` (float strength of the effect).
    """

    effects: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "StatusComponent", "effects": [dict(e) for e in self.effects]}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> StatusComponent:
        return cls(effects=[dict(e) for e in data.get("effects", [])])


@dataclass
class ColliderComponent(Component):
    """Defines an axis-aligned bounding box for collision detection."""

    width: float = 1.0
    height: float = 1.0
    solid: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "ColliderComponent",
            "width": self.width,
            "height": self.height,
            "solid": self.solid,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ColliderComponent:
        return cls(
            width=float(data.get("width", 1.0)),
            height=float(data.get("height", 1.0)),
            solid=bool(data.get("solid", True)),
        )


@dataclass
class FactionComponent(Component):
    """Assigns an entity to a named faction for AI targeting."""

    faction: str = "neutral"

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "FactionComponent", "faction": self.faction}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FactionComponent:
        return cls(faction=data.get("faction", "neutral"))
