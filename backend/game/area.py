"""Area -- Milestone 1's minimal per-tick game world container.

Deliberately thin: one hardcoded player `Entity`, no save/load, no
`PlayerCharacter`/party-controller layer. Driven from `GameTick._do_tick()`
via a plain `update(delta_time)` call, never through the ECS `World`/
`SystemScheduler` pipeline -- confirmed (via `grep -rn "ecs_world" backend/`
and `grep -rn "World()" backend/`) that nothing in this codebase ever
populates a live `World`, so a registered `System` would compile, look
correct, and never actually run against real data. `GroupRegistry`/
`ZoneRegistry` (both real, working engine-layer code) are already built
around exactly this "driven by a plain per-tick call" pattern instead --
this class follows the same precedent, not the dead one.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from backend.engine.config import load_engine_config
from backend.engine.ecs.entity import Entity
from backend.engine.group import GroupRegistry
from backend.engine.spatial import SpatialGrid
from backend.engine.zone import ZoneRegistry, apply_zone_effect

PLAYER_ENTITY_ID = "player_1"
MOVE_SPEED = 200.0  # world units/sec -- placeholder until real art/scale


class Area:
    """One hardcoded milestone-1 area: a single player entity, no
    terrain, no zones authored yet.

    `spatial_grid` is constructed but deliberately NOT wired into
    `update()` yet: `SpatialGrid._get_cell()` hardcodes `entity.x`/
    `entity.y` -- i.e. it indexes the X/Y plane -- but this game's
    ground plane is X/Z (Y-up, confirmed by `FreeCamera`/
    `ThirdPersonCamera`/`mat4.py`'s shared convention), and entity.y
    stays near 0 for every ground-walking entity. Nothing in this
    milestone actually queries the grid (no AI, no proximity checks),
    so wiring it in now would just build a silently-broken index. Fix
    properly (an explicit coordinate accessor, or a shadow (x, z)
    pair) whenever the first real spatial query is actually added --
    not before, per this repo's own "don't build unverified
    infrastructure" precedent (`zone.py`'s own docstring makes exactly
    this argument about the ecs_world gap).
    """

    def __init__(self) -> None:
        self.area_id = "area-milestone1"
        self.entities: Dict[str, Entity] = {}
        self.groups = GroupRegistry()
        self.zones = ZoneRegistry()  # unused for now -- see class docstring
        cfg = load_engine_config()
        self.spatial_grid = SpatialGrid(
            cfg.world_width, cfg.world_height, cfg.grid_cell_size
        )
        self.dirty_entities: set[str] = set()
        self.removed_entities: set[str] = set()
        self.player_entity_id: Optional[str] = None

    def add_entity(self, entity: Entity) -> None:
        self.entities[entity.entity_id] = entity
        self.dirty_entities.add(entity.entity_id)

    def process_player_action(self, action: Dict[str, Any]) -> None:
        """Handle one `player_action` payload -- the exact shape
        `client/engine/input.py`'s `process_gameplay_input_area_relative()`/
        `process_gameplay_input_camera_relative()` both send (movement
        *style* is purely a client-side concern; by the time `direction`
        reaches here it's already in this server's one expected
        convention regardless of which style produced it):
        `{"type": "move", "direction": {"x", "y"}, "facing"}`
        (`facing` omitted entirely on the idle/zero-vector send, so it
        must never be clobbered to a default in that case).
        """
        if action.get("type") != "move":
            return
        entity = self.entities.get(self.player_entity_id)
        if entity is None:
            return

        direction = action.get("direction", {})
        # XZ mapping, corrected against a real hands-on test (both axes
        # were inverted -- W moved backward, D moved left): confirmed
        # convention is yaw=0 -> forward=+Z, right=-X (right = cross
        # (forward, up) = cross((0,0,1), (0,1,0)) = (-1,0,0) -- the same
        # math ThirdPersonCamera/audio.py's _spatial_gains already use).
        # input.py's "right" action sends direction.x=+1 and "up" sends
        # direction.y=-1 -- both need negating to land on world -X
        # (screen-right) and world +Z (forward) respectively.
        entity.vx = -direction.get("x", 0) * MOVE_SPEED
        entity.vz = -direction.get("y", 0) * MOVE_SPEED

        if "facing" in action:
            entity.facing = action["facing"]
        moving = entity.vx != 0 or entity.vz != 0
        entity.state = "moving" if moving else "idle"
        entity.is_dirty = True
        self.dirty_entities.add(entity.entity_id)

    def update(self, delta_time: float) -> None:
        for entity in self.entities.values():
            entity.update(delta_time)
            if entity.is_dirty:
                self.dirty_entities.add(entity.entity_id)
                entity.is_dirty = False

        def dispatch_effects(zone, entity_id: str, effects: list) -> None:
            for effect in effects:
                apply_zone_effect(
                    self.entities, entity_id, effect, self.groups, zone=zone
                )

        self.zones.update(self.entities, dispatch_effects)

    def get_state_delta(self) -> Dict[str, Any]:
        """Build (and clear) this tick's dirty-entity/removed-entity
        delta -- mirrors `legacy`'s `Area.get_state_delta()` shape.
        Clearing here, not in the caller, keeps "cleared after
        broadcast" (Entity's own dirty-flag contract) a one-step
        operation.
        """
        delta: Dict[str, Any] = {}
        if self.dirty_entities:
            delta["entities"] = {
                eid: self.entities[eid].serialize()
                for eid in self.dirty_entities
                if eid in self.entities
            }
        if self.removed_entities:
            delta["removed"] = list(self.removed_entities)
        self.dirty_entities.clear()
        self.removed_entities.clear()
        return delta


def create_milestone1_area() -> Area:
    """Factory for the one hardcoded area+player this milestone needs
    -- no Area-JSON loading yet (see module docstring). Player spawns
    at the origin with a placeholder `render_template` borrowed from
    the existing dev-fixture meshes (`area_viewer.py`'s
    `_register_dev_fixtures()`), since no real character art exists.
    """
    area = Area()
    player = Entity(
        entity_id=PLAYER_ENTITY_ID,
        x=0.0,
        y=0.0,
        z=0.0,
        state="idle",
        facing="down",
        # Real bug found via a blank live-run screenshot, not assumed:
        # EntityRenderer.draw_entity() silently no-ops every entity
        # until its animation data finishes loading, and the client's
        # DEFAULT_ANIMATION_DATA_PATHS ("assets/data/
        # human_animations.json") doesn't exist anywhere in this repo
        # -- so any entity that doesn't supply its own path never
        # renders at all, forever, with zero error. This mesh entity
        # has no real animations either, but still needs *a* loadable
        # file to clear that gate -- reusing run_client_test.py's own
        # exact fixture for its (also-unanimated) crate entities.
        animation_data_paths=["assets/data/example_human_animations.json"],
    )
    player.render_template = "entity-example-crate"
    area.add_entity(player)
    area.player_entity_id = PLAYER_ENTITY_ID
    return area
