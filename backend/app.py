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


if __name__ == "__main__":
    # Start the game loop in a separate thread
    import threading

    game_thread = threading.Thread(target=game_loop.run, daemon=True)
    game_thread.start()

    # Start the Flask-SocketIO server
    logger.info(f"Starting server on {HOST}:{PORT}")
    logger.info(f"Frontend path: {FRONTEND_PATH}")
    socketio.run(app, host=HOST, port=PORT, debug=DEBUG, allow_unsafe_werkzeug=True)
