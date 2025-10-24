@echo off
echo Starting Real-Time Simulation Game...
echo.

REM Check if virtual environment exists
if not exist "venv\Scripts\python.exe" (
    echo Error: Virtual environment not found!
    echo Please run setup.bat first.
    pause
    exit /b 1
)

REM Run the game
venv\Scripts\python.exe main.py

pause
