@echo off
REM To enable hot reload in dev mode, set: set DEV_HOT_RELOAD=1
REM Requires Git LFS (git-lfs.github.com) for the asset submodule's
REM binary files - without it, images/fonts/audio stay as text pointer
REM files instead of real content.
echo Setting up Real-Time Simulation Game (PyWebView)
echo.

echo [1/5] Fetching asset submodule...
git submodule update --init --recursive
if %errorlevel% neq 0 (
    echo Error: Failed to fetch frontend/assets submodule
    pause
    exit /b 1
)

echo [2/5] Creating Python virtual environment...
python -m venv venv
if %errorlevel% neq 0 (
    echo Error: Failed to create virtual environment
    pause
    exit /b 1
)

echo [3/5] Activating virtual environment...
call venv\Scripts\activate.bat

echo [4/5] Installing Python dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo Error: Failed to install Python dependencies
    pause
    exit /b 1
)

echo [5/5] Building assets...
python tools/build_assets.py
if %errorlevel% neq 0 (
    echo Error: Asset build failed
    pause
    exit /b 1
)

echo.
echo Setup complete!
echo.
echo To run the game:
echo   Run: run.bat
echo.
echo Or manually:
echo   1. venv\Scripts\activate
echo   2. python main.py
echo.
pause
