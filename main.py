"""Main entry point for the desktop application."""

import webview
import threading
import time
import sys
import os
import socket
import subprocess
import platform

# Add the project root to the Python path early
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.independant_logger import Logger

# Initialize logger
logger = Logger(
    log_name="main",
    log_file="main.log",
    log_level=20,  # INFO
).get_logger()


# Conditionally disable GPU acceleration for Nouveau drivers (fixes black screen issues)
def should_disable_gpu():
    """Check if GPU acceleration should be disabled based on driver."""
    # Only check on Linux systems
    if platform.system() != "Linux":
        return False

    try:
        # Check if using Nouveau (open-source NVIDIA driver)
        result = subprocess.run(
            ["lspci", "-k"], capture_output=True, text=True, timeout=2
        )
        output = result.stdout.lower()

        # Look for Nouveau driver in use
        if "nouveau" in output and ("vga" in output or "nvidia" in output):
            logger.warning(
                "Nouveau GPU driver detected - disabling GPU acceleration for stability"
            )
            return True

    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        # If we can't determine, err on the side of compatibility
        logger.info(f"Could not detect GPU driver ({e}), enabling GPU acceleration")
        return False

    return False


# Disable GPU acceleration if needed
if should_disable_gpu():
    os.environ["WEBKIT_DISABLE_COMPOSITING_MODE"] = "1"
    os.environ["WEBKIT_DISABLE_DMABUF_RENDERER"] = "1"

from backend.app import app, socketio


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
    logger.info("Starting game server...")

    # Use the existing global game_loop instance from backend.app
    from backend.app import game_loop
    
    game_thread = threading.Thread(target=game_loop.run, daemon=True)
    game_thread.start()

    # Start the Flask-SocketIO server
    socketio.run(
        app, host="127.0.0.1", port=5000, debug=False, allow_unsafe_werkzeug=True
    )


def main():
    """Main application entry point."""
    logger.info("=" * 50)
    logger.info("Real-Time Simulation Game")
    logger.info("=" * 50)

    # Start the Flask server in a separate thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # Wait for the server to be ready
    logger.info("Waiting for server to start...")
    if not is_server_ready():
        logger.error("ERROR: Server failed to start within timeout period!")
        logger.error("Try running the backend directly: python backend/app.py")
        return

    logger.info("Server is ready!")
    time.sleep(0.5)  # Brief additional delay for stability

    # Create the webview window
    logger.info("Opening game window...")
    window = webview.create_window(
        title="Untitled",
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

    logger.info("Game window closed. Exiting...")


if __name__ == "__main__":
    main()
