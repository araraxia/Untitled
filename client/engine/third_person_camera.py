"""`ThirdPersonCamera` -- follows a target entity's live position with
a fixed world-space offset.

Shares the `update(delta_time)` / `apply(camera)` interface documented
in `camera_modes.py` (the single import surface for every camera mode
in this package) -- see that module's docstring for the full
convention (`FreeCamera`/`OrbitCamera` parity, `setdefault` semantics
for `up`/`fov`/`near`/`far`). Import `ThirdPersonCamera` from
`camera_modes`, not from here, unless you have a specific reason to
depend on this file directly.
"""

_UP = [0.0, 1.0, 0.0]


class ThirdPersonCamera:
    """Follows a target entity's live position with a fixed world-space
    offset. Barebones "bind to an entity, move with it" behavior only
    -- none of the polish items below are implemented yet; they're
    left as notes for whoever picks this up next.

    `target` is expected to be a live reference into `Scene.entities`
    (a plain dict with at least "x"/"y"/"z" keys -- the same object
    `area_viewer.py`/`interpolation.py` already mutate in place every
    tick), NOT a snapshot copied at construction time, so this
    controller always reads wherever the entity currently is, not
    wherever it was when the camera was created.

    `offset` is a fixed *world-space* [x, y, z] added to the target's
    position to get the camera's position -- the default sits it
    behind and above the target along the same +Z-is-forward
    convention `FreeCamera`/`OrbitCamera` use (yaw=0 -> forward=+Z), so
    "behind" is -Z. `look_offset` is added to the target's position to
    get the look-at point, so the camera isn't staring at the target's
    feet if its `x/y/z` is a ground-level origin. Both are placeholder
    tuning values -- what's actually right depends on the target
    entity's own pivot/origin convention, so callers should tune them
    per asset rather than trust these defaults.

    ------------------------------------------------------------------
    PLANNED, NOT YET BUILT (left as notes, per request to keep this
    barebones for now):

    - **Rotation around the entity**: mouse-driven orbit (yaw/pitch),
      the same idea as `run_client_test.py`'s `OrbitCamera`, but
      recentered on `target`'s live position every frame instead of a
      fixed point captured once. `self.offset` would become a
      spherical `(yaw, pitch, radius)` triple instead of a fixed
      Cartesian vector, converted to Cartesian in `apply()` the same
      way `OrbitCamera.apply()` already does.
    - **Locking to an angle behind the entity**: once entities carry a
      real 3D facing/yaw (today's `transform3d.rotation`, or a
      dedicated "facing" field), rebuild `offset` from that yaw each
      frame instead of a world-space constant, so the camera stays
      "behind" the entity as it turns. Wants a spring/lerp on the
      camera's own yaw toward the entity's yaw (a "leash" angle) so it
      doesn't snap instantly on every turn.
    - **Collision detection**: raycast from the target's position to
      the desired camera position against level geometry (`Scene.
      zones`, static meshes) and pull the camera in along that ray to
      the first hit, so it doesn't clip through walls/terrain. Needs a
      real raycast-vs-mesh/AABB primitive that doesn't exist anywhere
      in this engine yet -- `picking.py` only does screen-space entity
      picking (a 2D point against projected entity bounds), not
      world-space ray/geometry intersection.
    - **Position/look smoothing**: right now `apply()` snaps straight
      to `target + offset` every frame. Fine for a static offset, but
      will look janky the moment the target moves fast or the offset
      itself starts moving (once orbit/angle-lock land above). A
      simple exponential lerp in `update()` toward the desired
      position/look-at, using `delta_time`, would fix that -- that's
      exactly why `update()` already takes `delta_time` even though
      the barebones version below doesn't use it yet.
    ------------------------------------------------------------------
    """

    def __init__(
        self,
        target: dict,
        offset=(0.0, 120.0, -250.0),
        look_offset=(0.0, 80.0, 0.0),
        up=None,
        fov=None,
        near=None,
        far=None,
    ):
        self.target = target
        self.offset = list(offset)
        self.look_offset = list(look_offset)
        self.up = list(up) if up is not None else None
        self.fov = fov
        self.near = near
        self.far = far

    def update(self, delta_time: float) -> None:
        pass  # no smoothing/orbit/collision yet -- see class docstring

    def _target_position(self) -> list:
        return [
            self.target.get("x", 0.0),
            self.target.get("y", 0.0),
            self.target.get("z", 0.0),
        ]

    def apply(self, camera: dict) -> None:
        target_pos = self._target_position()
        camera["mode"] = "3d"
        camera["position"] = [target_pos[i] + self.offset[i] for i in range(3)]
        camera["target"] = [
            target_pos[i] + self.look_offset[i] for i in range(3)
        ]
        if self.up is not None:
            camera["up"] = list(self.up)
        else:
            camera.setdefault("up", list(_UP))
        if self.fov is not None:
            camera["fov"] = self.fov
        else:
            camera.setdefault("fov", 0.7853981633974483)  # pi/4
        if self.near is not None:
            camera["near"] = self.near
        else:
            camera.setdefault("near", 1)
        if self.far is not None:
            camera["far"] = self.far
        else:
            camera.setdefault("far", 2000)
