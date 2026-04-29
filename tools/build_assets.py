"""Orchestrate all asset pre-processing steps."""

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

TOOLS_DIR = Path(__file__).parent
CACHE_PATH = TOOLS_DIR / ".asset_cache.json"
PENDING_DIR = Path("frontend/assets/pending")
PARAM_MAPS_DIR = Path("frontend/assets/images/param_maps")
ANIM_DIR = Path("frontend/assets/data/animation")

# Channel suffixes used to discover source images in pending/.
# A sprite named ``<stem>`` is expected to have files named
# ``<stem>_r.png``, ``<stem>_g.png``, etc. (all optional).
_CHANNEL_SUFFIXES: dict[str, str] = {
    "r": "_r",
    "g": "_g",
    "b": "_b",
    "a": "_a",
}


# ---------------------------------------------------------------------------
# Hash helpers
# ---------------------------------------------------------------------------


def _file_hash(path: Path) -> str:
    """Return the SHA-256 hex digest of *path*."""
    sha = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _load_cache() -> dict[str, str]:
    """Load the hash cache from disk, returning an empty dict on failure."""
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_cache(cache: dict[str, str]) -> None:
    """Persist the hash cache to disk."""
    CACHE_PATH.write_text(
        json.dumps(cache, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Step 1: Pack param maps
# ---------------------------------------------------------------------------


def _pack_param_maps(
    cache: dict[str, str],
) -> tuple[int, int]:
    """Pack channel source images found in ``frontend/assets/pending/``.

    For each sprite stem that has at least one ``<stem>_<channel>.png``
    file in ``pending/``, the four RGBA channels are packed into a single
    param-map PNG under ``frontend/assets/images/param_maps/``.

    Sprites are skipped when the output already exists **and** none of the
    source files have changed since the last build (checked via SHA-256).

    Returns:
        ``(packed, skipped)`` counts.
    """
    # Import here so the module can be imported even without PIL installed.
    from pack_param_map import pack  # type: ignore[import]

    if not PENDING_DIR.exists():
        return 0, 0

    # Collect all ``<stem>_<channel>.png`` groups.
    stems: dict[str, dict[str, Path]] = {}
    for fpath in sorted(PENDING_DIR.iterdir()):
        if not fpath.is_file() or fpath.suffix.lower() != ".png":
            continue
        name = fpath.stem  # e.g. "lantern_r"
        for ch, suffix in _CHANNEL_SUFFIXES.items():
            if name.endswith(suffix):
                sprite_stem = name[: -len(suffix)]
                stems.setdefault(sprite_stem, {})[ch] = fpath
                break

    packed = 0
    skipped = 0
    for sprite_stem, channels in stems.items():
        output = PARAM_MAPS_DIR / f"{sprite_stem}_params.png"

        # Compute current hashes for all source files.
        current: dict[str, str] = {str(p): _file_hash(p) for p in channels.values()}
        cached: dict[str, str] = {k: cache.get(k, "") for k in current}

        if output.exists() and current == cached:
            skipped += 1
            continue

        PARAM_MAPS_DIR.mkdir(parents=True, exist_ok=True)
        pack(
            r_path=str(channels["r"]) if "r" in channels else None,
            g_path=str(channels["g"]) if "g" in channels else None,
            b_path=str(channels["b"]) if "b" in channels else None,
            a_path=str(channels["a"]) if "a" in channels else None,
            output_path=str(output),
        )
        cache.update(current)
        packed += 1

    return packed, skipped


# ---------------------------------------------------------------------------
# Step 2: Build manifest
# ---------------------------------------------------------------------------


def _build_manifest() -> int:
    """Invoke build_manifest.main() and return the total entry count."""
    import build_manifest  # type: ignore[import]

    manifest = build_manifest.build_manifest()
    build_manifest.MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    build_manifest.MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    total = (
        len(manifest["images"])
        + len(manifest["animations"])
        + len(manifest["materials"])
        + len(manifest["audio"])
    )
    return total


# ---------------------------------------------------------------------------
# Step 3: Validate animation JSON
# ---------------------------------------------------------------------------

_REQUIRED_ANIM_KEYS = {"id", "frames"}


def _validate_animations() -> tuple[int, int]:
    """Validate all animation JSON files in the animation data directory.

    Prints a warning for each file that is not valid JSON or is missing
    required top-level keys (``"id"``, ``"frames"``).  The build is never
    aborted by validation failures.

    Returns:
        ``(valid, invalid)`` counts.
    """
    if not ANIM_DIR.exists():
        return 0, 0

    valid = 0
    invalid = 0
    for fpath in sorted(ANIM_DIR.rglob("*.json")):
        if not fpath.is_file():
            continue
        try:
            data: Any = json.loads(fpath.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(
                f"  [WARN] Invalid JSON in {fpath}: {exc}",
                file=sys.stderr,
            )
            invalid += 1
            continue

        if not isinstance(data, dict):
            print(
                f"  [WARN] {fpath}: root is not a JSON object",
                file=sys.stderr,
            )
            invalid += 1
            continue

        missing = _REQUIRED_ANIM_KEYS - data.keys()
        if missing:
            print(
                f"  [WARN] {fpath}: missing required keys: "
                f"{', '.join(sorted(missing))}",
                file=sys.stderr,
            )
            invalid += 1
        else:
            valid += 1

    return valid, invalid


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run all asset build steps and print a summary."""
    # Ensure tools/ is on sys.path so sibling modules can be imported.
    tools_str = str(TOOLS_DIR)
    if tools_str not in sys.path:
        sys.path.insert(0, tools_str)

    t_start = time.monotonic()
    cache = _load_cache()

    # -- Step 1: param maps --------------------------------------------------
    t0 = time.monotonic()
    packed, skipped = _pack_param_maps(cache)
    t1 = time.monotonic()
    print(f"[1/3] Param maps: {packed} packed, {skipped} skipped " f"({t1 - t0:.2f}s)")

    # -- Step 2: manifest ----------------------------------------------------
    t0 = time.monotonic()
    manifest_entries = _build_manifest()
    t1 = time.monotonic()
    print(f"[2/3] Manifest: {manifest_entries} entries " f"({t1 - t0:.2f}s)")

    # -- Step 3: animation validation ----------------------------------------
    t0 = time.monotonic()
    valid_anims, invalid_anims = _validate_animations()
    t1 = time.monotonic()
    print(
        f"[3/3] Animations: {valid_anims} valid, {invalid_anims} invalid "
        f"({t1 - t0:.2f}s)"
    )

    # -- Persist cache & summary ---------------------------------------------
    _save_cache(cache)

    elapsed = time.monotonic() - t_start
    print(
        f"\nBuild complete in {elapsed:.2f}s — "
        f"{packed} param maps packed, "
        f"{manifest_entries} manifest entries, "
        f"{invalid_anims} animation warning(s)."
    )


if __name__ == "__main__":
    main()
