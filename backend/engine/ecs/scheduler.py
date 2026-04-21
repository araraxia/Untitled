"""ECS SystemScheduler — dependency-ordered system execution."""

from collections import deque
from typing import Dict, List, Set, Type

from backend.engine.ecs.system import System
from backend.engine.ecs.world import World


class SystemScheduler:
    """Runs registered systems in dependency-respecting order each tick.

    Usage::

        scheduler = SystemScheduler()
        scheduler.register(MovementSystem())
        scheduler.register(AISystem())
        scheduler.build()          # call once after all register() calls
        # each tick:
        scheduler.run(world, delta_time)
    """

    def __init__(self) -> None:
        self._systems: List[System] = []
        self._order: List[System] = []
        self._built: bool = False

    def register(self, system: System) -> None:
        """Add *system* to the scheduler.

        Must be called before :meth:`build`.

        Args:
            system: A concrete :class:`System` instance to register.
        """
        self._systems.append(system)
        self._built = False

    def build(self) -> None:
        """Compute execution order using Kahn's topological sort.

        Raises:
            RuntimeError: If a dependency cycle is detected among the
                registered systems.
        """
        # Map each system type to its registered instance(s).
        type_to_instances: Dict[Type[System], List[System]] = {}
        for sys in self._systems:
            cls = type(sys)
            type_to_instances.setdefault(cls, []).append(sys)

        # Build adjacency: dependency → dependents
        in_degree: Dict[System, int] = {s: 0 for s in self._systems}
        dependents: Dict[System, List[System]] = {s: [] for s in self._systems}

        for sys in self._systems:
            for dep_type in type(sys).dependencies:
                dep_instances = type_to_instances.get(dep_type, [])
                for dep in dep_instances:
                    dependents[dep].append(sys)
                    in_degree[sys] += 1

        # Kahn's BFS
        queue: deque[System] = deque(s for s in self._systems if in_degree[s] == 0)
        order: List[System] = []
        visited: Set[int] = set()

        while queue:
            sys = queue.popleft()
            if id(sys) in visited:
                continue
            visited.add(id(sys))
            order.append(sys)
            for dependent in dependents[sys]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(order) != len(self._systems):
            raise RuntimeError(
                "Cycle detected in system dependencies. "
                "Check the dependencies class variables on your systems."
            )

        self._order = order
        self._built = True

    def run(self, world: World, delta_time: float) -> None:
        """Execute all systems in dependency order.

        Args:
            world: The active ECS :class:`World`.
            delta_time: Seconds elapsed since the last tick.

        Raises:
            RuntimeError: If :meth:`build` has not been called yet.
        """
        if not self._built:
            raise RuntimeError("SystemScheduler.build() must be called before run().")
        for system in self._order:
            system.update(world, delta_time)
