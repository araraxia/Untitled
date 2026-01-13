"""Flask application with SocketIO setup."""

from flask import Flask, render_template, send_from_directory
from flask_socketio import SocketIO, emit
import os
from backend.config import HOST, PORT, DEBUG
from backend.independant_logger import Logger

# Initialize logger
logger = Logger(
    log_name="backend.app",
    log_file="app.log",
    log_level=20,  # INFO
).get_logger()

# Get the absolute path to the project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_PATH = os.path.join(PROJECT_ROOT, "frontend")

app = Flask(__name__, static_folder=FRONTEND_PATH, template_folder=FRONTEND_PATH)
app.config["SECRET_KEY"] = "your-secret-key-here"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Import game loop after socketio is created
from backend.game_loop import GameLoop

game_loop = GameLoop(socketio)


@app.route("/")
def index():
    """Serve the main game page."""
    return render_template("index.html")


@app.route("/css/<path:filename>")
def serve_css(filename):
    """Serve CSS files."""
    return send_from_directory(os.path.join(FRONTEND_PATH, "css"), filename)


@app.route("/js/<path:filename>")
def serve_js(filename):
    """Serve JavaScript files."""
    return send_from_directory(os.path.join(FRONTEND_PATH, "js"), filename)


@app.route("/assets/<path:filename>")
def serve_assets(filename):
    """Serve asset files (fonts, images, audio, etc.)."""
    return send_from_directory(os.path.join(FRONTEND_PATH, "assets"), filename)


@socketio.on("connect")
def handle_connect():
    """Handle client connection."""
    logger.info("Client connected")
    emit("connection_response", {"status": "connected"})

    # Send the full initial game state to the newly connected client
    full_state = game_loop.world.get_full_state()
    emit("initial_state", full_state)


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


@socketio.on("request_player_list")
def handle_request_player_list():
    """Handle request for list of available players."""
    from pathlib import Path
    import json

    player_dir = Path("data/player")
    players = []

    if player_dir.exists():
        logger.debug(f"Loading player list from {player_dir}")
        for player_file in player_dir.glob("*.json"):
            try:
                logger.debug(f"Loading player file: {player_file}")
                with open(player_file, "r") as f:
                    player_data = json.load(f)
                    players.append(
                        {
                            "player_id": player_data.get("player_id"),
                            "controlled_entity_ids": player_data.get(
                                "controlled_entity_ids", []
                            ),
                        }
                    )
            except Exception as e:
                logger.error(f"Error loading player file {player_file}: {e}")
    else:
        logger.warning(f"Player directory {player_dir} does not exist")

    emit("player_list", {"players": players})


@socketio.on("load_player")
def handle_load_player(data):
    """Handle loading a player and their controlled entities."""
    from pathlib import Path
    from backend.simulation.player import PlayerCharacter
    from backend.simulation.entity import Entity

    player_id = data.get("player_id")
    if not player_id:
        emit("error", {"message": "No player ID provided"})
        return

    try:
        # Load or create player
        player_file = Path("data/players") / f"{player_id}.json"

        if player_file.exists():
            # Load existing player - PlayerCharacter handles entity loading internally
            player = PlayerCharacter.load_by_id(player_id, load_entities=True)
            logger.info(f"Loaded existing player {player_id} with {len(player.get_controlled_entities())} entities")
        else:
            # Create new player with a default entity
            from backend.config import WORLD_WIDTH, WORLD_HEIGHT
            
            player = PlayerCharacter(player_id=player_id)
            
            # Create and add default entity
            default_entity = Entity(
                entity_id=f"entity_{player_id[:8]}",
                x=WORLD_WIDTH // 2,
                y=WORLD_HEIGHT // 2,
                animation_data_paths=["assets/data/example_human_animations.json"]
            )
            player.add_controlled_entity(default_entity)
            
            logger.info(f"Created new player {player_id} with default entity")

        # Load player controller and entities into world
        game_loop.world.load_player_controller(player)

        # Send the full game state with loaded entities
        full_state = game_loop.world.get_full_state()
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


if __name__ == "__main__":
    # Start the game loop in a separate thread
    import threading

    game_thread = threading.Thread(target=game_loop.run, daemon=True)
    game_thread.start()

    # Start the Flask-SocketIO server
    logger.info(f"Starting server on {HOST}:{PORT}")
    logger.info(f"Frontend path: {FRONTEND_PATH}")
    socketio.run(app, host=HOST, port=PORT, debug=DEBUG, allow_unsafe_werkzeug=True)
