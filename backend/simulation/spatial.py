"""Spatial partitioning for efficient queries."""

from typing import List, Tuple, Dict, Set
from backend.simulation.entity import Entity


class SpatialGrid:
    """Grid-based spatial partitioning for entity queries."""

    def __init__(self, width: int, height: int, cell_size: int = 32):
        self.width = width
        self.height = height
        self.cell_size = cell_size
        self.cols = width // cell_size
        self.rows = height // cell_size
        self.grid: Dict[Tuple[int, int], Set[str]] = {}
        self.entity_positions: Dict[str, Tuple[int, int]] = {}

    def _get_cell(self, x: float, y: float) -> Tuple[int, int]:
        """Get the grid cell for a position."""
        col = int(x // self.cell_size)
        row = int(y // self.cell_size)
        return (col, row)

    def insert(self, entity: Entity):
        """Insert an entity into the grid."""
        cell = self._get_cell(entity.x, entity.y)
        if cell not in self.grid:
            self.grid[cell] = set()
        self.grid[cell].add(entity.entity_id)
        self.entity_positions[entity.entity_id] = cell

    def remove(self, entity: Entity):
        """Remove an entity from the grid."""
        if entity.entity_id in self.entity_positions:
            cell = self.entity_positions[entity.entity_id]
            if cell in self.grid:
                self.grid[cell].discard(entity.entity_id)
            del self.entity_positions[entity.entity_id]

    def update(self, entity: Entity):
        """Update an entity's position in the grid."""
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
        """Query entities in a rectangular area."""
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

    def query_radius(self, x: float, y: float, radius: float) -> Set[str]:
        """Query entities within a radius."""
        # Simple implementation using bounding box
        return self.query_area(x - radius, y - radius, radius * 2, radius * 2)
