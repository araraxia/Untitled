"""SocketIO registration for character onboarding flow."""

from __future__ import annotations

from typing import Any

from flask_socketio import emit


def register_character_flow_handlers(socketio, game_loop, logger) -> None:
    """Register SocketIO handlers for character onboarding flow.

    Args:
        socketio: Flask-SocketIO server instance.
        game_loop: Active game loop object with player instance state.
        logger: Logger used for diagnostics.
    """

    def emit_error(message: str) -> None:
        """Emit a consistent onboarding error payload."""
        emit("error", {"message": message})

    @socketio.on("request_save_list")
    def handle_request_save_list() -> None:
        """Return a list of save-slot summaries."""
        from backend.save_manager import SaveManager

        saves = SaveManager.list_saves()
        emit("save_list", {"saves": saves})

    @socketio.on("request_races")
    def handle_request_races() -> None:
        """Return available races for character creation."""
        from backend.game.new_game import NewGameManager

        logger.info("Client requested races list")
        try:
            new_game_manager = NewGameManager(game_loop)
            races = new_game_manager.get_available_races()
            emit("races_list", {"races": races})
            logger.info("Sent %d races to client", len(races))
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Error fetching races: %s", exc)
            emit_error(f"Error fetching races: {str(exc)}")

    @socketio.on("request_backgrounds")
    def handle_request_backgrounds(data: dict[str, Any] | None) -> None:
        """Return backgrounds for a specific race id."""
        from backend.game.new_game import NewGameManager

        payload = data or {}
        race_id = payload.get("race_id", "human")
        logger.info("Client requested backgrounds for race: %s", race_id)
        try:
            new_game_manager = NewGameManager(game_loop)
            backgrounds = new_game_manager.get_backgrounds_for_race(race_id)
            emit(
                "backgrounds_list",
                {"race_id": race_id, "backgrounds": backgrounds},
            )
            logger.info("Sent %d backgrounds for race %s", len(backgrounds), race_id)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Error fetching backgrounds for race %s: %s", race_id, exc)
            emit_error(f"Error fetching backgrounds: {str(exc)}")

    @socketio.on("new_player")
    def handle_new_player(data: dict[str, Any] | None) -> None:
        """Create player shell and attach it to game loop."""
        from backend.game.new_game import NewGameManager

        payload = data or {}
        player_name = payload.get("player_name") or payload.get(
            "player_id", "New_Player"
        )

        new_game_manager = NewGameManager(game_loop)
        new_game_manager.init_new_game(save_name=player_name)
        player_character = new_game_manager.player_character
        game_loop.player_instance = player_character

        emit(
            "new_player_initialized",
            {
                "player_id": player_character.player_id,
            },
        )

    @socketio.on("new_character")
    def handle_new_character(data: dict[str, Any] | None) -> None:
        """Create a character for the initialized player shell."""
        from backend.game.new_game import NewGameManager

        payload = data or {}

        try:
            player_character = game_loop.player_instance
            if not player_character:
                emit_error("No player initialized. Please start a new game first.")
                return

            new_game_manager = NewGameManager(game_loop)

            character_name = payload.get("player_name", "Unnamed")
            race_id = payload.get("race_id", "human")
            background_name = payload.get("background_name")
            personality = payload.get("personality", [])
            appearance = payload.get("appearance", {})
            stats = payload.get("stats", {})
            items = payload.get("items", [])

            entity = new_game_manager.init_new_character(
                character_name=character_name,
                race_id=race_id,
                background_name=background_name,
                personality=personality,
                appearance=appearance,
                stats=stats,
                items=items,
            )

            player_character.save_to_file()

            logger.info(
                "Character %s created for player %s",
                character_name,
                player_character.player_id,
            )
            emit(
                "character_created",
                {
                    "player_id": player_character.player_id,
                    "entity_id": entity.entity_id,
                    "character_name": character_name,
                },
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Error creating character: %s", exc)
            import traceback

            logger.error(traceback.format_exc())
            emit_error(f"Failed to create character: {str(exc)}")
