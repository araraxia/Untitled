"""Pathfinding utilities — A*, flow fields, and path caching."""

from __future__ import annotations

import heapq
import math
from collections import OrderedDict, deque
from typing import (
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    TYPE_CHECKING,
)

from backend.engine.spatial import SpatialGrid

if TYPE_CHECKING:
    from backend.engine.ecs.world import World

# 8-directional neighbour offsets with movement costs.
# Cardinal cost = 1.0; diagonal cost ≈ √2.
_NEIGHBOURS: List[Tuple[int, int, float]] = [
    (-1, 0, 1.0),
    (1, 0, 1.0),
    (0, -1, 1.0),
    (0, 1, 1.0),
    (-1, -1, 1.414),
    (-1, 1, 1.414),
    (1, -1, 1.414),
    (1, 1, 1.414),
]


def _cell_blocked(
    grid: SpatialGrid,
    cx: int,
    cy: int,
    world: Optional["World"],
) -> bool:
    """Return True if (cx, cy) contains a solid collider entity.

    Always returns False when *world* is None (no component access).
    """
    if world is None:
        return False
    entity_ids: Set[str] = grid.grid.get((cx, cy), set())
    if not entity_ids:
        return False
    from backend.engine.ecs.component import ColliderComponent  # noqa

    for eid in entity_ids:
        comp = world.get_component(eid, ColliderComponent)
        if comp is not None and comp.solid:
            return True
    return False


def astar(
    grid: SpatialGrid,
    start: Tuple[float, float],
    goal: Tuple[float, float],
    cell_size: float,
    world: Optional["World"] = None,
) -> List[Tuple[float, float]]:
    """Return world-space waypoints from start to goal via A*.

    Uses Chebyshev distance as the heuristic for 8-directional
    movement.  Returns an empty list if no path exists.

    Args:
        grid: SpatialGrid used for collision checking.
        start: World-space (x, y) start coordinate.
        goal: World-space (x, y) goal coordinate.
        cell_size: Grid cell size in world units.
        world: Optional ECS World; required for solid-collider
            checks.  When omitted every cell is treated as open.
    """

    def to_cell(wx: float, wy: float) -> Tuple[int, int]:
        return (int(wx // cell_size), int(wy // cell_size))

    def to_world(cx: int, cy: int) -> Tuple[float, float]:
        half = cell_size * 0.5
        return (cx * cell_size + half, cy * cell_size + half)

    def chebyshev(ax: int, ay: int, bx: int, by: int) -> float:
        return float(max(abs(ax - bx), abs(ay - by)))

    start_cell = to_cell(*start)
    goal_cell = to_cell(*goal)

    if start_cell == goal_cell:
        return [goal]

    g_score: Dict[Tuple[int, int], float] = {start_cell: 0.0}
    came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}

    # Heap entries: (f_score, tiebreak, cell)
    counter: int = 0
    h = chebyshev(*start_cell, *goal_cell)
    open_heap: List[Tuple[float, int, Tuple[int, int]]] = [(h, counter, start_cell)]
    in_open: Set[Tuple[int, int]] = {start_cell}
    closed: Set[Tuple[int, int]] = set()

    while open_heap:
        _, _, current = heapq.heappop(open_heap)
        in_open.discard(current)

        if current == goal_cell:
            path: List[Tuple[float, float]] = []
            node = current
            while node in came_from:
                path.append(to_world(*node))
                node = came_from[node]
            path.reverse()
            path.append(to_world(*goal_cell))
            return path

        closed.add(current)
        cx, cy = current

        for dx, dy, cost in _NEIGHBOURS:
            nx, ny = cx + dx, cy + dy
            neighbour = (nx, ny)
            if neighbour in closed:
                continue
            if _cell_blocked(grid, nx, ny, world):
                continue
            tentative_g = g_score[current] + cost
            if tentative_g < g_score.get(neighbour, math.inf):
                came_from[neighbour] = current
                g_score[neighbour] = tentative_g
                f = tentative_g + chebyshev(nx, ny, *goal_cell)
                counter += 1
                heapq.heappush(open_heap, (f, counter, neighbour))
                in_open.add(neighbour)

    return []


class FlowField:
    """Pre-computed movement vectors for a single goal cell.

    Useful when many entities share the same destination (e.g. a
    party all moving to the same target tile).  Each cell stores the
    normalised direction vector pointing toward the goal.
    """

    def __init__(
        self,
        grid: SpatialGrid,
        goal: Tuple[float, float],
        cell_size: float,
        world: Optional["World"] = None,
    ) -> None:
        """Build the flow field via BFS from goal outward.

        Args:
            grid: SpatialGrid for blocked-cell queries.
            goal: World-space goal coordinate.
            cell_size: Grid cell size in world units.
            world: Optional ECS World for solid-collider checks.
        """
        self._cell_size = cell_size
        goal_cell: Tuple[int, int] = (
            int(goal[0] // cell_size),
            int(goal[1] // cell_size),
        )
        self._directions: Dict[Tuple[int, int], Tuple[float, float]] = {}
        self._build(grid, goal_cell, world)

    def _build(
        self,
        grid: SpatialGrid,
        goal_cell: Tuple[int, int],
        world: Optional["World"],
    ) -> None:
        """Populate direction vectors via BFS from the goal cell."""
        queue: deque[Tuple[int, int]] = deque([goal_cell])
        parent: Dict[Tuple[int, int], Optional[Tuple[int, int]]] = {goal_cell: None}

        while queue:
            current = queue.popleft()
            cx, cy = current
            for dx, dy, _ in _NEIGHBOURS:
                nx, ny = cx + dx, cy + dy
                neighbour = (nx, ny)
                if neighbour in parent:
                    continue
                if _cell_blocked(grid, nx, ny, world):
                    continue
                parent[neighbour] = current
                queue.append(neighbour)

        for cell, par in parent.items():
            if par is None:
                self._directions[cell] = (0.0, 0.0)
                continue
            dx = float(par[0] - cell[0])
            dy = float(par[1] - cell[1])
            length = math.sqrt(dx * dx + dy * dy)
            if length > 0.0:
                self._directions[cell] = (
                    dx / length,
                    dy / length,
                )
            else:
                self._directions[cell] = (0.0, 0.0)

    def direction_at(self, world_x: float, world_y: float) -> Tuple[float, float]:
        """Return the pre-computed direction for a world position.

        Returns:
            Normalised (dx, dy) vector toward the goal, or
            (0.0, 0.0) if the position maps to an unvisited cell.
        """
        cell: Tuple[int, int] = (
            int(world_x // self._cell_size),
            int(world_y // self._cell_size),
        )
        return self._directions.get(cell, (0.0, 0.0))


class PathCache:
    """LRU cache mapping (start_cell, goal_cell) -> waypoint list.

    Paths are invalidated when a solid-collider entity is added to
    or removed from a grid cell that any cached path passes through.
    Uses ``collections.OrderedDict`` for O(1) LRU eviction.
    """

    def __init__(self, capacity: int = 256) -> None:
        """Initialise with a fixed LRU capacity.

        Args:
            capacity: Maximum number of cached paths before the
                least-recently-used entry is evicted.
        """
        self._capacity = capacity
        self._cache: OrderedDict[
            Tuple[Tuple[int, int], Tuple[int, int]],
            List[Tuple[float, float]],
        ] = OrderedDict()
        # Maps grid cell -> set of cache keys whose paths pass through
        # that cell.  Used for O(paths-in-cell) invalidation.
        self._cell_index: Dict[
            Tuple[int, int],
            Set[Tuple[Tuple[int, int], Tuple[int, int]]],
        ] = {}

    def get(
        self,
        start: Tuple[int, int],
        goal: Tuple[int, int],
    ) -> Optional[List[Tuple[float, float]]]:
        """Return the cached path for (start, goal), or None."""
        key = (start, goal)
        if key not in self._cache:
            return None
        self._cache.move_to_end(key)
        return self._cache[key]

    def put(
        self,
        start: Tuple[int, int],
        goal: Tuple[int, int],
        path: List[Tuple[float, float]],
        cell_size: float = 1.0,
    ) -> None:
        """Store *path* and index its cells; evict LRU if at capacity.

        Args:
            start: Grid-cell start for the cache key.
            goal: Grid-cell goal for the cache key.
            path: World-space waypoint list to cache.
            cell_size: Cell size used to convert waypoints to cells.
        """
        key = (start, goal)
        if key in self._cache:
            self._remove_from_index(key)
        elif len(self._cache) >= self._capacity:
            lru_key, _ = self._cache.popitem(last=False)
            self._remove_from_index(lru_key)
        self._cache[key] = path
        for wx, wy in path:
            cell: Tuple[int, int] = (
                int(wx // cell_size),
                int(wy // cell_size),
            )
            self._cell_index.setdefault(cell, set()).add(key)

    def _remove_from_index(
        self,
        key: Tuple[Tuple[int, int], Tuple[int, int]],
    ) -> None:
        """Remove *key* from every cell-index entry it appears in."""
        for cell_keys in self._cell_index.values():
            cell_keys.discard(key)

    def invalidate_near(self, cell: Tuple[int, int]) -> None:
        """Invalidate all cached paths that pass through *cell*."""
        keys = list(self._cell_index.pop(cell, set()))
        for key in keys:
            self._cache.pop(key, None)
            self._remove_from_index(key)
