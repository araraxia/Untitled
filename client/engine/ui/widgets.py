"""Composable, custom-drawn widgets built on draw.py + theme.py + nav.py.

Plain functions, not a class hierarchy -- each widget draws itself
through a UIDrawContext and reports its own interaction state
(hover/click/confirm) back to the caller. There is no persistent widget
object or retained tree, matching this codebase's existing immediate-mode
conventions (client/game/ui.py, character_creation.py, both legacy-branch
precedent): call the same function every frame, state lives in the
caller (or in nav.FocusManager for focus), not in a widget instance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Tuple

from imgui_bundle import imgui

from client.engine.ui.draw import Color, Point, UIDrawContext
from client.engine.ui.nav import FocusManager
from client.engine.ui.theme import Theme

if TYPE_CHECKING:
    import wgpu

Rect = Tuple[Point, Point]


def panel(
    ctx: UIDrawContext,
    p_min: Point,
    p_max: Point,
    theme: Theme,
    bg_key: str = "surface",
    border_key: str = "border",
    rounding: float = 4.0,
) -> None:
    """A themed rectangular background + border -- the base most other
    widgets draw on top of."""
    ctx.rect(p_min, p_max, theme.color(bg_key), rounding)
    ctx.rect_border(p_min, p_max, theme.color(border_key), rounding, thickness=2.0)


def label(
    ctx: UIDrawContext,
    pos: Point,
    text: str,
    theme: Theme,
    font_key: str = "body",
    color_key: str = "text",
    size: float = 16.0,
    wrap_width: float = 0.0,
) -> None:
    """Draw *text*. Falls back to imgui's current default font if the
    theme doesn't define font_key (rather than drawing nothing) --
    correct behaviour for a theme with no custom font asset registered
    yet, see theme.py's module docstring.
    """
    font = theme.font(font_key) or imgui.get_font()
    ctx.text(font, size, pos, theme.color(color_key), text, wrap_width)


def button(
    ctx: UIDrawContext,
    nav: FocusManager,
    element_id: str,
    p_min: Point,
    p_max: Point,
    label_text: str,
    theme: Theme,
    font_key: str = "body",
) -> bool:
    """Draw a themed button. Returns True the one frame it's activated
    -- a direct mouse click, or nav CONFIRM while it has focus. Register
    with nav before checking hover so a mouse hover correctly claims
    focus the same frame it happens (see FocusManager.hovering).
    """
    nav.register(element_id, (p_min, p_max))
    is_hovering = nav.hovering(element_id)
    is_focused = nav.is_focused(element_id)

    bg_key = "accent" if (is_hovering or is_focused) else "surface"
    panel(ctx, p_min, p_max, theme, bg_key=bg_key)

    text_pos = (p_min[0] + 8, p_min[1] + 6)
    label(ctx, text_pos, label_text, theme, font_key=font_key)

    clicked = is_hovering and ctx.clicked()
    confirmed = nav.consume_confirm(element_id)
    return clicked or confirmed


def image_button(
    ctx: UIDrawContext,
    nav: FocusManager,
    element_id: str,
    p_min: Point,
    p_max: Point,
    texture_view: "wgpu.GPUTextureView",
    theme: Theme,
    uv_min: Point = (0.0, 0.0),
    uv_max: Point = (1.0, 1.0),
) -> bool:
    """Same activation contract as button(), drawn as an image (an icon,
    a skin-art button face) with a themed focus/hover outline instead of
    a solid fill."""
    nav.register(element_id, (p_min, p_max))
    is_hovering = nav.hovering(element_id)
    is_focused = nav.is_focused(element_id)

    ctx.image(texture_view, p_min, p_max, uv_min, uv_max)
    if is_hovering or is_focused:
        ctx.rect_border(p_min, p_max, theme.color("accent"), thickness=2.0)

    clicked = is_hovering and ctx.clicked()
    confirmed = nav.consume_confirm(element_id)
    return clicked or confirmed


def progress_bar(
    ctx: UIDrawContext,
    p_min: Point,
    p_max: Point,
    fraction: float,
    theme: Theme,
    fill_key: str = "accent",
    bg_key: str = "surface",
    overlay_text: "str | None" = None,
) -> None:
    """A themed, custom-drawn fill bar (HP/AP/any 0-1 value). fraction is
    clamped to [0, 1]."""
    fraction = max(0.0, min(1.0, fraction))
    panel(ctx, p_min, p_max, theme, bg_key=bg_key)
    if fraction > 0:
        fill_max = (p_min[0] + (p_max[0] - p_min[0]) * fraction, p_max[1])
        ctx.rect(p_min, fill_max, theme.color(fill_key))
    if overlay_text:
        label(ctx, (p_min[0] + 6, p_min[1] + 2), overlay_text, theme)


def animated_icon(
    ctx: UIDrawContext,
    p_min: Point,
    p_max: Point,
    sheet,
    controller,
) -> None:
    """Draw the sprite sheet's current animation frame.

    Caller must have already called controller.update(delta_ms) this
    frame -- this function only reads .current_frame, it doesn't advance
    playback, matching AnimationController's own update()/draw split
    (client/engine/animation.py). sheet/controller are entity-free
    (client/engine/gpu_sprite_sheet.py's GPUSpriteSheet and
    client/engine/animation.py's AnimationController both work with no
    Entity reference at all) -- exactly why this is usable for a bouncing
    cursor or an animated icon with no fake game entity involved.
    """
    uv = sheet.get_uv_rect(controller.current_frame)
    ctx.image(sheet.albedo_texture_view, p_min, p_max, (uv[0], uv[1]), (uv[2], uv[3]))
