"""Save-file format constants and version-migration registry."""

from __future__ import annotations

from typing import Any, Callable, Dict

SAVE_VERSION: int = 1

# Maps save_version -> callable(data: dict) -> dict.
# Each migration upgrades data from version N to N+1.
_MIGRATIONS: Dict[int, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}


class SaveVersionError(Exception):
    """Raised when a save file's version is newer than the engine supports."""


def register_migration(
    from_version: int,
    fn: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> None:
    """Register a migration function for save_version == from_version.

    Args:
        from_version: The save_version the migration reads from.
        fn: Callable that accepts a data dict at ``from_version`` and
            returns a data dict at ``from_version + 1``.
    """
    _MIGRATIONS[from_version] = fn


def migrate(data: Dict[str, Any]) -> Dict[str, Any]:
    """Apply all registered migrations to bring data up to SAVE_VERSION.

    Reads ``data['save_version']``, applies migrations in ascending
    order until the data reaches ``SAVE_VERSION``, and returns the
    updated dict.

    Args:
        data: Raw save data loaded from disk.

    Returns:
        Data dict at ``SAVE_VERSION``.

    Raises:
        SaveVersionError: If ``data['save_version']`` is greater than
            ``SAVE_VERSION``.
    """
    version: int = int(data.get("save_version", 1))

    if version > SAVE_VERSION:
        raise SaveVersionError(
            f"Save file version {version} is newer than the engine "
            f"supports (max {SAVE_VERSION})."
        )

    while version < SAVE_VERSION:
        migration = _MIGRATIONS.get(version)
        if migration is None:
            # No migration registered; bump the version marker and
            # continue so gaps don't stall the loop.
            version += 1
            data = dict(data, save_version=version)
            continue
        data = migration(data)
        version = int(data.get("save_version", version + 1))

    return data
