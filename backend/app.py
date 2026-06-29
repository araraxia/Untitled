"""Flask application with SocketIO setup."""

from flask import Flask, render_template, send_from_directory
from flask_socketio import SocketIO, emit
import os
from backend.engine.config import HOST, PORT, DEBUG
from backend.engine.config import load_engine_config
from backend.game.config import load_game_config
from backend.game.character_flow_service import register_character_flow_handlers
from backend.independant_logger import Logger
from pathlib import Path

import threading

# Load configs at startup (falls back to defaults if JSON absent)
engine_config = load_engine_config()
game_config = load_game_config()

# Initialize logger
logger = Logger(
    log_name="backend.app",
    log_file="app.log",
    log_level=20,  # INFO
).get_logger()

# Get the absolute path to the project root
FILE_PATH = Path(__file__).resolve()
PROJECT_ROOT = FILE_PATH.parent.parent
FRONTEND_PATH = PROJECT_ROOT / "frontend"
ASSET_PATH = FRONTEND_PATH / "assets"
CSS_PATH = FRONTEND_PATH / "css"
JS_PATH = FRONTEND_PATH / "js"


app = Flask(
    __name__, static_folder=str(FRONTEND_PATH), template_folder=str(FRONTEND_PATH)
)
app.config["SECRET_KEY"] = "your-secret-key-here"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Import game loop after socketio is created
from backend.game.tick import GameTick

game_loop = GameTick(socketio)
register_character_flow_handlers(socketio, game_loop, logger)


# Entry point for the application from main.py
@app.route("/")
def index():
    """Serve the main game page."""
    return render_template("index.html")


@app.route("/css/<path:filename>")
def serve_css(filename):
    """Serve CSS files."""
    return send_from_directory(str(CSS_PATH), filename)


@app.route("/js/<path:filename>")
def serve_js(filename):
    """Serve JavaScript files."""
    return send_from_directory(str(JS_PATH), filename)


@app.route("/assets/<path:filename>")
def serve_assets(filename):
    """Serve asset files (fonts, images, audio, etc.)."""
    return send_from_directory(str(ASSET_PATH), filename)


@socketio.on("connect")
def handle_connect():
    """Handle client connection."""
    logger.info("Client connected")
    emit("connection_response", {"status": "connected"})
    # Note: initial_state is sent after player selection in handle_load_player()


@socketio.on("disconnect")
def handle_disconnect():
    """Handle client disconnection."""
    logger.info("Client disconnected")


@socketio.on("player_action")
def handle_player_action(data):
    """Handle player action from client."""
    game_loop.queue_player_action(data)


@socketio.on("party_command")
def handle_party_command(data):
    """Handle party command from client."""
    game_loop.queue_party_command(data)


@socketio.on("delete_player")
def handle_delete_player(data):
    """Handle deleting a player and their data."""
    from backend.save_manager import SaveManager

    player_id = data.get("player_id")
    if not player_id:
        emit("error", {"message": "No player ID provided"})
        return

    try:
        save_manager = SaveManager(socketio, player_id=player_id)
        save_manager.delete_player_data()
        emit("player_deleted", {"player_id": player_id})
        logger.info(f"Player {player_id} data deleted")
    except FileNotFoundError:
        emit("error", {"message": f"Player file for ID {player_id} does not exist."})


@socketio.on("load_player")
def handle_load_game(data):
    """Handle loading a player and their controlled entities."""
    from backend.save_manager import SaveManager

    player_id = data.get("player_id")
    if not player_id:
        emit("error", {"message": "No player ID provided"})
        return

    try:
        save_manager = SaveManager(socketio, player_id=player_id)
        save_manager.load_game()
        emit(
            "player_loaded",
        )
    except FileNotFoundError:
        emit("error", {"message": f"Player file for ID {player_id} does not exist."})

    # Start game loop on first player load (thread-safe)
    if not game_loop.running:
        logger.info("Starting game loop for first player load")
        game_thread = threading.Thread(target=game_loop.run, daemon=True)
        game_thread.start()
        # Brief pause to ensure game loop initializes
        import time

        time.sleep(0.1)

    try:
        # Load existing player - PlayerCharacter handles entity loading internally
        from backend.game.entities.player import PlayerCharacter

        player = PlayerCharacter.load_by_id(player_id, load_entities=True)
        logger.info(
            f"Loaded existing player {player_id} with {len(player.get_controlled_entities())} entities"
        )

        # Load player controller and entities into world
        game_loop.current_area.load_player_controller(player)

        # Send the full game state with loaded entities
        full_state = game_loop.current_area.get_full_state()
        full_state["player_id"] = player_id
        full_state["controlled_entity_ids"] = [
            e.entity_id for e in player.get_controlled_entities()
        ]

        emit("player_loaded", full_state)
        logger.info(
            f"Player {player_id} loaded with {len(player.get_controlled_entities())} controlled entities"
        )

    except Exception as e:
        logger.error(f"Error loading player {player_id}: {e}")
        import traceback

        logger.error(traceback.format_exc())
        emit("error", {"message": f"Failed to load player: {str(e)}"})


@socketio.on("request_save_list")
def handle_request_save_list():
    """Return a list of save-slot summaries to the requesting client."""
    from backend.save_manager import SaveManager

    saves = SaveManager.list_saves()
    emit("save_list", {"saves": saves})


@socketio.on("save_game")
def handle_save_game():
    """Trigger a manual save for the current player."""
    from backend.save_manager import SaveManager

    player = game_loop.player_instance
    if not player:
        emit(
            "save_complete",
            {"status": "error", "message": "No active player."},
        )
        return
    try:
        sm = SaveManager(socketio, player_id=player.player_id)
        sm.save_game(player, game_loop)
        emit("save_complete", {"status": "ok", "message": "Game saved."})
        logger.info(f"Manual save completed for player {player.player_id}")
    except Exception as e:
        logger.error(f"Error saving game: {e}")
        emit("save_complete", {"status": "error", "message": str(e)})


if os.environ.get("DEV_HOT_RELOAD", "0") == "1":
    from backend.engine.hot_reload import HotReloadWatcher

    _hot_reload = HotReloadWatcher(
        socketio,
        "frontend/assets",
        "frontend/js/engine/sprites",
    )
    _hot_reload.start()

if __name__ == "__main__":
    # Note: Game loop will start automatically when first player loads

    # Start the Flask-SocketIO server
    logger.info(f"Starting server on {HOST}:{PORT}")
    logger.info(f"Frontend path: {FRONTEND_PATH}")
    socketio.run(app, host=HOST, port=PORT, debug=DEBUG, allow_unsafe_werkzeug=True)
