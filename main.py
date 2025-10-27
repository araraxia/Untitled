"""Main entry point for the desktop application."""

import webview
import threading
import time
import sys
import os
import socket

# Disable GPU acceleration for WebKit (fixes black screen on some Linux systems)
os.environ['WEBKIT_DISABLE_COMPOSITING_MODE'] = '1'
os.environ['WEBKIT_DISABLE_DMABUF_RENDERER'] = '1'

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.app import app, socketio
from backend.game_loop import GameLoop


def is_server_ready(host="127.0.0.1", port=5000, timeout=10):
    """Check if the server is ready to accept connections."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


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

    # Wait for the server to be ready
    print("Waiting for server to start...")
    if not is_server_ready():
        print("ERROR: Server failed to start within timeout period!")
        print("Try running the backend directly: python backend/app.py")
        return

    print("Server is ready!")
    time.sleep(0.5)  # Brief additional delay for stability

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

    # Start the webview with debug mode and hardware acceleration disabled
    webview.start(debug=True, http_server=False, private_mode=False)

    print("Game window closed. Exiting...")


if __name__ == "__main__":
    main()
