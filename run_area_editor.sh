#!/usr/bin/env bash
# Launches the standalone Area/Scene editor (client/main.py) --
# opens the launcher screen (Open Area / New Area / View Asset) with
# no arguments, or pass through flags for a direct boot, e.g.:
#   ./run_area_editor.sh --area=frontend/assets/data/area/area-example.json --mode=builder
#
# No backend/game branch needed -- see docs/graphics/AREA_SYSTEM.md.

set -e

cd "$(dirname "$0")"

if [ -f ".venv/Scripts/python.exe" ]; then
    PYTHON=".venv/Scripts/python.exe"
elif [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
else
    echo "Error: virtual environment not found (.venv)."
    echo "Run setup.bat (Windows) first, or see docs/DEBIAN_SETUP.md (Linux)."
    exit 1
fi

exec "$PYTHON" client/main.py "$@"
