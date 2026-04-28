"""AABB collision utilities and simple physics helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from backend.engine.spatial import SpatialGrid


def get_terrain_friction(
    grid: Optional["SpatialGrid"],
    x: float,
    y: float,
) -> float:
    """Return the friction coefficient for the terrain at (x, y).

    Terrain tile friction is out of scope for Phase 4.  This stub
    always returns ``0.0`` so callers fall back to the default
    velocity damping multiplier.

    Args:
        grid: The spatial grid (unused in this stub).
        x: World-space x coordinate.
        y: World-space y coordinate.

    Returns:
        ``0.0`` unconditionally.
    """
    return 0.0


def aabb_overlap(
    ax: float,
    ay: float,
    aw: float,
    ah: float,
    bx: float,
    by: float,
    bw: float,
    bh: float,
) -> tuple[float, float] | None:
    """Return the MTV to push A out of B, or None if no overlap.

    Positions are the top-left corner of each axis-aligned bounding
    box.  The minimum translation vector (MTV) is the shortest
    displacement that moves box A so it no longer intersects box B.
    Only one axis component of the MTV will be non-zero — the axis
    with the smaller penetration depth.

    Args:
        ax: Left edge of box A.
        ay: Top edge of box A.
        aw: Width of box A.
        ah: Height of box A.
        bx: Left edge of box B.
        by: Top edge of box B.
        bw: Width of box B.
        bh: Height of box B.

    Returns:
        ``(dx, dy)`` translation to push A out of B, or ``None`` if
        the boxes do not overlap.
    """
    # Compute penetration depths on each axis.
    x_push_left = (ax + aw) - bx  # push A left to separate
    x_push_right = (bx + bw) - ax  # push A right to separate
    y_push_up = (ay + ah) - by  # push A up to separate
    y_push_down = (by + bh) - ay  # push A down to separate

    # Separation on either axis means no overlap.
    if x_push_left <= 0 or x_push_right <= 0:
        return None
    if y_push_up <= 0 or y_push_down <= 0:
        return None

    # Choose the smallest displacement per axis.
    dx = -x_push_left if x_push_left < x_push_right else x_push_right
    dy = -y_push_up if y_push_up < y_push_down else y_push_down

    # Return along the axis with the smaller penetration depth.
    if abs(dx) <= abs(dy):
        return (dx, 0.0)
    return (0.0, dy)
