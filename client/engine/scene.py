"""Scene -- the single runtime container for entities, camera,
lighting, zones, and the authored start-camera record.

Steps 3-4 of .github/prompts/area-system.prompt.md (see that file's
branch-reconciliation banner: this class has no backend/game-branch
dependency at all and is fully buildable on `engine`). Populated either
by `load_from_area_file()` (a pre-authored Area JSON) or, on a game
branch, by the live SocketIO gameplay stream (Step 5's compatibility
shim -- not implemented here, see the banner for why); modified
imperatively at runtime by any of add_entity/update_entity/remove_entity/
set_camera/set_lighting/set_start_camera/add_zone/update_zone/
remove_zone.

`client/engine/renderer.py`/`entity_renderer.py` read `scene.entities`/
`scene.camera` every frame (fog/ambient fields included -- see
`set_lighting()`'s dual-write below). `scene.lighting`, `scene.zones`,
and `scene.start_camera` are never read by the render loop; they exist
purely for authoring round-trips (`to_area_file_json()`/
`load_from_area_file()`) and editor visualization
(`.github/prompts/level-editor.prompt.md`).
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Fields `set_lighting()` mirrors from `self.lighting` onto `self.camera`
# -- the renderer only ever reads fog/ambient off the live camera object
# it already has a reference to each frame (client/engine/entity_renderer
# .py), never off `Scene.lighting` directly. See set_lighting()'s
# docstring for why this dual-write exists at all.
_LIGHTING_CAMERA_KEYS = ("ambientColor", "fogColor", "fogNear", "fogFar")

# Default camera before anything is loaded/authored -- 2D mode, matching
# "2D fields today" being the pre-3D-coordinate-mapping default per
# renderer.py's get_view_projection_matrix() (returns None, i.e. "use
# the existing 2D path," whenever camera.mode != '3d').
_DEFAULT_CAMERA = {"mode": "2d", "x": 0.0, "y": 0.0, "zoom": 1.0}


class Scene:
    """The one runtime container both the network path (a game branch's
    Step 5 shim) and the file-load path (`load_from_area_file`)
    populate, and the one object builder/test/cutscene code writes into
    via the API below. No rendering logic lives here -- see module
    docstring.
    """

    def __init__(self) -> None:
        self.entities: dict[str, dict] = {}
        # entity_id -> 'authoritative' | 'local'. Purely in-memory
        # bookkeeping -- never sent to or read from any file/network
        # payload. Kept as a side dict (not a key inside each entity's
        # own data) so a stored entity's dict is exactly what a file/
        # network payload would contain, no stripping needed anywhere.
        self._entity_source: dict[str, str] = {}

        self.camera: dict = dict(_DEFAULT_CAMERA)
        self.lighting: dict = {}
        self.start_camera: Optional[dict] = None
        self.zones: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Entities
    # ------------------------------------------------------------------

    def add_entity(self, entity_id: str, data: dict, source: str = "local") -> bool:
        """Add or fully replace an entity record.

        If *entity_id* already exists tagged with a *different* source,
        the write is refused (a loud warning, never a silent pick) --
        an entity added directly through this API (builder placement,
        test script, cutscene dressing) must never silently overwrite
        or be overwritten by a networked/file-loaded one and vice
        versa. A same-source re-add (e.g. a second network update for
        the same id) proceeds normally.

        Returns:
            True if the write proceeded, False if refused.
        """
        existing_source = self._entity_source.get(entity_id)
        if existing_source is not None and existing_source != source:
            logger.warning(
                "Scene.add_entity: refusing to overwrite entity %r "
                "(existing source=%r, new source=%r)",
                entity_id,
                existing_source,
                source,
            )
            return False

        self.entities[entity_id] = data
        self._entity_source[entity_id] = source
        return True

    def update_entity(self, entity_id: str, patch: dict) -> None:
        """Merge *patch* onto an existing entity's data. No-op with a
        warning if *entity_id* isn't present -- mirrors the defensive
        style the JS `handleStateUpdate()` this replaces already used.
        """
        if entity_id not in self.entities:
            logger.warning("Scene.update_entity: unknown entity %r, ignoring", entity_id)
            return
        self.entities[entity_id].update(patch)

    def remove_entity(self, entity_id: str) -> None:
        self.entities.pop(entity_id, None)
        self._entity_source.pop(entity_id, None)

    def entity_source(self, entity_id: str) -> Optional[str]:
        """Return 'authoritative'/'local' for *entity_id*, or None if
        not present. Read-only helper for editor/builder UI (Step 7's
        entity list panel shows this per row).
        """
        return self._entity_source.get(entity_id)

    # ------------------------------------------------------------------
    # Camera / lighting
    # ------------------------------------------------------------------

    def set_camera(self, camera_data: dict) -> None:
        """Merge onto the live camera view. Called every frame by
        follow/free-fly logic -- not an authoring action. Never touches
        `start_camera`; see `set_start_camera()`.
        """
        self.camera.update(camera_data)

    def set_lighting(self, lighting_data: dict) -> None:
        """Merge onto `self.lighting` (the authored-shape record, for
        round-tripping) **and** onto `self.camera` (only the fog/
        ambient keys) -- the renderer never reads `Scene.lighting`
        directly, so without this second write the Area file's
        `lighting` block would be authored data with nothing consuming
        it, the same class of bug `ambientColor` had in
        `3d-coordinate-mapping.prompt.md` before it was fixed there.
        """
        self.lighting.update(lighting_data)
        for key in _LIGHTING_CAMERA_KEYS:
            if key in lighting_data:
                self.camera[key] = lighting_data[key]

    def set_start_camera(self, camera_data: dict) -> None:
        """Merge onto the *authored* starting camera, decoupled from
        the live `camera`'s constant movement (free-fly, follow). An
        explicit, deliberate authoring action -- per
        `area-system.prompt.md`'s Constraints, only `load_from_area_file`
        and (once it exists) `level-editor.prompt.md`'s "Set Start
        Camera" action may call this; no per-frame camera-movement code
        may.
        """
        if self.start_camera is None:
            self.start_camera = {}
        self.start_camera.update(camera_data)

    # ------------------------------------------------------------------
    # Zones -- storage/round-trip only, no containment logic here. See
    # .github/prompts/zones.prompt.md for Zone/ZoneRegistry (backend-
    # only; Scene never simulates zone containment, only stores and
    # round-trips the authored definitions for editor visualization).
    # ------------------------------------------------------------------

    def add_zone(self, zone_id: str, data: dict) -> None:
        self.zones[zone_id] = data

    def update_zone(self, zone_id: str, patch: dict) -> None:
        if zone_id not in self.zones:
            logger.warning("Scene.update_zone: unknown zone %r, ignoring", zone_id)
            return
        self.zones[zone_id].update(patch)

    def remove_zone(self, zone_id: str) -> None:
        self.zones.pop(zone_id, None)

    # ------------------------------------------------------------------
    # File load/save (Step 4)
    # ------------------------------------------------------------------

    @classmethod
    def load_from_area_file(cls, path: "str | Path") -> "Scene":
        """Read an Area JSON file directly off disk (`open()`/
        `json.load` -- per this task's direct-filesystem-access
        constraint, no HTTP/manifest involvement) and construct a
        populated `Scene`. No network connection is opened or required.
        """
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        scene = cls()

        for entity_id, entity_data in (data.get("entities") or {}).items():
            scene.add_entity(entity_id, entity_data, "authoritative")

        camera = data.get("camera")
        if camera:
            # Both: the loaded scene should visibly start there *and*
            # remember it as the authored spawn point.
            scene.set_camera(camera)
            scene.set_start_camera(camera)

        lighting = data.get("lighting")
        if lighting:
            scene.set_lighting(lighting)

        for zone_id, zone_data in (data.get("zones") or {}).items():
            scene.add_zone(zone_id, zone_data)

        return scene

    def to_area_file_json(self) -> dict:
        """Serialize this Scene back into the Area file shape
        `Area.to_dict()` produces on the backend, so a file saved here
        is loadable by `Area.from_dict()` unmodified once that exists.

        Every entity is included regardless of `_source` -- what a
        builder places is real content once saved; the source tag is a
        purely in-memory runtime concept and is dropped (not written)
        here. `camera` is `start_camera` if one has been explicitly
        authored, falling back to the live `camera`'s current value
        only for a scene that was never given one -- this is what keeps
        free-fly movement during editing from silently changing the
        saved spawn point.
        """
        camera_out = self.start_camera if self.start_camera is not None else dict(self.camera)
        return {
            "entities": {eid: dict(data) for eid, data in self.entities.items()},
            "camera": camera_out,
            "lighting": dict(self.lighting) if self.lighting else None,
            "zones": {zid: dict(data) for zid, data in self.zones.items()},
        }

    def save_to_area_file(self, path: "str | Path") -> None:
        """Write `to_area_file_json()` directly to *path* via `open()`
        -- no Blob/download dance, no backend route (per this task's
        direct-filesystem-access constraint; a native app can just
        write the file).
        """
        Path(path).write_text(
            json.dumps(self.to_area_file_json(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
