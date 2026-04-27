"""Behaviour tree classes for AI decision-making."""

import logging
import math
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Type

from backend.engine.ecs.component import (
    FactionComponent,
    PathComponent,
    PositionComponent,
    StatsComponent,
)
from backend.engine.ecs.world import World
from backend.engine.events import EventBus

logger = logging.getLogger(__name__)

_ATTACK_RANGE: float = 50.0
_SAFE_DISTANCE: float = 200.0


# -----------------------------------------------------------------------
# Node status
# -----------------------------------------------------------------------


class NodeStatus(Enum):
    """Return value for every BehaviourNode.tick() call."""

    SUCCESS = auto()
    FAILURE = auto()
    RUNNING = auto()


# -----------------------------------------------------------------------
# Base node
# -----------------------------------------------------------------------


class BehaviourNode:
    """Abstract base for all behaviour tree nodes."""

    name: str = "BehaviourNode"

    def tick(
        self,
        entity_id: str,
        world: World,
        bus: EventBus,
    ) -> NodeStatus:
        """Evaluate this node for one tick and return its status."""
        raise NotImplementedError


# -----------------------------------------------------------------------
# Composite nodes
# -----------------------------------------------------------------------


class Sequence(BehaviourNode):
    """Tick children left-to-right.

    Returns FAILURE on the first child failure.
    Returns SUCCESS only when all children succeed.
    Returns RUNNING if a child returns RUNNING.
    """

    name: str = "Sequence"

    def __init__(self, children: List[BehaviourNode]) -> None:
        self.children = children

    def tick(
        self,
        entity_id: str,
        world: World,
        bus: EventBus,
    ) -> NodeStatus:
        """Tick children in order; fail fast on first failure."""
        for child in self.children:
            status = child.tick(entity_id, world, bus)
            if status != NodeStatus.SUCCESS:
                return status
        return NodeStatus.SUCCESS


class Selector(BehaviourNode):
    """Tick children left-to-right.

    Returns SUCCESS on the first child success.
    Returns FAILURE only when all children fail.
    Returns RUNNING if a child returns RUNNING.
    """

    name: str = "Selector"

    def __init__(self, children: List[BehaviourNode]) -> None:
        self.children = children

    def tick(
        self,
        entity_id: str,
        world: World,
        bus: EventBus,
    ) -> NodeStatus:
        """Tick children in order; succeed fast on first success."""
        for child in self.children:
            status = child.tick(entity_id, world, bus)
            if status != NodeStatus.FAILURE:
                return status
        return NodeStatus.FAILURE


class Parallel(BehaviourNode):
    """Tick all children every frame.

    Returns SUCCESS when at least *min_success* children succeed.
    Returns FAILURE if enough children fail to make success
    impossible.  Otherwise returns RUNNING.
    """

    name: str = "Parallel"

    def __init__(
        self,
        children: List[BehaviourNode],
        min_success: int = 1,
    ) -> None:
        self.children = children
        self.min_success = min_success

    def tick(
        self,
        entity_id: str,
        world: World,
        bus: EventBus,
    ) -> NodeStatus:
        """Tick every child and return the aggregate status."""
        successes = 0
        failures = 0
        for child in self.children:
            status = child.tick(entity_id, world, bus)
            if status == NodeStatus.SUCCESS:
                successes += 1
            elif status == NodeStatus.FAILURE:
                failures += 1
        if successes >= self.min_success:
            return NodeStatus.SUCCESS
        remaining = len(self.children) - failures
        if remaining < self.min_success:
            return NodeStatus.FAILURE
        return NodeStatus.RUNNING


# -----------------------------------------------------------------------
# Internal helpers
# -----------------------------------------------------------------------


def _nearest_enemy(
    entity_id: str,
    world: World,
) -> Optional[str]:
    """Return the entity ID of the closest entity in a rival faction.

    Returns ``None`` when the acting entity has no
    :class:`PositionComponent` or :class:`FactionComponent`, or when
    no enemy entities exist.
    """
    my_pos: Optional[PositionComponent] = world.get_component(
        entity_id, PositionComponent
    )
    my_faction: Optional[FactionComponent] = world.get_component(
        entity_id, FactionComponent
    )
    if my_pos is None or my_faction is None:
        return None

    best_id: Optional[str] = None
    best_dist: float = float("inf")
    for eid, (pos, faction) in world.query_with_components(
        PositionComponent, FactionComponent
    ):
        if eid == entity_id:
            continue
        if faction.faction == my_faction.faction:
            continue
        dx = pos.x - my_pos.x
        dy = pos.y - my_pos.y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < best_dist:
            best_dist = dist
            best_id = eid
    return best_id


# -----------------------------------------------------------------------
# Leaf nodes
# -----------------------------------------------------------------------


class Idle(BehaviourNode):
    """Always returns SUCCESS; publishes no events."""

    name: str = "Idle"

    def tick(
        self,
        entity_id: str,
        world: World,
        bus: EventBus,
    ) -> NodeStatus:
        return NodeStatus.SUCCESS


class Seek(BehaviourNode):
    """Set a PathComponent toward the nearest enemy faction entity.

    Returns RUNNING while the target is outside *attack_range*.
    Returns SUCCESS once within *attack_range* world units.
    Returns FAILURE if no valid target exists.
    """

    name: str = "Seek"

    def __init__(
        self,
        attack_range: float = _ATTACK_RANGE,
    ) -> None:
        self.attack_range = attack_range

    def tick(
        self,
        entity_id: str,
        world: World,
        bus: EventBus,
    ) -> NodeStatus:
        my_pos: Optional[PositionComponent] = world.get_component(
            entity_id, PositionComponent
        )
        if my_pos is None:
            return NodeStatus.FAILURE

        target_id = _nearest_enemy(entity_id, world)
        if target_id is None:
            return NodeStatus.FAILURE

        target_pos: Optional[PositionComponent] = world.get_component(
            target_id, PositionComponent
        )
        if target_pos is None:
            return NodeStatus.FAILURE

        dx = target_pos.x - my_pos.x
        dy = target_pos.y - my_pos.y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist <= self.attack_range:
            return NodeStatus.SUCCESS

        path: Optional[PathComponent] = world.get_component(entity_id, PathComponent)
        if path is None:
            world.add_component(
                entity_id,
                PathComponent(
                    waypoints=[(target_pos.x, target_pos.y)],
                    current_index=0,
                ),
            )
        else:
            path.waypoints = [(target_pos.x, target_pos.y)]
            path.current_index = 0
        return NodeStatus.RUNNING


class Flee(BehaviourNode):
    """Set a PathComponent away from the nearest threat.

    Returns RUNNING while within *safe_distance* world units of the
    threat.  Returns SUCCESS once far enough away or if no threat
    is present.
    """

    name: str = "Flee"

    def __init__(
        self,
        flee_distance: float = _SAFE_DISTANCE,
        safe_distance: float = _SAFE_DISTANCE,
    ) -> None:
        self.flee_distance = flee_distance
        self.safe_distance = safe_distance

    def tick(
        self,
        entity_id: str,
        world: World,
        bus: EventBus,
    ) -> NodeStatus:
        my_pos: Optional[PositionComponent] = world.get_component(
            entity_id, PositionComponent
        )
        if my_pos is None:
            return NodeStatus.FAILURE

        target_id = _nearest_enemy(entity_id, world)
        if target_id is None:
            return NodeStatus.SUCCESS

        target_pos: Optional[PositionComponent] = world.get_component(
            target_id, PositionComponent
        )
        if target_pos is None:
            return NodeStatus.SUCCESS

        dx = my_pos.x - target_pos.x
        dy = my_pos.y - target_pos.y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist >= self.safe_distance:
            return NodeStatus.SUCCESS

        if dist > 0:
            nx = dx / dist
            ny = dy / dist
        else:
            nx, ny = 1.0, 0.0

        flee_x = my_pos.x + nx * self.flee_distance
        flee_y = my_pos.y + ny * self.flee_distance

        path: Optional[PathComponent] = world.get_component(entity_id, PathComponent)
        if path is None:
            world.add_component(
                entity_id,
                PathComponent(
                    waypoints=[(flee_x, flee_y)],
                    current_index=0,
                ),
            )
        else:
            path.waypoints = [(flee_x, flee_y)]
            path.current_index = 0
        return NodeStatus.RUNNING


class Attack(BehaviourNode):
    """Publish a combat_action event if a target is in range.

    Returns SUCCESS if an attack was issued.
    Returns FAILURE if no valid target, out of range, or the
    entity has fewer than 10 action points.
    """

    name: str = "Attack"

    def __init__(
        self,
        attack_range: float = _ATTACK_RANGE,
    ) -> None:
        self.attack_range = attack_range

    def tick(
        self,
        entity_id: str,
        world: World,
        bus: EventBus,
    ) -> NodeStatus:
        my_pos: Optional[PositionComponent] = world.get_component(
            entity_id, PositionComponent
        )
        stats: Optional[StatsComponent] = world.get_component(entity_id, StatsComponent)
        if my_pos is None or stats is None:
            return NodeStatus.FAILURE

        target_id = _nearest_enemy(entity_id, world)
        if target_id is None:
            return NodeStatus.FAILURE

        target_pos: Optional[PositionComponent] = world.get_component(
            target_id, PositionComponent
        )
        if target_pos is None:
            return NodeStatus.FAILURE

        dx = target_pos.x - my_pos.x
        dy = target_pos.y - my_pos.y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist > self.attack_range:
            return NodeStatus.FAILURE
        if stats.action_points < 10:
            return NodeStatus.FAILURE

        bus.publish(
            "combat_action",
            {
                "attacker": entity_id,
                "target": target_id,
                "action": "attack",
            },
        )
        return NodeStatus.SUCCESS


class UseItem(BehaviourNode):
    """Placeholder item-use node; always returns SUCCESS."""

    name: str = "UseItem"

    def tick(
        self,
        entity_id: str,
        world: World,
        bus: EventBus,
    ) -> NodeStatus:
        logger.debug(
            "UseItem: entity %s used an item (placeholder).",
            entity_id,
        )
        return NodeStatus.SUCCESS


# -----------------------------------------------------------------------
# BehaviourTree wrapper
# -----------------------------------------------------------------------


class BehaviourTree:
    """Wraps a root BehaviourNode and drives it each tick."""

    def __init__(
        self,
        tree_id: str,
        root: BehaviourNode,
    ) -> None:
        self.tree_id = tree_id
        self.root = root

    def tick(
        self,
        entity_id: str,
        world: World,
        bus: EventBus,
    ) -> NodeStatus:
        """Evaluate the root node for one tick."""
        return self.root.tick(entity_id, world, bus)


# -----------------------------------------------------------------------
# Tree loader
# -----------------------------------------------------------------------

_NODE_REGISTRY: Dict[str, Type[BehaviourNode]] = {
    "Sequence": Sequence,
    "Selector": Selector,
    "Parallel": Parallel,
    "Idle": Idle,
    "Seek": Seek,
    "Flee": Flee,
    "Attack": Attack,
    "UseItem": UseItem,
}


class BehaviourTreeLoader:
    """Loads behaviour tree definitions from JSON config dicts.

    JSON format (stored under ``config/game.json`` key
    ``'behaviour_trees'``)::

        {
          "tree_id": {
            "type": "Sequence",
            "children": [
              {"type": "Seek"},
              {"type": "Attack"}
            ]
          }
        }
    """

    def load_from_config(
        self,
        tree_id: str,
        trees_config: Dict[str, Any],
    ) -> BehaviourTree:
        """Build a :class:`BehaviourTree` for *tree_id*.

        *trees_config* is the value of the ``'behaviour_trees'``
        key in ``config/game.json``.

        Raises:
            KeyError: If *tree_id* is absent from *trees_config*.
        """
        if tree_id not in trees_config:
            raise KeyError(f"Behaviour tree '{tree_id}' not found in config.")
        root = self._build_node(trees_config[tree_id])
        return BehaviourTree(tree_id=tree_id, root=root)

    def load(self, tree_def: Dict[str, Any]) -> BehaviourTree:
        """Parse a single tree definition dict.

        The dict must contain a ``"type"`` key for the root node.
        An optional ``"tree_id"`` key names the tree; defaults to
        ``"unnamed"``.
        """
        tree_id: str = tree_def.get("tree_id", "unnamed")
        root_def = tree_def.get("root", tree_def)
        root = self._build_node(root_def)
        return BehaviourTree(tree_id=tree_id, root=root)

    def _build_node(
        self,
        node_def: Dict[str, Any],
    ) -> BehaviourNode:
        """Recursively build a BehaviourNode from a definition dict."""
        node_type = node_def.get("type")
        if node_type not in _NODE_REGISTRY:
            raise ValueError(
                f"Unknown behaviour node type: '{node_type}'. "
                f"Valid types: {list(_NODE_REGISTRY)}"
            )
        cls = _NODE_REGISTRY[node_type]
        children_defs: List[Dict[str, Any]] = node_def.get("children", [])
        kwargs: Dict[str, Any] = {
            k: v for k, v in node_def.items() if k not in ("type", "children")
        }

        if issubclass(cls, (Sequence, Selector)):
            children = [self._build_node(c) for c in children_defs]
            return cls(children=children)  # type: ignore[call-arg]
        if issubclass(cls, Parallel):
            children = [self._build_node(c) for c in children_defs]
            return cls(
                children=children,
                min_success=int(kwargs.get("min_success", 1)),
            )
        return cls(**kwargs)  # type: ignore[call-arg]
