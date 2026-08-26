"""Save mechanisms for Area files and entity-definition files, both
refreshing the manifest afterward. Step 11 tasks 1-3 of
.github/prompts/level-editor.prompt.md.

Two separate, explicit functions -- not one generalised "guess which
directory to write based on content shape" function, per the prompt's
own instruction to keep them distinct.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# tools/build_manifest.py isn't a package module (no tools/__init__.py
# import path via `tools.build_manifest` is avoided elsewhere in this
# repo too) -- import it the same way backend/engine/hot_reload.py
# already does: add tools/ to sys.path, then a plain `import`.
_TOOLS_DIR = str(REPO_ROOT / "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import build_manifest  # noqa: E402 -- must follow the sys.path insert above

from client.engine.scene import Scene  # noqa: E402

AREA_DIR = REPO_ROOT / "frontend" / "assets" / "data" / "area"
ENTITY_DIR = REPO_ROOT / "frontend" / "assets" / "data" / "entity"
MANIFEST_PATH = REPO_ROOT / "frontend" / "assets" / "manifest.json"


def _refresh_manifest() -> None:
    """Rebuild manifest.json in-process (a plain Python import/call,
    not a subprocess or HTTP call) so a newly-saved area or entity-
    definition is immediately discoverable via the launcher (Step 3)
    without a manual rebuild step.
    """
    manifest = build_manifest.build_manifest()
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def save_area(scene: Scene, area_id: str) -> Path:
    """Write *scene* to `frontend/assets/data/area/area-<id>.json` and
    refresh the manifest. Returns the path written.
    """
    AREA_DIR.mkdir(parents=True, exist_ok=True)
    path = AREA_DIR / f"area-{area_id}.json"
    scene.save_to_area_file(path)
    _refresh_manifest()
    return path


def save_entity_definition(definition: dict, entity_definition_id: str) -> Path:
    """Write an entity-definition dict to `frontend/assets/data/entity/
    entity-<id>.json` and refresh the manifest. This is what Step 8
    task 4's shared-template edits persist through.
    """
    ENTITY_DIR.mkdir(parents=True, exist_ok=True)
    path = ENTITY_DIR / f"entity-{entity_definition_id}.json"
    path.write_text(
        json.dumps(definition, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _refresh_manifest()
    return path


def load_entity_definition(entity_definition_id: str) -> "dict | None":
    """Read an entity-definition file back off disk by id, or None if
    it doesn't exist. Used by the property panel (Step 8 task 4) to
    load the current shared-template contents before editing them.
    """
    path = ENTITY_DIR / f"entity-{entity_definition_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def area_id_from_path(path: "str | Path") -> str:
    """Extract the `<id>` from an `area-<id>.json` filename -- the
    inverse of `save_area`'s naming convention, used when Step 3's
    launcher/Step 11's "Save" needs to know an already-opened area's
    id to save back in place.
    """
    stem = Path(path).stem
    return stem[len("area-") :] if stem.startswith("area-") else stem
