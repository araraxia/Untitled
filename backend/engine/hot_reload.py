"""File-system watcher for dev-mode hot reload of assets and shaders."""

import sys
from pathlib import Path
from typing import Any

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

# Ensure the tools directory is importable when running from the project root.
_TOOLS_DIR = str(Path(__file__).resolve().parent.parent.parent / "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

_SHADER_EXTENSIONS = {".wgsl"}
_PENDING_SUFFIX_PARTS = ("assets", "pending")


def _rebuild_manifest() -> None:
    """Re-run build_manifest and silently swallow import/runtime errors."""
    try:
        import build_manifest  # type: ignore[import]
        import json

        manifest = build_manifest.build_manifest()
        build_manifest.MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        build_manifest.MANIFEST_PATH.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:  # pragma: no cover
        print(f"[HotReload] Manifest rebuild failed: {exc}", file=sys.stderr)


def _repack_param_map(changed: Path) -> None:
    """Re-pack the param map whose source channel image changed.

    Only acts when *changed* is a ``<stem>_<channel>.png`` file inside
    ``frontend/assets/pending/``.
    """
    try:
        import build_assets  # type: ignore[import]

        cache = build_assets._load_cache()
        packed, _ = build_assets._pack_param_maps(cache)
        if packed:
            build_assets._save_cache(cache)
    except Exception as exc:  # pragma: no cover
        print(f"[HotReload] Param map repack failed: {exc}", file=sys.stderr)


class _AssetEventHandler(FileSystemEventHandler):
    """Handles file-system events under the assets directory."""

    def __init__(
        self,
        socketio: Any,
        assets_root: Path,
    ) -> None:
        super().__init__()
        self._socketio = socketio
        self._assets_root = assets_root

    def on_modified(self, event: FileSystemEvent) -> None:
        self._handle(event)

    def on_created(self, event: FileSystemEvent) -> None:
        self._handle(event)

    def _handle(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        changed = Path(str(event.src_path))

        # Re-pack param map if a pending channel image changed.
        if _PENDING_SUFFIX_PARTS[0] in changed.parts and (
            _PENDING_SUFFIX_PARTS[1] in changed.parts
        ):
            _repack_param_map(changed)

        # Always rebuild the manifest on any asset change.
        _rebuild_manifest()

        # Emit reload event with a path relative to the assets root.
        try:
            rel = changed.relative_to(self._assets_root).as_posix()
        except ValueError:
            rel = changed.name

        self._socketio.emit("asset_reload", {"path": rel})


class _ShaderEventHandler(FileSystemEventHandler):
    """Handles file-system events under the shaders directory."""

    def __init__(self, socketio: Any, shaders_root: Path) -> None:
        super().__init__()
        self._socketio = socketio
        self._shaders_root = shaders_root

    def on_modified(self, event: FileSystemEvent) -> None:
        self._handle(event)

    def on_created(self, event: FileSystemEvent) -> None:
        self._handle(event)

    def _handle(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        changed = Path(str(event.src_path))
        if changed.suffix.lower() not in _SHADER_EXTENSIONS:
            return

        try:
            rel = changed.relative_to(self._shaders_root).as_posix()
        except ValueError:
            rel = changed.name

        self._socketio.emit("shader_reload", {"path": rel})


class HotReloadWatcher:
    """Watches an assets directory (and, optionally, a shader-source
    directory) and emits SocketIO reload events.

    Args:
        socketio: The Flask-SocketIO instance.
        assets_dir: Path to ``frontend/assets/``.
        shaders_dir: Optional path to a directory of standalone shader
            source files to watch for ``.wgsl`` changes. The
            current desktop client (``client/engine/shader_cache.py``)
            has no such directory -- its WGSL lives as Python string
            literals, not files on disk -- so this is only meaningful
            if some future client reintroduces standalone shader files.
            Omit (or pass ``None``) to skip shader watching entirely.
    """

    def __init__(
        self,
        socketio: Any,
        assets_dir: str | Path,
        shaders_dir: "str | Path | None" = None,
    ) -> None:
        self._socketio = socketio
        self._assets_dir = Path(assets_dir).resolve()
        self._shaders_dir = Path(shaders_dir).resolve() if shaders_dir else None
        self._observer = Observer()

    def start(self) -> None:
        """Start the background observer thread."""
        if self._assets_dir.exists():
            self._observer.schedule(
                _AssetEventHandler(self._socketio, self._assets_dir),
                str(self._assets_dir),
                recursive=True,
            )
        if self._shaders_dir is not None and self._shaders_dir.exists():
            self._observer.schedule(
                _ShaderEventHandler(self._socketio, self._shaders_dir),
                str(self._shaders_dir),
                recursive=True,
            )
        self._observer.start()
        print("[HotReload] Watcher started.")

    def stop(self) -> None:
        """Stop the observer thread cleanly."""
        self._observer.stop()
        self._observer.join()
        print("[HotReload] Watcher stopped.")
