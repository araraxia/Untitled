"""2D UI-menu authoring editor, built directly on `client/engine/ui/`'s
real widget functions -- the live preview *is* the runtime appearance,
not separate editor chrome. Step 14 of
.github/prompts/level-editor.prompt.md.

Self-contained boot (own `renderer.init_renderer()`, own
`ImguiRenderer`), mirroring `area_viewer.py`'s pattern -- a 2D-only
screen-space viewport, no 3D raycasting needed at all (UI elements
never have a 3D mode).
"""

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.independant_logger import Logger

logger = Logger(
    log_name="ui_editor",
    log_file="ui_editor.log",
    log_level=20,
).get_logger()

from imgui_bundle import imgui
from wgpu.utils.imgui import ImguiRenderer

from client.engine import imgui_wgpu_compat  # noqa: F401
from client.engine import renderer
from client.engine.asset_loader import asset_loader
from client.engine.editor_commands import Command, EditorCommands
from client.engine.ui import draw, templates, theme as ui_theme, widgets
from client.engine.ui.nav import FocusManager

UI_MENU_DIR = REPO_ROOT / "frontend" / "assets" / "data" / "ui"

_ELEMENT_TYPES = ("panel", "label", "button", "image_button", "progress_bar")

_TRIGGER_TYPES = ("keybind", "zone", "entity_interact")


class MenuDocument:
    """The menu-authoring equivalent of `Scene` -- a flat list of
    elements (each `{"type", "rect": [[x0,y0],[x1,y1]], ...type-
    specific fields}`) plus a `triggers` dict. Reused as the "scene"
    `EditorCommands` wraps -- that class doesn't actually call any
    `Scene`-specific method, it just stores whatever's passed and lets
    command closures use it, so it works unmodified for menu documents
    too.
    """

    def __init__(self) -> None:
        self.menu_id = "untitled_menu"
        self.elements: dict[str, dict] = {}
        self.element_order: list[str] = []
        self.triggers: dict = {"show": [], "hide": []}

    def add_element(self, element_id: str, data: dict) -> None:
        self.elements[element_id] = dict(data)
        if element_id not in self.element_order:
            self.element_order.append(element_id)

    def update_element(self, element_id: str, patch: dict) -> None:
        if element_id in self.elements:
            self.elements[element_id].update(patch)

    def remove_element(self, element_id: str) -> None:
        self.elements.pop(element_id, None)
        if element_id in self.element_order:
            self.element_order.remove(element_id)

    def add_trigger(self, kind: str, trigger: dict) -> None:
        self.triggers.setdefault(kind, []).append(dict(trigger))

    def remove_trigger(self, kind: str, index: int) -> None:
        triggers = self.triggers.get(kind, [])
        if 0 <= index < len(triggers):
            triggers.pop(index)

    def to_json(self) -> dict:
        return {
            "menu_id": self.menu_id,
            "elements": [dict(self.elements[eid], id=eid) for eid in self.element_order],
            "triggers": self.triggers,
        }

    @classmethod
    def from_json(cls, data: dict) -> "MenuDocument":
        doc = cls()
        doc.menu_id = data.get("menu_id", "untitled_menu")
        for element in data.get("elements", []):
            element_id = element.get("id")
            if element_id:
                doc.add_element(element_id, {k: v for k, v in element.items() if k != "id"})
        doc.triggers = data.get("triggers", {"show": [], "hide": []})
        return doc


def add_ui_element_command(doc: MenuDocument, element_id: str, data: dict) -> Command:
    data = dict(data)
    return Command(
        do=lambda: doc.add_element(element_id, dict(data)),
        undo=lambda: doc.remove_element(element_id),
        label=f"Add element {element_id}",
    )


def remove_ui_element_command(doc: MenuDocument, element_id: str, data: dict) -> Command:
    data = dict(data)
    return Command(
        do=lambda: doc.remove_element(element_id),
        undo=lambda: doc.add_element(element_id, dict(data)),
        label=f"Remove element {element_id}",
    )


def update_ui_element_command(doc: MenuDocument, element_id: str, old_patch: dict, new_patch: dict) -> Command:
    old_patch, new_patch = dict(old_patch), dict(new_patch)
    return Command(
        do=lambda: doc.update_element(element_id, dict(new_patch)),
        undo=lambda: doc.update_element(element_id, dict(old_patch)),
        label=f"Edit element {element_id}",
    )


def add_trigger_command(doc: MenuDocument, kind: str, trigger: dict) -> Command:
    trigger = dict(trigger)
    index_holder = {}

    def _do():
        doc.triggers.setdefault(kind, []).append(dict(trigger))
        index_holder["index"] = len(doc.triggers[kind]) - 1

    def _undo():
        idx = index_holder.get("index")
        if idx is not None:
            doc.remove_trigger(kind, idx)

    return Command(do=_do, undo=_undo, label=f"Add {kind} trigger")


def remove_trigger_command(doc: MenuDocument, kind: str, index: int, trigger: dict) -> Command:
    trigger = dict(trigger)
    return Command(
        do=lambda: doc.remove_trigger(kind, index),
        undo=lambda: doc.triggers.setdefault(kind, []).insert(index, dict(trigger)),
        label=f"Remove {kind} trigger",
    )


def _generate_element_id(doc: MenuDocument, element_type: str) -> str:
    n = 1
    while f"{element_type}_{n}" in doc.elements:
        n += 1
    return f"{element_type}_{n}"


def _rect_contains(point, rect) -> bool:
    (x0, y0), (x1, y1) = rect
    return x0 <= point[0] <= x1 and y0 <= point[1] <= y1


def _draw_live_preview(ctx, nav: FocusManager, theme, doc: MenuDocument, selected_id: "str | None") -> None:
    """Render every element via its real `client/engine/ui/widgets.py`
    function -- what you see while editing is what the menu actually
    looks like at runtime, per Step 14 task 3.
    """
    for element_id in doc.element_order:
        element = doc.elements[element_id]
        rect = element.get("rect", [[0, 0], [100, 30]])
        p_min, p_max = tuple(rect[0]), tuple(rect[1])
        element_type = element.get("type", "panel")

        if element_type == "panel":
            widgets.panel(ctx, p_min, p_max, theme)
        elif element_type == "label":
            widgets.label(ctx, p_min, element.get("text", ""), theme, font_key=element.get("font_key", "body"))
        elif element_type == "button":
            widgets.button(ctx, nav, element_id, p_min, p_max, element.get("text", "Button"), theme)
        elif element_type == "progress_bar":
            widgets.progress_bar(ctx, p_min, p_max, 0.6, theme)
        # image_button needs a real texture_view -- skipped in the live
        # preview if no asset is assigned yet (drawn as a panel
        # placeholder instead), never a crash on an incomplete element.
        elif element_type == "image_button":
            widgets.panel(ctx, p_min, p_max, theme, bg_key="surface")
            widgets.label(ctx, p_min, "[image_button]", theme, size=12.0)

        if element_id == selected_id:
            draw_list = imgui.get_foreground_draw_list()
            from client.engine.gizmo import pack_color, to_imvec2

            draw_list.add_rect(to_imvec2(p_min), to_imvec2(p_max), pack_color((255, 210, 60), 255), 0.0, 0, 2.0)


def _draw_property_panel(doc: MenuDocument, commands: EditorCommands, selected_id: "str | None") -> None:
    if selected_id is None or selected_id not in doc.elements:
        return
    element = doc.elements[selected_id]
    imgui.begin("Element Properties")
    imgui.text(f"id: {selected_id}  type: {element.get('type')}")

    # Same bug class as area_viewer.py's property panel, found by the
    # same audit pass: is_item_deactivated_after_edit() only reflects
    # the immediately preceding widget -- checking it once after four
    # separate input_float() calls only ever saw y1's state, so editing
    # x0/y0/x1 alone and tabbing away was silently lost (no live-write
    # fallback existed here at all, unlike area_viewer's position
    # fields, which at least masked the bug with a live-sync branch).
    # Fixed by checking deactivation immediately after each widget and
    # OR-ing the results, plus adding the live-sync else branch so
    # typing is visible immediately, not just on commit.
    rect = element.get("rect", [[0, 0], [100, 30]])
    p_min, p_max = list(rect[0]), list(rect[1])
    rect_deactivated = False
    for i, label_text in enumerate(("x0", "y0")):
        _, p_min[i] = imgui.input_float(label_text, p_min[i])
        rect_deactivated = rect_deactivated or imgui.is_item_deactivated_after_edit()
    for i, label_text in enumerate(("x1", "y1")):
        _, p_max[i] = imgui.input_float(label_text, p_max[i])
        rect_deactivated = rect_deactivated or imgui.is_item_deactivated_after_edit()

    if rect_deactivated and [p_min, p_max] != rect:
        commands.execute(update_ui_element_command(doc, selected_id, {"rect": rect}, {"rect": [p_min, p_max]}))
    else:
        doc.elements[selected_id]["rect"] = [list(p_min), list(p_max)]

    if element.get("type") in ("label", "button"):
        text = element.get("text", "")
        _, new_text = imgui.input_text("text", text)
        if imgui.is_item_deactivated_after_edit() and new_text != text:
            commands.execute(update_ui_element_command(doc, selected_id, {"text": text}, {"text": new_text}))

    imgui.end()


def _draw_trigger_panel(doc: MenuDocument, commands: EditorCommands, state: dict) -> None:
    imgui.begin("Triggers")
    for kind in ("show", "hide"):
        imgui.text(f"{kind.capitalize()} triggers")
        for i, trigger in enumerate(list(doc.triggers.get(kind, []))):
            imgui.text(f"  {i}: {trigger}")
            if imgui.button(f"Remove##{kind}-{i}"):
                commands.execute(remove_trigger_command(doc, kind, i, trigger))

        buffer_key = f"new_trigger_type_{kind}"
        chosen = state.get(buffer_key, _TRIGGER_TYPES[0])
        _, idx = imgui.combo(f"##{buffer_key}", _TRIGGER_TYPES.index(chosen), list(_TRIGGER_TYPES))
        chosen = _TRIGGER_TYPES[idx]
        state[buffer_key] = chosen

        key_buffer_key = f"new_trigger_key_{kind}"
        _, state[key_buffer_key] = imgui.input_text(f"key/id##{kind}", state.get(key_buffer_key, ""))

        if imgui.button(f"+ Add {kind} trigger"):
            value = state.get(key_buffer_key, "")
            if chosen == "keybind":
                trigger = {"type": "keybind", "key": value}
            elif chosen == "zone":
                trigger = {"type": "zone", "zone_id": value, "on": "enter"}
            else:
                trigger = {"type": "entity_interact", "entity_id": value}
            commands.execute(add_trigger_command(doc, kind, trigger))
        imgui.separator()
    imgui.end()


def run(menu_id: "str | None" = None) -> None:
    asset_loader.load_manifest()

    doc = MenuDocument()
    if menu_id:
        path = UI_MENU_DIR / f"menu-{menu_id}.json"
        if path.exists():
            doc = MenuDocument.from_json(json.loads(path.read_text(encoding="utf-8")))
        else:
            doc.menu_id = menu_id

    commands = EditorCommands(doc)

    renderer.init_renderer()
    imgui_renderer = ImguiRenderer(renderer.device, renderer.canvas)
    draw.init(imgui_renderer)

    if not asset_loader.has("ui_theme"):
        asset_loader.register("ui_theme", "assets/data/ui_theme.json")
    theme = ui_theme.load_theme(renderer.device, "ui_theme")
    nav = FocusManager()

    editor_state = {
        "selected_id": None,
        "dragging": False,
        "resizing": False,
        "drag_offset": (0.0, 0.0),
        "new_element_type": _ELEMENT_TYPES[0],
        "status_message": "",
    }

    def on_pointer_down(event: dict) -> None:
        if event.get("button") != 1:
            return
        io = imgui.get_io()
        if io.want_capture_mouse:
            return
        point = (event["x"], event["y"])
        hit = None
        for element_id in reversed(doc.element_order):
            rect = doc.elements[element_id].get("rect", [[0, 0], [0, 0]])
            if _rect_contains(point, rect):
                hit = element_id
                break
        editor_state["selected_id"] = hit
        if hit is not None:
            p_max = doc.elements[hit]["rect"][1]
            if abs(point[0] - p_max[0]) < 10 and abs(point[1] - p_max[1]) < 10:
                editor_state["resizing"] = True
            else:
                editor_state["dragging"] = True
            editor_state["drag_start_rect"] = [list(c) for c in doc.elements[hit]["rect"]]
            editor_state["drag_start_point"] = point

    def on_pointer_move(event: dict) -> None:
        if editor_state["selected_id"] is None or not (editor_state["dragging"] or editor_state["resizing"]):
            return
        element_id = editor_state["selected_id"]
        if element_id not in doc.elements:
            return
        point = (event["x"], event["y"])
        start_point = editor_state["drag_start_point"]
        start_rect = editor_state["drag_start_rect"]
        dx = point[0] - start_point[0]
        dy = point[1] - start_point[1]

        if editor_state["dragging"]:
            new_rect = [[start_rect[0][0] + dx, start_rect[0][1] + dy], [start_rect[1][0] + dx, start_rect[1][1] + dy]]
        else:
            new_rect = [list(start_rect[0]), [start_rect[1][0] + dx, start_rect[1][1] + dy]]
        doc.elements[element_id]["rect"] = new_rect

    def on_pointer_up(event: dict) -> None:
        if event.get("button") != 1:
            return
        if editor_state["dragging"] or editor_state["resizing"]:
            element_id = editor_state["selected_id"]
            if element_id in doc.elements:
                new_rect = [list(c) for c in doc.elements[element_id]["rect"]]
                old_rect = editor_state["drag_start_rect"]
                if new_rect != old_rect:
                    commands.execute(update_ui_element_command(doc, element_id, {"rect": old_rect}, {"rect": new_rect}))
        editor_state["dragging"] = False
        editor_state["resizing"] = False

    renderer.canvas.add_event_handler(on_pointer_down, "pointer_down")
    renderer.canvas.add_event_handler(on_pointer_move, "pointer_move")
    renderer.canvas.add_event_handler(on_pointer_up, "pointer_up")

    def gui() -> None:
        imgui.begin("UI Menu Editor")
        imgui.text(f"menu_id: {doc.menu_id}")
        _, type_idx = imgui.combo(
            "Add type", _ELEMENT_TYPES.index(editor_state["new_element_type"]), list(_ELEMENT_TYPES)
        )
        editor_state["new_element_type"] = _ELEMENT_TYPES[type_idx]
        if imgui.button("Add Element"):
            element_type = editor_state["new_element_type"]
            element_id = _generate_element_id(doc, element_type)
            data = {"type": element_type, "rect": [[40, 40], [200, 80]]}
            if element_type in ("label", "button"):
                data["text"] = element_type.capitalize()
            commands.execute(add_ui_element_command(doc, element_id, data))
            editor_state["selected_id"] = element_id

        if editor_state["selected_id"] and imgui.button("Delete Selected"):
            element_id = editor_state["selected_id"]
            data = dict(doc.elements.get(element_id, {}))
            commands.execute(remove_ui_element_command(doc, element_id, data))
            editor_state["selected_id"] = None

        if imgui.button("Save"):
            UI_MENU_DIR.mkdir(parents=True, exist_ok=True)
            path = UI_MENU_DIR / f"menu-{doc.menu_id}.json"
            path.write_text(json.dumps(doc.to_json(), indent=2), encoding="utf-8")
            editor_state["status_message"] = f"Saved to {path}"

        if editor_state["status_message"]:
            imgui.text_wrapped(editor_state["status_message"])
        imgui.end()

        _draw_property_panel(doc, commands, editor_state["selected_id"])
        _draw_trigger_panel(doc, commands, editor_state)

        # **Real bug fixed here (2026-08-22, found via a live crash
        # report)**: `draw.begin_frame()`/`_draw_live_preview()`
        # (which reaches `imgui.get_foreground_draw_list()` for the
        # selection outline) were originally called from a separate
        # `draw_frame()` function *before* `imgui_renderer.render()` --
        # i.e. outside the imgui frame bracket entirely
        # (`imgui.new_frame()` ... `imgui.render()`, which
        # `imgui_renderer.render()` establishes around calling this
        # `gui()` function). `run_ui_test.py`'s already-verified
        # pattern calls `draw.begin_frame()` from inside its `gui()`
        # callback for exactly this reason -- this file didn't follow
        # it. Moved here to match.
        ctx = draw.begin_frame()
        nav.begin_frame()
        _draw_live_preview(ctx, nav, theme, doc, editor_state["selected_id"])
        nav.end_frame()

    imgui_renderer.set_gui(gui)

    def draw_frame() -> None:
        renderer._draw_frame()
        imgui_renderer.render()

    renderer.run(draw_frame)
    logger.info("UI menu editor closed.")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--menu", default=None, help="menu_id to load, or omit for a new blank menu.")
    args = parser.parse_args()
    run(menu_id=args.menu)


if __name__ == "__main__":
    main()
