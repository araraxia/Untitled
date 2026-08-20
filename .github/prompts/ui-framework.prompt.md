---
agent: agent
description: Custom-drawn, art-asset-skinned UI framework (Phase 7 of ROADMAP.md). The engine-layer primitives (client/engine/ui/) are built and verified; this file now tracks applying them to rebuild the actual game HUD/inventory/dialogue on a game branch.
tools:
  - read_file
  - create_file
  - replace_string_in_file
  - multi_replace_string_in_file
  - grep_search
  - file_search
  - get_errors
  - run_in_terminal
---

# Task: UI Framework (Phase 7)

**Rewritten a second time.** The first rewrite this session (imgui-bundle
default-widget-based) was superseded before any of it was built, once a
much larger vision was scoped: fully custom-drawn, art-asset-skinned
menus, keyboard/mouse/gamepad navigation, animated elements, 3D content
and shader effects embedded inside UI panels, and reusable templates.
That architecture is now built and verified on the `engine` branch, as
`client/engine/ui/` — this file's remaining scope is applying it to a
real game's UI on a game branch. If you're picking this up cold, read
`client/engine/ui/`'s module docstrings (`draw.py` especially) and
`run_ui_test.py` before anything else — they're the real, current spec;
what follows here is the status and the remaining work.

## What's built and verified (on `engine`, done)

`client/engine/ui/` — imgui-bundle used only as the input/layout/frame-
lifecycle engine (hit-testing, keyboard state, the `new_frame()`/
`render()` bracket); every visible pixel is drawn through `ImDrawList`,
never imgui's own widget chrome:

- **`draw.py`** — `UIDrawContext` (rect/rect_border/circle/line/text/
  image primitives, manual hover/click hit-testing) and the
  wgpu-texture-to-imgui bridge (`_TextureRegistry`, wrapping the
  confirmed `imgui_renderer.backend.register_texture(view) ->
  ImTextureRef`). **The one hard rule the whole package follows**:
  nothing here is safe to call outside the imgui frame bracket —
  confirmed SIGSEGV in this codebase's wgpu/imgui-bundle pairing if
  violated (see `client/game/ui.py`, legacy branch, for the original
  `open_popup()` reproduction this generalizes from). Anything
  triggered from an input callback must use a pending-request pattern,
  never call into this package directly from a callback.
- **`theme.py`** — JSON-driven `Theme` (colors, optional custom fonts via
  `imgui.get_io().fonts.add_font_from_file_ttf`, optional skin images) —
  see `frontend/assets/data/ui_theme.json` for the real (colors-only
  today; no font/skin assets exist yet, `widgets.label` falls back to
  imgui's default font rather than drawing nothing).
- **`gamepad.py`** — per-frame GLFW gamepad polling (`glfw.get_gamepad_state`
  et al., confirmed present, previously unused anywhere in this
  codebase). Edge-triggered `buttons_pressed`, per-joystick-id state.
  **Not verified against physical hardware this session** — verify
  before shipping a controller-dependent feature.
- **`nav.py`** — `FocusManager`: keyboard + gamepad → one abstract
  `NavAction` set (UP/DOWN/LEFT/RIGHT/CONFIRM/BACK). Mouse hover claims
  focus automatically so mouse and nav never disagree. v1 is a flat
  focus order (UP/LEFT and DOWN/RIGHT both step through one list) — real
  2D-grid navigation (e.g. an inventory grid) is a documented future
  extension, not yet needed by anything built.
- **`widgets.py`** — `panel`, `label`, `button`, `image_button`,
  `progress_bar`, `animated_icon` — composable functions, not a class
  hierarchy, each drawing itself and reporting hover/click/confirm state
  back to the caller (no retained widget tree, matching this codebase's
  existing immediate-mode conventions).
- **`panel3d.py`** — `Panel3D`: the render-to-texture bridge for
  embedding 3D content or a shader effect inside a UI rect. Owns an
  offscreen `GPUTexture` (+ depth), defaults its format to
  `renderer.canvas_format` (**a real bug was found and fixed** during
  verification: defaulting to a hardcoded `rgba8unorm` produced a GPU
  validation error, since every existing render pipeline in this
  codebase — `ShaderCache`'s sprite/material/mesh pipelines — is
  compiled against `renderer.canvas_format`, not a fixed format).
- **`templates.py`** — `window`, `confirm_dialog`, `chat_box` — game-
  agnostic patterns; copy text/callbacks/theme are always caller-supplied.
- **`shader_cache.py`'s new `'orb'` variant** — a liquid-fill,
  fresnel-rimmed orb effect (Diablo/PoE-style health/mana orb), added to
  the existing `MATERIAL_FRAGMENT_SHADERS` dict with no new bind-group-
  layout/uniform-field plumbing — fill level, liquid/highlight/rim
  colors, and rim falloff all reuse existing unused `MatUniforms` slots
  (`intensity`, `pal_a..d`, `ramp_steps`), the same reuse pattern
  `FS_COSINE` already established for a different purpose.
- **`GPUSpriteSheet.albedo_texture_view`** (small addition to
  `client/engine/gpu_sprite_sheet.py`) — a *stable*, cached
  `GPUTextureView` (not recreated per call), needed so `widgets.animated_icon`
  can display sprite frames through `draw.py`'s texture-registration
  cache without leaking a "new" texture registration every frame.
- **`run_ui_test.py`** — standalone smoke test (no backend, no game
  content, mirrors `run_client_test.py`'s hand-built-scene approach).
  Exercises every primitive above in one screen: a themed window, two
  nav-navigable buttons, an animating progress bar, a real 4-frame
  animated icon (`frontend/assets/images/ui/test_cursor_strip.png`, a
  fixture created for this test), an embedded `Panel3D` showing a
  rotating mesh (reusing `run_client_test.py`'s crate fixtures), and a
  `confirm_dialog`. **Verified**: runs 20+ seconds with zero draw errors
  and zero exceptions after the format-default fix above.

## Branch placement

Per this session's engine/game branch split: everything above is
reusable across any game built on this engine and ships on `engine`. The
*game-specific* application — rebuilding `client/game/ui.py`'s actual
HUD, plus the inventory panel and dialogue box originally scoped for
this phase, using `client/engine/ui/` instead of plain imgui widgets or
hand-rolled DOM — belongs on a game branch (`legacy` today). That's the
remaining work below.

## Remaining work (game-branch application)

Read `client/game/ui.py` (legacy branch) in full first — it already has
a working HUD (HP/AP text, party panel, command-menu popup) built during
the Phase 13 migration; this is a redesign of its visuals through
`client/engine/ui/`, not a rewrite of its game logic (party selection,
command dispatch, the `_pending_command_menu` pattern all stay).

1. **HUD**: replace the plain `imgui.text()` HP/AP lines with
   `widgets.progress_bar`, themed via a real project theme (extend
   `ui_theme.json` with this game's actual palette/fonts/skin art —
   the engine-side `ui_theme.json` is a placeholder with no custom
   fonts/skins, not meant to ship as-is).
2. **Inventory panel** (new `client/game/inventory_panel.py`): a
   `templates.window` sized to a grid, `widgets.image_button` per slot
   (drag-and-drop via imgui's own `begin_drag_drop_source`/
   `set_drag_drop_payload_py_id`/`accept_drag_drop_payload_py_id` —
   confirmed present, not yet wired to anything in `client/engine/ui/`
   since drag-and-drop is inherently game-content-shaped, not generic).
   Data contract (`inventory_update` SocketIO event) and backend stub
   handlers (`item_use`/`item_move` on `backend/app.py`, game-branch
   only) are unchanged from this phase's original scope.
3. **Dialogue box** (new `client/game/dialogue_box.py`): `templates.window`
   + `widgets.button` per choice + a typewriter reveal (elapsed-time
   character count, not `time.sleep`). Dialogue JSON schema and
   `dialogue_start`/`dialogue_end`/`dialogue_choice` events unchanged
   from this phase's original scope.
4. **Wire into `client/main.py`**: `client.engine.ui.draw.init(imgui_renderer)`
   once at startup (right after `ImguiRenderer` construction, same
   place `run_ui_test.py` does it); load the game's real theme once via
   `client.engine.ui.theme.load_theme`; call the new HUD/inventory/
   dialogue draw functions from the same per-frame callback
   `render_hud()`/`render_party_command_menu()` already run from.
5. **The orb, if this game wants one**: instantiate a `Panel3D`, draw a
   full-quad using `shader_cache.get_material_pipeline('orb', ...)` (or
   `get_mesh_pipeline` if drawn as a 3D quad) inside its `render()`
   closure, display via `draw.UIDrawContext.image()`. Not started —
   the shader variant exists and is registered, nothing calls it yet.
6. **ROADMAP.md**: mark Phase 7 complete once the game-branch work above
   lands, noting (as this file's own status section does) that the
   engine-layer half shipped on `engine` and the game-layer half on
   whichever game branch did the work.
