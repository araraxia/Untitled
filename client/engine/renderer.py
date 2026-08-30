"""GPU/window bootstrap and render loop coordinator.

Port of frontend/js/engine/renderer.js's device/canvas setup,
get_view_projection_matrix(), and the per-frame command-encoding
lifecycle -- Step 5 of .github/prompts/wgpu-py-migration.prompt.md.
Only the bootstrap/skeleton lands in this step: adapter/device request,
GLFW window + wgpu canvas, depth/scene texture creation, the camera
matrix helper, and a bare render loop that clears to a background
color. Entity/sprite/mesh/particle/lighting drawing is added in Steps
6-9 as those modules get ported.

Uses `rendercanvas` (a `wgpu` dependency, not chosen separately) for the
GLFW canvas -- confirmed via Step 1's audit that `wgpu.gui.glfw
.WgpuCanvas` no longer exists in wgpu 0.32; canvas creation now goes
through `rendercanvas.glfw.RenderCanvas`, and its render loop is
callback-driven (`canvas.request_draw(draw_function)` + `loop.run()`)
rather than a `requestAnimationFrame` polling loop or a bare `while
running:` loop -- the browser JS version's structure does not map
1:1 here, this is the one place in the port that's a real adaptation,
not a mechanical translation.
"""

import glfw
import wgpu
from rendercanvas.glfw import RenderCanvas, loop

from client.engine import mat4
from client.engine.lighting_pass import LightingPass

# Matches main.py's current PyWebView window defaults exactly (Step 5
# task 2) -- same size on first launch regardless of which client opens.
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
WINDOW_MIN_WIDTH = 800
WINDOW_MIN_HEIGHT = 600
WINDOW_TITLE = "Untitled"

# Matches main.py's webview.create_window(background_color="#1a1a1a") and
# frontend/css/style.css's body background -- same clear color regardless
# of client, so a resize/loading flash looks consistent either way.
BACKGROUND_COLOR = (0x1A / 255, 0x1A / 255, 0x1A / 255, 1.0)

# Depth texture format used by every depth-tested pipeline once mesh/
# billboard drawing lands (Steps 6+) -- matches shaderCache.js's
# DEPTH_FORMAT ('depth24plus') exactly; the two clients must agree since
# they'll eventually share WGSL pipeline source verbatim.
DEPTH_FORMAT = "depth24plus"

# --------------------------------------------------------------------
# Module-level state, mirroring renderer.js's module-level `let`
# variables at the same abstraction level (not wrapped in a class) --
# per this task's "faithful, mechanical port... at the same abstraction
# level it already lives at" constraint.
# --------------------------------------------------------------------

canvas: "RenderCanvas | None" = None
device: "wgpu.GPUDevice | None" = None
context: "wgpu.GPUCanvasContext | None" = None
canvas_format: "str | None" = None
depth_texture: "wgpu.GPUTexture | None" = None
scene_texture: "wgpu.GPUTexture | None" = None
lighting_pass: "LightingPass | None" = None


def init_renderer() -> None:
    """Create the GLFW window, request the adapter/device, configure the
    canvas context, and allocate the depth/scene textures.

    Equivalent to renderer.js's initWebGPU() plus the window-creation
    half of what main.py currently does via webview.create_window() --
    those two concerns are separate steps in the JS/PyWebView world
    (browser window already exists; initWebGPU() only acquires the GPU
    device) but collapse into one function here since this client owns
    window creation itself.
    """
    global canvas, device, context, canvas_format, depth_texture, scene_texture

    canvas = RenderCanvas(
        size=(WINDOW_WIDTH, WINDOW_HEIGHT),
        title=WINDOW_TITLE,
        update_mode="continuous",
        max_fps=60,
    )

    # rendercanvas's public constructor has no min-size option (only
    # `size`/`title`/`update_mode`/`min_fps`/`max_fps`/`vsync`/
    # `present_method`) -- reach into the underlying GLFW window handle
    # directly to match PyWebView's min_size=(800, 600). `_window` is a
    # private GlfwRenderCanvas attribute, not public API; if a future
    # rendercanvas version renames/removes it, this call fails loudly
    # (AttributeError) rather than silently losing the constraint.
    glfw.set_window_size_limits(
        canvas._window,
        WINDOW_MIN_WIDTH,
        WINDOW_MIN_HEIGHT,
        glfw.DONT_CARE,
        glfw.DONT_CARE,
    )

    adapter = wgpu.gpu.request_adapter_sync(canvas=canvas)
    device = adapter.request_device_sync()

    context = canvas.get_wgpu_context()
    canvas_format = context.get_preferred_format(adapter)
    context.configure(
        device=device,
        format=canvas_format,
        # renderer.js configures 'premultiplied' to match the browser
        # canvas compositing model. That's not just a style choice here:
        # this backend/surface combination (verified during Step 5)
        # raises `ValueError: unsupported alpha-mode: premultiplied not
        # in ['opaque']` -- a real platform difference, not a porting
        # bug. The window is opaque anyway (no through-the-window
        # transparency use case), so 'opaque' costs nothing here; if a
        # future backend/platform combination *does* support
        # premultiplied and something needs it, query
        # context.get_configuration() / the adapter's supported alpha
        # modes rather than assuming either value works everywhere.
        alpha_mode="opaque",
    )

    width, height = canvas.get_physical_size()
    depth_texture = create_depth_texture(width, height)
    scene_texture = create_scene_texture(width, height)

    # renderer.js's initRenderer() unconditionally calls initLightingPass()
    # on the WebGPU path -- there is no non-GPU path in this client (see
    # entity_renderer.py's "no Canvas-2D fallback" note), so it's
    # unconditional here too, not an opt-in.
    init_lighting_pass()


def set_cursor_locked(locked: bool) -> None:
    """Hide and confine the cursor to the window (GLFW's
    `CURSOR_DISABLED` mode) for always-on mouse-look, or restore normal
    cursor behavior. `rendercanvas`'s public `RenderCanvas` constructor
    has no cursor-mode option -- reach into the underlying GLFW window
    handle directly, same precedent as `init_renderer()`'s own
    `glfw.set_window_size_limits(canvas._window, ...)` call above.
    `_window` is a private `GlfwRenderCanvas` attribute, not public
    API; if a future rendercanvas version renames/removes it, this
    call fails loudly (AttributeError) rather than silently doing
    nothing.

    While disabled, GLFW reports an unbounded *virtual* cursor position
    through the same `pointer_move` events as normal -- diffing
    consecutive positions (as `ThirdPersonCamera._on_pointer_move`
    does) yields true relative mouse motion even though the real
    cursor never moves. Also enables GLFW's raw mouse motion when the
    platform supports it (bypasses OS pointer acceleration/ballistics
    for a truer look-sensitivity feel); harmless no-op where it's
    unsupported.
    """
    mode = glfw.CURSOR_DISABLED if locked else glfw.CURSOR_NORMAL
    glfw.set_input_mode(canvas._window, glfw.CURSOR, mode)
    if glfw.raw_mouse_motion_supported():
        glfw.set_input_mode(canvas._window, glfw.RAW_MOUSE_MOTION, locked)


def init_lighting_pass() -> None:
    """(Re-)initialize the LightingPass and allocate the scene texture
    it composites from. Safe to call multiple times -- re-creates
    resources if already active, matching renderer.js's
    initLightingPass().
    """
    global lighting_pass, scene_texture

    if scene_texture is not None:
        scene_texture.destroy()
    width, height = canvas.get_physical_size()
    scene_texture = create_scene_texture(width, height)

    lighting_pass = LightingPass(device, canvas_format)
    lighting_pass.set_scene_texture(scene_texture)


def resize(width: int, height: int) -> None:
    """Reallocate the depth/scene textures (and point the lighting pass
    at the new scene texture) at the new physical size. Call this from
    the canvas's "resize" event handler (client/main.py, Step 15) --
    port of renderer.js's resizeCanvas(), minus the DOM canvas.width/
    height assignment (rendercanvas already owns the real surface size).
    """
    global depth_texture, scene_texture

    if lighting_pass is not None:
        if scene_texture is not None:
            scene_texture.destroy()
        scene_texture = create_scene_texture(width, height)
        lighting_pass.set_scene_texture(scene_texture)

    if depth_texture is not None:
        depth_texture.destroy()
    depth_texture = create_depth_texture(width, height)


def create_depth_texture(width: int, height: int) -> "wgpu.GPUTexture":
    """Allocate (or reallocate) the depth texture used by the sprite/
    mesh passes. Matches DEPTH_FORMAT, mirroring renderer.js's
    createDepthTexture().
    """
    return device.create_texture(
        size=(width, height, 1),
        format=DEPTH_FORMAT,
        usage=wgpu.TextureUsage.RENDER_ATTACHMENT,
    )


def create_scene_texture(width: int, height: int) -> "wgpu.GPUTexture":
    """Allocate (or reallocate) the offscreen scene texture the base
    sprite/mesh pass renders into, so the lighting pass (Step 7) can
    sample it. Mirrors renderer.js's createSceneTexture().
    """
    return device.create_texture(
        size=(width, height, 1),
        format=canvas_format,
        usage=wgpu.TextureUsage.RENDER_ATTACHMENT | wgpu.TextureUsage.TEXTURE_BINDING,
    )


def get_view_projection_matrix(camera: dict, aspect: float) -> "list[float] | None":
    """Compute the view-projection matrix for a 3D camera.

    `camera` carries either 2D fields ({x, y, zoom}) or 3D fields
    ({mode: '3d', position, target, up, fov, near, far}). Returns None
    for 2D mode (or an absent/unset mode) -- direct port of renderer.js's
    getViewProjectionMatrix(), including its "2D path builds its own
    inline orthographic MVP, never routed through here" rule.
    """
    if not camera or camera.get("mode") != "3d":
        return None

    fov = camera.get("fov", 3.14159265358979 / 4)
    near = camera.get("near", 0.1)
    far = camera.get("far", 1000)
    up = camera.get("up", [0, 1, 0])

    projection = mat4.perspective(fov, aspect, near, far)
    view = mat4.look_at(camera["position"], camera["target"], up)
    return mat4.multiply(projection, view)


def _draw_frame() -> None:
    """Bare render-loop skeleton (Step 5 scope): acquire the current
    canvas texture, clear it to BACKGROUND_COLOR, submit. No entity
    drawing yet -- that lands as the sprite (Step 6-7), mesh (Step 8-9),
    and lighting (Step 7) passes get ported and wired in here.

    Registered as the canvas's draw function via
    canvas.request_draw(_draw_frame) in run(); rendercanvas calls this
    each scheduled frame and presents the result automatically -- no
    explicit context.present() call needed (confirmed against
    BaseRenderCanvas.request_draw's docstring during Step 5).
    """
    current_texture = context.get_current_texture()
    command_encoder = device.create_command_encoder()

    render_pass = command_encoder.begin_render_pass(
        color_attachments=[
            {
                "view": current_texture.create_view(),
                "clear_value": BACKGROUND_COLOR,
                "load_op": "clear",
                "store_op": "store",
            }
        ],
    )
    render_pass.end()

    device.queue.submit([command_encoder.finish()])


def run(draw_function=None) -> None:
    """Start the render loop. Blocks until the window is closed --
    the native-client equivalent of the browser's requestAnimationFrame
    loop running for the lifetime of the tab, or PyWebView's
    webview.start() call in the current main.py.

    `draw_function` defaults to this module's own bare `_draw_frame`
    skeleton (Step 5 scope: clears to BACKGROUND_COLOR, nothing else) --
    Step 15's `client/main.py` passes its own real per-frame function
    instead (entity rendering, lighting composite, imgui), since that
    orchestration needs `client.engine.entity_renderer.EntityRenderer`,
    which itself imports this module -- a real circular-import
    constraint (confirmed: entity_renderer.py has `from client.engine
    import ... renderer`), not present in JS's flat, import-free
    `<script>` model. Keeping renderer.py free of that import and
    letting the entry point supply its own draw function avoids it.
    """
    canvas.request_draw(draw_function or _draw_frame)
    loop.run()
