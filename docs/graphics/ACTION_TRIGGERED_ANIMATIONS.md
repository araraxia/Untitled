# Action-Triggered Animation Playback

How to make a discrete, server-authoritative action — an attack, a jump,
using an item — play a one-shot animation on the client, distinct from
the continuous state-driven `walk`/`stand` animation or a looping
transform clip (`animation_id`, [DATA_STRUCTURES.md](DATA_STRUCTURES.md)'s
"Transform Animation Clips"), and have it revert automatically once the
action's duration elapses. Step 12 of
[`.github/prompts/3d-coordinate-mapping.prompt.md`](../../.github/prompts/3d-coordinate-mapping.prompt.md).

This is the one piece of the 3D coordinate mapping work that legitimately
touches the backend: *who* is acting and *when* is a server-authoritative
fact, so how long the action visually "lasts" has to be authoritative
too, or clients desync (see `.github/copilot-instructions.md`'s
"Physics & Simulation Boundary" — this is the same principle applied to
timing rather than position).

## The pattern, end to end

1. **Backend**: an action sets `entity.state` to the action's name (e.g.
   `"attacking"`) and records when it started. Every tick, any entity
   whose `state` is a timed action and whose duration has elapsed gets
   reverted back to `"idle"`/`"moving"`. This reaches clients through the
   ordinary `state_update` delta — no new network message type.
2. **Client, sprite/billboard entities**: the animation-selection code
   (`client/engine/entity_renderer.py`'s `update_entity_animation`)
   plays whichever clip's name matches `entity.state` exactly, if one
   exists in the entity's loaded animation data — falling back to the
   ordinary `walk`/`stand` pair otherwise. **Purely data-driven**: there
   is no hardcoded action-name list anywhere in `client/engine/` — a
   clip named `"attacking"` in your game's animation data JSON is all it
   takes.
3. **Client, mesh entities**: a `parts[]` entry's `action_animations:
   {state_name: clip_id}` map (`draw_entity_mesh_parts`,
   `client/engine/entity_renderer.py`) does the same thing per part,
   layered on top of the attachment chain (Step 9) and composing with
   dangle (Step 10) — a weapon can swing while a strap on it keeps
   dangling.

Because both client paths key off `entity.state` alone, the backend
doesn't need to tell the client anything beyond the state change it was
already sending — the one-shot/revert timing lives entirely
server-side, and the client's role is just "play the clip that matches
this state, if one exists."

## Backend: the timing pattern

`backend/engine/game_loop.py`'s `GameLoop` is an abstract base with no
concrete engine-layer subclass — every real tick loop lives on a game
branch (see `ARCHITECTURE.md`'s Branch model note). Since this pattern's
backend half genuinely needs a real, running 20 TPS tick loop to
demonstrate, **`backend/engine/example_game_loop.py` is a generic,
game-agnostic reference implementation** of it — not a game, not tied to
any specific action set, verified standalone by `run_gametick_test.py`
(no game-branch dependency, no GPU/window).

```python
# backend/engine/example_game_loop.py
ACTION_DURATIONS = {"activate": 400.0}  # milliseconds

def trigger_action(entity, action_type):
    entity.state = action_type
    entity.set_data("state_started_at", time.monotonic())  # tag data bag, Entity.set_data/get_data
    entity.is_dirty = True

def revert_expired_actions(entities, action_durations=None, idle_state="idle"):
    # every tick: revert any entity whose state's duration has elapsed
    ...

class ExampleGameLoop(GameLoop):
    def _do_tick(self, tick_start):
        # drain queued actions -> trigger_action(...)
        # revert_expired_actions(self.entities)
```

Three things worth calling out:

- **`entity.set_data`/`get_data`** (this repo's tag-data-bag API on
  `Entity`, `backend/engine/ecs/entity.py`) holds the start timestamp —
  not a bespoke `Entity` field. This is exactly the kind of optional,
  action-specific data that API exists for; `Entity` itself stays
  minimal.
- **20 TPS pacing is entirely inherited**, not reimplemented —
  `GameLoop.run()` already paces ticks against `TICK_DURATION`
  (`backend/engine/config.py`, `1/20`s). Subclassing `GameLoop` and
  overriding `_do_tick()` is the whole job; no timer/sleep-loop code
  needed in `ExampleGameLoop` itself.
- **A real game does not use `ExampleGameLoop` directly.** It defines
  its own `ACTION_DURATIONS` and reversion logic in its own
  `player.py`/`actions.py`/`tick.py` (on that game's branch — see
  `legacy` for the pre-split version of this exact idea, which this
  pattern generalises), following this file's shape rather than
  importing from it. `example_game_loop.py` exists to prove the pattern
  and let it be verified/iterated on independent of any one game.

Run `python run_gametick_test.py` to see it: an entity's `state` goes
`idle` → `activate` → (400ms later) `idle` again, automatically, with the
tick count confirming genuine 20 TPS pacing.

## Client: sprite/billboard path

**File:** `client/engine/entity_renderer.py`, `update_entity_animation`.

Nothing to configure in code — this works for *any* action name, for any
game, as long as the animation data JSON defines a matching clip:

```json
{
  "activate": {
    "default_sprite_sheet": "char_a_p1_0bas_humn.png",
    "default_sprite_version": "v00",
    "duration_type": "fixed",
    "frame_width": 64,
    "frame_height": 64,
    "frame_count": 2,
    "frame_duration": 150,
    "loop": false,
    "down": { "start_frame_index": 1 },
    "up": { "start_frame_index": 9 },
    "left": { "start_frame_index": 17, "flip_x": true },
    "right": { "start_frame_index": 17, "flip_x": false }
  }
}
```

The key thing that makes this a *one-shot* rather than a third looping
state (alongside `stand`/`walk`) is `"loop": false` — `AnimationController`
holds on the clip's last frame once it finishes, rather than wrapping
back to frame 0 (`client/engine/animation.py`'s `update()`). Once the
backend reverts `entity.state` away from `"activate"`, the next
`update_entity_animation` call picks `walk`/`stand` again automatically —
no explicit "stop" message needed in either direction.

See `frontend/assets/data/example_human_animations.json`'s `"activate"`
entry for a complete, working example (reusing an existing frame range
from that file's `"push"` clip for its art, since this is a documentation
fixture, not real game content — see that file for the full note on why).

## Client: mesh path

**File:** `client/engine/entity_renderer.py`, `draw_entity_mesh_parts` /
`_sample_part_action_animation`.

A `parts[]` entry (Step 9's multi-part mesh schema) gains
`action_animations`:

```json
{
  "id": "charm",
  "mesh": "mesh-example-staff-charm",
  "animation_id": "anim-transform-charm-spin",
  "action_animations": {
    "activate": "anim-transform-charm-activate-swing"
  },
  "dangle": { "stiffness": 6.0, "damping": 0.25, "maxOffset": 6.0 }
}
```

Resolution order per part, per frame:

1. If `entity.state` matches a key in `action_animations`, sample that
   clip **as a one-shot** (its own `loop` field is ignored — action
   playback always holds its last pose rather than looping, driven by a
   clock that resets to 0 the moment `entity.state` newly enters that
   value, not a continuously-running clock).
2. Otherwise, if `animation_id` is set, sample that clip normally
   (looping per its own `loop` field, Step 11's regular behaviour).
3. Otherwise, the part's static `localOffset` (Step 9's rest transform).
4. **Step 10's dangle offset is added on top of whichever of the above
   was used**, always — an action swing, a looping spin, and a dangle
   sway all compose rather than conflict.

See `frontend/assets/data/entity/entity-example-staff.json` (the
`"charm"` part) and
`frontend/assets/data/animation/animation-transform-charm-activate-swing.json`
for a complete, working example — the charm normally spins continuously,
swings once instead whenever the entity's `state` is `"activate"`, and
falls back to spinning the instant it reverts.

## Seeing it work

```bash
python run_client_test.py
```

Every ~2 seconds, for about half a second: `billboard_mid` (a sprite
entity) plays the one-shot `"activate"` sprite clip instead of standing
still, and the staff's charm plays its one-shot swing instead of its
usual spin — both fall back automatically the instant the (locally
simulated, in this no-backend test script) state reverts. The staff also
keeps spinning and the charm keeps dangling throughout, proving Steps
9–12 all compose correctly at once, not just Step 12 in isolation.

```bash
python run_gametick_test.py
```

Verifies the backend half alone: a plain `Entity`, `ExampleGameLoop`, one
queued `"activate"` action, and the state transition timing, with no
client/rendering involvement at all.

## Building a real game's action set

None of the above is real game content — `"activate"` is a placeholder
the same way a "Hello World" string is one. A real game (on its own
branch, see `ARCHITECTURE.md`'s Branch model note) splits into a *data*
half and a *trigger* half — deliberately, not as an implementation
detail:

- **Data (editor-authorable)**: an action's name and duration, and which
  clip plays for it on a given mesh part. `.github/prompts/level-editor
  .prompt.md`'s Step 15 ("Action Definitions Panel") builds an editor UI
  for exactly this — a registry (`frontend/assets/data/actions.json`,
  the editor-authored equivalent of `ACTION_DURATIONS`) and a per-part
  `action_animations` clip assignment, both written as plain data, no
  code. Once that panel exists, defining a new action or wiring which
  animation it plays doesn't require hand-editing JSON or Python at all.
- **Trigger (real gameplay code, not editor-authorable)**: deciding
  *when* an action actually fires — the player clicked with a weapon
  equipped, an AI decided to attack — plus calling `trigger_action`-
  equivalent logic and running the per-tick revert check. This stays
  real code in a game branch's own `backend/game/entities/player.py`/
  `systems/actions.py`/`tick.py`, following `example_game_loop.py`'s
  `trigger_action`/`revert_expired_actions` shape (a pattern to copy and
  adapt, not a shared runtime dependency) — and loading `actions.json`
  instead of hardcoding a Python dict, once both pieces exist. No editor
  tool decides *when* something happens; that's gameplay logic.

The client-side mechanism in `client/engine/entity_renderer.py` needs no
changes at all to support a new action either way — it's entirely
data-driven, reading whatever `actions.json`/`action_animations`/clip
names a game (or its editor-authored data) actually defines.

## See also

- [DATA_STRUCTURES.md](DATA_STRUCTURES.md) — full JSON schema reference,
  including `action_animations` and the animation-clip `loop` field
- `.github/prompts/level-editor.prompt.md` — Step 15, the Action
  Definitions panel that authors the *data* half of a real game's action
  set (`actions.json`, per-part clip assignment) without touching
  trigger-wiring code
- `.github/prompts/3d-coordinate-mapping.prompt.md` — Step 12, the
  originating task
- `.github/copilot-instructions.md` — "Physics & Simulation Boundary,"
  why action timing must be server-authoritative
