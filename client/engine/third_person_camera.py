"""`ThirdPersonCamera` -- follows a target entity's live position,
orbiting it via mouse-driven yaw/pitch around a fixed radius.

Shares the `update(delta_time)` / `apply(camera)` interface documented
in `camera_modes.py` (the single import surface for every camera mode
in this package) -- see that module's docstring for the full
convention (`FreeCamera`/`OrbitCamera` parity, `setdefault` semantics
for `up`/`fov`/`near`/`far`). Import `ThirdPersonCamera` from
`camera_modes`, not from here, unless you have a specific reason to
depend on this file directly.
"""

import math

_UP = [0.0, 1.0, 0.0]


class ThirdPersonCamera:
    """Follows a target entity's live position; the camera itself
    orbits that target on a fixed-radius sphere driven by mouse
    movement -- the same spherical `(yaw, pitch, radius)` -> Cartesian
    math `run_client_test.py`'s `OrbitCamera` already uses, just
    recentered on `target`'s live position every frame instead of a
    point captured once at construction.

    `target` is expected to be a live reference into `Scene.entities`
    (a plain dict with at least "x"/"y"/"z" keys -- the same object
    `area_viewer.py`/`interpolation.py` already mutate in place every
    tick), NOT a snapshot copied at construction time, so this
    controller always reads wherever the entity currently is, not
    wherever it was when the camera was created.

    `look_offset` is added to the target's position to get the look-at
    point, so the camera isn't aiming at the target's feet if its
    `x/y/z` is a ground-level origin -- a placeholder tuning value,
    what's actually right depends on the target entity's own pivot/
    origin convention.

    **Mouse-look is always-on, not drag-based** (a deliberate choice,
    different from `FreeCamera`/`OrbitCamera`'s right-drag/left-drag
    convention): call `bind(canvas)` once to register the pointer-move
    handler, and separately call `renderer.set_cursor_locked(True)`
    once gameplay starts -- this class only owns the yaw/pitch math and
    the event registration, never window/cursor state, so a caller can
    lock/unlock the cursor independently (e.g. releasing it for a
    pause menu later) without this class needing to know why.
    `sensitivity`/`pitch_limits` are tuning placeholders; adjust to
    feel once this is actually running with a locked cursor.

    ------------------------------------------------------------------
    PLANNED, NOT YET BUILT (left as notes for whoever picks this up
    next):

    - **Locking to an angle behind the entity**: once entities carry a
      real 3D facing/yaw (today's `transform3d.rotation`, or a
      dedicated "facing" field), snap/lerp `self.yaw` toward the
      entity's own facing on movement, the way many third-person
      action games re-center the camera behind a moving character
      rather than leaving it wherever the last look input put it.
    - **Collision detection**: raycast from the target's position to
      the desired camera position against level geometry (`Scene.
      zones`, static meshes) and pull the camera in along that ray to
      the first hit, so it doesn't clip through walls/terrain. Needs a
      real raycast-vs-mesh/AABB primitive that doesn't exist anywhere
      in this engine yet -- `picking.py` only does screen-space entity
      picking (a 2D point against projected entity bounds), not
      world-space ray/geometry intersection.
    - **Position/look smoothing**: right now `apply()` snaps straight
      to the current yaw/pitch/radius every frame. Fine for direct
      mouse-look, but a target moving fast (once real movement speed/
      platforming exists) could still benefit from a small positional
      lag/spring -- that's exactly why `update()` already takes
      `delta_time` even though it doesn't use it yet.
    ------------------------------------------------------------------
    """

    def __init__(
        self,
        target: dict,
        yaw: float = math.pi,
        pitch: float = 0.4415,
        radius: float = 277.4,
        look_offset=(0.0, 80.0, 0.0),
        sensitivity: float = 0.0025,
        pitch_limits=(-0.2, 1.3),
        up=None,
        fov=None,
        near=None,
        far=None,
    ):
        self.target = target
        self.yaw = yaw
        self.pitch = pitch
        self.radius = radius
        self.look_offset = list(look_offset)
        self.sensitivity = sensitivity
        self.pitch_limits = pitch_limits
        self.up = list(up) if up is not None else None
        self.fov = fov
        self.near = near
        self.far = far

        # None until the first pointer_move after bind() -- skips
        # computing a (huge, wrong) delta against a position we never
        # actually observed. See _on_pointer_move.
        self._last_x = None
        self._last_y = None

    def bind(self, canvas) -> None:
        """Register the always-on mouse-look handler on *canvas*
        (`renderer.canvas`) -- via `canvas.add_event_handler(...)`,
        never a raw GLFW callback. GLFW only allows one callback per
        event type per window; `rendercanvas.glfw` already owns the
        window's raw callbacks to power this cross-backend event
        system (which `wgpu.utils.imgui.ImguiRenderer` also depends
        on) -- a second raw registration would silently break both.
        Same hard-won reason `client/engine/input.py`'s and
        `free_camera.py`'s own module docstrings document.
        """
        canvas.add_event_handler(self._on_pointer_move, "pointer_move")

    def _on_pointer_move(self, event: dict) -> None:
        if self._last_x is None:
            self._last_x = event["x"]
            self._last_y = event["y"]
            return
        dx = event["x"] - self._last_x
        dy = event["y"] - self._last_y
        self._last_x = event["x"]
        self._last_y = event["y"]

        self.yaw -= dx * self.sensitivity
        pitch_min, pitch_max = self.pitch_limits
        new_pitch = self.pitch - dy * self.sensitivity
        self.pitch = max(pitch_min, min(pitch_max, new_pitch))

    def update(self, delta_time: float) -> None:
        pass  # no smoothing/collision yet -- see class docstring

    def _target_position(self) -> list:
        return [
            self.target.get("x", 0.0),
            self.target.get("y", 0.0),
            self.target.get("z", 0.0),
        ]

    def apply(self, camera: dict) -> None:
        target_pos = self._target_position()
        cos_pitch = math.cos(self.pitch)
        offset = [
            self.radius * cos_pitch * math.sin(self.yaw),
            self.radius * math.sin(self.pitch),
            self.radius * cos_pitch * math.cos(self.yaw),
        ]

        camera["mode"] = "3d"
        camera["position"] = [target_pos[i] + offset[i] for i in range(3)]
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
