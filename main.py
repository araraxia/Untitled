"""Main entry point for the desktop application."""

import webview
import threading
import time
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.app import app, socketio
from backend.game_loop import GameLoop


def start_server():
    """Start the Flask-SocketIO server in a separate thread."""
    print("Starting game server...")

    # Get the game loop instance and start it
    game_loop = GameLoop(socketio)
    game_thread = threading.Thread(target=game_loop.run, daemon=True)
    game_thread.start()

    # Start the Flask-SocketIO server
    socketio.run(
        app, host="127.0.0.1", port=5000, debug=False, allow_unsafe_werkzeug=True
    )


def main():
    """Main application entry point."""
    print("Real-Time Simulation Game")
    print("=" * 50)

    # Start the Flask server in a separate thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # Wait a moment for the server to start
    print("Waiting for server to start...")
    time.sleep(2)

    # Create the webview window
    print("Opening game window...")
    window = webview.create_window(
        title="Real-Time Simulation Game",
        url="http://127.0.0.1:5000",
        width=1280,
        height=720,
        resizable=True,
        fullscreen=False,
        min_size=(800, 600),
        background_color="#1a1a1a",
    )

    # Start the webview (this blocks until the window is closed)
    webview.start(debug=False)

    print("Game window closed. Exiting...")


if __name__ == "__main__":
    main()
