"""ECS-style systems for entity processing."""

import json
import logging
import math
import random
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from backend.engine.ecs.system import System
from backend.engine.ecs.world import World
from backend.engine.ecs.component import (
    AIComponent,
    ColliderComponent,
    PathComponent,
    PositionComponent,
    StatsComponent,
    StateComponent,
    StatusComponent,
    VelocityComponent,
)
from backend.engine.physics import aabb_overlap, get_terrain_friction
from backend.engine.ecs.entity import Entity
from backend.engine.events import EventBus
from backend.engine.behaviour_tree import BehaviourTree, BehaviourTreeLoader

if TYPE_CHECKING:
    from backend.engine.spatial import SpatialGrid

logger = logging.getLogger(__name__)

_GAME_CONFIG_PATH: Path = (
    Path(__file__).resolve().parent.parent.parent.parent / "config" / "game.json"
)


class MovementSystem(System):
    """Applies velocity components to position components each tick."""

    def __init__(self, event_bus: Optional[EventBus] = None) -> None:
        self._bus = event_bus

    def update(self, world: World, delta_time: float) -> None:
        """Update entity positions based on their velocity components."""
        for eid, (pos, vel) in world.query_with_components(
            PositionComponent, VelocityComponent
        ):
            if vel.vx != 0 or vel.vy != 0:
                pos.x += vel.vx * delta_time
                pos.y += vel.vy * delta_time
                entity = world.get(eid)
                if entity is not None:
                    entity.x = pos.x
                    entity.y = pos.y
                    entity.is_dirty = True
                if self._bus is not None:
                    self._bus.publish(
                        "entity_moved",
                        {"id": eid, "x": pos.x, "y": pos.y},
                    )


class PhysicsSystem(System):
    """Integrates velocity, damps motion, and resolves AABB collisions.

    Each tick, entities with velocity are stepped forward, terrain
    friction (or a default 0.85 multiplier) is applied, and solid
    collider pairs are separated via the minimum translation vector
    returned by ``aabb_overlap``.  The entity's record in the
    spatial grid is refreshed after each integration step.
    """

    _DAMPING: float = 0.85
    _MIN_VELOCITY: float = 0.001

    def __init__(
        self,
        spatial_grid: Optional["SpatialGrid"] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self._grid = spatial_grid
        self._bus = event_bus

    def update(self, world: World, delta_time: float) -> None:
        """Integrate velocity, apply damping, and resolve collisions."""
        # Pre-collect all solid colliders for overlap tests.
        solid: List[tuple] = [
            (eid, pos, col)
            for eid, (pos, col) in world.query_with_components(
                PositionComponent, ColliderComponent
            )
            if col.solid
        ]

        for eid, (pos, vel, col) in world.query_with_components(
            PositionComponent, VelocityComponent, ColliderComponent
        ):
            # 1. Integrate position.
            pos.x += vel.vx * delta_time
            pos.y += vel.vy * delta_time

            # 2. Terrain friction or default velocity damping.
            friction = get_terrain_friction(self._grid, pos.x, pos.y)
            if friction > 0.0:
                factor = 1.0 - friction * delta_time
                vel.vx *= factor
                vel.vy *= factor
            else:
                vel.vx *= self._DAMPING
                vel.vy *= self._DAMPING
            if abs(vel.vx) < self._MIN_VELOCITY:
                vel.vx = 0.0
            if abs(vel.vy) < self._MIN_VELOCITY:
                vel.vy = 0.0

            # 3. Resolve collisions against all solid entities.
            for other_eid, other_pos, other_col in solid:
                if other_eid == eid:
                    continue
                mtv = aabb_overlap(
                    pos.x,
                    pos.y,
                    col.width,
                    col.height,
                    other_pos.x,
                    other_pos.y,
                    other_col.width,
                    other_col.height,
                )
                if mtv is not None:
                    dx, dy = mtv
                    pos.x += dx
                    pos.y += dy
                    if dx != 0.0:
                        vel.vx = 0.0
                    if dy != 0.0:
                        vel.vy = 0.0

            # 4. Sync entity object and refresh spatial grid.
            entity = world.get(eid)
            if entity is not None:
                entity.x = pos.x
                entity.y = pos.y
                entity.is_dirty = True
                if self._grid is not None:
                    self._grid.update(entity)
            if self._bus is not None:
                self._bus.publish(
                    "entity_moved",
                    {"id": eid, "x": pos.x, "y": pos.y},
                )


class PathfindingSystem(System):
    """Advances entities along pre-computed movement paths.

    Each tick, pathing entities move toward the next waypoint in
    their ``PathComponent`` at a speed derived from their
    ``StatsComponent`` (if present) or a default fallback speed.
    The ``PathComponent`` is removed when all waypoints are reached.
    """

    dependencies = [PhysicsSystem]

    # Multiplier: StatsComponent.speed * _STEP_SPEED = world units/s
    _STEP_SPEED: float = 50.0

    def __init__(
        self,
        spatial_grid: Optional["SpatialGrid"] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self._grid = spatial_grid
        self._bus = event_bus

    def update(self, world: World, delta_time: float) -> None:
        """Move each entity one step along its PathComponent."""
        for eid, (pos, path) in world.query_with_components(
            PositionComponent, PathComponent
        ):
            if path.current_index >= len(path.waypoints):
                world.remove_component(eid, PathComponent)
                continue

            stats: Optional[StatsComponent] = world.get_component(eid, StatsComponent)
            speed = (
                stats.speed * self._STEP_SPEED
                if stats is not None
                else self._STEP_SPEED
            )

            wx, wy = path.waypoints[path.current_index]
            dx = wx - pos.x
            dy = wy - pos.y
            dist = math.sqrt(dx * dx + dy * dy)
            step = speed * delta_time

            if step >= dist:
                pos.x = wx
                pos.y = wy
                path.current_index += 1
            else:
                factor = step / dist
                pos.x += dx * factor
                pos.y += dy * factor

            entity = world.get(eid)
            if entity is not None:
                entity.x = pos.x
                entity.y = pos.y
                entity.is_dirty = True

            if self._bus is not None:
                self._bus.publish(
                    "entity_moved",
                    {"id": eid, "x": pos.x, "y": pos.y},
                )

            if path.current_index >= len(path.waypoints):
                world.remove_component(eid, PathComponent)


class AISystem(System):
    """Drives entity AI via behaviour trees each tick.

    Each entity with an :class:`AIComponent` maps to a named
    :class:`BehaviourTree`.  Trees are loaded from
    ``config/game.json`` under the ``behaviour_trees`` key and
    cached in memory to avoid repeated JSON parsing.
    """

    dependencies = [PathfindingSystem]

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        trees_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._bus: EventBus = event_bus if event_bus is not None else EventBus()
        if trees_config is not None:
            self._trees_config: Dict[str, Any] = trees_config
        else:
            self._trees_config = self._load_trees_config()
        self._loader: BehaviourTreeLoader = BehaviourTreeLoader()
        self._cache: Dict[str, BehaviourTree] = {}

    @staticmethod
    def _load_trees_config() -> Dict[str, Any]:
        """Load the behaviour_trees section from game.json."""
        try:
            with _GAME_CONFIG_PATH.open("r", encoding="utf-8") as fh:
                data: Dict[str, Any] = json.load(fh)
            return data.get("behaviour_trees", {})
        except (OSError, json.JSONDecodeError):
            return {}

    def _get_tree(self, tree_id: str) -> Optional[BehaviourTree]:
        """Return a cached or freshly loaded BehaviourTree by ID."""
        if tree_id in self._cache:
            return self._cache[tree_id]
        if tree_id not in self._trees_config:
            logger.warning(
                "AISystem: behaviour tree '%s' not found.",
                tree_id,
            )
            return None
        tree = self._loader.load_from_config(tree_id, self._trees_config)
        self._cache[tree_id] = tree
        return tree

    def update(self, world: World, delta_time: float) -> None:
        """Tick the behaviour tree for each AI-controlled entity."""
        for eid, (ai, _pos) in world.query_with_components(
            AIComponent, PositionComponent
        ):
            tree = self._get_tree(ai.behaviour_tree_id)
            if tree is None:
                continue
            tree.tick(eid, world, self._bus)


class CombatSystem(System):
    """Resolves combat actions and processes status effects each tick.

    Action points accumulate each tick based on each entity's speed.
    Combat actions arrive via the ``'combat_action'`` event (published
    by the ``Attack`` behaviour-tree leaf) and are resolved
    immediately.  Status effects tick down and are purged when their
    duration expires.
    """

    dependencies = [AISystem]

    _AP_COST: int = 10  # action points spent per attack

    def __init__(self, event_bus: Optional[EventBus] = None) -> None:
        self._bus: EventBus = event_bus if event_bus is not None else EventBus()
        self._world: Optional[World] = None
        self._bus.subscribe("combat_action", self._on_combat_action)

    def update(self, world: World, delta_time: float) -> None:
        """Accumulate action points and process status effects."""
        self._world = world

        # Accumulate action points for all entities with stats.
        for _eid, (stats,) in world.query_with_components(StatsComponent):
            stats.action_points = min(
                stats.action_points + stats.speed,
                stats.max_action_points,
            )

        # Process status effects for entities that have both.
        for _eid, (status, stats) in world.query_with_components(
            StatusComponent, StatsComponent
        ):
            remaining: List[Dict] = []
            for effect in status.effects:
                effect["duration"] -= 1
                etype: str = effect.get("type", "")
                magnitude: float = float(effect.get("magnitude", 0.0))
                if etype == "poisoned":
                    stats.hp -= int(magnitude)
                elif etype == "stunned":
                    stats.action_points = 0
                if effect["duration"] > 0:
                    remaining.append(effect)
            status.effects = remaining

    def _on_combat_action(self, payload: Dict[str, Any]) -> None:
        """Handle a ``'combat_action'`` event from an Attack leaf node."""
        if self._world is None:
            return
        if payload.get("action") != "attack":
            return

        attacker_id: str = payload.get("attacker", "")
        target_id: str = payload.get("target", "")

        atk_stats: Optional[StatsComponent] = self._world.get_component(
            attacker_id, StatsComponent
        )
        tgt_stats: Optional[StatsComponent] = self._world.get_component(
            target_id, StatsComponent
        )
        if atk_stats is None or tgt_stats is None:
            return

        if atk_stats.action_points < self._AP_COST:
            return
        atk_stats.action_points -= self._AP_COST

        raw_chance = 0.65 + (atk_stats.attack - tgt_stats.defence) * 0.05
        hit_chance = max(0.05, min(0.95, raw_chance))
        is_hit = random.random() < hit_chance

        damage: int = 0
        if is_hit:
            damage = max(1, atk_stats.attack - tgt_stats.defence // 2)
            tgt_stats.hp -= damage

        self._bus.publish(
            "combat_result",
            {
                "attacker": attacker_id,
                "target": target_id,
                "hit": is_hit,
                "damage": damage,
                "target_hp": tgt_stats.hp,
            },
        )
        if tgt_stats.hp <= 0:
            self._bus.publish("entity_died", {"entity_id": target_id})
