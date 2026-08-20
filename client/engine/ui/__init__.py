"""client.engine.ui -- a fully custom-drawn, art-asset-skinned UI layer.

imgui-bundle is used only as the input/layout/frame-lifecycle engine
(hit-testing via is_mouse_hovering_rect/is_mouse_clicked, keyboard state
via is_key_pressed, the new_frame()/render() bracket) -- every visible
pixel is drawn through draw.py's ImDrawList wrappers, never imgui's own
widget chrome (no imgui.button()/imgui.begin() window borders). See
draw.py's module docstring for the one hard rule every module in this
package follows: nothing here is safe to call outside the imgui frame
bracket (confirmed SIGSEGV in this codebase's wgpu/imgui-bundle pairing
if violated, not a style preference -- see client/game/ui.py, only on
the legacy branch, for where that was first found).

Call init(imgui_renderer) once at startup, after ImguiRenderer is
constructed and before any other function in this package is used.
"""

from client.engine.ui.draw import init

__all__ = ["init"]
