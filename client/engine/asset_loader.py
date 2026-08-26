"""AssetLoader -- maps short asset keys to file paths on disk.

Port of frontend/js/engine/assetLoader.js -- Step 10 of
.github/prompts/wgpu-py-migration.prompt.md, **ported ahead of Step 9**
(entity_renderer.py): re-reading entityRenderer.js fresh (per that
step's own instruction) surfaced that it calls `assetLoader.resolve()`
directly in `_resolveRenderTemplate`/`drawEntityMesh`, matching the
actual JS `<script>` load order in index.html (assetLoader.js loads
before entityRenderer.js) -- this porting task's own Step 1 audit note
had that dependency backwards ("entityRenderer -> assetLoader"). This
file's docstring is the correction; entity_renderer.py (still Step 9)
is written against this module, not the other way around.

Material JSON, entity JSON, and other data files reference assets by a
plain string key (e.g. 'lantern_atlas') rather than a raw file path. At
runtime AssetLoader resolves those keys to file paths this client reads
directly off disk (json.load()/PIL, not fetch()) -- per this port's
established direct-filesystem-access convention.

Usage:
    asset_loader.register('lantern_atlas', 'assets/images/sprites/objects/lantern_atlas.png')
    path = asset_loader.resolve('lantern_atlas')
    # -> 'assets/images/sprites/objects/lantern_atlas.png'

A single shared instance is exported as the module-level `asset_loader`
for use by material_loader.py, entity_renderer.py, and other engine
modules -- the Python analog of the JS version's `window.assetLoader`
global.

Deliberate adaptation: `load_manifest()` is synchronous (reads
manifest.json directly off disk), so there is no Python equivalent of
the JS version's `assetLoader.manifestReady` promise property callers
had to `await`. Instead, `load_manifest()` must simply be called (and
have returned) before resolving any manifest-only key -- a plain
ordering requirement, not something to synchronize on. Also, unlike the
JS version's module-level `assetLoader.manifestReady =
assetLoader.loadManifest(...)` (which fires disk I/O immediately on
script load), this module does NOT call load_manifest() automatically
on import -- only the built-in example registrations happen at import
time (matching `assetLoader.registerAll({...})`). Triggering real file
I/O as a side effect of a bare `import` is not idiomatic Python;
whatever bootstraps the client (main.py, Step 15) calls
`asset_loader.load_manifest()` explicitly during startup instead.
"""

import json
from pathlib import Path
from typing import Optional

# client/engine/asset_loader.py -> client/engine -> client -> repo root
# -> frontend. Matches material_loader.py's/mesh.py's FRONTEND_DIR.
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

# Manifest categories currently scanned by tools/build_manifest.py and
# read here -- matches assetLoader.js's categories list exactly as of
# this port, plus "fonts"/"ui_skins" (client/engine/ui/theme.py, this
# session's custom-drawn UI framework), "areas" (level-editor.prompt.md
# Step 2 -- lets the launcher list Area files the same way it already
# lists meshes/entities, no filesystem scanning of its own), and
# "ui_menus" (level-editor.prompt.md Step 14 -- the UI-menu editor's
# saved menu-<id>.json files).
MANIFEST_CATEGORIES = [
    "images",
    "animations",
    "materials",
    "meshes",
    "entities",
    "areas",
    "ui_menus",
    "audio",
    "fonts",
    "ui_skins",
]


class AssetLoader:
    def __init__(self):
        self._registry: dict[str, str] = {}
        # category -> {asset_id: path}, populated only by load_manifest()
        # (register()/register_all() have no category, by design -- a
        # dev-test fixture registered directly, like
        # area_viewer.py's _register_dev_fixtures(), is deliberately
        # resolvable but not browsable). Lets category-grouped UI
        # (level-editor.prompt.md's asset browser/launcher) list "every
        # mesh" without re-parsing manifest.json itself.
        self._by_category: dict[str, dict[str, str]] = {}
        # category -> {asset_id: full manifest entry dict}, populated
        # alongside _by_category by load_manifest() -- audio.prompt.md
        # Step 3's playback engine needs an audio entry's "type"/"loop"/
        # "loop_start_s"/"loop_end_s" fields, which resolve()/
        # list_category() (path-only, by design) don't expose. Same
        # "found a real gap, added a narrowly-scoped method" precedent
        # list_category() itself was added under (see ROADMAP.md's
        # Phase 14 row).
        self._entries: dict[str, dict[str, dict]] = {}

    def register(self, key: str, path: str) -> None:
        """Register an asset key with its path. Re-registering the same
        key overwrites the previous entry.

        Args:
            key: Short identifier (e.g. 'lantern_atlas').
            path: Path relative to FRONTEND_DIR (e.g.
                'assets/images/sprites/objects/lantern_atlas.png').
        """
        self._registry[key] = path

    def register_all(self, mapping: dict) -> None:
        """Register multiple assets at once from a plain dict of
        {key: path} entries.
        """
        self._registry.update(mapping)

    def resolve(self, key: str) -> str:
        """Resolve an asset key to its registered path.

        If the value already looks like a path (contains '/' or starts
        with 'http') it is returned unchanged -- this preserves
        backward compatibility with material/entity JSON that embeds
        raw paths instead of a registered key.

        Raises:
            ValueError: If key is empty, or not registered and doesn't
                look like a raw path.
        """
        if not key:
            raise ValueError("[asset_loader] resolve() called with empty key")

        if "/" in key or key.startswith("http"):
            return key

        path = self._registry.get(key)
        if path is None:
            raise ValueError(f'[asset_loader] Unknown asset key: "{key}"')
        return path

    def has(self, key: str) -> bool:
        """Return True if key is registered."""
        return key in self._registry

    def unregister(self, key: str) -> None:
        """Remove a single key from the registry."""
        self._registry.pop(key, None)

    def load_manifest(self, manifest_path: "str | None" = None) -> None:
        """Read the asset manifest JSON and register all entries.
        Entries already registered via register_all() are NOT
        overwritten.

        Args:
            manifest_path: Path relative to FRONTEND_DIR. Defaults to
                'assets/manifest.json', matching the JS version's
                default manifest URL.
        """
        rel_path = manifest_path or "assets/manifest.json"
        full_path = FRONTEND_DIR / rel_path
        if not full_path.exists():
            return

        try:
            manifest = json.loads(full_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        registered = 0
        for category in MANIFEST_CATEGORIES:
            entries = manifest.get(category)
            if not isinstance(entries, dict):
                continue
            category_map = self._by_category.setdefault(category, {})
            entry_map = self._entries.setdefault(category, {})
            for asset_id, entry in entries.items():
                if isinstance(entry, dict) and isinstance(entry.get("path"), str):
                    category_map[asset_id] = entry["path"]
                    entry_map[asset_id] = entry
                if asset_id in self._registry:
                    continue
                if isinstance(entry, dict) and isinstance(entry.get("path"), str):
                    self.register(asset_id, entry["path"])
                    registered += 1

    def list_category(self, category: str) -> dict[str, str]:
        """Return `{asset_id: path}` for every manifest entry under
        *category* (e.g. `"meshes"`, `"entities"`, `"areas"`) --
        populated only by `load_manifest()`. Empty dict if the
        manifest hasn't been loaded yet or the category has no
        entries.
        """
        return dict(self._by_category.get(category, {}))

    def get_entry(self, category: str, asset_id: str) -> "dict | None":
        """Return the full manifest entry dict for *asset_id* under
        *category* -- e.g. an audio entry's "type"/"loop"/
        "loop_start_s"/"loop_end_s" fields, which resolve()/
        list_category() don't expose (path-only, by design). None if
        the manifest hasn't been loaded yet or has no such entry.
        """
        return self._entries.get(category, {}).get(asset_id)


# ----------------------------------------------------------------------
# Shared instance + built-in asset registrations
# ----------------------------------------------------------------------

# Global AssetLoader instance. All engine modules that need asset
# resolution import this reference.
asset_loader = AssetLoader()

# Example / lantern assets -- placeholders until real atlases are added.
asset_loader.register_all(
    {
        # Lantern
        "lantern_atlas": "assets/images/sprites/objects/lantern_atlas.png",
        "lantern_params": "assets/images/param_maps/lantern_params.png",
        "glow_pulse_atlas": "assets/images/effects/glow/lantern_glow.png",
        # Human / player
        "human_atlas": "assets/images/sprites/human/human_atlas.png",
        "human_params": "assets/images/param_maps/human_params.png",
        # Colour ramp LUTs
        "fire_ramp": "assets/images/color_ramps/fire_ramp.png",
        "ice_ramp": "assets/images/color_ramps/ice_ramp.png",
        "poison_ramp": "assets/images/color_ramps/poison_ramp.png",
    }
)
