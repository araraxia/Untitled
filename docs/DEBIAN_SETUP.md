# Native Desktop Client Setup for Debian/Ubuntu

Setup for the desktop client (`client/`, launched via `python main.py`) — GLFW window + `wgpu-py` (WebGPU) device + `imgui-bundle` UI. No browser, no WebKitGTK, no PyWebView — the earlier PyWebView/browser client and its GTK3/Qt setup requirements have been deleted entirely (`.github/prompts/wgpu-py-migration.prompt.md`); see [ARCHITECTURE.md](../ARCHITECTURE.md).

## System Dependencies Required

The native client needs two things from the system: a Vulkan-capable GPU driver (for `wgpu-py`/`wgpu-native`) and the GLFW windowing library (for `glfw`, the Python bindings this project uses for the window). Neither GTK3 nor Qt is required.

```bash
sudo apt update
sudo apt install -y \
    libglfw3 \
    mesa-vulkan-drivers \
    xserver-xorg-core \
    libvulkan1
```

Notes on each package, verified against the actual libraries this project depends on (`rendercanvas`'s own installed docstring for `glfw`; `wgpu-py`'s official Linux setup docs for the Vulkan/Mesa packages — see <https://wgpu-py.readthedocs.io/en/stable/start.html>), not guessed:

- **`libglfw3`** — the GLFW C library the `glfw` PyPI package (a thin ctypes wrapper) loads at runtime. On Wayland, install `libglfw3-wayland` instead (or alongside).
- **`mesa-vulkan-drivers`** — open-source Vulkan drivers `wgpu-native` renders through on most Linux systems (AMD/Intel GPUs, or `llvmpipe`/`lavapipe` software rendering when no GPU is present, e.g. CI). If you have a proprietary NVIDIA driver installed, its own Vulkan ICD (from the `nvidia-driver`/`nvidia-utils` package) is used instead and this package isn't strictly required, but doesn't hurt to have as a fallback.
- **`xserver-xorg-core`** — X11 support. If running under Wayland, XWayland (used for compatibility) is typically already available by default on modern desktop environments.
- **`libvulkan1`** — the Vulkan loader itself.

**WSL is not supported** for GPU rendering (per `wgpu-py`'s own documentation) — use a real Linux install or dual-boot, not WSL, for GPU-accelerated rendering.

Then create the venv and install Python dependencies as usual:

```bash
git submodule update --init --recursive
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**pip >= 20.3** is required on Linux for `wgpu`'s wheels to resolve correctly — check with `pip --version` and `pip install --upgrade pip` first if needed.

## Running the Application

```bash
source venv/bin/activate
python main.py
```

This launches `client/main.py`'s native GLFW window — the same entry point as Windows, no browser-mode fallback needed.

**On the `engine` branch itself, this doesn't run.** `client/main.py` imports `backend.app` and `client.game`, both of which only exist on a game branch (e.g. `legacy`) — see [ARCHITECTURE.md](../ARCHITECTURE.md)'s Branch model note. Check out a game branch to run something end to end; these system dependencies still apply there unchanged.

## Troubleshooting

### `wgpu` reports no adapter found / blank or crashing window
- Confirm a Vulkan ICD is actually installed and visible: `vulkaninfo --summary` (from the `vulkan-tools` package, `sudo apt install vulkan-tools` if not present) should list at least one usable GPU or the LavaPipe software adapter.
- If running headless/CI with no real GPU, confirm `mesa-vulkan-drivers` is installed — LavaPipe (software rendering) still requires it.
- Confirm you're not running under WSL — see the WSL note above.

### `ImportError` / `OSError` loading GLFW
- Confirm `libglfw3` (or `libglfw3-wayland` under Wayland) is installed system-wide, not just the `glfw` pip package — the pip package is a wrapper around the system library, not a bundled copy of it, on Linux.

### `ModuleNotFoundError: No module named 'backend'`
- Run `python main.py` (or `python -m backend.app` for the server alone) from the repository root, not `python backend/app.py` directly — running a file directly doesn't add the repo root to `sys.path` the way `python main.py`'s own `sys.path.insert` does.

## System Requirements

- Debian 13 (or a compatible Linux distribution) — Ubuntu 22.04+ should work equivalently
- Python 3.10+
- A Vulkan-capable GPU (or Mesa's LavaPipe software rendering as a fallback) and `libglfw3`
