"""JSON-driven UI theme: colors, fonts, and skin images -- the single
source of "what does this UI look like" for anything built with
client/engine/ui/. This module only loads and caches them; draw.py is
what actually draws with them.

Expected theme JSON shape (see frontend/assets/data/ui_theme.json for a
real example)::

    {
      "colors": {"accent": [0.91, 0.27, 0.38, 1.0], ...},
      "fonts": {"body": {"path": "assets/fonts/body.ttf", "size": 16}},
      "skins": {"panel_bg": "ui_panel_bg"}
    }

`fonts` is optional -- omit it (or leave it `{}`) if no custom font
asset exists yet; widgets.py falls back to imgui's own default font
rather than drawing nothing. `skins` values are asset-loader keys
(resolved via AssetLoader, same as any other image asset), not raw paths.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Optional

import wgpu
from imgui_bundle import imgui
from PIL import Image

from client.engine.asset_loader import FRONTEND_DIR, asset_loader
from client.engine.ui.draw import Color

if TYPE_CHECKING:
    pass


class Theme:
    """A loaded theme: named colors, named fonts, named skin textures."""

    def __init__(self) -> None:
        self.colors: Dict[str, Color] = {}
        self._fonts: Dict[str, "imgui.ImFont"] = {}
        self._skin_views: Dict[str, "wgpu.GPUTextureView"] = {}

    def color(self, key: str, default: Color = (1.0, 1.0, 1.0, 1.0)) -> Color:
        return self.colors.get(key, default)

    def font(self, key: str) -> "imgui.ImFont | None":
        """Return the loaded font, or None if this theme doesn't define
        one under *key* -- widgets.label() falls back to imgui's current
        default font in that case, it does not fail."""
        return self._fonts.get(key)

    def skin_view(self, key: str) -> "wgpu.GPUTextureView | None":
        return self._skin_views.get(key)


def load_theme(device, asset_id: str) -> Theme:
    """Load a theme JSON asset (resolved via AssetLoader) and upload its
    skin images. Call once at startup (or on an explicit theme switch),
    never per-frame -- texture/font creation is real GPU/CPU work.

    Font loading happens through imgui's own font atlas
    (imgui.get_io().fonts) -- per Dear ImGui's own contract, prefer
    loading every font a session will ever need up front, before the
    render loop's first frame, rather than adding fonts mid-session.
    """
    path = FRONTEND_DIR / asset_loader.resolve(asset_id)
    data = json.loads(path.read_text(encoding="utf-8"))

    theme = Theme()

    for key, value in data.get("colors", {}).items():
        theme.colors[key] = tuple(float(c) for c in value)

    fonts_atlas = imgui.get_io().fonts
    for key, font_spec in data.get("fonts", {}).items():
        font_path = FRONTEND_DIR / font_spec["path"]
        if not font_path.exists():
            print(f"[ui.theme] Font not found, skipping: {font_path}")
            continue
        theme._fonts[key] = fonts_atlas.add_font_from_file_ttf(
            str(font_path), float(font_spec.get("size", 16))
        )

    for key, image_key in data.get("skins", {}).items():
        try:
            image_path = FRONTEND_DIR / asset_loader.resolve(image_key)
        except ValueError as err:
            print(f"[ui.theme] Cannot resolve skin '{image_key}': {err}")
            continue
        if not image_path.exists():
            print(f"[ui.theme] Skin image not found, skipping: {image_path}")
            continue
        theme._skin_views[key] = _load_skin_texture(device, image_path)

    return theme


def _load_skin_texture(device, path: Path) -> "wgpu.GPUTextureView":
    """Upload a plain RGBA image as a wgpu texture and return a *stable*
    view (created once, here) -- same identity-must-stay-stable
    requirement as GPUSpriteSheet.albedo_texture_view/Panel3D.texture_view,
    for draw.py's texture-registration cache.
    """
    image = Image.open(path).convert("RGBA")
    width, height = image.size
    pixels = image.tobytes()

    texture = device.create_texture(
        size=(width, height, 1),
        format="rgba8unorm",
        usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST,
    )
    device.queue.write_texture(
        {"texture": texture},
        pixels,
        {"bytes_per_row": width * 4, "rows_per_image": height},
        (width, height, 1),
    )
    return texture.create_view()
