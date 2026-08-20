"""Render-to-texture bridge: embed 3D-rendered content or a custom
screen-space shader effect inside a 2D UI panel.

Owns one offscreen wgpu texture (+ optional depth texture), a dedicated
render pass, and the resulting view -- handed to draw.py's image(),
itself backed by the confirmed wgpu.utils.imgui.ImguiWgpuBackend
texture-registration bridge (client/engine/renderer.py's own
create_scene_texture()/create_depth_texture() are the precedent this
follows: device.create_texture(..., usage=RENDER_ATTACHMENT|
TEXTURE_BINDING), reallocated on resize, never on the swapchain).

One instance per embedded panel -- a character preview, a shader effect
(the health orb), any future one. Not a singleton; each embedded 3D/
shader element in a UI screen owns its own Panel3D.
"""

from __future__ import annotations

from typing import Callable, Optional, Tuple

import wgpu

from client.engine import renderer
from client.engine.ui import draw

Color4 = Tuple[float, float, float, float]


class Panel3D:
    def __init__(
        self,
        device,
        width: int,
        height: int,
        depth: bool = True,
        format: "str | None" = None,
    ) -> None:
        """
        Args:
            format: GPUTextureFormat for the offscreen color texture.
                Defaults to renderer.canvas_format -- the format every
                existing render pipeline in this codebase (ShaderCache's
                sprite/material/mesh pipelines, all compiled against
                renderer.canvas_format) is validated against. A panel
                drawing through EntityRenderer.draw_entity_mesh_parts or any
                other shader_cache.py pipeline MUST use this default;
                only override it for a fully custom, self-contained
                pipeline compiled against a different format on purpose.
        """
        self._device = device
        self._format = format or renderer.canvas_format
        self._depth = depth
        self._width = 0
        self._height = 0
        self._texture: "wgpu.GPUTexture | None" = None
        self._view: "wgpu.GPUTextureView | None" = None
        self._depth_texture: "wgpu.GPUTexture | None" = None
        self.resize(width, height)

    @property
    def texture_view(self) -> "wgpu.GPUTextureView":
        """Stable across frames until the next resize() -- draw.py's
        texture-registration cache depends on this identity staying put
        (same requirement as GPUSpriteSheet.albedo_texture_view)."""
        return self._view

    def resize(self, width: int, height: int) -> None:
        """(Re)allocate the offscreen texture(s) at a new size. A no-op
        if the size hasn't actually changed. Releases the old view's
        imgui registration first (if one was ever registered) so a
        resized panel doesn't leave a stale registration behind.
        """
        if width == self._width and height == self._height and self._texture is not None:
            return

        if self._view is not None:
            draw.release_texture(self._view)
        if self._texture is not None:
            self._texture.destroy()
        if self._depth_texture is not None:
            self._depth_texture.destroy()

        self._width, self._height = width, height

        self._texture = self._device.create_texture(
            size=(width, height, 1),
            format=self._format,
            usage=wgpu.TextureUsage.RENDER_ATTACHMENT | wgpu.TextureUsage.TEXTURE_BINDING,
        )
        self._view = self._texture.create_view()

        if self._depth:
            self._depth_texture = self._device.create_texture(
                size=(width, height, 1),
                format="depth24plus",
                usage=wgpu.TextureUsage.RENDER_ATTACHMENT,
            )
        else:
            self._depth_texture = None

    def render(
        self,
        draw_fn: Callable[[object], None],
        clear_value: Color4 = (0.0, 0.0, 0.0, 0.0),
    ) -> "wgpu.GPUTextureView":
        """Run one render pass into this panel's offscreen texture and
        return its (stable) view, ready to hand to draw.UIDrawContext.image().

        Call once per frame, from inside the UI draw callback -- same
        frame-bracket rule as everything else in this package (the pass
        itself is a plain wgpu call, safe any time, but there's no
        reason to render a panel that isn't being drawn this frame).

        Args:
            draw_fn: Called with the pass_encoder; does the actual
                drawing. A character preview passes a closure calling
                client.engine.entity_renderer.EntityRenderer.draw_entity_mesh_parts(
                entity, camera, pass_encoder, definition); a shader
                effect (e.g. the health orb) passes a closure issuing its
                own pipeline's draw call against a quad vertex buffer.
        """
        command_encoder = self._device.create_command_encoder()

        depth_attachment = None
        if self._depth_texture is not None:
            depth_attachment = {
                "view": self._depth_texture.create_view(),
                "depth_clear_value": 1.0,
                "depth_load_op": "clear",
                "depth_store_op": "store",
            }

        pass_encoder = command_encoder.begin_render_pass(
            color_attachments=[
                {
                    "view": self._view,
                    "clear_value": clear_value,
                    "load_op": "clear",
                    "store_op": "store",
                }
            ],
            depth_stencil_attachment=depth_attachment,
        )
        draw_fn(pass_encoder)
        pass_encoder.end()

        self._device.queue.submit([command_encoder.finish()])
        return self._view

    def destroy(self) -> None:
        if self._view is not None:
            draw.release_texture(self._view)
            self._view = None
        if self._texture is not None:
            self._texture.destroy()
            self._texture = None
        if self._depth_texture is not None:
            self._depth_texture.destroy()
            self._depth_texture = None
