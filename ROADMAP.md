# Engine Packaging Roadmap

This document tracks the incremental work required to turn this repository from a monolithic game prototype into a modular, extensible game engine with a clear boundary between engine infrastructure and game-specific content.

---

## Philosophy

The engine is not a separate product — it is the lower half of this same repository. "Packaging" means establishing a clean API surface between the two halves so that game content can be replaced, extended, or swapped without touching engine code.

```text
┌─────────────────────────────────────────┐
│  GAME LAYER  (content, rules, world)    │
├─────────────────────────────────────────┤
│  ENGINE API  (stable, versioned)        │
├──────────────┬──────────────────────────┤
│  Simulation  │  Rendering               │
│  (Python)    │  (wgpu)                  │
└──────────────┴──────────────────────────┘
```

---

## Branch model (current)

As of the split after Phase 13, this `engine` branch carries engine/tooling code only (`backend/engine/`, `client/engine/`) — no game content. The game-specific work this document's Phase 1 ("Engine–Game Separation") originally pulled into `backend/game/`/`client/game/` moved to its own branch, `legacy`, forked from `engine`. Future games branch from `engine` the same way; branches don't auto-sync, an engine improvement reaches a game branch only via an explicit `git merge engine`/rebase. Phases below that reference `backend/game/`/`client/game/` paths describe that layer as it exists on a game branch (`legacy` today), not code present on `engine` itself — see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Phase Progress

| Phase | Name | Status |
| ----- | ---- | ------ |
| 0 | WebGPU Foundation | ✅ Complete |
| 1 | Engine–Game Separation | ✅ Complete |
| 2 | Graphics Pipeline Completion | ✅ Complete |
| 3 | ECS Overhaul | ✅ Complete |
| 4 | Simulation Systems | ✅ Complete |
| 5 | Asset Pipeline | ✅ Complete |
| 6 | Save / Load / Persistence | ✅ Complete |
| 7 | UI Framework | 🔲 In Progress — engine-layer half done & verified (`client/engine/ui/`: custom-drawn primitives, theme, nav w/ gamepad, render-to-texture panels, `run_ui_test.py`); game-layer half (rebuild the HUD, add inventory panel + dialogue box on a game branch) not started. See ui-framework.prompt.md. |
| 8 | Audio | 🔶 In Progress (engine-branch scope, fallback playback path + basic OSC sender implemented and verified, 2026-08-26) — `client/engine/audio.py`: a `miniaudio`-backed fallback playback engine (master/`music`/`sfx`/`ambient` bus mixing, manual equal-power pan + linear distance attenuation, music streaming with crossfade, loop points) plus `client/engine/network.py`'s `play_music`/`stop_music`/`play_sfx` callback slots (Step 4) and `tools/build_manifest.py`'s audio scan extended with `ambient` classification + loop metadata (Step 2) are done, verified via `run_audio_test.py` (headless, 25 assertions, no GPU/backend/game branch needed) against real project assets (`frontend/assets/audio/sfx/{footstep1,hit4}.wav`). **Real bug found and fixed via the prompt's own required cross-thread stress test, not theorized**: the mixer's per-sample Python mixing loop stalls past ~1000 simultaneous voices (confirmed: 1200 concurrent voices never drained); capped at `_MAX_SFX_VOICES = 64`, re-verified clean afterward. `backend/engine/osc.py` (Step 6) is also done: a generic, config-driven, no-op-safe OSC sender (`send_tempo`/`send_pattern`/`send_event`, JSON-encoded payloads, optional `scsynth` launch/supervision) — verified directly (enabled/disabled config switching, real UDP sends with nothing listening, a failed `scsynth` launch, `shutdown()`), no game branch needed. `miniaudio`/`python-osc` both confirmed installed cleanly on Windows (prebuilt wheel / pure-Python wheel respectively) and pinned in `requirements.txt` (a real gap from Step 3 — `miniaudio` was never actually added there until this pass); Linux installation of `miniaudio` is still unconfirmed (`docs/DEBIAN_SETUP.md` not yet updated with any system-package finding). Not yet built, but buildable on `engine`: Step 8 (hardening `osc.py` — per-event health tracking, bounded retry, rate limiting; today's sender only tracks one global last-send flag). Blocked on a game branch: Step 7 (mapping real gameplay events to OSC cues/`play_music` calls, and `backend/app.py`'s own SocketIO handlers — neither exists on `engine`). See `.github/prompts/audio.prompt.md`. |
| 9 | Distribution & Tooling | 🔲 Not started |
| 10 | 3D Coordinate Mapping | ✅ Complete (engine-branch scope) — Steps 1–14 all done; see `docs/graphics/ACTION_TRIGGERED_ANIMATIONS.md` and a full-repo audit logged in `completed/3d-coordinate-mapping.prompt.md`, 2026-08-20. Every step independently re-confirmed against current code, not just against the prompt's own prior claims; `run_gametick_test.py` re-run clean. Two things remain deliberately open, neither blocking "complete" on this branch: (1) Step 12's real backend wiring — `example_game_loop.py` is verified generic reference content, but a real game still needs its own `ACTION_DURATIONS`/revert logic in `player.py`/`actions.py`/`tick.py` on a game branch, which doesn't exist here by design (see CLAUDE.md's Branch model); (2) Step 8's fog/`ambientColor` stylization hooks are correctly ported to `client/engine/shader_cache.py` and documented, but `run_client_test.py` only isolates `vertex_color`/`affine_uv`/`color_levels` — fog/ambient have never been visually exercised on the Python client, a test-coverage gap, not a known defect. |
| 11 | Area / Scene System | 🔶 In Progress (engine-branch scope implemented and verified, 2026-08-20) — `client/engine/scene.py`'s `Scene` (Steps 3–4, entities/camera/lighting/start_camera/zones, source-tagged refuse-on-collision, load/save round-trip), `client/engine/free_camera.py` + `client/engine/area_viewer.py` (Steps 6–7, the standalone viewer/builder tool, reclassified engine-layer — see `area-system.prompt.md`'s branch-reconciliation banner), a `scene_cue` callback slot in `network.py` (Step 8), and `docs/graphics/AREA_SYSTEM.md` (Step 12) are all done, verified via `run_scene_test.py` (headless) and live GPU runs of all three area-viewer modes against `frontend/assets/data/area/area-example.json`. Blocked on a game branch: Step 2 (`backend/game/area.py`'s schema extension), Step 5's game-layer shim (`game_state` is owned by `client/game/player_select.py`, which doesn't exist on `engine`), and Steps 9–10 (movement/collision fix, `ScriptComponent`/`ScriptMovementSystem` — also blocked a second, independent way: they target the `System`/`World` ECS pipeline `zones.prompt.md` documents as never populated, re-confirm before resuming either). |
| 12 | Zones & Triggers | 🔶 In Progress (engine-branch scope implemented and verified, 2026-08-20) — `backend/engine/zone.py`: `Zone`/`ZoneRegistry` (AABB or mesh-footprint volumes, enter/exit de-dup), `contains_point` (both shapes; mesh footprints reduced to their 2D convex hull — a necessary correction found during implementation, raw mesh vertex order isn't a perimeter walk), and `apply_zone_effect` (all 8 declarative effect types — reclassified engine-layer from its original `backend/game/area.py` placement, since none of them are game-specific). Verified headless via `run_zone_test.py`, no backend/GPU/game branch needed. Same `ecs_world`-not-populated caveat as everything else touching the ECS System pipeline — driven from a plain `update()` call, not registered as a `System`, mirroring `backend/engine/group.py`'s own precedent. Only Step 5 (a one-line `Area.update()` wiring call, documented in `docs/graphics/AREA_SYSTEM.md`) stays blocked on a game branch — `Area` doesn't exist on `engine`. |
| 13 | Native wgpu-py Desktop Client | ✅ Complete (18 of 18 steps; legacy PyWebView/JS client fully deleted, not just deprecated) — numbered out of chronological order (added after Phase 12 was already assigned); left as-is per this repo's own convention of not renumbering a completed, widely-cross-referenced phase. |
| 14 | Level Editor & Asset Viewer | 🔶 In Progress (engine-branch scope implemented, 2026-08-22) — `launcher.py`, `asset_preview.py`, `editor_commands.py`, `picking.py`, `gizmo.py` (imgui-overlay rendering, not a new GPU pipeline), the full property/asset-browser/grid/save panels, zone authoring, the UI-menu editor (`ui_editor.py`/`ui_menu_runtime.py`), and the Action Definitions panel are all built into `client/engine/area_viewer.py` and verified — pure logic (picking/gizmo/commands/zone-pose/action-registry math) via new unit tests, rendering/wiring via clean GPU boot tests with real and forced-selected data. **Real limitation, stated plainly**: no literal mouse-click/drag interaction was exercised (this environment can't simulate GLFW input events) — the math every handler calls is verified, the event-handler wiring itself needs a real interactive pass before trusting it fully. Also found and fixed while implementing: `client/main.py` had no path to the launcher at all (zero arguments fell through to real gameplay `main()` and crashed on `engine`); `AssetLoader` had no way to list a manifest category's contents (needed for the asset browser). Still blocked: `ScriptComponent`'s property-panel section (that component doesn't exist yet) and the UI-menu editor's `zone`/`entity_interact` trigger delivery (no `EventBus`→SocketIO bridge exists anywhere in this codebase). **Real dormant bug found and fixed while building Phase 15 (2026-08-28), confirming the "no real clicks yet" caveat above was warranted**: the property panel's "Confirm & Save Template" flow passes `entity.render_template` (always the `entity-<name>` *prefixed* form, per every entity id convention elsewhere in this codebase) straight into `area_io.save_entity_definition()`/`load_entity_definition()`, which expected the *bare* form and unconditionally re-prepended `entity-` — meaning that button, if ever actually clicked for a real entity, would have written to a wrong, double-prefixed file (`entity-entity-<name>.json`) rather than the real one, and `load_entity_definition()` would have silently returned `None` for the same reason. Fixed in `area_io.py` itself (see Phase 15's row) with `normalize_entity_id()`, so this panel now works correctly too. |
| 15 | Entity Builder & Blender Asset Pipeline | 🔶 In Progress (engine-branch scope implemented, 2026-08-27) — `client/engine/entity_builder.py`: part CRUD with mesh/material/`attachTo`/socket pickers constrained to real loaded data (never free text), "Scaffold Parts from Sockets," Import Mesh/Animation panels wrapping `convert_mesh.py`/`convert_animation.py` in-process, a Materials panel wrapping `pack_param_map.py`, playback (pause + per-action `entity.state` trigger preview — not true clip scrubbing, no seek API exists on `EntityRenderer`), and Save, all reachable from `launcher.py` ("New Entity" / per-entity "Edit"). Shared code extracted first, not duplicated: `OrbitCamera` → `client/engine/orbit_camera.py`, the per-part `dangle`/`localOffset`/`action_animations` editing widgets → `client/engine/entity_template_editing.py` (gained an `animation_id` field in the process), both now used by `area_viewer.py` too. `Mesh.socket_names()` added (a real gap — no way existed to enumerate a mesh's sockets, only look one up by name) and `area_io._refresh_manifest` made public (`refresh_manifest`) for the builder's own save paths. **Real bug found and fixed, not theorized**: `EntityRenderer` caches definitions/meshes/materials permanently with no invalidation path (correct for gameplay, fatal for a live-editing tool) — fixed by destroying and dropping the preview entity's renderer on every edit, forcing a fresh reload, the same targeted-internals-reach `asset_preview.py`'s own material-override code already established. Multi-mesh glTF exports (the actual common case — a whole rigid-part rig in one file) are handled via a separate agent's `tools/split_glb.py` (one multi-mesh `.glb` in, one single-mesh `.glb` per part out), wired into the Import Mesh panel as a second "Split Multi-Mesh GLB" button; confirmed end-to-end against a real 6-part bird rig (body/beak/2 legs/2 wings, body's 5 sockets intact after splitting). That same real data also caught a real bug in the scaffolding matcher: a plain substring check failed on reversed word order (`wing_l_socket` vs. a Blender-derived `l_wing` mesh id) — fixed with an order-independent word-set match, regression-tested against the exact bird mesh ids. Verified via `run_entity_builder_test.py` (20 headless assertions against real fixtures, no GPU) plus multiple live GPU boots including one with every collapsing header forced open to exercise the picker/field-editing code a normal automated boot can't reach (imgui sections start collapsed). **Real limitation, stated plainly**: no literal button clicks were exercised (same "can't simulate GLFW input events" limitation Phase 14 already documents) — Convert/Split/Pack/Save are each one line calling an already-independently-tested function, so the risk is narrowly in the click-to-call wiring, not the underlying logic. Not built (deliberately, documented as forward-looking in the module's own docstring): live in-editor texture/param-map painting. Interactive UI further reorganized per direct request: top/bottom menu bars mirroring `area_viewer.py`'s own (File/Parts/View), Parts and Materials folded into a tabbed right-side sidebar, Import folded into the File menu, a bottom-left toast for every action's outcome (`_show_toast`/`_draw_toast`, capturing `convert_mesh.py`/`split_glb.py`'s real printed output via `_capture_stdout`), and a native "Search..." file-open button (`tkinter.filedialog` — reversing the tool's own original "no tkinter" call once its actual justification, a packaging spec for the deleted PyWebView client, turned out not to apply). **Two more real bugs found and fixed via an actual "nothing renders" report, not theorized**: (1) `entity_renderer.py`'s `_draw_mesh_part` skipped the draw call entirely whenever no material handle was available, so any part with no `material_id` (every part this tool's own Add Part/Scaffold create) rendered as nothing with zero error — fixed with a shared, lazily-built magenta fallback material (`MaterialLoader.get_fallback_handle()`), an engine-layer fix that also benefits `area_viewer.py`/hand-authored content, not builder-only; (2) even with meshes drawing, a realistic "1 unit = 1 meter" model (e.g. a real bird part measuring ~0.13-unit radius) was still practically invisible against `OrbitCamera`'s fixed ~200-unit default (inherited from this engine's old pixel-tile-scale content, never migrated) — fixed by auto-fitting `orbit.radius`/`scene.camera` near-far to the loaded content's actual measured bounding radius on every edit. Also fixed: "Scaffold Parts from Sockets" used to add a duplicate, overlapping part at a socket that already had one attached (only guarded against id collisions, not socket collisions) — now shown, disabled, as "already attached" instead. **A third bug, reported immediately after (2) shipped, in the same shared camera class**: `client/engine/orbit_camera.py`'s `OrbitCamera._on_wheel` had its own fixed 20.0–2000.0 zoom clamp (also old-scale-sized) — once the camera could start at a sub-1.0 radius for small content, the first scroll snapped it to the 20.0 floor with no way back in ("scrolling out locks you out of scrolling back in"). Fixed in the shared class: widened to a scale-agnostic 0.01–100000.0 clamp and switched from a fixed additive step to a multiplicative one (`radius *= 1.15 ** (dy/100)`, calibrated against `rendercanvas`'s actual GLFW dy≈±100-per-notch), so zoom feel stays proportional at any scale — also fixes the same lockout in `asset_preview.py`. All three fixes verified numerically/live, not just read: `_draw_mesh_part` confirmed returning `True` (draw issued) instead of `False` with no `material_id`; `orbit.radius`/near/far confirmed live against real GPU state matching the auto-fit formula exactly; `OrbitCamera` confirmed zooming from 0.5 down past 0.023 and back out past 1.5 with no floor lockout. **New feature, per direct request: View > Mesh > Solid/Wireframe.** WebGPU has no native polygon/wireframe fill mode (unlike OpenGL/Vulkan/D3D's `PolygonMode::Line`), so this is real new engine-layer capability, not a settings toggle: `Mesh.wireframe_index_buffer` (a companion line-list index buffer built from the triangle indices at load time — 2 indices per triangle edge, edges duplicated rather than deduplicated across shared triangles) and `shader_cache.create_mesh_wireframe_pipeline()` (the same `vs_main` MVP-transform vertex stage as the solid mesh pipeline, paired with a trivial flat-white fragment shader and `line-list` topology). `EntityRenderer.set_wireframe()` swaps both the pipeline and index buffer/count together in `_draw_mesh_part`. Verified against real GPU state, not just compiled: a real crate mesh's 36 triangle indices produced exactly 72 wireframe indices (12 triangles × 6, matching the math), and `_draw_mesh_part` issued a real draw call in both modes and switched cleanly back and forth; a live run toggling `state.wireframe` mid-session (simulating the menu click) confirmed the change reaches the live preview renderer within a few frames and renders 10+ clean frames in wireframe before switching back. **New sidebar tab and workflow automation, per direct request.** "Meshes" tab (`_draw_meshes_tab`) lists meshes actually referenced by the entity's parts (`meshes_used_by_parts()`/`parts_using_mesh()`), derived live from `state.parts`, not tracked separately. "Split Multi-Mesh GLB" now auto-converts each part (`do_convert=True`, reversed from `False`), and both it and plain "Convert Mesh" auto-add a new, unattached part for each freshly-converted mesh (`_add_part_for_converted_mesh()`) — a no-op, not a duplicate, if a part already references that mesh (handles re-conversion after a Blender fix). **This required a real reconciliation with "Scaffold Parts from Sockets"**: once import routinely leaves unattached parts sitting around, Scaffold naively creating a new part per socket would double every part. Fixed with `find_unattached_part_for_mesh()` — Scaffold now attaches an existing matching unattached part instead of duplicating it, shown transparently per-row ("will attach existing part" vs. "will create a new part"). Verified end-to-end against the real 6-part bird rig: splitting the actual combined `bird.glb` with auto-convert produced exactly 6 unattached parts, and simulating Scaffold against them reused all 5 non-root parts (attaching, not duplicating) — final count stayed at 6, not 12. **Camera pan direction**: `OrbitCamera` gained a per-instance `invert_yaw` constructor flag (default off, so `asset_preview.py`'s camera is unaffected) — `entity_builder.py` sets it, per direct request to flip its own left/right drag-pan direction; verified numerically to produce the exact opposite yaw delta for the same drag. **Real bug found and fixed, reported directly as "saving names it `entity-entity-<name>`" and "saving did not save the parts"** — one root cause in `area_io.py` itself: every other entity asset id convention in this codebase (manifest keys, `render_template` values) is the *prefixed* `entity-<name>` form, but `save_entity_definition()`/`load_entity_definition()` alone expected the *bare* form and unconditionally re-prepended `entity-` — so reopening a saved entity via the launcher's "Edit" (which passes the prefixed, manifest-derived id) made `load_entity_definition()` look for a nonexistent double-prefixed file, silently return `None`, and start `state.parts` empty, then the next Save wrote to that same wrong path, orphaning the original file. Fixed with `area_io.normalize_entity_id()` (idempotent regardless of which form is passed in) plus stamping a correct `"id"` field into every saved entity JSON. **Being a shared `area_io.py` fix, this also retroactively fixes the identical dormant bug in `area_viewer.py`'s own template-editing save flow** (see Phase 14's row) — confirmed live: passing the prefixed form directly into `entity_builder.run()` (exactly as the launcher would) now correctly normalizes `state.entity_id` and loads real parts; re-saving with the prefixed id no longer creates a double-prefixed file and correctly overwrites the original. **New sidebar tab, per direct request: "Animations" — same shape as the Meshes tab, one content type over.** `_draw_animations_tab` lists the distinct animation clip ids referenced by any part (`animations_used_by_parts()`, combining `animation_id` — the continuous/looping field — with every value in `action_animations` — the one-shot/triggered map — since both reference the same kind of transform-clip id), each annotated with which part(s) use it and how (`parts_using_animation()`: `"animation_id"` vs. `"action:<name>"`). Read-only and derived live from `state.parts`, same as Meshes — assigning/changing animations stays in the Parts tab. Verified via 5 new headless assertions (57 total in `run_entity_builder_test.py`, all passing) plus a live GPU run against `entity-example-staff`'s real "charm" part (which has both a continuous `animation_id` and a one-shot `action_animations` entry), rendering both usages correctly for 15 frames with no crash. **New feature, per direct request, with a real runtime schema extension, not just new UI: "New Animation" + an Animation Editor window authoring multi-part rig clips.** Confirmed with the user first (a genuine architecture fork, not assumed): until now `transform_clip.py` was strictly one-clip-per-part; a keyframe can now optionally hold a `"parts"` map (`{part_id: {position/rotation/scale}}`) so one clip drives several parts on one shared timeline, each independently keyed — `sample_transform_clip()` gained a `part_id` parameter that filters to just that part's own keyframes when a `"parts"` map is present, fully backward-compatible (a clip with no `"parts"` map anywhere samples exactly as before regardless of `part_id`); `entity_renderer.py`'s two call sites (`_sample_part_animation`/`_sample_part_action_animation`, which already had `part_id` in scope) now forward it. The third transform type was confirmed to mean scale, not real shear (this engine has no shear math anywhere) — kept in scope as position/rotation/scale only. Editor: name-and-create an empty clip from the Animations tab; edit mode opens a window with a horizontally-scrollable keyframe strip (`imgui.begin_child(..., horizontal_scrollbar)`), a "gap from previous" field per keyframe (edits relative spacing, not raw absolute time, without shifting any other keyframe's own stored time), and per-assigned-part `drag_float3` position/rotation/scale plus assign/remove controls. Save stamps `animation_id` onto any newly-assigned part that doesn't already have one (`stamp_animation_id_for_assigned_parts()` — never overwrites an existing assignment), so assigning a part to a keyframe is enough by itself to make it play. Verified via 19 new headless assertions (76 total, all passing), including `sample_transform_clip`'s new multi-part path directly against a synthetic two-part rig clip. Live GPU verification went end-to-end against the real `entity-example-staff` fixture: replicated New Animation → opened the editor → added two keyframes → assigned `shaft` (previously unset) to both and `charm` (already carrying its own clip) to only the first → Save → reloaded the just-written file off disk and ran it through the real sampler exactly as `entity_renderer.py` does, confirming correct mid-clip interpolation, correct "hold at last known keyframe" for the part missing from the later keyframe, and correct stamping behavior (`shaft` got the new clip id; `charm`'s existing assignment was left untouched) — then continued rendering 15 real frames with `shaft`'s freshly-stamped multi-part clip actually active on the live render path, plus the full Animations tab and Animation Editor window (keyframe strip, drag_float3 fields, combo, collapsing headers), with no crash. **Follow-up, per direct request: the orbit-preview mesh now visibly tracks the transform being edited on the currently selected keyframe.** `apply_keyframe_preview()` returns a copy of the parts list where every part the selected keyframe assigns a transform to has its `localOffset` replaced by that keyframe's own position/rotation/scale, with `animation_id`/`action_animations` stripped from the copy — without that, a part with a real running animation (e.g. `charm`'s continuous spin) would have its live-sampled pose override the static preview pose the very next frame, since `entity_renderer.py` already layers any sampled animation on top of `localOffset` at render time; this reuses that exact mechanism rather than adding a second transform path. `_sync_preview_definition` now writes this overridden copy to the scratch preview file instead of `state.parts` directly, so the previewed pose can never leak into a real Save. Every action that changes the selected keyframe or a previewed part's transform (select a different keyframe, Add/Delete Keyframe, each drag_float3 edit, Assign/Remove-from-keyframe, closing the editor) re-syncs the preview. Verified via 7 new headless assertions (88 total) plus a live GPU script that monkeypatched `EntityRenderer._draw_mesh_part` to record the actual `world_matrix` each part is drawn with (not a cached value) and confirmed, against the real `shaft` part in sequence: posing it via a keyframe to `[3, 0, 0]` produced a drawn world x of exactly `3.0`; re-editing that same keyframe's position to `[-7, 2, 0]` moved it to `-7.0`; and closing the editor reverted it to `0.0` (its real, unset `localOffset`) — confirming both that edits reach the live mesh and that the override cleanly releases once editing stops. **Follow-up, per direct request: the Animations tab's plain per-row text + "Edit" button became a real, selectable table.** Confirmed with the user first that "select as active" means "open it in the Animation Editor" (not a separate live-preview player, and not a shortcut for assigning a part's `animation_id`) — an `imgui.begin_table` with "Animation"/"Used By" columns, each row a full-width `imgui.selectable` (`span_all_columns`, so clicking anywhere in the row works, not just the id text) whose highlighted state is read fresh from `state.editing_animation_id == animation_id` every frame, so the highlight always matches whatever's actually open (including via "New Animation", not just a row click). No new pure helpers needed — reuses `animations_used_by_parts`/`parts_using_animation`/`_open_animation_editor` unchanged. Verified live against the real `entity-example-staff` fixture: opened `anim-transform-charm-spin` directly so the table rendered a real selected row (not only the unselected case), alongside the open Animation Editor window, for 15 real frames with no crash. **Real bug found and fixed, reported directly as "it's not finding the flap animation I started."** The Animations table only ever reads `animations_used_by_parts(state.parts)` — it has no knowledge of clip files on disk beyond what the current entity's own parts actually reference. Root cause, confirmed against the user's real files: the Animation Editor's Save had correctly written `animation-transform-flap.json` (real keyframe data assigning `l_wing` a rotation, correctly registered in the manifest) and stamped `l_wing.animation_id` — but only in memory; persisting that to `entity-bird.json` has always required a separate, explicit File > Save, which never happened, so the next load of `bird` came back with `l_wing` carrying no animation_id and "flap" silently vanished from the table even though the clip file and manifest entry were both still correct. Per direct decision (weighed against "just warn more clearly," which would have preserved this tool's "only File > Save writes entity-<id>.json" rule) — `_save_animation_editor` now also immediately persists the entity whenever it actually stamps a part, gated on `state.entity_id` already being set. The real broken file was repaired directly (`entity-bird.json`'s `l_wing` now carries `"animation_id": "anim-transform-flap"`). Verified with a new headless integration test (seeds a throwaway saved entity, assigns a part in a fresh clip, confirms no `animation_id` on disk pre-Save, confirms it's there post-Save — 90 total assertions, all passing) plus a live GPU script reproducing the same sequence through the real window plumbing end-to-end. **Real bug found and fixed, reported directly as "I'm applying transformations to parts in the animation but the mesh render is not updating with the transformations."** Not a rendering bug — reproduced live against the user's real `bird`/`l_wing`/`anim-transform-flap` files and confirmed the world transform was applied correctly every frame. The actual cause is a scale/framing mismatch: the bird measures ~0.13 units total, so the auto-fit camera sits only ~0.5 units away at a 45° FOV — a visible area only ~0.2 units top-to-bottom — while the user's real `flap` clip poses `l_wing` to position `[0, 50, 2]`, ~240x past the edge of that frame. Correctly rendered, just invisible. Both requested fixes: `keyframe_preview_reach()` (a new pure helper approximating how far the currently-previewed keyframe's posed parts extend from the origin) now widens `_sync_preview_definition`'s camera auto-fit (`max(entity_bounding_radius(...), keyframe_preview_reach(...))`) so a far-posed keyframe stays in view instead of silently exceeding the frustum; `position_drag_speed()` scales the position `drag_float3`'s pixel-to-unit speed to the entity's own bounding radius (`max(radius * 0.02, 0.0005)`) instead of a fixed `0.01`, so a short drag on a tiny model no longer flings a part dozens of units — deliberately position-only, since rotation/scale are already size-independent. Verified with 7 new headless assertions (97 total) plus a live GPU script posing the real `l_wing` to the clip's actual `[0, 50, 2]`, confirming `orbit.radius` widened from `0.5` to over `151` and `scene.camera["far"]` from `100.0` to over `2500` — the posed wing is now inside the visible frustum instead of ~240x past its edge. |

---

## Phase 0 — WebGPU Foundation ✅

**Goal:** Replace Canvas 2D with a WebGPU render pipeline.

**Completed work:**

- `initWebGPU()` in `renderer.js` — device acquisition, canvas context, feature flag
- `shaderCache.js` — WGSL sprite pipeline, `ShaderCache` class
- `gpuBuffers.js` — `createUniformBuffer`, `writeUniformBuffer`, `createQuadVertexBuffer`
- `gpuSpriteSheet.js` — `GPUSpriteSheet` (load, UV rect, bind group)
- `entityRenderer.js` — GPU draw path; Canvas 2D entity path removed
- `renderer.js` — GPU render loop with `GPURenderPassEncoder` threading
- Overlay canvas pattern for 2D HUD over WebGPU surface

**Remaining graphics milestones** are tracked in Phase 2.

---

## Phase 1 — Engine–Game Separation ✅

**Goal:** Establish a clear directory boundary and API contract between engine-level infrastructure and game-specific content. No engine module should import content; no content module should reach into engine internals.

### 1.1 — Directory Restructure ✅ ✅

Reorganise source into two top-level namespaces:

```text
backend/
  engine/           ← ECS framework, event bus, spatial, save/load base, loop
  game/             ← entities, systems, actions specific to THIS game
frontend/js/
  engine/           ← renderer, input, network, interpolation, asset loader
  game/             ← character creation, party UI, world-specific shaders
```

Key moves:
- `backend/simulation/` → split: `engine/ecs/`, `engine/spatial.py`, `game/entities/`
- `backend/game_loop.py` → `engine/game_loop.py` (loop mechanics) + `game/tick.py` (game rules)
- `frontend/js/renderer.js`, `entityRenderer.js`, `interpolation.js` → `engine/`
- `frontend/js/characterCreation.js`, `playerSelect.js` → `game/`

### 1.2 — Configuration Injection ✅

Replace hard-coded constants in `config.py` with an injectable config schema:

- `EngineConfig` dataclass: tick rate, world size, grid cell size, log paths
- `GameConfig` dataclass: race definitions, base stats, starting conditions
- Both loaded from JSON at startup; validated against a schema

### 1.3 — Engine API Surface ✅

Define the stable API that game code calls into:

**Python:**
- `engine.ecs.World` — entity/component CRUD
- `engine.ecs.System` — base class for systems
- `engine.events.EventBus` — publish/subscribe message broker
- `engine.spatial.SpatialGrid` — spatial queries
- `engine.loop.GameLoop` — configurable tick loop

**JavaScript:**
- `engine.Renderer` — WebGPU render coordinator
- `engine.Input` — input event stream
- `engine.Network` — SocketIO abstraction
- `engine.AssetLoader` — asset registry and loading

**Prompt file:** `.github/prompts/engine-architecture.prompt.md`

---

## Phase 2 — Graphics Pipeline Completion ✅

**Goal:** Complete the material system, parameter maps, and combiner as specified in `docs/graphics/OVERVIEW.md` (steps 3–5), then extend with lighting.

### 2.1 — Material System (OVERVIEW.md Step 3) ✅

- Define bind group layout for: uniform buffer (slot 0), albedo texture (slot 1), param map (slot 2), sampler (slot 3)
- `MaterialLoader` class: parses `material/*.json`, creates `GPUBindGroup` per material
- `EntityRenderer` selects bind group by entity material key

### 2.2 — Parameter Map Support (OVERVIEW.md Step 4) ✅

- Complete `tools/pack_param_map.py`: packs R=roughness, G=emission mask, B=palette index, A=alpha into a single RGBA texture per sprite
- Upload param maps as `GPUTexture` objects in `GPUSpriteSheet`
- Update material JSON schema (see `docs/graphics/DATA_STRUCTURES.md`)

### ✅ 2.3 — Combiner / Fragment Shader (OVERVIEW.md Step 5)

- Parameterise the WGSL fragment shader with combiner formula driven by material JSON
- `ShaderCache` generates pipeline variants from material flags (emission, palette swap, etc.)
- See `docs/graphics/COMBINER.md` and `RENDER_WORKFLOWS.md` for full specification

### ✅ 2.4 — Lighting Pass

- Second render pass: additive point-light contribution; lights defined as entities with a `light` component
- WGSL shader: screen-space light accumulation, output multiplied into base pass
- Deferred or simple forward approach (TBD based on entity count)

### ✅ 2.5 — Particle System (Compute)

- `GPUComputePipeline` for particle simulation (position + velocity integration)
- Emitter component on entities; particle data lives entirely on GPU
- Render pass reads particle buffer via storage binding

**Prompt file:** `.github/prompts/material-system.prompt.md`

---

## Phase 3 — ECS Overhaul ✅

**Goal:** Replace the current loose entity class hierarchy with a proper Entity-Component-System that scales to hundreds of entity types and thousands of instances.

### 3.1 — Component Registry ✅

- `Component` base class with a unique type ID
- `ComponentRegistry` maps type → storage array
- Struct-of-arrays storage layout for cache efficiency on hot paths (movement, AI)

### 3.2 — World Queries ✅

- `world.query(ComponentA, ComponentB)` — yields entities possessing all listed component types
- Archetype-based storage (optional optimisation if benchmarks demand it)
- Iterator-compatible; systems iterate queries in their `update()` method

### 3.3 — System Scheduler ✅

- `System` base class with `dependencies: list[type[System]]`
- Topological sort constructs an execution order per tick
- Systems can declare `PARALLEL` flag; scheduler runs non-overlapping parallel groups via `concurrent.futures`

### 3.4 — Event Bus ✅

- `EventBus.publish(event_type, payload)` — synchronous dispatch within a tick
- `EventBus.subscribe(event_type, handler)` — handler registration
- Replaces direct SocketIO calls for internal simulation communication (SocketIO remains only for client ↔ server boundary)

**Prompt file:** `.github/prompts/ecs-overhaul.prompt.md`

---

## Phase 4 — Simulation Systems ✅

**Goal:** Replace placeholder system bodies with real implementations.

### 4.1 — Pathfinding ✅

- A* over the spatial grid; heuristic = Chebyshev distance for 8-directional movement
- Flow fields for large groups (party members all moving toward same goal)
- Path cache with invalidation on entity add/remove near path tiles

### 4.2 — AI / Behaviour Trees ✅

- `BehaviourTree` + `BehaviourNode` base classes
- Leaf nodes: `Seek`, `Flee`, `Idle`, `UseItem`, `Attack`
- Composite nodes: `Sequence`, `Selector`, `Parallel`
- Party members use BTs; tree data loaded from JSON for moddability

### 4.3 — Combat System ✅

- Turn-based resolution within real-time simulation (action points)
- Stat derivation: damage formula, dodge, hit chance from entity stats
- Status effects as Components (poisoned, stunned, burning)
- `CombatEvent` published to `EventBus`; other systems (audio, UI, particles) subscribe

### 4.4 — Simple Physics ✅

- AABB collision response for solid entities
- Velocity damping; slope/terrain friction coefficients
- No rigid-body physics; keep it lightweight

**Prompt file:** `.github/prompts/simulation-systems.prompt.md`

---

## Phase 5 — Asset Pipeline ✅

**Goal:** Build a reliable, repeatable pipeline from source assets to engine-ready data.

### 5.1 — Asset Manifest

- `frontend/assets/manifest.json` auto-generated from the assets directory
- Maps logical asset IDs to file paths, metadata (frame size, frame count, material key)
- `AssetLoader` reads manifest at startup; all asset requests go through it by ID, not path

### 5.2 — Build Tools

- `tools/build_assets.py` — orchestrates all pre-processing: pack param maps, compile animation JSON to binary, verify manifest
- Run as part of `setup.bat`; results cached; invalidated by source file hash

### 5.3 — Procedural Generation Framework

- `engine/procgen/` — wave function collapse (WFC) implementation
- Tile rule sets loaded from JSON; weighted outcomes; key cell injection
- Used for area generation; see `notes.md` for design intent

### 5.4 — Hot Reload (Dev Mode)

- Watch `frontend/assets/` for file changes
- On change: re-run `pack_param_map.py` for the changed asset, send reload event via SocketIO
- Shaders watched separately; pipeline recompiled on WGSL change without full restart

---

## Phase 6 — Save / Load / Persistence ✅

**Goal:** Persistent game state that survives process restarts, with clean versioning.

### 6.1 — Save File Format

- One directory per save slot: `saves/<slot_name>/`
- `world.json` — world metadata, player ref, tick count
- `area-<id>.json` — serialised entity list + component data per area
- `player-<id>.json` — player controller state, inventory, stats

### 6.2 — Serialisation / Deserialisation

- Each `Component` subclass implements `to_dict()` / `from_dict()`
- `World.serialise()` iterates all entities and their components
- Version field in each file; migration functions for format upgrades

### 6.3 — Save Management UI

- Load / new game screen (already partially stubbed in `playerSelect.js`)
- Auto-save every N ticks (configurable)
- Manual save via keybind; save slots with timestamps

---

## Phase 7 — UI Framework

**Goal:** A fully custom-drawn, art-asset-skinned UI — imgui-bundle used only as the input/hit-testing/frame-lifecycle engine, never its default widget chrome — supporting keyboard/mouse/gamepad navigation, animated elements, and 3D/shader content embedded inside UI panels (e.g. a liquid health orb). Redesigned mid-phase from an earlier, narrower "use imgui's default widgets" draft once the real scope was clear — see `.github/prompts/ui-framework.prompt.md`.

**Engine-layer half: done and verified**, ships on `engine` as `client/engine/ui/` (`draw.py`/`theme.py`/`gamepad.py`/`nav.py`/`widgets.py`/`panel3d.py`/`templates.py`) plus a new `shader_cache.py` `'orb'` variant and a standalone smoke test, `run_ui_test.py` (confirmed: runs 20+ seconds, zero draw errors). One real bug found and fixed during verification: `Panel3D` must default its offscreen texture format to `renderer.canvas_format`, not a hardcoded format, since every existing render pipeline in this codebase is compiled against the former.

**Game-layer half: not started**, belongs on a game branch (`legacy` today), not `engine` — see the prompt file's "Remaining work" section: rebuild `client/game/ui.py`'s existing HUD (built ad hoc during Phase 13, not previously tracked here) plus a new inventory panel and dialogue box using `client/engine/ui/` instead of plain imgui widgets.

### 7.1 — Core drawing/input primitives (`client/engine/ui/`) — ✅ done, engine-layer

- `draw.py`'s `ImDrawList`-based primitives + the confirmed `imgui_renderer.backend.register_texture()` wgpu-to-imgui texture bridge
- `nav.py`'s input-method-agnostic focus (keyboard + `gamepad.py`'s GLFW polling, mouse hover claims focus so the two never disagree)
- `widgets.py`'s composable functions (not a class hierarchy) and `templates.py`'s game-agnostic patterns (confirm/deny, chat box, titled window)

### 7.2 — Theme + embedded 3D/shader content — ✅ done, engine-layer

- `theme.py`: JSON colour palette + optional custom fonts/skin images, applied via `draw.py`'s primitives directly (no `imgui.push_style_color` widget-chrome dependency)
- `panel3d.py`'s render-to-texture bridge for embedding 3D content or a shader effect in a UI rect; `shader_cache.py`'s new `'orb'` variant is the first real consumer (liquid fill + fresnel rim, reusing existing unused `MatUniforms` slots — no new bind-group layout needed)

### 7.3 — Inventory & Dialogue — 🔲 not started, game-layer (see prompt file)

- `InventoryPanel` — grid layout, drag-and-drop (`imgui`'s own drag-drop API, confirmed present), item tooltips, built on `widgets.image_button`
- `DialogueBox` — scripted conversation trees (JSON schema in the prompt file), built on `templates.window` + `widgets.button`
- Both driven by data fetched from server via SocketIO, wired through `network.py`'s existing callback-dict pattern; both must reuse `ui.py`'s pending-request pattern for anything triggered outside the imgui frame bracket (confirmed SIGSEGV otherwise — the same rule `client/engine/ui/draw.py`'s whole design enforces)

---

## Phase 8 — Audio

**Goal:** Integrated audio engine for music and spatial sound effects.
SuperCollider + OSC is the primary event-driven runtime path; a small
Python playback engine is the fallback. Rebuilt 2026-08-25 against the
native `client/`/engine-branch architecture — the original 8.1–8.3
below targeted the deleted `frontend/js/` browser client's Web Audio
API, which no longer applies (no browser, no autoplay policy, no
`AudioContext`). See `.github/prompts/audio.prompt.md` for the full,
current spec, including the engine/game-branch split this phase now
requires (`backend/app.py`-side event mapping is a game-branch
concern, same as Phases 11/12/14).

### 8.1 — Engine-Layer Fallback Playback Engine

- `client/engine/audio.py`: a `miniaudio`-backed playback engine,
  opened at client startup (no user-gesture gate — native apps don't
  need one)
- Master volume, `music`/`sfx`/`ambient` buses, implemented as plain
  gain multiplication in a manual mixing callback, not a node graph
- All audio routed through its bus before the master multiplier;
  nothing writes straight to the output device

### 8.2 — Music Playback

- Streaming/decoding from `frontend/assets/audio/music/` via
  `client/engine/asset_loader.py` (direct filesystem read, no
  `fetch()`)
- Crossfade between tracks via a linear gain ramp inside the mixing
  callback
- Loop points defined in the audio manifest (`tools/build_manifest.py`
  extended in Step 2 of the prompt file)

### 8.3 — Spatial SFX

- Manual stereo pan + distance attenuation per active voice, computed
  from listener/source position vectors each mixer callback — a
  deliberate approximation, not `PannerNode`/HRTF; real
  spatialization quality is SuperCollider's job (8.4)
- Listener position/orientation updates from whatever owns the live
  `camera` dict each frame (`client/engine/camera_modes.py`/
  `free_camera.py`'s `apply(camera)` convention), never a direct
  `Scene` reference from the playback engine itself
- Fire-and-forget API: `audio.play_sfx(asset_id, world_x, world_y, world_z)`

### 8.4 — Live Coding Option (SuperCollider + OSC)

- `backend/engine/osc.py`: generic, config-driven, no-op-safe OSC
  sender (`send_tempo`/`send_pattern`/`send_event`) — engine-layer,
  no game-event knowledge, mirroring where `EventBus`/`SpatialGrid`/
  `GroupRegistry` already live
- Launch and supervise SuperCollider (`scsynth`/`sclang`) optionally,
  config-driven (`auto_launch`)
- Mapping real game events (`area_enter`, `combat_start`,
  `low_health`) to OSC cues is a game branch's own system
  (`backend/game/systems/`), subscribing to `EventBus` — **blocked on
  a game branch existing**, not buildable on `engine`
- Fallback to `client/engine/audio.py` if SuperCollider is unavailable
- Keep this path optional so packaged builds can ship without requiring SuperCollider

---

## Phase 9 — Distribution & Tooling

**Goal:** A one-step build that produces a distributable executable with no Python installation required.

### 9.1 — PyInstaller Packaging

> **Updated for the native client (Phase 13, `.github/prompts/wgpu-py-migration.prompt.md`) — do not bundle PyWebView or plan around `run_browser.py`; this project doesn't use either anymore.**

- `tools/build.py` — runs PyInstaller with spec file; bundles Flask, SocketIO, `client/` (GLFW + `wgpu-py` + `imgui-bundle`), and all game assets into a single directory or `.exe`
- Windows: sign with code signing certificate (optional)
- macOS: bundle as `.app`, notarise (optional)
- Linux: ships directly, same as Windows/macOS — the native client doesn't depend on WebKitGTK, so there's nothing to defer and no `run_browser.py`/AppImage fallback needed

### 9.2 — Developer Tools

- **Entity Inspector**: overlay panel listing all entities in the current area with live component values
- **Perf Overlay**: superseded — Phase 14's level editor already has this (entity count + live FPS, in its Scene Settings panel), not a separate future page
- **Animation Preview**: superseded — Phase 14's asset preview mode (`client/engine/asset_preview.py`) generalises this: orbit camera, live stylization toggles, animation playback, works for meshes/entities/materials, not just sprite clips. See [docs/graphics/AREA_SYSTEM.md](docs/graphics/AREA_SYSTEM.md#asset-preview-mode).

### 9.3 — Release Versioning

- Semantic versioning (`MAJOR.MINOR.PATCH`): MAJOR = save format break, MINOR = new engine feature, PATCH = bug fix
- Version baked into build artifact names and reported in `engine.version`

---

## Phase 10 — 3D Coordinate Mapping (Future)

**Goal:** Implement the "2.5D / 3D (Future)" section of `docs/graphics/COORDINATE_MAPPING.md` — a real perspective camera, billboarded sprites in a 3D world, and a minimal textured-mesh draw path — without disturbing the existing 2D orthographic rendering. This phase is a **foundation**, not a commitment to a single art direction: stylization is layered on as opt-in flags so later rendering techniques can build on the same camera/mesh plumbing without inheriting assumptions from whatever look ships first.

### 10.1 — Matrix Helpers & 3D Camera ✅

- `frontend/js/engine/mat4.js` — explicit, dependency-free `identity`/`perspective`/`lookAt`/`multiply`/`translationScale`/`rotationXYZ`/`compose` helpers, matching the project's existing hand-built flat-`Float32Array` MVP convention
- `camera` object gains optional `mode` (`'2d'` default / `'3d'`), `position`, `target`, `up`, `fov`, `near`, `far`; `getViewProjectionMatrix()` added to `renderer.js`, returns `null` in 2D mode
- Fog/ambient fields (`fogColor`/`fogNear`/`fogFar`/`ambientColor`) land with Step 8 (stylization hooks), not here

### 10.2 — Billboarded Sprites ✅

- Sprite quads built from the camera's right/up vectors so 2.5D sprites face the camera in a 3D world without per-entity meshes
- Reuses existing sprite/material pipelines and bind groups — only the model matrix construction differs
- Depth testing added via a separate, depth-tested pipeline variant (`ShaderCache.getSpritePipeline3D`) and a depth texture/attachment, kept fully independent of the existing 2D pipeline so 2D rendering is provably unaffected
- Verified rendering and depth-sorting correctly via a throwaway dev harness (`frontend/test-3d.html` + `run_desktop_test.py`, opened through the real PyWebView/WebView2 client rather than a browser, to sidestep browser-default WebGPU availability issues)

### 10.3 — Minimal Textured Mesh Path

- Small project-defined mesh JSON format (`position`/`normal`/`uv`/optional `color` per vertex + index list) under `frontend/assets/data/mesh/` — a project-specific runtime format, not a glTF subset
- `Mesh` class uploads interleaved vertex + index buffers; new `'mesh'` `ShaderCache` pipeline variant issues indexed draws
- An entity-**definition** file (`frontend/assets/data/entity/entity-<uuid>.json`) references a `mesh` — shared appearance data, no placement. A networked entity opts in via `render_template` (which definition to use) plus `transform3d` (this instance's rotation/scale — position is its existing `x`/`y`/`z`); entities without either are unaffected. Position/rotation/scale are deliberately never on the shared definition — two placed copies of one template must be independently positioned

### 10.4 — Mesh Authoring Pipeline

- `tools/convert_mesh.py` — build-time-only converter (stdlib `json`/`struct`, no new pip dependency) from Blender-exported glTF 2.0 (`.gltf`/`.glb`) into the 10.3 mesh JSON format; reads geometry only (position/normal/uv/color, single mesh/primitive) and refuses skins, morph targets, or multiple primitives rather than mishandling them
- Not a runtime import path — glTF is never loaded by the engine itself, only consumed offline by this tool
- `tools/build_manifest.py` gains a `"meshes"` manifest category (mirroring `animations`/`materials`); `assetLoader.js`'s `loadManifest()` category list is extended to match, so mesh assets resolve by id like every other asset type

### 10.5 — Optional Stylization Hooks

- Independent, opt-in flags — `vertex_color` (Gouraud tint), `affine_uv` (N64-style texture warp), `color_levels` (colour banding), scene fog (`fogColor`/`fogNear`/`fogFar`) — each defaulting to off/neutral
- Happen to compose into a low-poly N64 look, but are named and gated generically so any future rendering technique can adopt some, all, or none of them independently
- A mesh/material that sets none of these renders identically to the plain Step 10.3 path

### 10.6 — Multi-Part Meshes & Attachment Sockets

- Mesh JSON gains optional named `sockets` (local anchor points); `convert_mesh.py` extracts them from unmeshed, named glTF nodes (Blender Empties) without widening the converter into a general importer
- Entities gain an optional `parts` array — each part a mesh + an optional `attachTo: { part, socket }` — composed through the attachment chain at render time; entities using a plain `mesh` field are unaffected
- The foundation both 10.7 and 10.8 build on: a staff and its separately-modeled hanging charm are two parts, not one rigid mesh

### 10.7 — Secondary-Motion "Dangle" Spring

- `frontend/js/engine/dangle.js` — a hand-rolled, client-side-only spring-damper per dangling part (inertial kick from parent motion, gravity, spring-to-rest, damping), **not** a physics engine and **not** connected to the backend ECS/collision system in any way
- Opt-in per part via a `dangle: { stiffness, damping, gravity, maxOffset }` block; the cosmetic-motion answer for something like a charm hanging off a staff swaying slightly as the player moves
- Governed by `.github/copilot-instructions.md`'s "Physics & Simulation Boundary": lives strictly on the frontend/cosmetic side, is never named "physics," and never writes back into authoritative entity state — see `backend/engine/physics.py`'s module docstring for the same boundary stated from the backend side

### 10.8 — Transform Animation Clips

- New `"type": "transform"` animation clip (keyframed `position`/`rotation`/`scale`, reusing the existing clip-JSON pattern) for authored, repeating part motion — a spinning coin, a bobbing lid
- `sampleTransformClip()` — hand-rolled linear interpolation, matching `RENDER_WORKFLOWS.md` Workflow E's `lerpPreset` style
- Composes with 10.7's dangle offset — a part can spin *and* wobble from movement simultaneously

### 10.9 — Action-Triggered Animation Playback

- One-shot animations for discrete actions (attack, jump) — the *only* backend-touching sub-phase, since action start/duration must be server-authoritative to avoid client desync
- Backend: `ACTION_DURATIONS` table + `state_started_at` timestamp + per-tick auto-revert (`player.py`, `actions.py`, `tick.py`); reuses the existing `state_update` broadcast, no new message type; adds a `"jump"` action alongside the existing `move`/`attack`/`use_item`/`interact`
- Frontend: extends the existing `entity.state` → animation mapping with one-shot (`loop: false`) sprite clips, and an `action_animations` map on mesh parts for one-shot transform-clip playback; composes with 10.7 (dangle) and 10.8 (looping clips)

**Scope note:** No skeletal animation, skinning, rigid-body/collision physics, or shadow mapping — perspective projection, camera, billboards, static/multi-part meshes, a build-time mesh authoring tool, opt-in stylization toggles, attachment sockets, a cosmetic dangle spring, transform animation clips, and server-timed one-shot action playback only.

**Prompt file:** `.github/prompts/3d-coordinate-mapping.prompt.md`

---

## Phase 11 — Area / Scene System (Future)

**Goal:** A single runtime container (`Scene`) for entities, camera, and lighting, populated either from a pre-authored Area file or the live SocketIO gameplay stream, and writable at any time via a small imperative API — so the same rendering pipeline serves a map builder, a dev/test harness, a plain asset/scene viewer, and scripted gameplay dressing without four separate implementations. Depends on Phase 10 for the `camera`/`fog`/mesh-`parts` fields this phase's schema reuses, and extends Phase 6's `Area` file format rather than forking it.

### 11.1 — Area File Schema Extension

- `backend/game/area.py` gains optional `camera`/`lighting` blocks (passive metadata, no gameplay effect) in `to_dict()`/`from_dict()`/`get_full_state()`; absent by default, so every existing save file is unaffected
- Field names reuse Phase 10's `camera` object and `fogColor`/`fogNear`/`fogFar` exactly, rather than inventing parallel ones

### 11.2 — `Scene`: Single Runtime Container

- `frontend/js/engine/scene.js` — the one object both the network path and a file load populate; `entities`/`camera`/`lighting`/`startCamera` plus `addEntity`/`updateEntity`/`removeEntity`/`setCamera`/`setLighting`/`setStartCamera`
- `camera` is the live, constantly-moving view; `lighting` and `startCamera` are the authored values actually written to a save file — separated specifically so flying around to inspect a scene never silently changes what gets saved as the spawn point/ambience (Phase 14's editor is the only thing that calls `setStartCamera`)
- Every entity tagged `'authoritative'` (network or file) or `'local'` (runtime-injected); a same-id collision across tags is refused with a warning, never silently arbitrated
- `gameState` (the existing global in `main.js`) becomes a thin proxy onto `Scene`, so `renderer.js`/`ui.js`/`input.js` need zero changes — this phase wraps the working gameplay path, it doesn't rewrite it

### 11.3 — Four Run Modes, One Boot Path

- Gameplay: unchanged, network-driven, existing `index.html`
- Viewer / Builder / Test: one new page (`frontend/area-viewer.html`), file-loaded, zero network connection, free-fly camera — differentiated only by what runs after load (nothing / a crude on-page panel / a script), not by separate implementations
- Builder stays intentionally crude (plain form controls, a save-to-file button) — a working round-trip through the Phase 11.1 schema matters more than editor polish

### 11.4 — Scripted Gameplay Dressing

- A server-sent cue can trigger `scene.addEntity(..., 'local')` for purely cosmetic, non-networked moments (a cutscene camera pan, a decorative prop)
- Governed by the same rule as `.github/copilot-instructions.md`'s "Physics & Simulation Boundary": anything added this way is non-authoritative; if it needs to be simulated or interactive, it must be a real backend entity delivered through `state_update` instead

### 11.5 — Movement/Collision Foundation Fix (prerequisite for 11.6)

- Tracing the actual per-tick execution order (`tick.py` registration × `scheduler.py`'s topological sort) surfaced two real bugs: collider-bearing entities are double-integrated (`MovementSystem` and `PhysicsSystem` both move them, the second pass uncollided), and path-driven AI movement (`Seek`/`Flee` → `PathfindingSystem`) teleports position and skips collision entirely because it currently runs after `PhysicsSystem` resolves for the tick
- Fix: `MovementSystem` skips collider-bearing entities; `PathfindingSystem` sets velocity instead of teleporting position; dependency graph reordered so `PhysicsSystem` is always the last movement system to run each tick, integrating and colliding everyone exactly once
- Also switches `PhysicsSystem`'s collision candidate lookup from an O(n²) full scan to the already-present `SpatialGrid`
- Not scope creep — building script-driven movement on top of these bugs would make "interact with other entities" unreliable and "multiple entities" scale badly, which is exactly what 11.6 needs to avoid

### 11.6 — Script-Driven Entity Movement

- `ScriptComponent` (`waypoint_loop`/`orbit`/`follow`, params + runtime state) processed by a new `ScriptMovementSystem` that only ever writes `VelocityComponent` — never position directly — so every script-driven entity rides 11.5's single corrected `PhysicsSystem` pass for integration and collision, the same as player and AI-driven entities
- Real backend ECS entities, not client-side `Scene` additions — per the Physics & Simulation Boundary, only authoritative, server-simulated entities can genuinely interact (collide, trigger, be detected); a script-driven entity is only ever purely cosmetic if added via `Scene.addEntity(..., 'local')` instead, in which case it explicitly cannot interact with anything
- `ColliderComponent` gains an optional `trigger` flag (overlap-only, no push-out) publishing an `"entity_overlap"` `EventBus` event — the generic hook for pickups/doors/area markers, following the same event pattern `CombatEvent` already established
- Authored the same way as any other entity — a `ScriptComponent` entry in an entity's `components` list round-trips through the existing serialization/Area-file machinery with no new code; needs a `ColliderComponent` too if it should actually collide, which is optional (a script entity with no collider moves but passes through everything)
- Known limitation, documented not solved here: standalone viewer/builder/test modes (11.3) have no backend running, so a placed `ScriptComponent` entity is inert data there — it only actually moves/interacts inside a real gameplay session

**Prompt file:** `.github/prompts/area-system.prompt.md`

---

## Phase 12 — Zones & Triggers (Future)

**Goal:** Spatial trigger volumes — `Zone`/`ZoneRegistry`, added this session (not part of the original phase plan). Two shapes: a simple two-corner AABB, or a mesh-footprint volume (a cached 2D XZ-plane point-in-polygon test plus a Y-range check — an explicit, documented approximation, not true volumetric containment). Declarative `on_enter`/`on_exit` effects: fire an `EventBus` event, add/remove the entity from a `GroupRegistry` group (`backend/engine/group.py`), or set/clear tag data / attach a `Component` on the entity directly. Depends on Phase 11 (the Area-file schema this extends with a `zones` key).

**Architectural note carried over from `backend/engine/group.py`'s own precedent this session**: `ZoneRegistry` is driven from `Area.update()` each tick, *not* registered as an ECS `System` with the `SystemScheduler` — because nothing in this codebase ever populates `ecs_world` (confirmed: no call to `ecs_world.add()`/`add_component()` anywhere), so a registered `System` would compile correctly and never see real data. This is the same reasoning, not a new one.

**Scope note:** exactly two shapes, no general 3D-volume system; no third-party geometry dependency (hand-rolled point-in-polygon); effects are declarative data, never `eval`/`exec`.

**Prompt file:** `.github/prompts/zones.prompt.md`

---

## Phase 14 — Level Editor & Asset Viewer (Future)

**Goal:** Turn Phase 11's deliberately crude builder mode into a fairly polished level editor and asset viewer — a real launcher for opening/starting areas and previewing assets, a full translate/rotate/scale gizmo, undo/redo, a property panel, an asset browser, grid/snapping, and a proper save flow. Depends on Phase 11 (`Scene`, the standalone boot path) and Phase 10 (`mat4.compose`/`rotationXYZ`, `render_template`, stylization hooks, `parts`/`dangle`/`animation_id`). Extended this session with zone authoring (depends on Phase 12, above), a UI-menu editor built on Phase 7's `client/engine/ui/`, and an Action Definitions panel (Phase 10 Step 12's data half only).

### 14.1 — Entry Point / Launcher

- One landing screen (Open Area / New Area / View Asset), shown by `client/engine/launcher.py` when the native client starts with no `--area`/`--asset` argument — manifest-driven (`"areas"` category, alongside the existing `"meshes"`/`"entities"`), zero backend connection required
- Asset preview mode generalises and supersedes this document's own Phase 9.2 "Animation Preview" page concept — one orbit-camera viewer with live stylization toggles and animation playback, not a second redundant page

### 14.2 — Full Transform Gizmo

- Mode-switchable (`T`/`R`/`S`) translate/rotate/scale gizmo — axis handles for translate and scale, rotation rings per axis, plus a uniform-scale handle — working in both 2D and 3D, synced live with numeric property-panel fields
- No free-form bounding-box/corner-drag resize (axis and uniform handles only) and no multi-select — explicit scope boundaries

### 14.3 — Undo/Redo, Property Panel, Asset Browser

- `EditorCommands` command-stack layer wraps `Scene`'s existing API (`add_entity`/`update_entity`/`remove_entity`/`set_camera`/`set_lighting`) — `Scene` itself stays unaware undo exists
- Property panel splits instance-level fields (transform, `render_template`, `ScriptComponent`) — plain edit, no confirmation — from template-level fields (`parts[]`'s `localOffset`/`dangle`/`animation_id`/`action_animations`) — explicit confirm + warning, since a write there changes every placement of that template, everywhere, not just the selected one
- Manifest-driven, searchable asset browser replaces the crude "type a raw asset id" flow from Phase 11.3

### 14.4 — Grid/Snapping and Save Flow

- Ground grid, position snapping, optional rotation snapping, live entity-count/FPS readout
- A Scene Settings panel with explicit "Set Start Camera"/"Set Start Lighting" actions — the only calls to `Scene.set_start_camera()` in the whole system
- Area-save and entity-definition-save finished for real as direct filesystem writes (`open(path, 'w')` — no Flask dev route, matching the native client's direct-filesystem-access convention), both refreshing `manifest.json` after writing so new/edited files are immediately discoverable via the 14.1 launcher; "Load" is the 14.1 launcher, not a second dialog

### 14.5 — Zone Authoring and UI Menu Authoring (added this session)

- Zone placement reuses this phase's own gizmo (AABB) and asset browser (mesh-footprint) rather than inventing new interactions; a property panel edits Phase 12's 8 effect types as repeatable `on_enter`/`on_exit` rows
- A 2D-only UI-menu editor built directly on Phase 7's `client/engine/ui/` real widget functions — the live preview *is* the runtime appearance, not separate editor chrome — with keybind, zone, and entity-interact triggers; zone/entity triggers write back into the *referenced* zone's/entity's own data rather than inventing a parallel mechanism

### 14.6 — Action Definitions Panel (added this session)

- An `actions.json` registry (name + `duration_ms`, the editor-authored equivalent of `backend/engine/example_game_loop.py`'s `ACTION_DURATIONS`) plus a per-part "Action Animations" section assigning a transform clip per action, both undoable and manifest-free (a single well-known asset, like `ui_theme.json`)
- Deliberately data-only: deciding *when* an action fires is real gameplay logic in a game branch's own `player.py`/`actions.py`, not something this panel authors — see `docs/graphics/ACTION_TRIGGERED_ANIMATIONS.md`'s data/trigger split

**Scope note:** No multi-select, no history-panel UI, no custom asset import UI, no terrain tools, no real-time collaborative editing, no visual behaviour-tree/script editor, no new zone shapes/effect types beyond what Phase 12 already defines, no action trigger-wiring (data authoring only).

**Prompt file:** `.github/prompts/level-editor.prompt.md`

---

## Phase 15 — Entity Builder & Blender Asset Pipeline (Future)

**Goal:** House every Blender-export conversion script (`convert_mesh.py`, `convert_animation.py`, `pack_param_map.py`) and the rigid-part-hierarchy authoring workflow behind one launcher-reachable tool, replacing hand-run CLI scripts and hand-edited entity-definition JSON. Depends on Phase 10 (`parts`/`attachTo`/`localOffset`/sockets/`dangle`/`animation_id`/`action_animations` schema) and Phase 14 (the launcher, `asset_preview.py`'s orbit camera, and `area_viewer.py`'s template-editing panel, all extended/shared rather than duplicated).

### 15.1 — Shared-Code Extraction

- `OrbitCamera` extracted out of `asset_preview.py` into its own module so this new tool and asset preview both use one implementation
- The per-part `dangle`/`localOffset`/`action_animations` editing UI extracted out of `area_viewer.py`'s `_draw_template_section` into a shared function both files call

### 15.2 — Import Tooling

- A `frontend/assets/pending/models/` and `.../animations/` convention (extending the existing `pending/` directory `build_assets.py` already uses for param-map source images) — no native OS file dialog, no `tkinter` (explicitly excluded from the packaged build per Phase 9)
- Import Mesh / Import Animation panels calling `convert_mesh.convert()`/`convert_animation.convert()` in-process, surfacing their exact `ConvertError` messages unmodified

### 15.3 — Part Builder

- Add/remove parts; mesh and material pickers; an `attachTo` picker restricted to already-added earlier parts (enforcing `entity_renderer.py`'s ordering rule in the UI itself) and a socket picker restricted to the parent mesh's real, loaded sockets — no free-text socket names
- "Scaffold Parts from Sockets" — suggests part/socket pairings by naming convention against the root mesh's sockets, always user-confirmed before any part is added

### 15.4 — Materials and Animation
e
- Material assignment wraps `pack_param_map.pack()` against picked albedo/roughness/emission/palette/alpha images and writes `material-<id>.json` — import-and-run only, no in-tool painting surface (documented forward-looking design, not built this phase)
- Per-part `animation_id` assignment plus playback preview (play/pause/scrub/loop, and one-shot `action_animations` preview) reusing `entity_renderer.py`'s existing clip-sampling code, not a new player

### 15.5 — Save Flow and Launcher Integration

- Explicit "Save Entity," writing `entity-<id>.json` and refreshing `manifest.json` in-process — same pattern Phase 14's Area save already established
- A third launcher action (alongside Open Area / View Asset) opening this tool for a new or existing entity

**Scope note:** No live texture/param-map painting, no native file dialogs, no skeletal/skinned mesh support, no Area/zone placement or gizmo (that's Phase 14's), no Blender scripting/automation.

**Prompt file:** `.github/prompts/entity-builder.prompt.md`

---

## Prompt Files

Each phase has a companion agent prompt in `.github/prompts/`. Completed
phases (all steps done) move to `.github/prompts/completed/` to keep the
working directory to just what's still active — a plain relocation, not
a rewrite; see each file's own historical content for what actually
shipped.

| Phase | Prompt file |
| ----- | ----------- |
| 0 | `completed/webgpu-migration.prompt.md` ✅ |
| 1 | `completed/engine-architecture.prompt.md` ✅ |
| 2 | `completed/material-system.prompt.md` ✅ |
| 3 | `completed/ecs-overhaul.prompt.md` ✅ |
| 4 | `completed/simulation-systems.prompt.md` ✅ |
| 5 | `completed/asset-pipeline.prompt.md` ✅ |
| 6 | `completed/save-load.prompt.md` ✅ |
| 7 | `ui-framework.prompt.md` 🔶 in progress |
| 8 | `audio.prompt.md` ✅ |
| 9 | `distribution.prompt.md` |
| 10 | `completed/3d-coordinate-mapping.prompt.md` ✅ |
| 11 | `area-system.prompt.md` |
| 12 | `zones.prompt.md` |
| 13 | `completed/wgpu-py-migration.prompt.md` ✅ |
| 14 | `level-editor.prompt.md` |
| 15 | `entity-builder.prompt.md` |

---

## Sequencing Notes

Phases 1 and 3 are **prerequisites** for everything else — a clean architecture and a proper ECS are the foundation every other phase depends on. Tackle them before adding more features.

Phase 2 is largely independent and can proceed in parallel with Phase 3, since it lives entirely in the JavaScript/WebGPU layer while Phase 3 lives in Python.

Phases 4–9 depend on Phase 3 completing. They can largely proceed in any order after that, with one exception: the save/load format (Phase 6.1) should be stabilised before Phase 4 adds many new component types, to avoid excessive migration work.
