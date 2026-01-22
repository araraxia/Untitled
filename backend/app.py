"""Flask application with SocketIO setup."""

from flask import Flask, render_template, send_from_directory
from flask_socketio import SocketIO, emit
import os
from backend.config import HOST, PORT, DEBUG
from backend.independant_logger import Logger
from pathlib import Path

from backend.simulation import player

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
DATA_PATH = ASSET_PATH / "data"


app = Flask(
    __name__, static_folder=str(FRONTEND_PATH), template_folder=str(FRONTEND_PATH)
)
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


@socketio.on("request_player_list")
def handle_request_player_list():
    """Handle request for list of available players."""
    logger.info("Client requested player list")
    from pathlib import Path
    import json

    player_dir = DATA_PATH / "player"
    players = []

    if player_dir.exists():
        logger.info(f"Loading player list from {player_dir}")
        for player_file in player_dir.glob("*.json"):
            try:
                logger.info(f"Loading player file: {player_file}")
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


@socketio.on("request_races")
def handle_request_races():
    """Handle request for available races."""
    logger.info("Client requested races list")
    from backend.simulation.new_game import NewGameManager

    try:
        new_game_manager = NewGameManager(game_loop)
        races = new_game_manager.get_available_races()
        emit("races_list", {"races": races})
        logger.info(f"Sent {len(races)} races to client")
    except Exception as e:
        logger.error(f"Error fetching races: {e}")
        emit("error", {"message": f"Error fetching races: {str(e)}"})


@socketio.on("request_backgrounds")
def handle_request_backgrounds(data):
    """Handle request for backgrounds for a specific race."""
    race_id = data.get("race_id", "human")
    logger.info(f"Client requested backgrounds for race: {race_id}")
    from backend.simulation.new_game import NewGameManager

    try:
        new_game_manager = NewGameManager(game_loop)
        backgrounds = new_game_manager.get_backgrounds_for_race(race_id)
        emit("backgrounds_list", {"race_id": race_id, "backgrounds": backgrounds})
        logger.info(f"Sent {len(backgrounds)} backgrounds for race {race_id}")
    except Exception as e:
        logger.error(f"Error fetching backgrounds for race {race_id}: {e}")
        emit("error", {"message": f"Error fetching backgrounds: {str(e)}"})


@socketio.on("new_player")
def handle_new_game(data):
    """Handle creating a new player and initializing their character."""
    from backend.simulation.new_game import NewGameManager

    new_game_manager = NewGameManager(game_loop)

    player_name = data.get("player_name", "New_Player")

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
def handle_new_character(data):
    """Handle creating a new character for an existing player."""
    from backend.simulation.new_game import NewGameManager

    try:
        # Get the player character that was initialized in new_player
        player_character = game_loop.player_instance
        if not player_character:
            emit(
                "error",
                {"message": "No player initialized. Please start a new game first."},
            )
            return

        new_game_manager = NewGameManager(game_loop)

        # Extract character data from request
        character_name = data.get("player_name", "Unnamed")
        race_id = data.get("race_id", "human")
        background_name = data.get("background_name")
        personality = data.get("personality", [])
        appearance = data.get("appearance", {})
        stats = data.get("stats", {})
        items = data.get("items", [])

        # Create the character entity
        entity = new_game_manager.init_new_character(
            character_name=character_name,
            race_id=race_id,
            background_name=background_name,
            personality=personality,
            appearance=appearance,
            stats=stats,
            items=items,
        )

        # Save the player data
        player_character.save_to_file()

        logger.info(
            f"Character {character_name} created for player {player_character.player_id}"
        )
        emit(
            "character_created",
            {
                "player_id": player_character.player_id,
                "entity_id": entity.entity_id,
                "character_name": character_name,
            },
        )

    except Exception as e:
        logger.error(f"Error creating character: {e}")
        import traceback

        logger.error(traceback.format_exc())
        emit("error", {"message": f"Failed to create character: {str(e)}"})


@socketio.on("delete_player")
def handle_delete_player(data):
    """Handle deleting a player and their data."""
    from backend.load_save import SaveManager

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
    from backend.load_save import SaveManager

    player_id = data.get("player_id")
    if not player_id:
        emit("error", {"message": "No player ID provided"})
        return

    try:
        save_manager = SaveManager(player_id=player_id, game_loop=game_loop)
        save_manager.load_game()
        emit(
            "player_loaded",
        )
    except FileNotFoundError:
        emit("error", {"message": f"Player file for ID {player_id} does not exist."})

    return

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


if __name__ == "__main__":
    # Note: Game loop will start automatically when first player loads

    # Start the Flask-SocketIO server
    logger.info(f"Starting server on {HOST}:{PORT}")
    logger.info(f"Frontend path: {FRONTEND_PATH}")
    socketio.run(app, host=HOST, port=PORT, debug=DEBUG, allow_unsafe_werkzeug=True)
