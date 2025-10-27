 PyWebView Setup for Debian 13

## System Dependencies Required

PyWebView on Linux requires either **GTK3** or **Qt** with Python bindings. Here are your options:

### Option 1: GTK3 (Recommended for Debian)

Install the required system packages (includes Cairo and GObject Introspection):

```bash
sudo apt update
sudo apt install -y \
    python3-gi \
    python3-gi-cairo \
    gir1.2-gtk-3.0 \
    gir1.2-webkit2-4.1 \
    libcairo2-dev \
    libgirepository-2.0-dev \
    gir1.2-girepository-2.0 \
    pkg-config
```

Then install the Python package in your virtual environment:

```bash
source /home/aria/code/Untitled/.venv/bin/activate
pip install PyGObject
```

### Option 2: Qt5/Qt6

Install Qt dependencies:

```bash
sudo apt update
sudo apt install python3-pyqt5 python3-pyqt5.qtwebengine
```

Then install the Python packages:

```bash
source /home/aria/code/Untitled/.venv/bin/activate
pip install PyQt5 PyQtWebEngine
```

## Quick Setup (Recommended)

Run this single command to install all GTK3 dependencies:

```bash
sudo apt update && sudo apt install -y python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1 libcairo2-dev libgirepository-2.0-dev gir1.2-girepository-2.0 pkg-config
```

Then activate your virtual environment and install PyGObject:

```bash
source /home/aria/code/Untitled/.venv/bin/activate
pip install PyGObject
```

## Running the Application

After installing the dependencies:

```bash
source /home/aria/code/Untitled/.venv/bin/activate
python main.py
```

## Troubleshooting

### "No module named 'gi'" error
- You need to install the system packages: `sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1`
- Then install PyGObject in your venv: `pip install PyGObject`

### "cairo dependency not found" when installing PyGObject
- Install Cairo development files: `sudo apt install libcairo2-dev libgirepository-2.0-dev pkg-config`
- Then try again: `pip install PyGObject`

### "girepository-2.0 is required but not found" error
- Install GObject Introspection 2.0: `sudo apt install libgirepository-2.0-dev gir1.2-girepository-2.0`
- Then try again: `pip install PyGObject`

### "No module named 'qtpy'" error
- Install Qt packages: `sudo apt install python3-pyqt5 python3-pyqt5.qtwebengine`
- Then: `pip install PyQt5 PyQtWebEngine`

### Still not working?
Try installing both options and let pywebview choose automatically.

## System Requirements

- Debian 13 (or compatible Linux distribution)
- Python 3.8 or higher
- GTK3 or Qt5/Qt6 with WebKit/WebEngine support

## Why These Dependencies?

PyWebView creates native desktop windows using the system's GUI framework:
- **Windows**: Uses Edge WebView2 (built into Windows 10/11)
- **macOS**: Uses WKWebView (built into macOS)
- **Linux**: Requires GTK3+WebKit2 or Qt+WebEngine (must be installed separately)
