"""Launcher screen -- the real first entry point for opening/starting
areas and previewing assets. Step 3 of
.github/prompts/level-editor.prompt.md.

Replaces hand-typing an `--area=<path>` command-line flag with a real
first screen: an imgui window shown at startup, not a second
executable. Works with zero backend connection, same as every other
standalone mode -- reads the manifest via `asset_loader.py`'s direct
filesystem access, nothing else.

**In-process transition, not a subprocess relaunch** -- but also not a
literally-seamless single continuous window: `renderer.run()`'s render
loop blocks until its canvas closes (`RenderCanvas.close()`), so
choosing an option here closes the launcher's window and `main()` (this
module's own, or `client/main.py`'s) then calls into
`area_viewer.run()`/`run_preview()`, which opens a fresh window. Same
process, same Python call stack, no subprocess -- just not one window
object reused across the transition, since `renderer.py`'s blocking
run-loop design doesn't support swapping what's being drawn into an
already-open window mid-loop.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.independant_logger import Logger

logger = Logger(
    log_name="launcher",
    log_file="launcher.log",
    log_level=20,
).get_logger()

from imgui_bundle import imgui
from wgpu.utils.imgui import ImguiRenderer

from client.engine import imgui_wgpu_compat  # noqa: F401
from client.engine import renderer
from client.engine.asset_loader import asset_loader

# A single small local settings file for "last opened" -- best-effort,
# not a full recent-files list (Step 3 task 2: "one 'last opened' entry
# is enough for 'easy to use'").
EDITOR_STATE_PATH = REPO_ROOT / "client" / ".editor_state.json"

_CATEGORY_TO_ASSET_TYPE = {"meshes": "mesh", "entities": "entity", "materials": "material"}


def _load_last_opened() -> "dict | None":
    if not EDITOR_STATE_PATH.exists():
        return None
    try:
        return json.loads(EDITOR_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _save_last_opened(kind: str, key: str) -> None:
    try:
        EDITOR_STATE_PATH.write_text(
            json.dumps({"kind": kind, "key": key}), encoding="utf-8"
        )
    except OSError:
        pass


class LauncherResult:
    """What the user chose. `action` is one of 'open_area'/'new_area'/
    'view_asset'/None (window closed with nothing chosen -- quit).
    """

    def __init__(self) -> None:
        self.action: "str | None" = None
        self.area_path: "str | None" = None
        self.default_lighting = False
        self.asset_id: "str | None" = None
        self.asset_type: "str | None" = None


def run() -> LauncherResult:
    """Show the launcher window; blocks until the user picks something
    or closes the window. Returns the choice, if any.
    """
    asset_loader.load_manifest()
    result = LauncherResult()
    last_opened = _load_last_opened()

    logger.info("Opening launcher...")
    renderer.init_renderer()
    imgui_renderer = ImguiRenderer(renderer.device, renderer.canvas)

    # **Real crash found via live interactive testing, fixed here**:
    # `gui()` runs *inside* `imgui_renderer.render()`'s own frame
    # bracket, before it's done submitting its own draw commands
    # against the current surface texture. Calling
    # `renderer.canvas.close()` synchronously from inside it destroys
    # that texture mid-submit ("Texture with '<Surface Texture>' label
    # has been destroyed", a wgpuQueueSubmit validation error). Same
    # pending-request pattern this codebase already established for
    # `imgui.open_popup()`'s own frame-bracket SIGSEGV (`client/game/
    # ui.py` on `legacy`): buttons below only ever set `result.action`;
    # `draw()` closes the canvas afterward, once the frame is done.

    # Search-bar text per list -- plain dict, mutated in place from
    # inside gui() same as `result` above (no `nonlocal` needed since
    # nothing ever rebinds the dict itself, only its contents).
    filters = {"areas": "", "meshes": "", "entities": "", "materials": ""}
    _LIST_SIZE = imgui.ImVec2(0, 220)

    def _filtered_sorted_keys(entries: dict, filter_text: str) -> list:
        needle = filter_text.lower()
        return sorted(k for k in entries.keys() if not needle or needle in k.lower())

    # Sized to comfortably fit both columns' fixed-height (220px) scroll
    # lists plus their search bars/headers -- found via a live user
    # report that the window opened too short. Root cause: imgui
    # persists window geometry to an imgui.ini next to the process's
    # cwd, and this window had been sized small back when it was a
    # single stacked column of buttons; that stale saved height then
    # silently overrode this frame's actual (much taller) content on
    # every later run. Fixed two ways together: an explicit size,
    # applied unconditionally (cond=0, i.e. every frame, not just
    # first-use) so this window's size is always deterministic; and
    # `no_saved_settings` so this window's geometry is never written to
    # (or read back from) imgui.ini at all, past or future.
    _WINDOW_SIZE = imgui.ImVec2(800, 560)

    def gui() -> None:
        imgui.set_next_window_size(_WINDOW_SIZE)
        imgui.begin("Launcher", flags=imgui.WindowFlags_.no_saved_settings)

        # Two columns (Step: "isn't sustainable as more areas/assets are
        # added" -- fixed-size scrollable child windows instead of an
        # ever-growing flat list): left = Continue + area functions,
        # right = View Asset, side by side via same_line() between two
        # begin_child()/end_child() blocks.
        imgui.begin_child("LauncherLeftColumn", imgui.ImVec2(360, 0))

        if last_opened and last_opened.get("kind") == "area":
            key = last_opened.get("key", "")
            if asset_loader.has(key) and imgui.button(f"Continue: {key}"):
                result.action = "open_area"
                result.area_path = str(REPO_ROOT / "frontend" / asset_loader.resolve(key))
            imgui.separator()

        imgui.text("Open Area")
        _, filters["areas"] = imgui.input_text("Search##area-search", filters["areas"])
        areas = asset_loader.list_category("areas")
        imgui.begin_child("AreaList", _LIST_SIZE, imgui.ChildFlags_.borders)
        for area_id in _filtered_sorted_keys(areas, filters["areas"]):
            # Real bug, found via live user report ("open buttons ...
            # but no labels"): imgui's `##` syntax hides everything
            # after it from display, using it only as a hidden
            # uniqueness suffix for the widget ID -- `f"Open##area-
            # {area_id}"` rendered as a bare "Open" button with the
            # actual area_id invisible. Fixed by putting area_id in the
            # visible part of the label instead.
            if imgui.button(f"Open {area_id}##area-{area_id}"):
                result.action = "open_area"
                result.area_path = str(REPO_ROOT / "frontend" / areas[area_id])
                _save_last_opened("area", area_id)
        imgui.end_child()

        imgui.separator()
        imgui.text("New Area")
        if imgui.button("Empty"):
            result.action = "new_area"
        imgui.same_line()
        if imgui.button("Empty with default lighting"):
            result.action = "new_area"
            result.default_lighting = True

        imgui.end_child()
        imgui.same_line()

        imgui.begin_child("LauncherRightColumn", imgui.ImVec2(360, 0))
        imgui.text("View Asset")
        if imgui.begin_tab_bar("ViewAssetTabs"):
            for category in ("meshes", "entities", "materials"):
                selected, _ = imgui.begin_tab_item(category.capitalize())
                if selected:
                    entries = asset_loader.list_category(category)
                    _, filters[category] = imgui.input_text(f"Search##{category}-search", filters[category])
                    imgui.begin_child(f"{category}List", _LIST_SIZE, imgui.ChildFlags_.borders)
                    for asset_id in _filtered_sorted_keys(entries, filters[category]):
                        if imgui.button(f"View {asset_id}##{category}-{asset_id}"):
                            result.action = "view_asset"
                            result.asset_id = asset_id
                            result.asset_type = _CATEGORY_TO_ASSET_TYPE[category]
                            _save_last_opened(result.asset_type, asset_id)
                    imgui.end_child()
                    imgui.end_tab_item()
            imgui.end_tab_bar()
        imgui.end_child()

        imgui.end()

    imgui_renderer.set_gui(gui)

    def draw() -> None:
        renderer._draw_frame()  # bare clear -- no scene to render in the launcher itself
        imgui_renderer.render()
        if result.action is not None:
            renderer.canvas.close()

    renderer.run(draw)
    logger.info(f"Launcher closed -- action={result.action}")
    return result


def main() -> None:
    """Standalone entry point (`python -m client.engine.launcher`) --
    shows the launcher, then boots whatever was chosen via
    `client.engine.area_viewer`/`client.engine.asset_preview`, looping
    back to the launcher screen afterward when that mode reports its own
    "back to launcher" affordance was used.

    Real bug, found via a live user report ("Clicking 'Return to
    launcher' after viewing a mesh just closes the asset preview window
    without returning to the launcher"): asset_preview.run() always
    correctly returned `back_to_launcher` (True when its "Back to
    Launcher" button was clicked, False on a plain window-close), but
    this function never looked at that return value or re-invoked run()
    -- it just fell through and the whole process exited either way, so
    the button's own label was a lie. Fixed by looping.
    """
    from client.engine import area_viewer, asset_preview

    while True:
        result = run()
        if result.action is None:
            return

        if result.action == "open_area":
            area_viewer.run(area_path=result.area_path, mode="builder")
            return
        elif result.action == "new_area":
            area_viewer.run(area_path=None, mode="builder")
            return
        elif result.action == "view_asset":
            back_to_launcher = asset_preview.run(
                asset_id=result.asset_id, asset_type=result.asset_type
            )
            if not back_to_launcher:
                return
            # else: loop back around to `run()` and show the launcher again.


if __name__ == "__main__":
    main()
