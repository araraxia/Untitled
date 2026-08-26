"""`StaticCamera` -- a fixed gameplay camera; position/target/up never
change once set. The obvious case: an authored establishing shot, a
cutscene camera, a menu/character-select backdrop.

Shares the `update(delta_time)` / `apply(camera)` interface documented
in `camera_modes.py` (the single import surface for every camera mode
in this package) -- see that module's docstring for the full
convention (`FreeCamera`/`OrbitCamera` parity, `setdefault` semantics
for `up`/`fov`/`near`/`far`). Import `StaticCamera` from
`camera_modes`, not from here, unless you have a specific reason to
depend on this file directly.
"""

_UP = [0.0, 1.0, 0.0]


class StaticCamera:
    """A fixed camera -- position/target/up never change once set. The
    obvious case: an authored establishing shot, a cutscene camera, a
    menu/character-select backdrop.
    """

    def __init__(
        self, position, target, up=None, fov=None, near=None, far=None
    ):
        self.position = list(position)
        self.target = list(target)
        self.up = list(up) if up is not None else list(_UP)
        self.fov = fov
        self.near = near
        self.far = far

    def update(self, delta_time: float) -> None:
        pass  # nothing to advance -- lets callers treat every mode uniformly

    def apply(self, camera: dict) -> None:
        camera["mode"] = "3d"
        camera["position"] = list(self.position)
        camera["target"] = list(self.target)
        camera["up"] = list(self.up)
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
