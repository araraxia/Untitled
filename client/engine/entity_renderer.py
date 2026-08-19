"""EntityRenderer -- the engine's per-entity draw path. Not tied to any
one genre or dimensionality: the same class dispatches each entity to
whichever pipeline its data calls for, chosen per-entity, per-frame:
  - 2D sprite atlas + animation clips (base wgpu sprite pipeline)
  - 3D camera-facing billboards (depth-tested, still sprite-sheet-based)
    -- 2.5D entities living in a 3D scene
  - 3D textured meshes (`render_template` -> entity-definition -> `mesh`)
    -- fully modeled geometry
A single area/scene can mix all three freely; there is no assumption
that the game is 2D, isometric, or any particular genre.

Port of frontend/js/engine/entityRenderer.js -- Step 9 of
.github/prompts/wgpu-py-migration.prompt.md (re-read fresh before
porting, per that step's own instruction, and written against a real
client/engine/asset_loader.py completed ahead of this step -- see
asset_loader.py's docstring for why the ordering flipped).

**No Canvas-2D fallback path in this client at all** -- unlike the JS
version's `useGPU` flag (branching between a WebGPU path and a
Canvas-2D circle/health-bar/label fallback for browsers without
WebGPU), this native client has no non-GPU rendering surface to fall
back to; wgpu-native either works or the client can't render, period.
So `drawEntityFallback`/`drawHealthBar`/`drawEntityLabel` and every
`useGPU`/`ctx` branch have no port here -- this class always takes the
GPU path. If a genuine "renderer failed to initialize" story is ever
needed, that's an error screen, not a parallel drawing implementation.

All `load()`-style methods here are synchronous, reading JSON/images
directly off disk -- same reasoning as every other Step 7/8 module.
Entity dicts are plain Python dicts (matching JS's plain objects);
`entity.get('x')`/`entity['x']` mirror the JS original's `??`/direct
access exactly, field by field.
"""

import array
import json
import time

from client.engine import gpu_buffers, mat4, material_loader, particle_system, renderer, shader_cache
from client.engine.animation import Animation, AnimationController
from client.engine.asset_loader import FRONTEND_DIR, asset_loader
from client.engine.gpu_sprite_sheet import GPUSpriteSheet
from client.engine.mesh import Mesh


class EntityRenderer:
    """
    Args:
        entity_id: The entity ID to render.
        animation_data_paths: List of animation data file paths
            (FRONTEND_DIR-relative), defaults to [].
    """

    def __init__(self, entity_id: str, animation_data_paths: "list[str] | None" = None):
        self.entity_id = entity_id
        self.animation_data_paths = animation_data_paths or []
        self.sprite_sheets: dict[str, GPUSpriteSheet] = {}
        self.animation_controllers: dict[str, AnimationController] = {}
        self.animation_data_list: list[dict] = []  # sorted by z-index
        self.loading_complete = False

        self._canvas = renderer.canvas
        self._shader_cache = shader_cache.ShaderCache(renderer.device, renderer.canvas_format)
        self._quad_vertex_buffer = gpu_buffers.create_quad_vertex_buffer(renderer.device)
        self._uniform_buffers: dict[str, object] = {}  # sprite_key -> GPUBuffer
        self._bind_groups: dict[str, object] = {}  # sprite_key -> GPUBindGroup

        # --- 3D billboard resources ---
        # Kept entirely separate from the 2D maps above: bind groups are
        # tied to the specific pipeline they were created against, and
        # 3D billboards use a distinct, depth-tested pipeline
        # (ShaderCache.get_sprite_pipeline_3d). Reusing a 2D bind group
        # with the 3D pipeline (or vice versa) would be invalid.
        self._uniform_buffers_3d: dict[str, object] = {}
        self._bind_groups_3d: dict[str, object] = {}

        # --- Mesh resources ---
        # render_template key -> resolved entity-definition dict, or
        # None while "in flight" / after a permanent failure (the
        # in-flight marker is written before load starts so repeated
        # per-frame calls for the same key never re-trigger a load).
        self._render_templates: dict[str, "dict | None"] = {}
        # mesh asset key -> Mesh instance, or None while loading/failed.
        self._meshes: dict[str, "Mesh | None"] = {}

        # --- Material system ---
        self._material_loader = material_loader.MaterialLoader(renderer.device, asset_loader)
        self._material_handles: dict[str, "dict | None"] = {}  # entity_id -> handle
        self._runtime_overrides: dict[str, dict] = {}  # entity_id -> {key: value, ...}
        self._particle_system: "particle_system.ParticleSystem | None" = None

        # Runtime-registered light for this entity. Set via
        # register_light(); queried by renderer.py each frame.
        self._registered_light: "dict | None" = None
        # Most recent delta_time (ms) from update_entity_animation. Used
        # by the particle emitter in draw_entity.
        self._last_delta_time = 0.0

    def load_all_animation_data(self) -> None:
        """Read all animation data files and sort by z-index."""
        try:
            loaded_data = []
            for path in self.animation_data_paths:
                full_path = FRONTEND_DIR / path
                data = json.loads(full_path.read_text(encoding="utf-8"))
                loaded_data.append({"path": path, "data": data})

            self.animation_data_list = sorted(
                (
                    {"path": d["path"], "data": d["data"], "z_index": d["data"].get("relative_z_index", 0)}
                    for d in loaded_data
                ),
                key=lambda d: d["z_index"],
            )

            self.preload_all_sprite_animations()
            self.loading_complete = True
        except Exception as err:  # noqa: BLE001 -- matches the JS catch-all
            print(f"[entity_renderer] Failed to load animation data: {err}")

    def preload_all_sprite_animations(self) -> None:
        """Preload all sprite animations from all animation data sources."""
        for entry in self.animation_data_list:
            animation_data = entry["data"]
            for anim_name, anim_config in animation_data.items():
                if anim_name in ("base_model_path", "relative_z_index"):
                    continue

                sprite_path = (
                    animation_data["base_model_path"]
                    + "/"
                    + anim_config["default_sprite_version"]
                    + "/"
                    + anim_config["default_sprite_sheet"]
                )
                sprite_key = anim_name

                if sprite_key not in self.sprite_sheets:
                    gpu_sheet = GPUSpriteSheet(
                        renderer.device,
                        "assets/" + sprite_path,
                        anim_config["frame_width"],
                        anim_config["frame_height"],
                        8,  # columns -- standard 8 columns for character sprites
                        8,  # rows -- standard 8 rows for character sprites
                    )
                    try:
                        gpu_sheet.load()
                        self.sprite_sheets[sprite_key] = gpu_sheet
                        pipeline = self._shader_cache.get_sprite_pipeline()
                        # Uniform buffer: mvp(64) + uv_rect(16) + tint(16) = 96 bytes
                        u_buf = gpu_buffers.create_uniform_buffer(renderer.device, 96)
                        self._uniform_buffers[sprite_key] = u_buf
                        self._bind_groups[sprite_key] = gpu_sheet.create_bind_group(
                            renderer.device, pipeline, u_buf
                        )
                    except Exception as err:  # noqa: BLE001
                        # Without this, a failed load for this one sprite
                        # sheet silently leaves sprite_sheets[key] unset
                        # forever -- get_animation_controller() then warns
                        # "not loaded" every frame, indistinguishable from
                        # "still loading."
                        print(
                            f"[entity_renderer] Failed to load sprite sheet "
                            f"'{sprite_key}' ({sprite_path}): {err}"
                        )

    def get_animation_controller(
        self, entity_id: str, animation_type: str = "stand"
    ) -> "AnimationController | None":
        """Get or create an animation controller for an entity."""
        controller_id = f"{entity_id}_{animation_type}"

        if controller_id not in self.animation_controllers:
            anim_config = None
            for entry in self.animation_data_list:
                if animation_type in entry["data"]:
                    anim_config = entry["data"][animation_type]
                    break

            if anim_config is None:
                print(f"[entity_renderer] Animation type '{animation_type}' not found")
                return None

            sprite_sheet = self.sprite_sheets.get(animation_type)
            if sprite_sheet is None:
                print(f"[entity_renderer] Sprite sheet for '{animation_type}' not loaded")
                return None

            animations = {}
            for direction in ("down", "up", "left", "right"):
                dir_config = anim_config.get(direction)
                if not dir_config:
                    continue

                if anim_config.get("duration_type") == "variable" and isinstance(
                    anim_config.get("frame_duration"), list
                ):
                    frame_durations = anim_config["frame_duration"]
                    frame_duration = sum(frame_durations) / len(frame_durations)
                else:
                    frame_duration = anim_config["frame_duration"]

                anim_name = f"{animation_type}_{direction}"
                animations[anim_name] = Animation(
                    anim_name,
                    dir_config["start_frame_index"],
                    anim_config["frame_count"],
                    frame_duration,
                    True,  # loop
                )

            self.animation_controllers[controller_id] = AnimationController(animations)

        return self.animation_controllers[controller_id]

    def update_entity_animation(self, entity_id: str, entity: dict, delta_time: float) -> None:
        """Update entity animation state based on entity data.

        Args:
            delta_time: Milliseconds since last update (matches the JS
                unit exactly).
        """
        self._last_delta_time = delta_time
        animation_type = "walk" if entity.get("state") == "moving" else "stand"
        direction = entity.get("facing", "down")

        controller = self.get_animation_controller(entity_id, animation_type)
        if controller is None:
            return

        animation_name = f"{animation_type}_{direction}"
        controller.play(animation_name)
        controller.update(delta_time)

        entity["_anim_controller"] = controller
        entity["_anim_type"] = animation_type

    def draw_entity(self, entity: dict, camera: dict, pass_encoder) -> None:
        """Draw a single entity with its current animation.

        pass_encoder must be the active GPURenderPassEncoder owned by
        renderer.py. Draw commands are recorded onto it; the caller is
        responsible for beginning and ending the render pass.
        """
        if not self.loading_complete:
            return

        # 3D path -- must branch before the 2D screen-space x/y
        # computation below, since a 3D camera has no camera.x/camera.y
        # (it has camera.position/target instead).
        if camera and camera.get("mode") == "3d":
            # Resolve entity.render_template (if set) to its
            # entity-definition JSON *before* deciding mesh vs.
            # billboard -- an entity whose resolved definition has a
            # `mesh` field routes to the mesh path; everything else (no
            # render_template, still loading, or a definition with no
            # mesh) falls through to the billboard path unchanged.
            definition = self._resolve_render_template(entity)
            if definition and definition.get("mesh"):
                self.draw_entity_mesh(entity, camera, pass_encoder, definition)
                return

            if "_anim_controller" not in entity:
                return  # no Canvas-2D fallback in 3D mode
            self.draw_entity_3d(entity, camera, pass_encoder)
            return

        # Use interpolated position for smooth movement.
        x = entity.get("display_x", entity.get("x")) - camera["x"]
        y = entity.get("display_y", entity.get("y")) - camera["y"]

        if "_anim_controller" not in entity:
            return

        anim_config = None
        for entry in self.animation_data_list:
            if entity.get("_anim_type") in entry["data"]:
                anim_config = entry["data"][entity["_anim_type"]]
                break

        direction = entity.get("facing", "down")
        dir_config = (anim_config or {}).get(direction) or {}
        flip_x = dir_config.get("flip_x", False)

        # --- Material path (Workflow B/C) ---
        # Entities that carry a 'material' field use the 4-binding
        # material pipeline. Loading is synchronous but still
        # incremental-first-frame: Workflow A is used as a fallback on
        # frames before the handle resolves the very first time.
        if entity.get("material"):
            mat_entity_id = entity.get("id") or entity.get("entity_id")
            mat_path = "assets/data/" + entity["material"]

            if mat_entity_id not in self._material_handles:
                try:
                    handle = self._material_loader.load(mat_path)
                    self._material_handles[mat_entity_id] = handle
                except Exception as err:  # noqa: BLE001
                    print(f"[entity_renderer] Material load failed: {err}")
                    self._material_handles[mat_entity_id] = None

            handle = self._material_handles.get(mat_entity_id)
            if handle:
                overrides = self._runtime_overrides.get(mat_entity_id, {})
                variant_key = "base"
                if handle["color_ramp_type"] == "cosine":
                    variant_key = "cosine"
                elif handle["flags"]["has_color_ramp"]:
                    variant_key = "ramp"
                elif "hue_shift" in overrides:
                    variant_key = "hue"
                elif handle["flags"]["has_overlay"]:
                    variant_key = "overlay"

                mat_pipeline = self._shader_cache.get_material_pipeline(
                    variant_key, self._material_loader.bind_group_layout
                )

                sprite_key = entity.get("_anim_type", "stand")
                gpu_sheet = self.sprite_sheets.get(sprite_key)
                frame_index = (
                    entity["_anim_controller"].current_frame if "_anim_controller" in entity else 0
                )
                uv_rect = (
                    gpu_sheet.get_uv_rect(frame_index)
                    if gpu_sheet and gpu_sheet.loaded
                    else [0.0, 0.0, 1.0, 1.0]
                )

                c_w, c_h = self._canvas.get_physical_size()
                fw = anim_config["frame_width"] if anim_config else 32
                fh = anim_config["frame_height"] if anim_config else 32
                scale_x = (-1 if flip_x else 1) * (fw / c_w)
                scale_y = fh / c_h
                tx = (2 * x) / c_w - 1
                ty = 1 - (2 * y) / c_h

                overlay_intensity = handle["overlays"][0]["intensity"] if handle["overlays"] else 1.0
                intensity = overrides.get("glow_intensity", overrides.get("hue_shift", overlay_intensity))
                ramp_steps = overrides.get("ramp_steps", 0.0)
                tint = overrides.get("tint", [1, 1, 1, 1])

                cosine = handle["cosine_params"] or overrides.get(
                    "cosine_params",
                    {"a": [0.5, 0.5, 0.5], "b": [0.5, 0.5, 0.5], "c": [1.0, 1.0, 1.0], "d": [0.0, 0.33, 0.67]},
                )

                mat_uniforms = _pack_floats(
                    [
                        scale_x, 0, 0, 0,
                        0, scale_y, 0, 0,
                        0, 0, 1, 0,
                        tx, ty, 0, 1,
                        uv_rect[0], uv_rect[1], uv_rect[2], uv_rect[3],
                        0, 0, 1, 1,
                        tint[0], tint[1], tint[2], tint[3],
                        intensity,
                        time.perf_counter(),
                        ramp_steps,
                        0,
                        cosine["a"][0], cosine["a"][1], cosine["a"][2], 0,
                        cosine["b"][0], cosine["b"][1], cosine["b"][2], 0,
                        cosine["c"][0], cosine["c"][1], cosine["c"][2], 0,
                        cosine["d"][0], cosine["d"][1], cosine["d"][2], 0,
                    ]
                )

                gpu_buffers.write_uniform_buffer(renderer.device, handle["uniform_buffer"], mat_uniforms)

                pass_encoder.set_pipeline(mat_pipeline)
                pass_encoder.set_bind_group(0, handle["bind_group"])
                pass_encoder.set_vertex_buffer(0, self._quad_vertex_buffer)
                pass_encoder.draw(6)
                self._render_particle_system(entity, camera, pass_encoder)
                return  # do not fall through to Workflow A
            # Handle still loading (or failed and stays None) -- fall
            # through to Workflow A this frame.

        # --- Workflow A (legacy sprite path) ---
        sprite_key = entity.get("_anim_type")
        gpu_sheet = self.sprite_sheets.get(sprite_key)
        if not gpu_sheet or not gpu_sheet.loaded:
            return

        frame_index = entity["_anim_controller"].current_frame
        uv_rect = gpu_sheet.get_uv_rect(frame_index)

        c_w, c_h = self._canvas.get_physical_size()
        scale_x = (-1 if flip_x else 1) * (anim_config["frame_width"] / c_w)
        scale_y = anim_config["frame_height"] / c_h
        tx = (2 * x) / c_w - 1
        ty = 1 - (2 * y) / c_h

        uniforms = _pack_floats(
            [
                scale_x, 0, 0, 0,
                0, scale_y, 0, 0,
                0, 0, 1, 0,
                tx, ty, 0, 1,
                uv_rect[0], uv_rect[1], uv_rect[2], uv_rect[3],
                1, 1, 1, 1,
            ]
        )

        gpu_buffers.write_uniform_buffer(renderer.device, self._uniform_buffers[sprite_key], uniforms)

        pipeline = self._shader_cache.get_sprite_pipeline()
        pass_encoder.set_pipeline(pipeline)
        pass_encoder.set_bind_group(0, self._bind_groups[sprite_key])
        pass_encoder.set_vertex_buffer(0, self._quad_vertex_buffer)
        pass_encoder.draw(6)
        self._render_particle_system(entity, camera, pass_encoder)

    def draw_entity_3d(self, entity: dict, camera: dict, pass_encoder) -> None:
        """Draw a camera-facing billboard sprite in 3D space. The sprite
        quad's plane is spanned by the camera's world-space right/up
        vectors rather than a fixed 2D orientation, so it always faces
        the camera as it orbits -- the "2.5D" technique described in
        docs/graphics/COORDINATE_MAPPING.md.

        Reuses the same SPRITE_WGSL shader, UV-rect logic, and
        per-frame animation state as the 2D Workflow A path -- only the
        model matrix differs, and depth testing is enabled
        (get_sprite_pipeline_3d) so multiple billboards occlude each
        other correctly by world depth.

        Args:
            entity: Must have '_anim_controller'/'_anim_type' set by
                update_entity_animation, plus x/y/z (world position),
                size ([width, height] in world units), and optionally
                pivot ([fx, fy], default [0.5, 0.5] = centered).
            camera: 3D camera ({mode: '3d', position, target, up, fov,
                near, far}).
        """
        if pass_encoder is None:
            return

        sprite_key = entity.get("_anim_type")
        gpu_sheet = self.sprite_sheets.get(sprite_key)
        if not gpu_sheet or not gpu_sheet.loaded:
            return

        frame_index = entity["_anim_controller"].current_frame
        uv_rect = gpu_sheet.get_uv_rect(frame_index)

        # Lazily create this sprite_key's 3D uniform buffer + bind
        # group, separate from the 2D path's (see the constructor
        # comment on _uniform_buffers_3d/_bind_groups_3d for why they
        # can't be shared).
        if sprite_key not in self._bind_groups_3d:
            pipeline_3d = self._shader_cache.get_sprite_pipeline_3d()
            u_buf = gpu_buffers.create_uniform_buffer(renderer.device, 96)
            self._uniform_buffers_3d[sprite_key] = u_buf
            self._bind_groups_3d[sprite_key] = gpu_sheet.create_bind_group(
                renderer.device, pipeline_3d, u_buf
            )

        c_w, c_h = self._canvas.get_physical_size()
        aspect = c_w / c_h
        view_projection = renderer.get_view_projection_matrix(camera, aspect)
        if view_projection is None:
            return  # defensive -- caller already checked camera.mode

        # Camera right/up in world space, per mat4.look_at's convention:
        # row 0 of the view matrix is the camera's world-space right
        # axis, row 1 is world-space up. Column-major storage means
        # "row N" is a strided read (index N, N+4, N+8), not a
        # contiguous one.
        up_3d = camera.get("up", [0, 1, 0])
        view = mat4.look_at(camera["position"], camera["target"], up_3d)
        right = [view[0], view[4], view[8]]
        up = [view[1], view[5], view[9]]

        size = entity.get("size", [32, 32])
        half_w = size[0] / 2
        half_h = size[1] / 2

        # Pivot: [fx, fy] as a fraction of size, matching the existing
        # 2D convention (fy follows image/UV space -- 0 = top, 1 =
        # bottom). Convert into local quad space, where the raw quad
        # spans [-1, 1] with +1 = top (see gpu_buffers.create_quad_vertex_buffer).
        pivot = entity.get("pivot", [0.5, 0.5])
        pivot_local_x = 2 * pivot[0] - 1
        pivot_local_y = 1 - 2 * pivot[1]

        ex = entity.get("x", 0)
        ey = entity.get("y", 0)
        ez = entity.get("z", 0)

        # The pivot shifts the quad so the chosen anchor point -- not
        # its geometric center -- lands on the entity's world position.
        offset_x = right[0] * half_w * pivot_local_x + up[0] * half_h * pivot_local_y
        offset_y = right[1] * half_w * pivot_local_x + up[1] * half_h * pivot_local_y
        offset_z = right[2] * half_w * pivot_local_x + up[2] * half_h * pivot_local_y

        # Model matrix: local quad X axis -> right * half_w, local Y ->
        # up * half_h, local Z is always 0 for this quad so the third
        # column's contents are irrelevant and left zeroed; translation
        # places the pivot-adjusted quad at the entity's world position.
        model = [
            right[0] * half_w, right[1] * half_w, right[2] * half_w, 0,
            up[0] * half_h, up[1] * half_h, up[2] * half_h, 0,
            0, 0, 0, 0,
            ex - offset_x, ey - offset_y, ez - offset_z, 1,
        ]

        mvp = mat4.multiply(view_projection, model)

        uniforms = _pack_floats(list(mvp) + [uv_rect[0], uv_rect[1], uv_rect[2], uv_rect[3], 1, 1, 1, 1])

        gpu_buffers.write_uniform_buffer(renderer.device, self._uniform_buffers_3d[sprite_key], uniforms)

        pipeline_3d = self._shader_cache.get_sprite_pipeline_3d()
        pass_encoder.set_pipeline(pipeline_3d)
        pass_encoder.set_bind_group(0, self._bind_groups_3d[sprite_key])
        pass_encoder.set_vertex_buffer(0, self._quad_vertex_buffer)
        pass_encoder.draw(6)

    def _resolve_render_template(self, entity: dict) -> "dict | None":
        """Resolve entity['render_template'] (if set) to its
        entity-definition JSON, caching the result. This is the link
        between a networked entity (which only knows *which* template
        to use) and the frontend/assets/data/entity/entity-<uuid>.json
        file that actually describes what it looks like (mesh/parts/
        material_id -- never placement, see the backend
        Entity.transform3d comment).

        Returns:
            The definition once loaded; None if render_template is
            unset, still loading, or permanently failed to resolve/load
            -- callers must treat None as "not ready, fall back to
            existing behaviour," not as an error to surface per-frame.
        """
        key = entity.get("render_template")
        if not key:
            return None

        if key in self._render_templates:
            return self._render_templates[key]

        # Mark as "attempted" immediately -- otherwise every frame
        # before the load resolves (or fails) would see no cache entry
        # and re-attempt the same load.
        self._render_templates[key] = None

        try:
            path = asset_loader.resolve(key)
        except ValueError as err:
            print(f"[entity_renderer] Cannot resolve render_template '{key}': {err}")
            return None  # stays None in the cache -- permanent, no retry

        full_path = FRONTEND_DIR / path
        try:
            data = json.loads(full_path.read_text(encoding="utf-8"))
            self._render_templates[key] = data
        except Exception as err:  # noqa: BLE001
            print(f"[entity_renderer] Failed to load entity definition '{key}' ({path}): {err}")
            # Leave cached as None -- falls back to the billboard path
            # forever rather than retrying a genuinely broken/missing
            # asset every frame.

        return self._render_templates.get(key)

    def draw_entity_mesh(self, entity: dict, camera: dict, pass_encoder, definition: dict) -> None:
        """Draw a static textured 3D mesh. Position comes from the
        entity's own x/y/z (per-instance); rotation/scale come from
        entity['transform3d']. Neither ever comes from `definition` --
        the entity-definition file supplies only appearance (mesh/
        material_id), never placement, so multiple entities can share
        one render_template and still be independently positioned and
        rotated.

        Reuses the entity's existing material bind group exactly like
        the 2D material path -- a mesh just needs UVs that land
        somewhere sensible on the same kind of 2D texture a sprite
        entity already uses; no separate 3D material system.
        """
        if pass_encoder is None:
            return

        mesh_key = definition["mesh"]

        if mesh_key not in self._meshes:
            self._meshes[mesh_key] = None  # in-flight marker
            try:
                mesh_path = asset_loader.resolve(mesh_key)
            except ValueError as err:
                print(f"[entity_renderer] Cannot resolve mesh '{mesh_key}': {err}")
                return
            try:
                m = Mesh(renderer.device)
                m.load(mesh_path)
                self._meshes[mesh_key] = m
            except Exception as err:  # noqa: BLE001
                print(f"[entity_renderer] Failed to load mesh '{mesh_key}' ({mesh_path}): {err}")
            return  # nothing to draw yet this frame (or ever, if load failed)

        loaded_mesh = self._meshes.get(mesh_key)
        if loaded_mesh is None:
            return  # still loading (or failed)

        # Material -- same lazy-load-and-cache pattern as the 2D
        # material path, keyed by entity id so this entity's handle is
        # reused across frames. Sourced from the *definition's*
        # material_id, not entity['material'] (that field belongs to
        # the legacy 2D-only path).
        mat_entity_id = entity.get("id") or entity.get("entity_id")
        if definition.get("material_id") and mat_entity_id not in self._material_handles:
            mat_path = "assets/data/" + definition["material_id"]
            try:
                handle = self._material_loader.load(mat_path)
                self._material_handles[mat_entity_id] = handle
            except Exception as err:  # noqa: BLE001
                print(f"[entity_renderer] Mesh material load failed: {err}")
                self._material_handles[mat_entity_id] = None

        handle = self._material_handles.get(mat_entity_id)
        if not handle:
            return  # no material loaded yet -- required for the mesh path

        c_w, c_h = self._canvas.get_physical_size()
        aspect = c_w / c_h
        view_projection = renderer.get_view_projection_matrix(camera, aspect)
        if view_projection is None:
            return  # defensive -- caller already checked camera.mode

        transform_3d = entity.get("transform3d") or {}
        rotation = transform_3d.get("rotation", [0, 0, 0])
        scale = transform_3d.get("scale", [1, 1, 1])
        position = [entity.get("x", 0), entity.get("y", 0), entity.get("z", 0)]

        model = mat4.compose(position, rotation, scale)
        mvp = mat4.multiply(view_projection, model)

        # Combiner variant (base/ramp/hue/cosine) selection from
        # material flags isn't wired up for mesh entities yet -- always
        # 'base' for now, matching the JS version's current state.
        variant_key = "base"
        # Affine UV is a compile-time pipeline choice (see
        # shader_cache.py's build_mesh_wgsl_common), so it's part of
        # which pipeline gets requested, not a uniform written below.
        pipeline = self._shader_cache.get_mesh_pipeline(
            variant_key, self._material_loader.bind_group_layout, handle["affine_uv"]
        )

        # Stylization inputs, each defaulting to a true no-op so a
        # material/camera that sets none of them renders identically to
        # the plain mesh path. vertex_color/color_levels come from the
        # material; fog/ambient come from the camera/scene object
        # (renderer.get_view_projection_matrix's docstring documents
        # these same fields) since that's the one runtime object
        # already read every frame.
        vertex_color_flag = 1 if handle["vertex_color"] else 0
        color_levels = handle["color_levels"] or 0
        fog_color = camera.get("fogColor", [0, 0, 0])
        fog_near = camera.get("fogNear", 0)
        fog_far = camera.get("fogFar", 0)  # <= 0 disables fog entirely
        ambient_color = camera.get("ambientColor", [1, 1, 1])  # [1,1,1] = no-op
        # Must match renderer.get_view_projection_matrix's exact
        # defaults -- the fragment shader linearizes NDC depth back to
        # a world-unit distance using these same near/far values, so a
        # mismatch here would silently desync the fog math from the
        # projection actually used to draw this frame.
        proj_near = camera.get("near", 0.1)
        proj_far = camera.get("far", 1000)

        mat_uniforms = _pack_floats(
            list(mvp)
            + [0, 0, 1, 1]  # uv_rect -- identity
            + [0, 0, 1, 1]  # uv_overlay -- unused by the mesh path
            + [1, 1, 1, 1]  # tint
            + [0]  # intensity
            + [time.perf_counter()]  # time
            + [0]  # ramp_steps
            + [0]  # _pad
            + [0.5, 0.5, 0.5, 0]  # pal_a
            + [0.5, 0.5, 0.5, 0]  # pal_b
            + [1.0, 1.0, 1.0, 0]  # pal_c
            + [0.0, 0.33, 0.67, 0]  # pal_d
            + [vertex_color_flag, color_levels, proj_near, proj_far]  # mesh_params
            + [fog_near, fog_far, 0, 0]  # fog_range
            + [fog_color[0], fog_color[1], fog_color[2], 0]  # fog_color
            + [ambient_color[0], ambient_color[1], ambient_color[2], 0]  # ambient_color
        )

        gpu_buffers.write_uniform_buffer(renderer.device, handle["uniform_buffer"], mat_uniforms)

        pass_encoder.set_pipeline(pipeline)
        pass_encoder.set_bind_group(0, handle["bind_group"])
        pass_encoder.set_vertex_buffer(0, loaded_mesh.vertex_buffer)
        pass_encoder.set_index_buffer(loaded_mesh.index_buffer, loaded_mesh.index_format)
        pass_encoder.draw_indexed(loaded_mesh.index_count)

    def set_entity_runtime(self, entity_id: str, key: str, value) -> None:
        """Store a named runtime value for an entity's material
        uniform. Changes are picked up on the next draw_entity call.

        Supported keys and their effect:
            'glow_intensity' -- maps to u.intensity (overlay/base variants)
            'hue_shift'      -- maps to u.intensity and selects 'hue' variant
            'tint'           -- maps to u.tint; value must be [r, g, b, a]
            'ramp_steps'     -- maps to u.ramp_steps; >=2 enables cel-shading
            'cosine_params'  -- overrides cosine palette; value must be
                                {a,b,c,d} each a 3-element [r,g,b] array
        """
        overrides = self._runtime_overrides.setdefault(entity_id, {})
        overrides[key] = value

    # ------------------------------------------------------------------
    # Lighting helpers
    # ------------------------------------------------------------------

    def register_light(self, entity_id: str, color: list, radius: float) -> None:
        """Attach a point light to a specific entity so it is included
        in the lighting pass each frame. The light's world position is
        taken from the entity's interpolated position at draw time.
        """
        self._registered_light = {"entity_id": entity_id, "color": color, "radius": radius}

    def unregister_light(self, entity_id: str) -> None:
        """Remove a previously registered light from this renderer instance."""
        if self._registered_light and self._registered_light["entity_id"] == entity_id:
            self._registered_light = None

    def get_registered_light(self, entity: "dict | None") -> "dict | None":
        """Return the registered light entry with the entity's current
        world position filled in, or None if no light is registered or
        entity is None.
        """
        if not self._registered_light or entity is None:
            return None
        return {
            "x": entity.get("display_x", entity.get("x")),
            "y": entity.get("display_y", entity.get("y")),
            "color": self._registered_light.get("color") or [1.0, 1.0, 0.9],
            "radius": self._registered_light.get("radius") or 150,
        }

    # ------------------------------------------------------------------
    # Particle helpers
    # ------------------------------------------------------------------

    def simulate_particles(self, command_encoder, dt_seconds: float) -> None:
        """Dispatch a compute simulation step for this entity's particle
        system. No-op if no particle system has been created yet. Must
        be called on the command_encoder BEFORE the sprite render pass
        begins.
        """
        if self._particle_system:
            self._particle_system.simulate(command_encoder, dt_seconds)

    def _render_particle_system(self, entity: dict, camera: dict, pass_encoder) -> None:
        """Emit new particles and issue the draw call for this entity's
        emitter. Called from draw_entity when entity['emitter'] is set.
        """
        if not entity.get("emitter") or pass_encoder is None:
            return
        if self._particle_system is None:
            max_p = entity["emitter"].get("max_particles", particle_system.DEFAULT_MAX_PARTICLES)
            self._particle_system = particle_system.ParticleSystem(
                renderer.device, renderer.canvas_format, max_p
            )
        dt_sec = self._last_delta_time / 1000.0
        self._particle_system.emit(
            entity.get("display_x", entity.get("x")),
            entity.get("display_y", entity.get("y")),
            entity["emitter"],
            dt_sec,
        )
        c_w, c_h = self._canvas.get_physical_size()
        self._particle_system.render(pass_encoder, camera, c_w, c_h)

    def destroy(self) -> None:
        """Release all GPU resources held by this renderer. Must be
        called when the entity is no longer needed.
        """
        for buf in self._uniform_buffers.values():
            buf.destroy()
        self._uniform_buffers = {}
        self._bind_groups = {}
        for buf in self._uniform_buffers_3d.values():
            buf.destroy()
        self._uniform_buffers_3d = {}
        self._bind_groups_3d = {}
        for sheet in self.sprite_sheets.values():
            sheet.destroy()
        self.sprite_sheets = {}
        for m in self._meshes.values():
            if m is not None:
                m.destroy()
        self._meshes.clear()
        self._render_templates.clear()
        self._material_handles.clear()
        self._runtime_overrides.clear()

        self.animation_controllers = {}
        self.animation_data_list = []
        self.loading_complete = False


def _pack_floats(values: list) -> array.array:
    """Pack a flat list of numbers into a float32 array.array, ready for
    device.queue.write_buffer(). Small local helper rather than a
    gpu_buffers.py export -- every call site here already builds a
    plain Python list the same way the JS `new Float32Array([...])`
    literals do; this is just the final packing step.
    """
    return array.array("f", values)
