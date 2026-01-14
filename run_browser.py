"""Run the game server and open in system browser (debugging alternative)."""

import sys
import os
import threading
import time
import webbrowser

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.app import app, socketio
from backend.independant_logger import Logger

# Initialize logger
logger = Logger(
    log_name="run_browser",
    log_file="browser.log",
    log_level=20,  # INFO
).get_logger()


def start_server():
    """Start the Flask-SocketIO server in a separate thread."""
    logger.info("Starting game server...")
    # Note: Game loop will start automatically when first player loads

    # Start the Flask-SocketIO server
    socketio.run(
        app, host="127.0.0.1", port=5000, debug=False, allow_unsafe_werkzeug=True
    )


def main():
    """Main application entry point."""
    logger.info("=" * 50)
    logger.info("Real-Time Simulation Game - Browser Mode")
    logger.info("=" * 50)

    # Start the Flask server in a separate thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # Wait for server to start
    logger.info("Waiting for server to start...")
    time.sleep(2)

    # Open in default browser
    logger.info("Opening in browser...")
    webbrowser.open("http://127.0.0.1:5000")

    logger.info("\nGame is running at: http://127.0.0.1:5000")
    logger.info("Press Ctrl+C to stop the server")

    try:
        # Keep the main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")


if __name__ == "__main__":
    main()
