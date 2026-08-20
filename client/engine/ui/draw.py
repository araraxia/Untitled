"""Custom UI drawing primitives -- thin wrappers around imgui's
ImDrawList API plus the wgpu-texture-to-imgui bridge.

Every visual element in client/engine/ui/ ends up as a call into this
module: a filled rect, a line of text in a loaded font, or an image
backed by a wgpu texture (static skin art, a spritesheet-frame sub-rect,
or a live render-to-texture panel3d.Panel3D -- all three go through the
same image() call, just with different textures/uv rects behind them).

**Hard rule, confirmed in this codebase, not a style preference**:
`client/game/ui.py` (legacy branch)'s module docstring documents a real,
reproduced SIGSEGV from calling `imgui.open_popup()` outside the
`new_frame()`/`render()` bracket -- the same wgpu/imgui-bundle backend
pairing this module draws through. Every function below (and the
`UIDrawContext` object begin_frame() hands out) must only be called from
inside that bracket, i.e. from client/main.py's per-frame UI callback (or
anything it calls synchronously), never from a GLFW event handler or any
other out-of-frame code path. If something needs to be triggered from an
input callback, record a pending request and act on it from inside the
frame (the same pattern client/game/ui.py already established for
popups) -- don't call anything in this module directly from a callback.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Tuple

from imgui_bundle import imgui

if TYPE_CHECKING:
    import wgpu

# (r, g, b, a), each 0.0-1.0 -- matches Theme.color()'s return shape.
Color = Tuple[float, float, float, float]

Point = Tuple[float, float]


def pack_color(color: Color) -> int:
    """Pack an (r, g, b, a) 0.0-1.0 tuple into imgui's packed ImU32, the
    type every ImDrawList add_* color parameter expects."""
    return imgui.color_convert_float4_to_u32(imgui.ImVec4(*color))


class _TextureRegistry:
    """Caches wgpu texture views -> imgui.ImTextureRef so callers never
    call imgui_renderer.backend.register_texture() directly.

    Keyed by id(texture_view) -- the same identity register_texture()
    itself keys on internally (wgpu/utils/imgui/imgui_backend.py:110).
    This means the *same* GPUTextureView object must be passed every
    frame for a given visual (GPUSpriteSheet.albedo_texture_view and
    Panel3D.texture_view are both designed to hand back a cached, stable
    view rather than a fresh one each call, specifically so this
    registry doesn't re-register -- and leak -- a "new" texture every
    single frame).
    """

    def __init__(self, imgui_renderer) -> None:
        self._backend = imgui_renderer.backend
        self._refs: Dict[int, "imgui.ImTextureRef"] = {}

    def get_ref(self, texture_view: "wgpu.GPUTextureView") -> "imgui.ImTextureRef":
        key = id(texture_view)
        ref = self._refs.get(key)
        if ref is None:
            ref = self._backend.register_texture(texture_view)
            self._refs[key] = ref
        return ref

    def release(self, texture_view: "wgpu.GPUTextureView") -> None:
        """Call when a texture view is being destroyed (e.g. Panel3D.resize()
        replacing its texture) so the stale registration doesn't linger."""
        key = id(texture_view)
        ref = self._refs.pop(key, None)
        if ref is not None:
            self._backend.unregister_texture(ref)


_registry: "_TextureRegistry | None" = None


def init(imgui_renderer) -> None:
    """One-time setup. Call once during client startup, right after
    ImguiRenderer is constructed (see client/main.py) -- everything else
    in this module (and package) requires this to have run first.
    """
    global _registry
    _registry = _TextureRegistry(imgui_renderer)


def release_texture(texture_view: "wgpu.GPUTextureView") -> None:
    """Unregister a texture view that's about to be destroyed. See
    _TextureRegistry.release's docstring."""
    if _registry is not None:
        _registry.release(texture_view)


class UIDrawContext:
    """A draw surface for the current frame. Only ever constructed by
    begin_frame() below -- never instantiate this directly.
    """

    __slots__ = ("_draw_list",)

    def __init__(self, draw_list) -> None:
        self._draw_list = draw_list

    # -- primitives ------------------------------------------------------

    def rect(self, p_min: Point, p_max: Point, color: Color, rounding: float = 0.0) -> None:
        self._draw_list.add_rect_filled(
            imgui.ImVec2(*p_min), imgui.ImVec2(*p_max), pack_color(color), rounding
        )

    def rect_border(
        self, p_min: Point, p_max: Point, color: Color, rounding: float = 0.0, thickness: float = 1.0
    ) -> None:
        self._draw_list.add_rect(
            imgui.ImVec2(*p_min), imgui.ImVec2(*p_max), pack_color(color), rounding, thickness=thickness
        )

    def circle(
        self, center: Point, radius: float, color: Color, filled: bool = True, segments: int = 0
    ) -> None:
        if filled:
            self._draw_list.add_circle_filled(imgui.ImVec2(*center), radius, pack_color(color), segments)
        else:
            self._draw_list.add_circle(imgui.ImVec2(*center), radius, pack_color(color), segments)

    def line(self, p1: Point, p2: Point, color: Color, thickness: float = 1.0) -> None:
        self._draw_list.add_line(imgui.ImVec2(*p1), imgui.ImVec2(*p2), pack_color(color), thickness)

    def text(
        self,
        font,
        size: float,
        pos: Point,
        color: Color,
        text: str,
        wrap_width: float = 0.0,
    ) -> None:
        """Draw *text* in an explicit font/size -- the confirmed 7-arg
        add_text overload, which needs no push_font()/pop_font() around
        it (unlike drawing through imgui's own widgets)."""
        self._draw_list.add_text(
            font, size, imgui.ImVec2(*pos), pack_color(color), text, wrap_width=wrap_width
        )

    def image(
        self,
        texture_view: "wgpu.GPUTextureView",
        p_min: Point,
        p_max: Point,
        uv_min: Point = (0.0, 0.0),
        uv_max: Point = (1.0, 1.0),
        tint: Color = (1.0, 1.0, 1.0, 1.0),
    ) -> None:
        """Draw a wgpu texture as an image -- static skin art, a
        spritesheet sub-rect (via uv_min/uv_max), or a Panel3D render
        target. Registered with imgui's texture backend on first use,
        reused every frame after -- callers never touch ImTextureRef
        directly. See _TextureRegistry's docstring for the identity
        requirement this depends on.
        """
        if _registry is None:
            raise RuntimeError(
                "client.engine.ui.draw.init() was never called -- "
                "call it once after constructing ImguiRenderer."
            )
        ref = _registry.get_ref(texture_view)
        self._draw_list.add_image(
            ref,
            imgui.ImVec2(*p_min),
            imgui.ImVec2(*p_max),
            imgui.ImVec2(*uv_min),
            imgui.ImVec2(*uv_max),
            pack_color(tint),
        )

    # -- hit-testing -------------------------------------------------------
    # Manual, imgui-widget-free hover/click detection -- see module
    # docstring: everything here reads live imgui IO state, safe only
    # inside the frame bracket, same as the drawing methods above.

    @staticmethod
    def mouse_pos() -> Point:
        p = imgui.get_mouse_pos()
        return (p.x, p.y)

    @staticmethod
    def hovering(p_min: Point, p_max: Point) -> bool:
        return imgui.is_mouse_hovering_rect(imgui.ImVec2(*p_min), imgui.ImVec2(*p_max))

    @staticmethod
    def clicked(button: int = 0) -> bool:
        return imgui.is_mouse_clicked(button)

    @staticmethod
    def released(button: int = 0) -> bool:
        return imgui.is_mouse_released(button)


def begin_frame(surface: str = "background") -> UIDrawContext:
    """Return a UIDrawContext for this frame.

    Must be called every frame from inside the imgui new_frame()/
    render() bracket (client/main.py's per-frame UI callback).

    Args:
        surface: 'background' (default) draws behind every imgui window/
            widget -- correct for a UI layer that owns the whole screen,
            which is the point of this package. 'foreground' draws in
            front of everything (cursors, tooltips). 'window' draws
            inside whatever imgui window is currently open -- rarely
            needed here, since this system deliberately avoids imgui's
            own window chrome.
    """
    if surface == "foreground":
        draw_list = imgui.get_foreground_draw_list()
    elif surface == "window":
        draw_list = imgui.get_window_draw_list()
    else:
        draw_list = imgui.get_background_draw_list()
    return UIDrawContext(draw_list)
