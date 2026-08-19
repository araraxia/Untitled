"""Compatibility shim for a confirmed upstream bug in `wgpu`'s bundled
imgui backend, hit while wiring up Step 15
(.github/prompts/wgpu-py-migration.prompt.md)'s real render integration.

`wgpu.utils.imgui.imgui_backend.ImguiWgpuBackend.render()` reads
`draw_data.cmd_lists_count`, an attribute imgui-bundle removed in its
1.92.0 rewrite (Dear ImGui's own font/texture system overhaul) in
favor of `len(draw_data.cmd_lists)`. Against this project's pinned
`wgpu==0.32.0` + `imgui-bundle==1.92.900`, that raises a real
`AttributeError` on the very first rendered frame -- not specific to
this project's setup, confirmed as an upstream issue already filed
against both of those exact versions: pygfx/wgpu-py#829, with an
open, not-yet-merged fix in pygfx/wgpu-py#830 (same one-line change
applied here).

Import this module once, before constructing any
`wgpu.utils.imgui.ImguiRenderer` (see client/main.py) -- it patches
`imgui.ImDrawData` at the class level so the property exists
regardless of which code path reads it.

Delete this file (and its one import in client/main.py) once
pygfx/wgpu-py#830 ships in a released `wgpu` version and
`requirements.txt` is bumped to it -- check whether
`hasattr(imgui.ImDrawData, 'cmd_lists_count')` is already True before
assuming this is still needed.
"""

from imgui_bundle import imgui

if not hasattr(imgui.ImDrawData, "cmd_lists_count"):
    imgui.ImDrawData.cmd_lists_count = property(lambda self: len(self.cmd_lists))
