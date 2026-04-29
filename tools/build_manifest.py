"""Auto-generate frontend/assets/manifest.json from the assets directory."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Paths are relative to the project root (where this script is run from).
FRONTEND_DIR = Path("frontend")
ASSETS_DIR = FRONTEND_DIR / "assets"
MANIFEST_PATH = ASSETS_DIR / "manifest.json"
MANIFEST_VERSION = 1

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
AUDIO_EXTENSIONS = {".mp3", ".ogg", ".wav"}
JSON_EXTENSIONS = {".json"}


def file_hash(path: Path) -> str:
    """Return the first 16 hex chars of the SHA-256 hash of a file."""
    sha = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()[:16]


def image_type(rel_path: Path) -> str:
    """Classify an image asset type from its server-relative path.

    Classification is based on the subdirectory under ``assets/images/``:
    ``param_maps`` → ``param_map``, ``color_ramps`` → ``color_ramp``,
    ``effects`` → ``effect``, ``ui`` → ``ui``, anything else → ``atlas``.
    """
    parts = rel_path.parts
    if "param_maps" in parts:
        return "param_map"
    if "color_ramps" in parts:
        return "color_ramp"
    if "effects" in parts:
        return "effect"
    if "ui" in parts:
        return "ui"
    return "atlas"


def image_dimensions(path: Path) -> tuple[int, int]:
    """Return (width, height) for an image file, or (0, 0) on failure."""
    if not PIL_AVAILABLE:
        return 0, 0
    try:
        with Image.open(path) as img:
            return img.size
    except Exception:
        return 0, 0


def audio_type(rel_path: Path) -> str:
    """Classify audio as ``'music'`` or ``'sfx'`` from its relative path."""
    if "music" in rel_path.parts:
        return "music"
    return "sfx"


def json_asset_id(path: Path) -> str:
    """Extract the asset ID from a JSON file's ``"id"`` field.

    Falls back to the filename stem if the file cannot be parsed or has
    no ``"id"`` key.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            value = data.get("id")
            if isinstance(value, str) and value:
                return value
    except Exception:
        pass
    return path.stem


def build_manifest() -> dict[str, Any]:
    """Scan asset directories and return a manifest dict.

    Walks ``frontend/assets/images/``, ``frontend/assets/data/animation/``,
    ``frontend/assets/data/material/``, and ``frontend/assets/audio/``
    recursively.  Files whose names start with ``example_`` or whose
    extensions are not in the recognised set are skipped.

    Returns:
        A manifest dict ready for JSON serialisation.
    """
    images: dict[str, Any] = {}
    animations: dict[str, Any] = {}
    materials: dict[str, Any] = {}
    audio_entries: dict[str, Any] = {}

    images_dir = ASSETS_DIR / "images"
    if images_dir.exists():
        for fpath in sorted(images_dir.rglob("*")):
            if not fpath.is_file():
                continue
            if fpath.name.startswith("example_"):
                continue
            if fpath.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            rel = fpath.relative_to(FRONTEND_DIR)
            w, h = image_dimensions(fpath)
            images[fpath.stem] = {
                "path": rel.as_posix(),
                "type": image_type(rel),
                "width": w,
                "height": h,
                "hash": file_hash(fpath),
            }

    anim_dir = ASSETS_DIR / "data" / "animation"
    if anim_dir.exists():
        for fpath in sorted(anim_dir.rglob("*")):
            if not fpath.is_file():
                continue
            if fpath.name.startswith("example_"):
                continue
            if fpath.suffix.lower() not in JSON_EXTENSIONS:
                continue
            rel = fpath.relative_to(FRONTEND_DIR)
            asset_id = json_asset_id(fpath)
            animations[asset_id] = {
                "path": rel.as_posix(),
                "hash": file_hash(fpath),
            }

    mat_dir = ASSETS_DIR / "data" / "material"
    if mat_dir.exists():
        for fpath in sorted(mat_dir.rglob("*")):
            if not fpath.is_file():
                continue
            if fpath.name.startswith("example_"):
                continue
            if fpath.suffix.lower() not in JSON_EXTENSIONS:
                continue
            rel = fpath.relative_to(FRONTEND_DIR)
            asset_id = json_asset_id(fpath)
            materials[asset_id] = {
                "path": rel.as_posix(),
                "hash": file_hash(fpath),
            }

    audio_dir = ASSETS_DIR / "audio"
    if audio_dir.exists():
        for fpath in sorted(audio_dir.rglob("*")):
            if not fpath.is_file():
                continue
            if fpath.name.startswith("example_"):
                continue
            if fpath.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            rel = fpath.relative_to(FRONTEND_DIR)
            audio_entries[fpath.stem] = {
                "path": rel.as_posix(),
                "type": audio_type(rel),
                "hash": file_hash(fpath),
            }

    return {
        "version": MANIFEST_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "images": images,
        "animations": animations,
        "materials": materials,
        "audio": audio_entries,
    }


def main() -> None:
    """Build and write the asset manifest to ``frontend/assets/manifest.json``."""
    manifest = build_manifest()
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    n_img = len(manifest["images"])
    n_anim = len(manifest["animations"])
    n_mat = len(manifest["materials"])
    n_aud = len(manifest["audio"])
    print(
        f"Generated manifest: {n_img} images, {n_anim} animations, "
        f"{n_mat} materials, {n_aud} audio"
    )


if __name__ == "__main__":
    main()
