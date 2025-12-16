"""Spatial partitioning for efficient queries."""

from typing import List, Tuple, Dict, Set
from backend.simulation.entity import Entity


class SpatialGrid:
    """Grid-based spatial partitioning system for efficient entity queries.

    Divides the world space into uniform grid cells to enable fast spatial lookups.
    Reduces entity query complexity from O(n) to O(k) where k is the number of
    entities in relevant grid cells.

    Typical use cases:
        - Collision detection
        - Line-of-sight calculations
        - Finding nearby entities
        - Area-of-effect queries

    Attributes:
        width: World width in units
        height: World height in units
        cell_size: Size of each grid cell (default 32 units)
        cols: Number of grid columns
        rows: Number of grid rows
        grid: Mapping of (col, row) -> set of entity IDs in that cell
        entity_positions: Mapping of entity_id -> (col, row) for quick lookups
    """

    def __init__(self, width: int, height: int, cell_size: int = 32):
        """Initialize the spatial grid.

        Args:
            width: Total world width in units
            height: Total world height in units
            cell_size: Size of each grid cell in units (default: 32).
                      Smaller cells = more precision but higher memory usage.
                      Larger cells = less memory but more entities per query.

        Example:
            >>> grid = SpatialGrid(width=1000, height=1000, cell_size=32)
            >>> # Creates a 31x31 grid (1000/32 = 31.25 rounded down)
        """
        self.width = width
        self.height = height
        self.cell_size = cell_size
        self.cols = width // cell_size
        self.rows = height // cell_size
        self.grid: Dict[Tuple[int, int], Set[str]] = {}
        self.entity_positions: Dict[str, Tuple[int, int]] = {}

    def _get_cell(self, x: float, y: float) -> Tuple[int, int]:
        """Convert world coordinates to grid cell coordinates.

        Args:
            x: World x coordinate
            y: World y coordinate

        Returns:
            Tuple of (column, row) representing the grid cell.

        Note:
            This is an internal helper method. Coordinates outside world bounds
            will return cells outside the valid grid range.

        Complexity: O(1)
        """
        col = int(x // self.cell_size)
        row = int(y // self.cell_size)
        return (col, row)

    def insert(self, entity: Entity):
        """Insert an entity into the spatial grid at its current position.

        Registers the entity in the appropriate grid cell based on its (x, y)
        coordinates. Should be called when spawning new entities.

        Args:
            entity: The entity to insert. Must have entity_id, x, and y attributes.

        Note:
            If entity already exists in the grid, this will create a duplicate entry.
            Use update() instead for moving existing entities.

        Complexity: O(1)

        Example:
            >>> player = PlayerCharacter("player_1", x=100, y=200)
            >>> spatial_grid.insert(player)
        """
        cell = self._get_cell(entity.x, entity.y)
        if cell not in self.grid:
            self.grid[cell] = set()
        self.grid[cell].add(entity.entity_id)
        self.entity_positions[entity.entity_id] = cell

    def remove(self, entity: Entity):
        """Remove an entity from the spatial grid entirely.

        Unregisters the entity from its current grid cell and removes all
        tracking information. Should be called when entities are destroyed
        or despawned.

        Args:
            entity: The entity to remove. Must have entity_id attribute.

        Note:
            Safe to call even if entity is not in the grid (no-op).
            Does not modify the entity itself, only grid bookkeeping.

        Complexity: O(1)

        Example:
            >>> spatial_grid.remove(dead_enemy)
        """
        if entity.entity_id in self.entity_positions:
            cell = self.entity_positions[entity.entity_id]
            if cell in self.grid:
                self.grid[cell].discard(entity.entity_id)
            del self.entity_positions[entity.entity_id]

    def update(self, entity: Entity):
        """Update an entity's grid position after it has moved.

        Efficiently handles entity movement by only updating grid cells when
        the entity crosses cell boundaries. If entity stays within the same
        cell, no updates are performed (optimization).

        Args:
            entity: The entity that has moved. Must have entity_id, x, and y attributes.

        Note:
            Should be called every frame/tick for moving entities.
            Automatically handles first-time registration if entity is not yet in grid.

        Complexity: O(1) - only updates if entity crosses cell boundary

        Example:
            >>> player.x += velocity_x * delta_time
            >>> player.y += velocity_y * delta_time
            >>> spatial_grid.update(player)  # Updates grid if cell changed
        """
        new_cell = self._get_cell(entity.x, entity.y)
        old_cell = self.entity_positions.get(entity.entity_id)

        if old_cell != new_cell:
            # Remove from old cell
            if old_cell and old_cell in self.grid:
                self.grid[old_cell].discard(entity.entity_id)

            # Add to new cell
            if new_cell not in self.grid:
                self.grid[new_cell] = set()
            self.grid[new_cell].add(entity.entity_id)
            self.entity_positions[entity.entity_id] = new_cell

    def query_area(self, x: float, y: float, width: float, height: float) -> Set[str]:
        """Query all entities within a rectangular bounding box.

        Returns entity IDs of all entities whose grid cells intersect with
        the specified rectangular area. This is a fast, approximate query.

        Args:
            x: Left edge of the rectangle (world coordinates)
            y: Top edge of the rectangle (world coordinates)
            width: Width of the rectangle in world units
            height: Height of the rectangle in world units

        Returns:
            Set of entity IDs within the queried area. May include entities
            near the edges that are technically outside the exact rectangle.

        Complexity: O(k) where k is the number of entities in intersecting cells

        Example:
            >>> # Find all entities in a 100x100 area starting at (50, 50)
            >>> entity_ids = spatial_grid.query_area(50, 50, 100, 100)
            >>> for eid in entity_ids:
            ...     entity = world.entities[eid]
            ...     # Process nearby entities
        """
        min_col = int(x // self.cell_size)
        max_col = int((x + width) // self.cell_size)
        min_row = int(y // self.cell_size)
        max_row = int((y + height) // self.cell_size)

        entities = set()
        for col in range(min_col, max_col + 1):
            for row in range(min_row, max_row + 1):
                if (col, row) in self.grid:
                    entities.update(self.grid[(col, row)])

        return entities

    def query_radius(
        self, x: float, y: float, radius: float, entities_dict: Dict[str, Entity] = None
    ) -> Set[str]:
        """Query entities within a circular radius.

        Args:
            x: Center x coordinate
            y: Center y coordinate
            radius: Radius distance
            entities_dict: Dictionary of entity_id -> Entity for distance filtering.
                          If None, returns bounding box approximation (faster but less accurate).

        Returns:
            Set of entity IDs within the circular radius.
        """
        # Get candidates from bounding box (fast grid lookup)
        candidates = self.query_area(x - radius, y - radius, radius * 2, radius * 2)

        # If no entities dict provided, return bounding box results (backwards compatible)
        if entities_dict is None:
            return candidates

        # Filter to actual circle using distance check
        radius_squared = radius * radius
        result = set()

        for entity_id in candidates:
            entity = entities_dict.get(entity_id)
            if entity:
                dx = entity.x - x
                dy = entity.y - y
                distance_squared = dx * dx + dy * dy

                if distance_squared <= radius_squared:
                    result.add(entity_id)

        return result
