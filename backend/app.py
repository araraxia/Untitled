"""Flask application with SocketIO setup -- Milestone 1.

No HTTP page/static routes, same as `legacy`'s equivalent file: the
desktop client (`client/main.py`) reads `frontend/assets/` directly
off disk and talks to this server over SocketIO only. This app exists
purely as the SocketIO endpoint.

Deliberately thin compared to `legacy`'s `backend/app.py`: no
player-select/character-creation/save-load flow, no party commands --
one hardcoded player entity in one hardcoded Area, straight into
gameplay on connect.
"""

from flask import Flask
from flask_socketio import SocketIO, emit

from backend.engine.config import DEBUG, HOST, PORT
from backend.game.area import create_milestone1_area
from backend.game.tick import GameTick
from backend.independant_logger import Logger

logger = Logger(
    log_name="backend.app", log_file="app.log", log_level=20
).get_logger()

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret-key"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

game_loop = GameTick(socketio)
game_loop.current_area = create_milestone1_area()
PLAYER_ENTITY_ID = game_loop.current_area.player_entity_id


@socketio.on("connect")
def handle_connect(auth=None):
    # Real bug found via a live socketio.Client() round trip (not
    # assumed): this installed python-socketio version calls connect
    # handlers with an `auth` argument; a zero-arg signature raises
    # TypeError on every connect. It's silently absorbed by
    # python-socketio's own backward-compat retry (harmless in
    # practice -- confirmed player_loaded/state_update still arrived
    # correctly), but accepting `auth` directly is the correct fix,
    # not relying on that internal fallback.
    logger.info("Client connected")
    # Lazily started on first connect, not at module import time --
    # importing backend.app (which client/main.py's editor/viewer boot
    # paths do transitively, via area_viewer.py's `import client.main
    # as client_main`) must not silently spin up a live tick loop for
    # sessions that never touch gameplay. GameLoop.start() is already
    # idempotent (no-ops if already running), matching legacy's own
    # "if not game_loop.running: start it" guard at first player load.
    game_loop.start()

    emit("connection_response", {"status": "connected"})
    emit(
        "player_loaded",
        {
            "player_entity_id": PLAYER_ENTITY_ID,
            "entities": {
                eid: entity.serialize()
                for eid, entity in game_loop.current_area.entities.items()
            },
        },
    )


@socketio.on("disconnect")
def handle_disconnect():
    logger.info("Client disconnected")


@socketio.on("player_action")
def handle_player_action(data):
    game_loop.queue_player_action(data)


if __name__ == "__main__":
    socketio.run(
        app, host=HOST, port=PORT, debug=DEBUG, allow_unsafe_werkzeug=True
    )
