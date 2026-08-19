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
# this port. "areas" (level-editor.prompt.md's Python-targeted Step 2)
# is not in this list yet because that step hasn't landed; add it there
# when it does, not here speculatively.
MANIFEST_CATEGORIES = ["images", "animations", "materials", "meshes", "entities", "audio"]


class AssetLoader:
    def __init__(self):
        self._registry: dict[str, str] = {}

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
            for asset_id, entry in entries.items():
                if asset_id in self._registry:
                    continue
                if isinstance(entry, dict) and isinstance(entry.get("path"), str):
                    self.register(asset_id, entry["path"])
                    registered += 1


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
