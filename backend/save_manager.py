"""SaveManager — persists and restores complete game state.

Save layout (new)::

    saves/
      <player_id>/
        player.json   — PlayerCharacter controller state
        world.json    — World metadata + tick count
        area-<id>.json — One file per serialised area

Legacy layout (read-only fall-back)::

    frontend/assets/data/player/player-<id>.json
    frontend/assets/data/player/player-<id>/world-<world_id>.json
    frontend/assets/data/player/player-<id>/area-<area_id>.json
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.engine.ecs.entity import Entity
from backend.engine.save_format import SAVE_VERSION, migrate
from backend.game.area import Area
from backend.game.entities.player import PlayerCharacter
from backend.game.tick import GameTick as GameLoop
from backend.game.world import World

FILE_PATH = Path(__file__).resolve()
PROJECT_ROOT = FILE_PATH.parent.parent

# New canonical save root
_SAVES_ROOT = PROJECT_ROOT / "saves"

# Legacy paths (read-only fall-back during transition)
_LEGACY_DATA = PROJECT_ROOT / "frontend" / "assets" / "data"
_LEGACY_PLAYER_DIR = _LEGACY_DATA / "player"


class SaveManager:
    """Handles saving, loading, and listing game saves for a player.

    All new saves are written under ``saves/<player_id>/``.  Reads try
    the new path first and fall back to the legacy
    ``frontend/assets/data/player/`` tree so existing saves are not
    broken.
    """

    def __init__(self, socketio: Any, player_id: Optional[str] = None):
        import uuid

        self.socketio = socketio
        self.game_loop: Optional[GameLoop] = None
        self.player_id: str = player_id or str(uuid.uuid4())

        self.player: Optional[PlayerCharacter] = None
        self.player_controlled_entity_ids: List[str] = []
        self.player_controlled_entities: List[Entity] = []
        self.world_id: Optional[str] = None
        self.world: Optional[World] = None
        self.current_area_id: Optional[str] = None
        self.current_area: Optional[Area] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _save_dir(self) -> Path:
        """Return the canonical save directory for this player."""
        return _SAVES_ROOT / self.player_id

    def _find_player_file(self) -> Path:
        """Return the first existing player.json path, or raise.

        Checks new layout then legacy layout.

        Raises:
            FileNotFoundError: If no player file exists.
        """
        new_path = self._save_dir / "player.json"
        if new_path.exists():
            return new_path

        legacy_path = _LEGACY_PLAYER_DIR / f"player-{self.player_id}.json"
        if legacy_path.exists():
            return legacy_path

        raise FileNotFoundError(
            f"No save file found for player_id={self.player_id!r}. "
            f"Checked {new_path} and {legacy_path}."
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_game(self, game_loop: Optional[GameLoop] = None) -> GameLoop:
        """Load a player's save and return a ready GameLoop.

        Tries the new save directory first, falls back to legacy paths.
        Runs ``migrate()`` on every loaded dict.

        Args:
            game_loop: The real, running GameLoop to populate
                (``current_world``/``current_area``) once loaded --
                mirrors ``save_game()``'s existing ``game_loop``
                parameter (see ``GameTick._run_autosave()``'s
                ``sm.save_game(self.player_instance, self)`` for the
                established pattern this follows). When omitted, falls
                back to the previous behavior of creating/reusing a
                throwaway ``GameLoop`` on this instance -- callers that
                need the loaded area/world to reach the app's actual
                running game loop (e.g. ``backend/app.py``'s
                ``handle_load_game()``) must pass their real one.

        Returns:
            Configured (but not yet running) :class:`GameLoop`.

        Raises:
            FileNotFoundError: If the player has no save on disk.
        """
        player_file = self._find_player_file()

        # Initialise or reset the game loop.
        if game_loop is not None:
            self.game_loop = game_loop
        elif not self.game_loop:
            self.game_loop = GameLoop(self.socketio)
        elif self.game_loop.running:
            self.game_loop.stop()

        # --- Player ---
        with open(player_file, "r", encoding="utf-8") as fh:
            raw_player = json.load(fh)
        player_data = migrate(raw_player)
        self.player = PlayerCharacter.load_from_file(
            file_path=player_file, load_entities=False
        )
        self.player_controlled_entity_ids = self.player.controlled_entity_ids

        # Determine data directory for world / area files.
        # New layout: saves/<player_id>/
        # Legacy layout: frontend/assets/data/player/player-<id>/
        save_dir = self._save_dir
        legacy_dir = _LEGACY_PLAYER_DIR / f"player-{self.player_id}"

        data_dir: Path = save_dir if save_dir.exists() else legacy_dir

        # --- World ---
        self.world_id = self.player.world_id
        try:
            self.world = World.load_world(data_dir, self.world_id)
        except FileNotFoundError:
            self.world = World(world_id=self.world_id, world_name="Untitled World")
        # Real bug, found via a real socket.io round trip against the
        # running backend (not assumed): this method never actually
        # propagated the loaded world/area onto self.game_loop, so
        # backend/app.py's handle_load_game() -- which reads
        # game_loop.current_area right after calling this -- always
        # saw None there and crashed with AttributeError. save_game()
        # already reads world/area via self.game_loop (getattr(...,
        # "current_world"/"current_area", None)); this mirrors that,
        # completing the wiring load_game() was apparently never
        # updated to match when the new saves/<id>/ layout landed.
        self.game_loop.current_world = self.world

        # --- Area ---
        self.current_area_id = self.player.area_id
        try:
            self.current_area = Area.load_area(data_dir, area_id=self.current_area_id)
        except FileNotFoundError:
            self.current_area = Area(
                area_id=self.current_area_id, area_name="Untitled Area"
            )
        self.game_loop.current_area = self.current_area

        return self.game_loop

    def save_game(self, player: PlayerCharacter, game_loop: GameLoop) -> None:
        """Persist the complete game state to ``saves/<player_id>/``.

        Pauses the game loop for the duration of the write, then
        resumes if it was not already paused.

        Args:
            player: The active :class:`PlayerCharacter` controller.
            game_loop: The running :class:`GameLoop`.
        """
        self.player = player
        self.game_loop = game_loop
        save_dir = self._save_dir
        save_dir.mkdir(parents=True, exist_ok=True)

        was_paused = self.game_loop.paused
        self.game_loop.pause()

        try:
            # --- Player ---
            now_iso = datetime.now(timezone.utc).isoformat()
            player.player_stats["last_save_timestamptz"] = now_iso
            player_data: Dict[str, Any] = player.to_dict()
            player_data["save_version"] = SAVE_VERSION
            with open(save_dir / "player.json", "w", encoding="utf-8") as fh:
                json.dump(player_data, fh, indent=4)

            # --- World ---
            world: Optional[World] = getattr(self.game_loop, "current_world", None)
            if world is None:
                world = World(world_id=player.world_id, world_name="Untitled World")
            world.save_to_file(save_dir)

            # --- Area ---
            area: Optional[Area] = getattr(self.game_loop, "current_area", None)
            if area is not None:
                area.save_to_file(save_dir)

        finally:
            if not was_paused:
                self.game_loop.resume()

    def delete_player_data(self) -> None:
        """Delete all save data for this player.

        Removes both the new ``saves/<player_id>/`` directory and any
        legacy ``frontend/assets/data/player/`` files.

        Raises:
            FileNotFoundError: If no data exists for the player.
        """
        new_dir = self._save_dir
        legacy_file = _LEGACY_PLAYER_DIR / f"player-{self.player_id}.json"
        legacy_dir = _LEGACY_PLAYER_DIR / f"player-{self.player_id}"

        found = False

        if new_dir.exists():
            shutil.rmtree(new_dir)
            found = True

        if legacy_file.exists():
            legacy_file.unlink()
            found = True

        if legacy_dir.exists():
            shutil.rmtree(legacy_dir)
            found = True

        if not found:
            raise FileNotFoundError(
                f"No save data found for player_id={self.player_id!r}."
            )

    @staticmethod
    def list_saves() -> List[Dict[str, Any]]:
        """Scan ``saves/`` and return a summary list for the UI.

        Returns:
            List of dicts, each containing:
            ``player_id``, ``player_name``, ``last_save``,
            ``tick_count``.
        """
        results: List[Dict[str, Any]] = []

        if not _SAVES_ROOT.exists():
            return results

        for slot_dir in sorted(_SAVES_ROOT.iterdir()):
            if not slot_dir.is_dir():
                continue
            player_file = slot_dir / "player.json"
            if not player_file.exists():
                continue

            try:
                with open(player_file, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                data = migrate(raw)
            except Exception:
                continue

            tick_count = 0
            world_file = slot_dir / "world.json"
            if world_file.exists():
                try:
                    with open(world_file, "r", encoding="utf-8") as fh:
                        wraw = json.load(fh)
                    wdata = migrate(wraw)
                    tick_count = int(wdata.get("tick_count", 0))
                except Exception:
                    pass

            stats = data.get("player_stats", {})
            results.append(
                {
                    "player_id": data.get("player_id", slot_dir.name),
                    "player_name": data.get("player_name", "Unknown"),
                    "last_save": stats.get("last_save_timestamptz"),
                    "tick_count": tick_count,
                }
            )

        return results
