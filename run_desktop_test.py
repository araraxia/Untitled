"""[DEV ONLY] Open a given page in the real PyWebView desktop client.

`main.py` hardcodes its window to "/" (the real game) — this script is
the debug equivalent for dev/test pages like frontend/test-3d.html,
using the same Edge WebView2 (Chromium) engine the packaged app actually
ships with, so WebGPU behaves the same way it will in production instead
of depending on whatever the OS's default browser happens to be.

Usage:
    python run_desktop_test.py               # opens /test-3d.html
    python run_desktop_test.py /some/path     # opens any other path
"""

import webview
import threading
import time
import sys
import os
import socket

# Add the project root to the Python path early
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.independant_logger import Logger

logger = Logger(
    log_name="run_desktop_test",
    log_file="desktop_test.log",
    log_level=20,  # INFO
).get_logger()

from backend.app import app, socketio

DEFAULT_PATH = "/test-3d.html"


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
    socketio.run(
        app, host="127.0.0.1", port=5000, debug=False, allow_unsafe_werkzeug=True
    )


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PATH
    if not path.startswith("/"):
        path = "/" + path
    url = f"http://127.0.0.1:5000{path}"

    logger.info("=" * 50)
    logger.info("[DEV ONLY] Desktop test launcher")
    logger.info("Target: %s", url)
    logger.info("=" * 50)

    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    logger.info("Waiting for server to start...")
    if not is_server_ready():
        logger.error("ERROR: Server failed to start within timeout period!")
        return

    logger.info("Server is ready!")
    time.sleep(0.5)

    logger.info("Opening window: %s", url)
    webview.create_window(
        title=f"[DEV TEST] {path}",
        url=url,
        width=1280,
        height=720,
        resizable=True,
        fullscreen=False,
        min_size=(800, 600),
        background_color="#1a1a1a",
    )

    # debug=True enables right-click → Inspect Element / devtools in the
    # webview window, same as main.py — needed to see console output.
    webview.start(debug=True, http_server=False, private_mode=False)

    logger.info("Test window closed. Exiting...")


if __name__ == "__main__":
    main()
