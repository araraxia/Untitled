"""Wave Function Collapse solver for 2-D tile grids."""

import math
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Any

# Direction helpers: (dy, dx) for each named direction.
_DIRS: dict[str, tuple[int, int]] = {
    "north": (-1, 0),
    "south": (1, 0),
    "east": (0, 1),
    "west": (0, -1),
}

# Opposite direction names used during constraint propagation.
_OPPOSITE: dict[str, str] = {
    "north": "south",
    "south": "north",
    "east": "west",
    "west": "east",
}


class WFCContradiction(Exception):
    """Raised when the WFC solver reaches an unsolvable state."""


@dataclass
class TileRule:
    """Adjacency constraint for a single tile type.

    ``allowed[direction]`` is the set of tile IDs that may appear
    next to this tile in that direction.  Direction keys:
    ``'north'``, ``'south'``, ``'east'``, ``'west'``.
    """

    tile_id: str
    weight: float
    allowed: dict[str, set[str]] = field(default_factory=dict)


class WFCSolver:
    """Wave Function Collapse solver for 2-D tile grids.

    Args:
        rules: Mapping of tile_id → TileRule.
        width: Grid width in cells.
        height: Grid height in cells.
        seed: Optional RNG seed for reproducible output.
    """

    def __init__(
        self,
        rules: dict[str, TileRule],
        width: int,
        height: int,
        seed: int | None = None,
    ) -> None:
        self._rules = rules
        self._width = width
        self._height = height
        self._rng = random.Random(seed)

        all_tiles = set(rules.keys())
        # _wave[row][col] = mutable set of still-possible tile IDs.
        self._wave: list[list[set[str]]] = [
            [set(all_tiles) for _ in range(width)] for _ in range(height)
        ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def inject(self, x: int, y: int, tile_id: str) -> None:
        """Force a specific cell to a known tile before solving.

        Args:
            x: Column index (0-based).
            y: Row index (0-based).
            tile_id: The tile to fix at this cell.

        Raises:
            ValueError: If *tile_id* is not in the rule set.
            WFCContradiction: If *tile_id* is not currently possible
                for the cell (already constrained away).
        """
        if tile_id not in self._rules:
            raise ValueError(f"Unknown tile_id '{tile_id}' — not present in rules.")
        cell = self._wave[y][x]
        if tile_id not in cell:
            raise WFCContradiction(
                f"Cannot inject '{tile_id}' at ({x}, {y}): " "already constrained out."
            )
        cell.clear()
        cell.add(tile_id)

    def solve(self) -> list[list[str]]:
        """Run the WFC algorithm and return the solved tile grid.

        Returns a ``height × width`` list of lists of tile IDs.

        Raises:
            WFCContradiction: If no valid layout exists.
        """
        # Propagate any injected constraints before the main loop.
        for row in range(self._height):
            for col in range(self._width):
                if len(self._wave[row][col]) == 1:
                    self._propagate(row, col)

        while True:
            rc = self._lowest_entropy_cell()
            if rc is None:
                break  # All cells collapsed.
            row, col = rc
            self._collapse(row, col)
            self._propagate(row, col)

        return [
            [next(iter(self._wave[r][c])) for c in range(self._width)]
            for r in range(self._height)
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _shannon_entropy(self, row: int, col: int) -> float:
        """Weighted Shannon entropy for the superposition at (row, col).

        Returns 0.0 for already-collapsed cells and ``-inf`` for empty
        (contradiction) cells.
        """
        options = self._wave[row][col]
        n = len(options)
        if n == 0:
            return float("-inf")
        if n == 1:
            return 0.0
        total_w = sum(self._rules[t].weight for t in options)
        if total_w <= 0:
            return float(n)  # Fall back to log(n) with uniform weight.
        entropy = 0.0
        for t in options:
            p = self._rules[t].weight / total_w
            if p > 0:
                entropy -= p * math.log(p)
        return entropy

    def _lowest_entropy_cell(self) -> tuple[int, int] | None:
        """Return (row, col) of the uncollapsed cell with lowest entropy.

        Returns ``None`` when all cells are collapsed.  Ties are broken
        by (row, col) order.
        """
        best: tuple[float, int, int] | None = None
        for row in range(self._height):
            for col in range(self._width):
                if len(self._wave[row][col]) <= 1:
                    continue
                e = self._shannon_entropy(row, col)
                if best is None or e < best[0]:
                    best = (e, row, col)
        if best is None:
            return None
        return best[1], best[2]

    def _collapse(self, row: int, col: int) -> None:
        """Randomly collapse (row, col) to one tile, weighted by TileRule.

        Raises:
            WFCContradiction: If the cell superposition is already empty.
        """
        options = list(self._wave[row][col])
        if not options:
            raise WFCContradiction(
                f"Contradiction at cell ({col}, {row}): no options remain."
            )
        weights = [self._rules[t].weight for t in options]
        chosen = self._rng.choices(options, weights=weights, k=1)[0]
        self._wave[row][col] = {chosen}

    def _propagate(self, start_row: int, start_col: int) -> None:
        """AC-3 style constraint propagation from a collapsed cell.

        Raises:
            WFCContradiction: If any cell's superposition becomes empty.
        """
        queue: deque[tuple[int, int]] = deque()
        queue.append((start_row, start_col))

        while queue:
            row, col = queue.popleft()
            current_options = self._wave[row][col]

            for direction, (dy, dx) in _DIRS.items():
                nr, nc = row + dy, col + dx
                if not (0 <= nr < self._height and 0 <= nc < self._width):
                    continue

                # Build the set of tiles allowed in this neighbour given
                # all currently possible tiles in the current cell.
                allowed_in_neighbour: set[str] = set()
                for tile_id in current_options:
                    rule = self._rules.get(tile_id)
                    if rule is None:
                        continue
                    allowed_in_neighbour.update(rule.allowed.get(direction, set()))

                neighbour_options = self._wave[nr][nc]
                constrained = neighbour_options & allowed_in_neighbour
                if len(constrained) < len(neighbour_options):
                    if not constrained:
                        raise WFCContradiction(
                            f"Contradiction at cell ({nc}, {nr}): "
                            "no options remain after propagation."
                        )
                    self._wave[nr][nc] = constrained
                    queue.append((nr, nc))


def load_rules(rule_def: dict[str, Any]) -> dict[str, TileRule]:
    """Parse a rule definition dict (loaded from JSON) into TileRule objects.

    Expected JSON format (stored under ``config/game.json`` key
    ``'wfc_tile_rules'``):

    .. code-block:: json

        {
          "grass": {
            "weight": 10,
            "allowed": {
              "north": ["grass", "dirt"],
              "south": ["grass", "dirt"],
              "east":  ["grass", "dirt"],
              "west":  ["grass", "dirt"]
            }
          },
          "dirt": { ... }
        }

    Args:
        rule_def: Raw dict parsed from JSON.

    Returns:
        Mapping of tile_id → :class:`TileRule`.
    """
    rules: dict[str, TileRule] = {}
    for tile_id, entry in rule_def.items():
        weight = float(entry.get("weight", 1.0))
        raw_allowed: dict[str, list[str]] = entry.get("allowed", {})
        allowed: dict[str, set[str]] = {
            direction: set(neighbours) for direction, neighbours in raw_allowed.items()
        }
        rules[tile_id] = TileRule(
            tile_id=tile_id,
            weight=weight,
            allowed=allowed,
        )
    return rules
