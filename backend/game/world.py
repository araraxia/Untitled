"""Game World — metadata and area registry."""

from __future__ import annotations

from pathlib import Path
from typing import Optional
import json

from backend.engine.save_format import SAVE_VERSION, migrate


class World:
    def __init__(
        self,
        world_id: Optional[str] = None,
        world_name: str = "Untitled World",
    ):
        self.world_id = world_id
        self.world_name = world_name
        self.tick_count: int = 0

    @classmethod
    def load_world(cls, data_dir: Path, world_id: str) -> World:
        """Load world data from a JSON file.

        Tries ``data_dir/world.json`` first, then falls back to
        ``data_dir/world-<world_id>.json`` for legacy saves.  Runs
        :func:`~backend.engine.save_format.migrate` on the raw data
        before deserialising.

        Args:
            data_dir: Directory where world data is stored.
            world_id: ID of the world to load.

        Returns:
            Populated World instance.

        Raises:
            FileNotFoundError: If neither file path exists.
        """
        primary = data_dir / "world.json"
        legacy = data_dir / f"world-{world_id}.json"

        if primary.exists():
            world_file = primary
        elif legacy.exists():
            world_file = legacy
        else:
            raise FileNotFoundError(
                f"World file not found for world_id={world_id!r} " f"in {data_dir}"
            )

        with open(world_file, "r", encoding="utf-8") as fh:
            raw = json.load(fh)

        data = migrate(raw)
        world = cls(
            world_id=data.get("world_id", world_id),
            world_name=data.get("world_name", "Untitled World"),
        )
        world.tick_count = int(data.get("tick_count", 0))
        return world

    def save_to_file(self, save_dir: Path) -> None:
        """Save the world to ``save_dir/world.json``.

        Args:
            save_dir: Target directory (e.g. ``saves/<player_id>/``).
        """
        save_dir.mkdir(parents=True, exist_ok=True)
        world_file = save_dir / "world.json"
        with open(world_file, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=4)

    def to_dict(self) -> dict:
        """Serialize the world to a dictionary."""
        return {
            "save_version": SAVE_VERSION,
            "world_id": self.world_id,
            "world_name": self.world_name,
            "tick_count": self.tick_count,
        }
