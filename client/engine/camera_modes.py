"""Single import surface for this package's camera modes -- each mode
lives in its own file (`free_camera.py`, `static_camera.py`,
`third_person_camera.py`); this module just collects and re-exports
them so a caller writes `from client.engine.camera_modes import
FreeCamera, StaticCamera, ThirdPersonCamera` without needing to know
(or care) which file actually defines which class. Add a new mode by
giving it its own file and re-exporting it here, the same way.

`FreeCamera` is the odd one out of the three -- see `free_camera.py`'s
own docstring: it's explicitly a dev-tool-only fly-cam for the Area
viewer/editor, never meant to ship in a game, whereas `StaticCamera`/
`ThirdPersonCamera` are meant for actual gameplay use on a game
branch (a fixed establishing/menu-backdrop shot, and a camera that
follows a moving entity). It's collected here anyway because all three
share the same interface below, so a caller juggling "which camera
mode is active right now" has one place to import any of them from.

Every mode shares the same lightweight interface -- call
`update(delta_time)` once per frame, then `apply(camera)` -- so a
render loop can hold any of these interchangeably behind one variable
without branching on type. `apply(camera)` writes directly into the
given camera dict (typically `scene.camera`): `mode`/`position`/
`target` are always overwritten; `up`/`fov`/`near`/`far` fall back to
`setdefault` when not explicitly given to the constructor (`FreeCamera`
never takes those at all, so they're always defaulted for it), so an
Area file's authored values survive instead of being silently
clobbered.
"""

from client.engine.free_camera import FreeCamera
from client.engine.static_camera import StaticCamera
from client.engine.third_person_camera import ThirdPersonCamera

__all__ = ["FreeCamera", "StaticCamera", "ThirdPersonCamera"]
