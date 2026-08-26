"""WASD + mouse-look free-fly camera for the standalone Area/Scene
viewer -- Step 6 task 4 of .github/prompts/area-system.prompt.md.

Deliberately independent of client/engine/input.py's game input system
(no input_config.json involvement, no network.send_player_action calls)
-- free-fly is a dev-tool-only concern, the exact same reasoning
run_client_test.py's OrbitCamera already documents for itself.

Bound via `canvas.add_event_handler(...)`, never a raw
`glfw.set_key_callback`/`glfw.set_cursor_pos_callback` -- see
client/engine/input.py's module docstring for the confirmed, hard-won
reason: `rendercanvas.glfw` already owns the window's raw GLFW callbacks
to power its own cross-backend event system (which
`wgpu.utils.imgui.ImguiRenderer` also depends on), and GLFW only allows
one callback per event type per window -- a second raw registration
would silently break rendercanvas's (and therefore imgui's) event
handling, exactly the bug input.py's docstring documents finding once
already.

Also re-exported from `camera_modes.py`, this package's single import
surface for every camera mode (`FreeCamera` included, despite it being
a dev-tool -- see that module's own docstring for why) -- import
`FreeCamera` from there, not from here, unless you have a specific
reason to depend on this file directly.
"""

import math

# rendercanvas pointer-event button numbering (see input.py's module
# docstring: MOUSE_BUTTON_1(left)->1, MOUSE_BUTTON_2(right)->2,
# MOUSE_BUTTON_3(middle)->3) -- right-drag to look around, so plain
# mouse movement (no button held) never fights imgui panel interaction.
_RIGHT_BUTTON = 2

_UP = [0.0, 1.0, 0.0]


class FreeCamera:
    """WASD (+ Q/E for down/up) to move, right-mouse-drag to look
    around. Call `bind(canvas)` once, `update(delta_time)` once per
    frame before `apply(camera)`.
    """

    def __init__(self, position=None, yaw: float = 0.0, pitch: float = 0.0, speed: float = 200.0):
        self.position = list(position) if position else [0.0, 100.0, 300.0]
        self.yaw = yaw
        self.pitch = pitch
        self.speed = speed

        self._looking = False
        self._last_x = 0.0
        self._last_y = 0.0
        self._keys_down: set[str] = set()

    @staticmethod
    def _yaw_pitch_toward(position, target) -> tuple:
        dx = target[0] - position[0]
        dy = target[1] - position[1]
        dz = target[2] - position[2]
        yaw = math.atan2(dx, dz)
        horizontal = math.sqrt(dx * dx + dz * dz)
        pitch = math.atan2(dy, horizontal) if horizontal > 1e-6 else 0.0
        return yaw, pitch

    @classmethod
    def from_look_at(cls, position, target, speed: float = 200.0) -> "FreeCamera":
        """Build a FreeCamera whose initial yaw/pitch look from
        *position* toward *target* -- used to seed free-fly from a
        loaded Area file's authored `start_camera` (or live `camera`)
        instead of always resetting to this module's own defaults,
        which would silently discard the authored viewpoint the
        instant the viewer opens.
        """
        yaw, pitch = cls._yaw_pitch_toward(position, target)
        return cls(position=position, yaw=yaw, pitch=pitch, speed=speed)

    def look_at(self, target) -> None:
        """Reorient (yaw/pitch only, position unchanged) to look at
        *target* from wherever the camera currently is -- Step 12's `F`
        "focus on the selected entity" shortcut. Same math as
        `from_look_at`, applied to an existing instance instead of
        constructing a new one.
        """
        self.yaw, self.pitch = self._yaw_pitch_toward(self.position, target)

    def bind(self, canvas) -> None:
        """Register this camera's handlers on *canvas* (renderer.canvas)
        -- see module docstring for why this, not a raw GLFW callback.
        """
        canvas.add_event_handler(self._on_key, "key_down", "key_up")
        canvas.add_event_handler(self._on_pointer_button, "pointer_down", "pointer_up")
        canvas.add_event_handler(self._on_pointer_move, "pointer_move")

    def _on_key(self, event: dict) -> None:
        key = event["key"].lower()
        if event["event_type"] == "key_down":
            self._keys_down.add(key)
        elif event["event_type"] == "key_up":
            self._keys_down.discard(key)

    def _on_pointer_button(self, event: dict) -> None:
        if event.get("button") != _RIGHT_BUTTON:
            return
        if event["event_type"] == "pointer_down":
            self._looking = True
            self._last_x = event["x"]
            self._last_y = event["y"]
        elif event["event_type"] == "pointer_up":
            self._looking = False

    def _on_pointer_move(self, event: dict) -> None:
        if not self._looking:
            return
        dx = event["x"] - self._last_x
        dy = event["y"] - self._last_y
        self._last_x = event["x"]
        self._last_y = event["y"]
        self.yaw -= dx * 0.005
        self.pitch = max(-1.5, min(1.5, self.pitch - dy * 0.005))

    def _forward(self) -> list:
        return [
            math.cos(self.pitch) * math.sin(self.yaw),
            math.sin(self.pitch),
            math.cos(self.pitch) * math.cos(self.yaw),
        ]

    def _right(self) -> list:
        # Real bug, found via a live user report (A/D panned backwards)
        # and confirmed against picking.py's camera_basis() (the actual
        # ground truth for screen-space "right," used by every
        # gizmo/picking calculation): this previously returned
        # cross(up, forward) instead of cross(forward, up) -- the exact
        # opposite direction. `cross(forward_flat, up)` with
        # forward_flat = [sin(yaw), 0, cos(yaw)] works out to
        # [-cos(yaw), 0, sin(yaw)] -- verified to match camera_basis()'s
        # right vector exactly at yaw=0 (both give (-1, 0, 0)). Yaw-only
        # (no-roll), same flat-ground-plane assumption
        # run_client_test.py's OrbitCamera already makes.
        return [-math.cos(self.yaw), 0.0, math.sin(self.yaw)]

    def update(self, delta_time: float) -> None:
        """Advance `position` from currently-held keys. Call once per
        frame, before `apply()`.
        """
        if not self._keys_down:
            return

        forward = self._forward()
        right = self._right()
        move = self.speed * delta_time

        if "w" in self._keys_down:
            self.position[0] += forward[0] * move
            self.position[1] += forward[1] * move
            self.position[2] += forward[2] * move
        if "s" in self._keys_down:
            self.position[0] -= forward[0] * move
            self.position[1] -= forward[1] * move
            self.position[2] -= forward[2] * move
        if "a" in self._keys_down:
            self.position[0] -= right[0] * move
            self.position[2] -= right[2] * move
        if "d" in self._keys_down:
            self.position[0] += right[0] * move
            self.position[2] += right[2] * move
        if "q" in self._keys_down:
            self.position[1] -= move
        if "e" in self._keys_down:
            self.position[1] += move

    def apply(self, camera: dict) -> None:
        """Write this camera's current state into *camera* (typically
        `scene.camera`, via `scene.set_camera(fc_camera_dict)` or a
        direct merge) -- called once per frame from the render loop,
        the same pattern run_client_test.py's OrbitCamera.apply() uses.
        Defaults fov/near/far/up only if not already present, so an
        Area file's authored camera values (once loaded) aren't
        clobbered by this dev tool's own defaults.
        """
        forward = self._forward()
        camera["mode"] = "3d"
        camera["position"] = list(self.position)
        camera["target"] = [
            self.position[0] + forward[0],
            self.position[1] + forward[1],
            self.position[2] + forward[2],
        ]
        camera.setdefault("up", list(_UP))
        camera.setdefault("fov", math.pi / 4)
        camera.setdefault("near", 1)
        camera.setdefault("far", 2000)
