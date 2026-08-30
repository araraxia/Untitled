"""Entity base class."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from backend.engine.ecs.component import Component, DataComponent

ENTITY_DIR = Path("data/entities")


class Entity:
    """Base class for all entities in the simulation.

    Deliberately minimal — position, rendering, and networking-relevant
    state only. Anything game-specific (stats, appearance, inventory, ...)
    belongs in a game-defined component or on the generic tag data bag via
    :meth:`get_data`/:meth:`set_data`, not as a hardcoded field here.

    Attributes:
        entity_id (str): Unique identifier for the entity.
        x (Optional[float]): X position of the entity.
        y (Optional[float]): Y position of the entity.
        vx (float): Velocity in the X direction.
        vy (float): Velocity in the Y direction.
        vz (float): Velocity in the Z direction (world-space forward
            axis on a Y-up ground plane -- see FreeCamera/
            ThirdPersonCamera/mat4.py's shared convention).
        state (str): Current state of the entity (e.g., "idle", "moving").
        facing (str): Direction the entity is facing ("up", "down", "left", "right").
        animation_data_paths (List[str]): List of paths to animation data files.
    """

    def __init__(
        self,
        entity_id: str,
        x: Optional[float] = None,
        y: Optional[float] = None,
        z: Optional[float] = None,
        state: str = "idle",
        facing: str = "down",
        animation_data_paths: Optional[List[str]] = None,
    ):
        self.entity_id = entity_id
        self.current_area_id: Optional[str] = None
        self.x = x if x is not None else -10000.0
        self.y = y if y is not None else -10000.0
        self.z = z if z is not None else 0.0
        self.vx = 0.0  # velocity x
        self.vy = 0.0  # velocity y
        self.vz = 0.0  # velocity z (world-space forward axis, Y-up)
        self.state = state  # e.g., idle, moving, attacking
        self.facing = facing  # direction entity is facing: up, down, left, right
        self.is_dirty = True
        self.animation_data_paths = animation_data_paths or []

        # 3D rendering (frontend/js/game/3d-coordinate-mapping): which
        # entity-definition (frontend/assets/data/entity/entity-<uuid>.json)
        # renders this entity, and how this one placement is rotated/scaled.
        # Deliberately no position fields here — x/y/z above already are
        # this instance's position; render_template/transform3d must never
        # carry placement data, only "what it looks like" (render_template)
        # and "how this copy is oriented" (transform3d).
        self.render_template: Optional[str] = None
        self.transform3d: Optional[Dict[str, Any]] = None

        # ECS component storage: type_id -> Component instance. Also the
        # home of the generic tag/data bag (see get_data/set_data below) —
        # not routed through the engine's World, since World is not yet
        # wired into the live tick loop.
        self._components: Dict[int, Component] = {}

    def add_component(self, component: Component) -> None:
        """Attach *component* to this entity, replacing any existing
        component of the same type."""
        self._components[type(component).type_id] = component

    def get_component(self, component_type: Type[Component]) -> Optional[Component]:
        """Return the attached component of *component_type*, or None."""
        return self._components.get(component_type.type_id)

    def remove_component(self, component_type: Type[Component]) -> None:
        """Detach the component of *component_type*, if present.
        No-op if not attached. Mirrors add_component/get_component's
        shape.
        """
        self._components.pop(component_type.type_id, None)

    def get_data(self, key: str, default: Any = None) -> Any:
        """Read *key* from this entity's tag data bag, or *default*."""
        comp = self.get_component(DataComponent)
        return comp.data.get(key, default) if comp else default

    def set_data(self, key: str, value: Any) -> None:
        """Write *key* into this entity's tag data bag, creating the
        backing component on first use."""
        comp = self.get_component(DataComponent)
        if comp is None:
            comp = DataComponent()
            self.add_component(comp)
        comp.data[key] = value

    def clear_data(self, key: str) -> None:
        """Remove *key* from this entity's tag data bag, if present.
        No-op (not an error) if the key or the backing DataComponent
        doesn't exist -- matches get_data/set_data's lazy-get-or-create
        style.
        """
        comp = self.get_component(DataComponent)
        if comp is not None:
            comp.data.pop(key, None)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the entity and all attached ECS components.

        Returns a JSON-compatible dict suitable for persistence.  The
        ``components`` list stores each component's :meth:`to_dict`
        output so they can be fully reconstructed via
        :meth:`from_dict`.
        """
        return {
            "entity_id": self.entity_id,
            "current_area_id": self.current_area_id,
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "vx": self.vx,
            "vy": self.vy,
            "vz": self.vz,
            "state": self.state,
            "facing": self.facing,
            "animation_data_paths": self.animation_data_paths,
            "render_template": self.render_template,
            "transform3d": self.transform3d,
            "components": [comp.to_dict() for comp in self._components.values()],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Entity:
        """Reconstruct an entity and its ECS components from a
        serialised dict produced by :meth:`to_dict`.

        Args:
            data: Persistence dict with an ``entity_id`` key.

        Returns:
            Fully populated Entity instance.
        """
        entity = cls(
            entity_id=data["entity_id"],
            x=data.get("x"),
            y=data.get("y"),
            z=data.get("z"),
            state=data.get("state", "idle"),
            facing=data.get("facing", "down"),
            animation_data_paths=data.get("animation_data_paths", []),
        )
        entity.current_area_id = data.get("current_area_id")
        entity.vx = data.get("vx", 0.0)
        entity.vy = data.get("vy", 0.0)
        entity.vz = data.get("vz", 0.0)
        entity.render_template = data.get("render_template")
        entity.transform3d = data.get("transform3d")
        for comp_data in data.get("components", []):
            try:
                comp = Component.from_dict(comp_data)
                entity.add_component(comp)
            except (ValueError, KeyError):
                pass
        return entity

    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> Entity:
        """Reconstruct an entity from a serialised dict.

        Accepts both the legacy network format (``"id"`` key produced
        by :meth:`serialize`) and the persistence format
        (``"entity_id"`` key produced by :meth:`to_dict`).

        Args:
            data: Dict from either :meth:`serialize` or :meth:`to_dict`.

        Returns:
            Reconstructed Entity instance.
        """
        # Normalise legacy key so from_dict can handle both formats.
        if "entity_id" not in data and "id" in data:
            data = dict(data, entity_id=data["id"])
        return cls.from_dict(data)

    def update(self, delta_time: float):
        """Update entity state."""
        # Update position based on velocity
        if self.vx != 0 or self.vy != 0 or self.vz != 0:
            self.x += self.vx * delta_time
            self.y += self.vy * delta_time
            self.z += self.vz * delta_time
            self.is_dirty = True

    def serialize(self) -> Dict[str, Any]:
        """Serialize entity state for network transmission."""
        return {
            "id": self.entity_id,
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "vx": self.vx,
            "vy": self.vy,
            "vz": self.vz,
            "state": self.state,
            "facing": self.facing,
            "animation_data_paths": self.animation_data_paths,
            "render_template": self.render_template,
            "transform3d": self.transform3d,
        }

    def save_to_file(self, directory: Path = ENTITY_DIR) -> str:
        """Save entity data to a JSON file named with the entity ID.

        Args:
            directory: Directory to save the file in (default: 'data/entities')

        Returns:
            str: Path to the saved file
        """
        save_dir = Path(directory)
        save_dir.mkdir(parents=True, exist_ok=True)

        data = self.to_dict()

        file_path = save_dir / f"{self.entity_id}.json"
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)

        return str(file_path)

    @classmethod
    def load_from_file(cls, file_path: Path) -> "Entity":
        """Load entity data from a JSON file.

        Args:
            file_path: Path to the JSON file containing entity data

        Returns:
            Entity: A new Entity instance with loaded data
        """
        with open(file_path, "r") as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def load_by_id(cls, entity_id: str, directory: Path = ENTITY_DIR) -> "Entity":
        """Load entity data using entity ID to construct the file path.

        Args:
            entity_id: The entity ID to load
            directory: Directory to load from (default: 'data/entities')

        Returns:
            Entity: A new Entity instance with loaded data
        """
        file_path = Path(directory) / f"{entity_id}.json"
        return cls.load_from_file(file_path)

    def receive_command(self, command: Dict[str, Any]):
        """Receive a high-level command (for party members/AI entities)."""
        pass  # Override in subclasses
