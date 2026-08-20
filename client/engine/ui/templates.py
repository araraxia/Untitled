"""Reusable, game-agnostic UI patterns built on widgets.py -- confirm/
deny dialogs, a scrolling text/chat log, a generic titled window.

Copy text, callbacks, and theme are always caller-supplied; nothing here
knows about any specific game's content, matching the engine/game
boundary this whole package sits on the engine side of.
"""

from __future__ import annotations

from typing import Callable, Optional, Sequence

from client.engine.ui import widgets
from client.engine.ui.draw import Point, UIDrawContext
from client.engine.ui.nav import FocusManager
from client.engine.ui.theme import Theme


def window(
    ctx: UIDrawContext,
    p_min: Point,
    p_max: Point,
    title: str,
    theme: Theme,
    body_fn: Optional[Callable[[], None]] = None,
) -> None:
    """A titled panel. body_fn, if given, is called right after the
    frame/title are drawn -- draw further content (buttons, text,
    images) inside it using the caller's own ctx/theme, positioned
    relative to p_min/p_max.
    """
    widgets.panel(ctx, p_min, p_max, theme)
    title_pos = (p_min[0] + 8, p_min[1] + 4)
    widgets.label(ctx, title_pos, title, theme, font_key="title")
    if body_fn is not None:
        body_fn()


def confirm_dialog(
    ctx: UIDrawContext,
    nav: FocusManager,
    element_id: str,
    p_min: Point,
    p_max: Point,
    message: str,
    theme: Theme,
    confirm_label: str = "Yes",
    cancel_label: str = "No",
) -> "str | None":
    """Draw a message + Yes/No buttons. Returns 'confirm', 'cancel', or
    None (nothing pressed this frame). Has no persistent state of its
    own beyond what nav/widgets already track by element_id -- the
    caller decides what happens next (close the dialog, etc.), same as
    every other function in this package.
    """
    widgets.panel(ctx, p_min, p_max, theme)

    message_pos = (p_min[0] + 12, p_min[1] + 12)
    widgets.label(
        ctx, message_pos, message, theme, wrap_width=(p_max[0] - p_min[0] - 24)
    )

    button_width = 80.0
    button_height = 28.0
    gap = 12.0
    button_y = p_max[1] - button_height - 12
    confirm_min = (p_max[0] - button_width * 2 - gap - 12, button_y)
    confirm_max = (confirm_min[0] + button_width, button_y + button_height)
    cancel_min = (p_max[0] - button_width - 12, button_y)
    cancel_max = (cancel_min[0] + button_width, button_y + button_height)

    if widgets.button(
        ctx, nav, f"{element_id}_confirm", confirm_min, confirm_max, confirm_label, theme
    ):
        return "confirm"
    if widgets.button(
        ctx, nav, f"{element_id}_cancel", cancel_min, cancel_max, cancel_label, theme
    ):
        return "cancel"
    if nav.consumed_back():
        return "cancel"
    return None


def chat_box(
    ctx: UIDrawContext,
    p_min: Point,
    p_max: Point,
    lines: Sequence[str],
    theme: Theme,
    font_key: str = "body",
    line_height: float = 20.0,
) -> None:
    """A scrolling, read-only text log -- draws as many of the most
    recent *lines* as fit the panel height, oldest at top. No input
    line/text entry here; that's a game-layer concern (wire an
    imgui.input_text or a custom-drawn field alongside this, per the
    actual game's chat UX) -- this is only the log display.
    """
    widgets.panel(ctx, p_min, p_max, theme)

    available_height = (p_max[1] - p_min[1]) - 16
    max_lines = max(1, int(available_height // line_height))
    visible = lines[-max_lines:]

    y = p_min[1] + 8
    for line in visible:
        widgets.label(
            ctx,
            (p_min[0] + 8, y),
            line,
            theme,
            font_key=font_key,
            wrap_width=(p_max[0] - p_min[0] - 16),
        )
        y += line_height
