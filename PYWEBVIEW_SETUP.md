# PyWebView Desktop Client Setup

This project has been configured to run as an independent desktop application using PyWebView, maintaining the HTML/JS frontend with a pure Python backend.

## Architecture

- **PyWebView**: Python-based desktop webview framework
- **Flask + SocketIO**: Backend server (runs in background thread)
- **Frontend**: HTML/CSS/JavaScript (displayed in native window)

## Advantages of PyWebView

- ✅ Pure Python - no Node.js required
- ✅ Native OS webview (Edge on Windows, WebKit on macOS, GTK on Linux)
- ✅ Smaller package size than Electron
- ✅ Lower memory footprint
- ✅ Easy to package with PyInstaller

## Setup Instructions

### 1. Create Virtual Environment

```cmd
python -m venv venv
venv\Scripts\activate
```

### 2. Install Dependencies

```cmd
pip install -r requirements.txt
```

Or run the automated setup:

```cmd
setup.bat
```

## Running the Application

### Quick Start

Simply run:

```cmd
run.bat
```

### Manual Start

```cmd
venv\Scripts\activate
python main.py
```

### Development Mode (Backend Only)

If you want to test the backend in a browser:

```cmd
venv\Scripts\activate
python backend\app.py
```

Then open `http://localhost:5000` in your browser.

## Building Standalone Executable

To create a standalone .exe file that doesn't require Python:

### 1. Install PyInstaller

```cmd
pip install pyinstaller
```

### 2. Build the executable

```cmd
pyinstaller --name="SimulationGame" ^
    --windowed ^
    --onefile ^
    --add-data "frontend;frontend" ^
    --add-data "backend;backend" ^
    --icon=assets/icon.ico ^
    main.py
```

The executable will be in the `dist/` folder.

## Project Structure

```
game-project/
├── main.py              # PyWebView application entry point
├── backend/             # Python Flask + SocketIO server
│   ├── app.py
│   ├── game_loop.py
│   ├── config.py
│   └── simulation/
├── frontend/            # HTML/CSS/JS game interface
│   ├── index.html
│   ├── css/
│   └── js/
├── requirements.txt     # Python dependencies
├── setup.bat           # Automated setup script
└── run.bat             # Run the game
```

## Key Features

### Native Window
- Uses the OS's native webview engine
- Windows: Edge WebView2
- macOS: WKWebView
- Linux: GTK WebKit2

### Integrated Backend
- Flask server starts automatically in a background thread
- No need to manage separate processes
- Clean shutdown when window closes

### Maintained Frontend
- All HTML/CSS/JS code unchanged
- Socket.IO communication works identically
- Same game logic and rendering

## Development Tips

- **Debug Mode**: Set `debug=True` in `webview.start()` to enable DevTools
- **Server Logs**: Python logs appear in the console/terminal
- **Hot Reload**: Restart the app to see backend changes
- **Backend runs on**: `127.0.0.1:5000`

## Troubleshooting

### PyWebView won't start
- Windows: Install Edge WebView2 Runtime (usually pre-installed on Windows 10/11)
- Install: `pip install --upgrade pywebview`

### Port already in use
Change the PORT in `backend/config.py` (default: 5000)

### Dependencies not installed
Run `pip install -r requirements.txt` in your virtual environment

### Window appears blank
- Wait 2-3 seconds for server to start
- Check console for Flask startup messages
- Try running `python backend/app.py` separately to test backend

## System Requirements

- Python 3.8 or higher
- Windows 10/11 with Edge WebView2 Runtime
- Or macOS 10.13+
- Or Linux with GTK3 and WebKit2

## Comparison: PyWebView vs Electron

| Feature | PyWebView | Electron |
|---------|-----------|----------|
| Language | Python | Node.js/JavaScript |
| Size | ~10-30 MB | ~100-150 MB |
| Memory | Lower | Higher |
| Setup | pip install | npm install |
| Native Feel | High | Medium |
| Cross-platform | Yes | Yes |

## Next Steps

1. Run `setup.bat` to install dependencies
2. Run `run.bat` to start the game
3. Build with PyInstaller for distribution
4. Add custom icon and branding
5. Package for other platforms
