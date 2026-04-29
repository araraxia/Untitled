@echo off
REM To enable hot reload in dev mode, set: set DEV_HOT_RELOAD=1
echo Setting up Real-Time Simulation Game (PyWebView)
echo.

echo [1/3] Creating Python virtual environment...
python -m venv venv
if %errorlevel% neq 0 (
    echo Error: Failed to create virtual environment
    pause
    exit /b 1
)

echo [2/3] Activating virtual environment...
call venv\Scripts\activate.bat

echo [3/4] Installing Python dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo Error: Failed to install Python dependencies
    pause
    exit /b 1
)

echo [4/4] Building assets...
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
