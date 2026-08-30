"""OrbitCamera -- drag-to-orbit, scroll-to-zoom camera for single-asset
inspection. Extracted from asset_preview.py (Step 1 of
.github/prompts/entity-builder.prompt.md) so entity_builder.py can reuse
it without a second hand-rolled copy of the same orbit math.
"""

import math


class OrbitCamera:
    """Drag to orbit, scroll to zoom -- same shape as
    run_client_test.py's own OrbitCamera (dev-tool-only, independent of
    client/engine/input.py's game input system).
    """

    # Real reported bug, fixed here rather than per-caller: these used
    # to be a fixed 20.0-2000.0 clamp with a fixed +/-0.5-per-scroll-
    # unit step, both sized for this engine's old pixel-tile-scale
    # content. entity_builder.py's camera auto-fit (per an earlier
    # report) can now start this camera at a radius well under 1.0 for
    # realistically-scaled "1 unit = 1 meter" content -- the old fixed
    # floor of 20.0 meant the very first scroll (either direction)
    # snapped the radius up to 20.0 and it could never come back down,
    # stranding the camera ~150x farther than a small model's own size
    # with no way to zoom back in. Widened generously (0.01-100000) to
    # comfortably cover both scales (and headroom beyond either) without
    # this class needing to know what "scale" the current content is.
    _MIN_RADIUS = 0.01
    _MAX_RADIUS = 100000.0
    # Multiplicative, not additive: a fixed absolute step per scroll
    # notch feels wildly inconsistent across content scales
    # (imperceptible at radius=2000, a huge relative jump at
    # radius=0.5) -- a percentage-per-notch step keeps the felt zoom
    # speed proportional to current distance at any scale. GLFW's
    # rendercanvas backend reports dy ~= +/-100 per full scroll notch
    # (rendercanvas/glfw.py: "dy": -100.0 * dy) -- this constant is
    # calibrated against that, not an arbitrary guess.
    _ZOOM_FACTOR_PER_NOTCH = 1.15

    def __init__(self, target=(0.0, 0.0, 0.0), radius: float = 200.0, invert_yaw: bool = False) -> None:
        self.yaw = 0.4
        self.pitch = 0.3
        self.radius = radius
        self.target = list(target)
        self._dragging = False
        self._last_x = 0.0
        self._last_y = 0.0
        # Per-instance, not a shared-class-wide change: a direct
        # request to flip left/right drag direction was scoped to
        # entity_builder.py's own camera only, not asset_preview.py's
        # (which also constructs this class with no args and should
        # keep its existing feel). Defaults to the original sign so
        # every existing caller is unaffected unless it opts in.
        self._yaw_sign = -1.0 if invert_yaw else 1.0

    def bind(self, canvas) -> None:
        canvas.add_event_handler(self._on_pointer_button, "pointer_down", "pointer_up")
        canvas.add_event_handler(self._on_pointer_move, "pointer_move")
        canvas.add_event_handler(self._on_wheel, "wheel")

    def _on_pointer_button(self, event: dict) -> None:
        if event.get("button") != 1:
            return
        if event["event_type"] == "pointer_down":
            self._dragging = True
            self._last_x = event["x"]
            self._last_y = event["y"]
        elif event["event_type"] == "pointer_up":
            self._dragging = False

    def _on_pointer_move(self, event: dict) -> None:
        if not self._dragging:
            return
        dx = event["x"] - self._last_x
        dy = event["y"] - self._last_y
        self._last_x = event["x"]
        self._last_y = event["y"]
        self.yaw -= dx * 0.008 * self._yaw_sign
        self.pitch = max(-1.4, min(1.4, self.pitch - dy * 0.008))

    def _on_wheel(self, event: dict) -> None:
        factor = self._ZOOM_FACTOR_PER_NOTCH ** (event["dy"] / 100.0)
        self.radius = max(self._MIN_RADIUS, min(self._MAX_RADIUS, self.radius * factor))

    def apply(self, camera: dict) -> None:
        x = self.target[0] + self.radius * math.cos(self.pitch) * math.sin(self.yaw)
        y = self.target[1] + self.radius * math.sin(self.pitch)
        z = self.target[2] + self.radius * math.cos(self.pitch) * math.cos(self.yaw)
        camera["mode"] = "3d"
        camera["position"] = [x, y, z]
        camera["target"] = list(self.target)
        camera.setdefault("up", [0, 1, 0])
        camera.setdefault("fov", math.pi / 4)
        camera.setdefault("near", 1)
        camera.setdefault("far", 2000)
