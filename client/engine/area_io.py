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


def refresh_manifest() -> None:
    """Rebuild manifest.json in-process (a plain Python import/call,
    not a subprocess or HTTP call) so a newly-saved area or entity-
    definition is immediately discoverable via the launcher (Step 3)
    without a manual rebuild step.

    Public (not `_refresh_manifest`) since entity_builder.py (Step 9 of
    .github/prompts/entity-builder.prompt.md) also needs it directly,
    for save paths (mesh/animation import, material save) that don't go
    through save_area()/save_entity_definition() below.
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
    refresh_manifest()
    return path


def normalize_entity_id(entity_definition_id: str) -> str:
    """Strip a leading `entity-` if present, so this module's own
    `entity-<id>.json` convention is idempotent regardless of which
    form the caller happens to be holding.

    Real bug this fixes: every OTHER "entity asset id" in this
    codebase (manifest keys, `asset_loader.register()` keys,
    `entity.render_template` field values -- see e.g.
    `area_viewer.py`'s `_register_dev_fixtures()` registering
    `"entity-example-crate"`, or `tools/build_manifest.py`'s
    `json_asset_id()` falling back to a JSON file's full filename stem,
    "entity-<name>", when the file has no explicit `"id"` field -- true
    of every entity-definition file in this project) is the *prefixed*
    form. `save_entity_definition()`/`load_entity_definition()` alone
    expected the *bare* form and unconditionally prepended `entity-`,
    so feeding a prefixed id back in (e.g. reopening a saved entity via
    the launcher's "Edit", or `area_viewer.py`'s property panel passing
    `entity.render_template` straight through) silently doubled the
    prefix on save (`entity-entity-<name>.json`) and, worse, made
    *load* look for a file that never existed at all -- returning None
    and silently starting from an empty `parts` list, which looks
    exactly like "my saved parts disappeared."
    """
    prefix = "entity-"
    return entity_definition_id[len(prefix) :] if entity_definition_id.startswith(prefix) else entity_definition_id


def save_entity_definition(definition: dict, entity_definition_id: str) -> Path:
    """Write an entity-definition dict to `frontend/assets/data/entity/
    entity-<id>.json` and refresh the manifest. This is what Step 8
    task 4's shared-template edits persist through.

    Also stamps the written JSON's own `"id"` field with the resolved
    `entity-<id>` value (overwriting any mismatched value already
    there) -- so a manifest rebuild reads a real, correct id instead of
    falling back to the filename stem, per `normalize_entity_id()`'s
    own docstring.

    Also defaults `"name"` to the bare id when *definition* doesn't
    already carry one -- per direct request ("make it trivial to
    rename parts, meshes or entities without it breaking relations"):
    unlike `"id"` (always derived fresh from *entity_definition_id*,
    never user-editable data), `"name"` is the caller's own freely-
    renamable display field, so an existing value is preserved as-is,
    never overwritten.
    """
    bare_id = normalize_entity_id(entity_definition_id)
    ENTITY_DIR.mkdir(parents=True, exist_ok=True)
    path = ENTITY_DIR / f"entity-{bare_id}.json"
    definition = {**definition, "id": f"entity-{bare_id}"}
    if not definition.get("name"):
        definition["name"] = bare_id
    path.write_text(
        json.dumps(definition, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    refresh_manifest()
    return path


def load_entity_definition(entity_definition_id: str) -> "dict | None":
    """Read an entity-definition file back off disk by id, or None if
    it doesn't exist. Used by the property panel (Step 8 task 4) to
    load the current shared-template contents before editing them.

    Accepts either the bare id or the `entity-<id>` prefixed form (see
    `normalize_entity_id()`) -- callers throughout this codebase hold
    either one depending on where the id came from.
    """
    bare_id = normalize_entity_id(entity_definition_id)
    path = ENTITY_DIR / f"entity-{bare_id}.json"
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


def entity_id_from_path(path: "str | Path") -> str:
    """Extract the bare `<id>` from an `entity-<id>.json` filename --
    same shape as `area_id_from_path()`, and the same normalization
    `normalize_entity_id()` applies to whatever's already been loaded
    (this one starts from a real file path instead).
    """
    stem = Path(path).stem
    return stem[len("entity-") :] if stem.startswith("entity-") else stem
