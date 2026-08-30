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

import hashlib
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
from client.engine.asset_loader import FRONTEND_DIR, asset_loader

# A single small local settings file for "last opened" -- best-effort,
# not a full recent-files list (Step 3 task 2: "one 'last opened' entry
# is enough for 'easy to use'").
EDITOR_STATE_PATH = REPO_ROOT / "client" / ".editor_state.json"

MANIFEST_PATH = FRONTEND_DIR / "assets" / "manifest.json"

_CATEGORY_TO_ASSET_TYPE = {"meshes": "mesh", "entities": "entity", "materials": "material"}


def _delete_asset(category: str, asset_id: str) -> None:
    """Permanently delete *asset_id*'s underlying file and its
    manifest.json entry, then drop it from the loader's in-memory
    state so it disappears from the list immediately. Called only
    after the user confirms via the "Confirm Delete" modal in gui() --
    this function itself does not ask.
    """
    try:
        full_path = FRONTEND_DIR / asset_loader.resolve(asset_id)
        full_path.unlink(missing_ok=True)
    except (OSError, ValueError):
        pass

    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = None
    if isinstance(manifest, dict) and isinstance(manifest.get(category), dict):
        manifest[category].pop(asset_id, None)
        try:
            MANIFEST_PATH.write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass

    asset_loader.remove_entry(category, asset_id)


def _rename_asset(category: str, asset_id: str, new_id: str) -> "str | None":
    """Rename *asset_id* to *new_id*: rewrites the asset JSON's own
    "id" field (`tools/build_manifest.py`'s `json_asset_id()` is what
    later reads that field back as the manifest key), renames the
    underlying file to match, and rewrites its manifest.json entry
    under the new key. Only touches this one file -- does not scan
    other entities/areas for references to the old id, same
    proportional scope as `_delete_asset()` above.

    Returns an error message to show in the modal on failure, or None
    on success.
    """
    if not new_id:
        return "Name cannot be empty."
    if new_id == asset_id:
        return None
    if new_id in asset_loader.list_category(category):
        return f'"{new_id}" already exists.'

    try:
        rel_path = asset_loader.resolve(asset_id)
    except ValueError:
        return f'"{asset_id}" is no longer registered.'
    full_path = FRONTEND_DIR / rel_path

    try:
        data = json.loads(full_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"Could not read {full_path.name}: {exc}"
    if not isinstance(data, dict):
        return f"{full_path.name} is not a JSON object."

    new_path = full_path.with_name(f"{new_id}{full_path.suffix}")
    if new_path.exists():
        return f"A file named {new_path.name} already exists."

    data["id"] = new_id
    try:
        full_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        full_path.rename(new_path)
    except OSError as exc:
        return f"Rename failed: {exc}"

    new_rel_path = new_path.relative_to(FRONTEND_DIR).as_posix()
    new_hash = hashlib.sha256(new_path.read_bytes()).hexdigest()[:16]

    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = None
    entry = None
    if isinstance(manifest, dict) and isinstance(manifest.get(category), dict):
        entry = manifest[category].pop(asset_id, None)
        if entry is not None:
            entry["path"] = new_rel_path
            entry["hash"] = new_hash
            manifest[category][new_id] = entry
            try:
                MANIFEST_PATH.write_text(
                    json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
            except OSError:
                pass

    asset_loader.remove_entry(category, asset_id)
    asset_loader.add_entry(
        category, new_id, entry or {"path": new_rel_path, "hash": new_hash}
    )
    return None


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
    'view_asset'/'build_entity'/None (window closed with nothing
    chosen -- quit).
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
    _WINDOW_SIZE = imgui.ImVec2(944, 560)

    # Selected list item per asset category -- the View/Edit buttons
    # below each list act on whichever entry is currently selected,
    # replacing the old per-row View/Edit buttons.
    selected_asset = {"meshes": None, "entities": None, "materials": None}

    # Delete confirmation state. `request_open` is a one-shot flag:
    # imgui's own open_popup() docs say "don't call every frame", so
    # the Delete button only sets it True for the one frame it was
    # clicked, and the modal-drawing code below clears it right after
    # calling open_popup() -- both still run from inside gui(), i.e.
    # inside the same new_frame()/render() bracket, so this needs none
    # of the close()-style next-frame deferral described above; that
    # deferral is only for calls (like canvas.close()) that can't
    # happen mid-frame at all.
    pending_delete = {"category": None, "asset_id": None, "request_open": False}

    # Rename state -- same one-shot `request_open` flag as
    # pending_delete above, plus the in-progress text field value and
    # an error string shown in the modal on a failed attempt (name
    # taken, bad JSON, etc.) instead of closing it.
    pending_rename = {
        "category": None,
        "asset_id": None,
        "request_open": False,
        "new_name": "",
        "error": "",
    }

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

        imgui.begin_child("LauncherRightColumn", imgui.ImVec2(504, 0))
        imgui.text("View Asset")
        if imgui.button("New Entity"):
            result.action = "build_entity"
            result.asset_id = None
        if imgui.begin_tab_bar("ViewAssetTabs"):
            for category in ("meshes", "entities", "materials"):
                selected, _ = imgui.begin_tab_item(category.capitalize())
                if selected:
                    entries = asset_loader.list_category(category)
                    _, filters[category] = imgui.input_text(f"Search##{category}-search", filters[category])
                    imgui.begin_child(f"{category}List", _LIST_SIZE, imgui.ChildFlags_.borders)
                    for asset_id in _filtered_sorted_keys(entries, filters[category]):
                        is_selected = selected_asset[category] == asset_id
                        clicked, _ = imgui.selectable(
                            f"{asset_id}##{category}-{asset_id}", is_selected
                        )
                        if clicked:
                            selected_asset[category] = asset_id
                    imgui.end_child()

                    current = selected_asset[category]
                    if imgui.button(f"View##view-{category}") and current is not None:
                        result.action = "view_asset"
                        result.asset_id = current
                        result.asset_type = _CATEGORY_TO_ASSET_TYPE[category]
                        _save_last_opened(result.asset_type, current)
                    # Entity Builder (entity-builder.prompt.md Step
                    # 10) can only edit entity-*definition* JSON --
                    # meshes/materials don't have a `parts` array of
                    # their own to build, so this button is
                    # entities-only, unlike "View" above.
                    if category == "entities":
                        imgui.same_line()
                        if imgui.button(f"Edit##edit-{category}") and current is not None:
                            result.action = "build_entity"
                            result.asset_id = current
                        # Rename (like Edit) is entities-only for now --
                        # _rename_asset() itself works for any JSON-based
                        # category, but meshes/materials weren't asked for.
                        imgui.same_line()
                        if imgui.button(f"Rename##rename-{category}") and current is not None:
                            pending_rename["category"] = category
                            pending_rename["asset_id"] = current
                            pending_rename["new_name"] = current
                            pending_rename["error"] = ""
                            pending_rename["request_open"] = True
                    imgui.same_line()
                    if imgui.button(f"Delete##delete-{category}") and current is not None:
                        pending_delete["category"] = category
                        pending_delete["asset_id"] = current
                        pending_delete["request_open"] = True
                    imgui.end_tab_item()
            imgui.end_tab_bar()
        imgui.end_child()

        # Delete confirmation modal -- deliberately outside/after the
        # tab bar and both columns so it still renders regardless of
        # which asset tab is active. open_popup() itself must only be
        # called on the triggering frame (per imgui's own docs), hence
        # the one-shot `request_open` flag rather than an unconditional
        # call gated only on pending_delete["asset_id"].
        if pending_delete["request_open"]:
            imgui.open_popup("Confirm Delete##asset")
            pending_delete["request_open"] = False
        modal_open, _ = imgui.begin_popup_modal(
            "Confirm Delete##asset", flags=imgui.WindowFlags_.always_auto_resize
        )
        if modal_open:
            imgui.text(
                f"Delete \"{pending_delete['asset_id']}\"? "
                "This permanently deletes the file and cannot be undone."
            )
            imgui.separator()
            if imgui.button("Delete", imgui.ImVec2(120, 0)):
                _delete_asset(pending_delete["category"], pending_delete["asset_id"])
                selected_asset[pending_delete["category"]] = None
                pending_delete["category"] = None
                pending_delete["asset_id"] = None
                imgui.close_current_popup()
            imgui.same_line()
            if imgui.button("Cancel", imgui.ImVec2(120, 0)):
                pending_delete["category"] = None
                pending_delete["asset_id"] = None
                imgui.close_current_popup()
            imgui.end_popup()

        # Rename modal -- same one-shot open pattern as the delete
        # modal above.
        if pending_rename["request_open"]:
            imgui.open_popup("Rename Entity##asset")
            pending_rename["request_open"] = False
        rename_open, _ = imgui.begin_popup_modal(
            "Rename Entity##asset", flags=imgui.WindowFlags_.always_auto_resize
        )
        if rename_open:
            imgui.text(f"Rename \"{pending_rename['asset_id']}\" to:")
            _, pending_rename["new_name"] = imgui.input_text(
                "##rename-new-name", pending_rename["new_name"]
            )
            if pending_rename["error"]:
                imgui.text_colored(imgui.ImVec4(1.0, 0.4, 0.4, 1.0), pending_rename["error"])
            imgui.separator()
            if imgui.button("Rename", imgui.ImVec2(120, 0)):
                error = _rename_asset(
                    pending_rename["category"],
                    pending_rename["asset_id"],
                    pending_rename["new_name"].strip(),
                )
                if error:
                    pending_rename["error"] = error
                else:
                    selected_asset[pending_rename["category"]] = pending_rename["new_name"].strip()
                    pending_rename["category"] = None
                    pending_rename["asset_id"] = None
                    pending_rename["error"] = ""
                    imgui.close_current_popup()
            imgui.same_line()
            if imgui.button("Cancel", imgui.ImVec2(120, 0)):
                pending_rename["category"] = None
                pending_rename["asset_id"] = None
                pending_rename["error"] = ""
                imgui.close_current_popup()
            imgui.end_popup()

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
    from client.engine import area_viewer, asset_preview, entity_builder

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
        elif result.action == "build_entity":
            back_to_launcher = entity_builder.run(entity_id=result.asset_id)
            if not back_to_launcher:
                return
            # else: loop back around to `run()` and show the launcher again.


if __name__ == "__main__":
    main()
