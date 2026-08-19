"""Client-side interpolation for smooth rendering.

Port of frontend/js/engine/interpolation.js -- Step 13 of
.github/prompts/wgpu-py-migration.prompt.md. Smallest file in this
task (54 lines in JS); a direct numeric port, no behavior changes.

**Same engine/game boundary fix as network.py/input.py (Steps 11-12),
for the same reason**: JS's `updateInterpolation(deltaTime)` reaches
directly into the game-layer global `gameState.entities`, only
possible because every `<script>` shares one global scope. Here the
entity collection is a plain parameter instead -- simpler than the
callback-registration pattern those two modules needed, since this is
a pure "take data in, mutate it in place, return nothing" function
with no game-layer *behavior* (menu state, pause, etc.) to externalize,
just a game-layer *data structure* to stop reaching for implicitly.
The caller (whichever module owns the entity collection, e.g. a future
`client/game/` state module or `client/main.py`'s render loop) passes
its own entities dict in each frame: `update_interpolation(entities,
delta_time)`.

Entity dicts are plain Python dicts (matching JS's plain objects, and
`entity_renderer.py`'s established convention) -- `display_x`/
`display_y` are this port's snake_case translation of JS's
`displayX`/`displayY`, already anticipated and read by
`entity_renderer.py` (`entity.get('display_x', entity.get('x'))`).
"""

INTERPOLATION_SPEED = 10  # Higher = faster interpolation.


def init_entity_interpolation(entity_id, entity_data: dict) -> None:
    """Initialize display position for a new entity.

    `entity_id` is unused, mirroring the JS original's own unused
    `entityId` parameter -- kept for signature fidelity with the
    source, not because this port needs it.
    """
    if entity_data.get("x") is not None and entity_data.get("y") is not None:
        entity_data["display_x"] = entity_data["x"]
        entity_data["display_y"] = entity_data["y"]


def update_interpolation(entities: dict, delta_time: float) -> None:
    """Update interpolated positions for all entities.

    Smoothly interpolates each entity's display position toward its
    actual position. `entities` is a dict of entity_id -> entity dict
    (the Python analog of JS's `gameState.entities`), mutated in place.
    `delta_time` is seconds elapsed since the last call.
    """
    for entity in entities.values():
        if entity.get("x") is not None and entity.get("y") is not None:
            if entity.get("display_x") is None:
                entity["display_x"] = entity["x"]
                entity["display_y"] = entity["y"]

            entity["display_x"] = lerp(
                entity["display_x"], entity["x"], INTERPOLATION_SPEED * delta_time
            )
            entity["display_y"] = lerp(
                entity["display_y"], entity["y"], INTERPOLATION_SPEED * delta_time
            )


def lerp(start: float, end: float, alpha: float) -> float:
    """Linear interpolation between two values."""
    return start + (end - start) * alpha
