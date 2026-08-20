# See .github/copilot-instructions.md's "Physics & Simulation Boundary"
# section -- this is client-side, purely cosmetic secondary motion
# (a dangling part swaying/lagging behind its parent). It has zero
# effect on gameplay state, never writes back into an entity's
# authoritative position/velocity, and must never be named or framed
# as "physics" (that word is reserved for backend/engine/physics.py
# and the ECS PhysicsSystem). Step 10 of
# .github/prompts/3d-coordinate-mapping.prompt.md.
"""Hand-rolled spring-damper for a mesh part that should hang and sway
slightly as its parent moves -- the client-side simulation behind "a
part that hangs and moves slightly as you move". No physics library;
matches client/engine/mat4.py's explicit, dependency-free style.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DangleParams:
    """Authored per-part dangle configuration -- one instance per
    parts[] entry's `dangle` block (docs/graphics/DATA_STRUCTURES.md).
    """

    stiffness: float = 8.0
    damping: float = 0.3
    inertia: float = 1.0
    gravity: Optional[List[float]] = None  # [x, y, z] or None (no gravity pull)
    max_offset: float = 0.2


@dataclass
class DangleState:
    """Per dangling part runtime state -- offset from rest and its
    velocity, both starting at rest. One instance per (entity id, part
    id), cached and updated once per render frame by
    entity_renderer.py's draw_entity_mesh_parts.
    """

    offset: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    velocity: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])


def update_dangle(
    state: DangleState,
    parent_delta_position: List[float],
    params: DangleParams,
    delta_time: float,
) -> None:
    """Advance one dangle spring by delta_time (seconds), in place.

    Args:
        state: Mutated in place -- offset/velocity updated to their
            new values.
        parent_delta_position: [dx, dy, dz], the dangling part's
            attachment point's world-space movement since the last
            update (this frame's world position minus last frame's).
        params: This part's authored spring configuration.
        delta_time: Seconds since the last update.
    """
    vx, vy, vz = state.velocity
    dx, dy, dz = parent_delta_position

    # Inertial kick: the child resists the parent's sudden movement,
    # which is what reads as "weight" swinging on the end of a staff.
    vx -= dx * params.inertia
    vy -= dy * params.inertia
    vz -= dz * params.inertia

    if params.gravity is not None:
        gx, gy, gz = params.gravity
        vx += gx * delta_time
        vy += gy * delta_time
        vz += gz * delta_time

    # Spring back toward rest (offset = [0, 0, 0]).
    ox, oy, oz = state.offset
    vx += -ox * params.stiffness * delta_time
    vy += -oy * params.stiffness * delta_time
    vz += -oz * params.stiffness * delta_time

    damp = 1.0 - params.damping
    vx *= damp
    vy *= damp
    vz *= damp

    ox += vx * delta_time
    oy += vy * delta_time
    oz += vz * delta_time

    # Clamp offset magnitude so a teleport/network hiccup can't fling
    # the part off-screen.
    magnitude = (ox * ox + oy * oy + oz * oz) ** 0.5
    if magnitude > params.max_offset and magnitude > 0.0:
        scale = params.max_offset / magnitude
        ox *= scale
        oy *= scale
        oz *= scale
        # A clamp is a hard energy loss, not a physical spring response
        # -- zero the velocity component along the clamped direction so
        # the part doesn't keep "pushing" against an invisible wall.
        vx = vy = vz = 0.0

    state.offset = [ox, oy, oz]
    state.velocity = [vx, vy, vz]


def dangle_params_from_dict(data: dict) -> DangleParams:
    """Parse a parts[] entry's `dangle` block into a DangleParams.
    Missing keys fall back to DangleParams' own defaults.
    """
    return DangleParams(
        stiffness=data.get("stiffness", DangleParams.stiffness),
        damping=data.get("damping", DangleParams.damping),
        inertia=data.get("inertia", DangleParams.inertia),
        gravity=data.get("gravity"),
        max_offset=data.get("maxOffset", DangleParams.max_offset),
    )
