/**
 * EntityRenderer - the engine's per-entity draw path. Not tied to any one
 * genre or dimensionality: the same class dispatches each entity to
 * whichever pipeline its data calls for, chosen per-entity, per-frame:
 *   - 2D sprite atlas + animation clips (Canvas 2D fallback or the base
 *     WebGPU sprite pipeline) — flat, screen-space entities
 *   - 3D camera-facing billboards (depth-tested, still sprite-sheet-based)
 *     — 2.5D entities living in a 3D scene
 *   - 3D textured meshes (`render_template` → entity-definition → `mesh`)
 *     — fully modeled geometry
 * A single area/scene can mix all three freely; there is no assumption
 * that the game is 2D, isometric, or any particular genre. See
 * docs/graphics/DATA_STRUCTURES.md and .github/prompts/3d-coordinate-mapping.prompt.md
 * for the data model each path consumes.
 */
class EntityRenderer {
  /**
   * Creates a new EntityRenderer instance
   * @param {CanvasRenderingContext2D} ctx - The canvas 2D rendering context
   * @param {string} entityId - The entity ID to render
   * @param {Array<string>} animationDataPaths - List of animation data file paths
   * @param {boolean} [useGPU=false] - When true, use the WebGPU render path
   */
  constructor(ctx, entityId, animationDataPaths = [], useGPU = false) {
    this.ctx = ctx;
    this.entityId = entityId;
    this.animationDataPaths = animationDataPaths;
    this.useGPU = useGPU;
    this.spriteSheets = {};
    this.animationControllers = {};
    this.animationDataList = []; // Store all animation data sorted by Z-index
    this.loadingComplete = false;

    if (useGPU) {
      this._canvas = document.getElementById("game-canvas");
      this._shaderCache = new ShaderCache(
        gpuDevice,
        navigator.gpu.getPreferredCanvasFormat(),
      );
      this._quadVertexBuffer = createQuadVertexBuffer(gpuDevice);
      this._uniformBuffers = {}; // spriteKey → GPUBuffer
      this._bindGroups = {}; // spriteKey → GPUBindGroup

      // --- 3D billboard resources (Step 4) ---
      // Kept entirely separate from the 2D maps above: bind groups are
      // tied to the specific pipeline they were created against
      // (gpuSpriteSheet.js's createBindGroup uses pipeline.getBindGroupLayout(0)),
      // and 3D billboards use a distinct, depth-tested pipeline
      // (ShaderCache.getSpritePipeline3D). Reusing a 2D bind group with
      // the 3D pipeline (or vice versa) would be invalid.
      this._uniformBuffers3D = {}; // spriteKey → GPUBuffer
      this._bindGroups3D = {}; // spriteKey → GPUBindGroup

      // --- Mesh resources (Step 5) ---
      // render_template key → resolved entity-definition JSON, or `null`
      // while a fetch is in flight / after a permanent failure (the
      // in-flight marker is written *before* the fetch starts, matching
      // renderer.js's getEntityRenderer race-condition fix, so repeated
      // per-frame calls for the same key never trigger duplicate fetches).
      /** @type {Map<string, Object|null>} */
      this._renderTemplates = new Map();
      // mesh asset key → Mesh instance, or `null` while loading/failed,
      // same in-flight-marker convention as _renderTemplates above.
      /** @type {Map<string, Mesh|null>} */
      this._meshes = new Map();

      // --- Material system ---
      this._materialLoader = new MaterialLoader(gpuDevice);
      /** @type {Map<string, import('./sprites/materialLoader.js').MaterialHandle|null>} */
      this._materialHandles = new Map(); // entityId → handle (null while loading)
      /** @type {Map<string, Object>} */
      this._runtimeOverrides = new Map(); // entityId → { key: value, … }
      /** @type {ParticleSystem|null} */
      this._particleSystem = null;
    }

    /**
     * Runtime-registered light for this entity (Phase 2.4).
     * Set via registerLight(); queried by renderer.js each frame.
     * @type {{entityId:string, color:number[], radius:number}|null}
     */
    this._registeredLight = null;
    /**
     * Most recent deltaTime (ms) from updateEntityAnimation.
     * Used by the particle emitter in drawEntity.
     */
    this._lastDeltaTime = 0;
  }

  /**
   * Load all animation data files and sort by Z-index
   * @returns {Promise<void>}
   */
  async loadAllAnimationData() {
    try {
      // Load all animation data files
      const loadPromises = this.animationDataPaths.map(async (path) => {
        const response = await fetch(path);
        const data = await response.json();
        return { path, data };
      });

      const loadedData = await Promise.all(loadPromises);

      // Sort by relative_z_index (if present)
      this.animationDataList = loadedData
        .map(({ path, data }) => ({
          path,
          data,
          zIndex: data.relative_z_index || 0,
        }))
        .sort((a, b) => a.zIndex - b.zIndex);

      // Preload sprite sheets for all animation data
      await this.preloadAllSpriteAnimations();
      this.loadingComplete = true;
    } catch (error) {
      console.error("Failed to load animation data:", error);
    }
  }

  /**
   * Preload all sprite animations from all animation data sources
   * @returns {Promise<void>}
   */
  async preloadAllSpriteAnimations() {
    // The Canvas 2D fallback (drawEntityFallback) doesn't use sprite
    // sheets at all — it draws a plain circle from entity.state/id. Skip
    // WebGPU sprite sheet creation entirely when useGPU is false, rather
    // than constructing a GPUSpriteSheet against a null gpuDevice (which
    // WebGPU-unavailable environments hit immediately on .load()'s
    // this._device.createTexture(...) call).
    if (!this.useGPU) return;

    const promises = [];

    // Iterate through each animation data file
    for (const { data: animationData } of this.animationDataList) {
      // Iterate over each animation type and load its sprite sheet
      for (const [animName, animConfig] of Object.entries(animationData)) {
        if (animName === "base_model_path" || animName === "relative_z_index")
          continue;

        const spritePath =
          animationData.base_model_path +
          "/" +
          animConfig.default_sprite_version +
          "/" +
          animConfig.default_sprite_sheet;
        const spriteKey = `${animName}`;

        // Create sprite sheet if not already loaded
        if (!this.spriteSheets[spriteKey]) {
          const gpuSheet = new GPUSpriteSheet(
            gpuDevice,
            "assets/" + spritePath,
            animConfig.frame_width,
            animConfig.frame_height,
            8, // columns - standard 8 columns for character sprites
            8, // rows - standard 8 rows for character sprites
          );
          promises.push(
            gpuSheet
              .load()
              .then(() => {
                this.spriteSheets[spriteKey] = gpuSheet;
                const pipeline = this._shaderCache.getSpritePipeline();
                // Uniform buffer: mvp(64) + uv_rect(16) + tint(16) = 96 bytes
                const uBuf = createUniformBuffer(gpuDevice, 96);
                this._uniformBuffers[spriteKey] = uBuf;
                this._bindGroups[spriteKey] = gpuSheet.createBindGroup(
                  gpuDevice,
                  pipeline,
                  uBuf,
                );
              })
              .catch((err) => {
                // Without this, a failed fetch/decode/texture-upload for
                // this one sprite sheet silently leaves spriteSheets[key]
                // unset forever — getAnimationController() then warns
                // "not loaded" every single frame, indistinguishable from
                // "still loading", with no indication anything actually
                // failed.
                console.error(
                  `[EntityRenderer] Failed to load sprite sheet '${spriteKey}' (${spritePath}):`,
                  err,
                );
              }),
          );
        }
      }
    }

    await Promise.all(promises);
  }

  /**
   * Get or create an animation controller for an entity
   * @param {string} entityId - Unique identifier for the entity
   * @param {string} animationType - Type of animation (e.g., 'stand', 'walk')
   * @returns {AnimationController}
   */
  getAnimationController(entityId, animationType = "stand") {
    const controllerId = `${entityId}_${animationType}`;

    if (!this.animationControllers[controllerId]) {
      // Find animation config from loaded animation data
      let animConfig = null;
      for (const { data } of this.animationDataList) {
        if (data[animationType]) {
          animConfig = data[animationType];
          break;
        }
      }

      if (!animConfig) {
        console.warn(`Animation type '${animationType}' not found`);
        return null;
      }

      const spriteSheet = this.spriteSheets[animationType];
      if (!spriteSheet) {
        console.warn(`Sprite sheet for '${animationType}' not loaded`);
        return null;
      }

      // Create animations for all directions
      const animations = {};
      const directions = ["down", "up", "left", "right"];

      directions.forEach((dir) => {
        const dirConfig = animConfig[dir];
        if (dirConfig) {
          // Handle frame duration (fixed or variable)
          let frameDuration;
          if (
            animConfig.duration_type === "variable" &&
            Array.isArray(animConfig.frame_duration)
          ) {
            // For variable duration, use average for now (can be enhanced later)
            frameDuration =
              animConfig.frame_duration.reduce((a, b) => a + b, 0) /
              animConfig.frame_duration.length;
          } else {
            frameDuration = animConfig.frame_duration;
          }

          const animName = `${animationType}_${dir}`;
          animations[animName] = new Animation(
            animName,
            dirConfig.start_frame_index,
            animConfig.frame_count,
            frameDuration,
            true, // loop
          );
        }
      });

      this.animationControllers[controllerId] = new AnimationController(
        spriteSheet,
        animations,
      );
    }

    return this.animationControllers[controllerId];
  }

  /**
   * Update entity animation state based on entity data
   * @param {string} entityId - Unique identifier for the entity
   * @param {Object} entity - Entity data object
   * @param {number} deltaTime - Time elapsed since last update (milliseconds)
   */
  updateEntityAnimation(entityId, entity, deltaTime) {
    this._lastDeltaTime = deltaTime;
    // Determine animation type based on entity state
    const animationType = entity.state === "moving" ? "walk" : "stand";
    const direction = entity.facing || "down";

    // Get or create animation controller
    const controller = this.getAnimationController(entityId, animationType);
    if (!controller) return;

    // Play the appropriate direction animation (use full animation name)
    const animationName = `${animationType}_${direction}`;
    controller.play(animationName);

    // Update animation
    controller.update(deltaTime);

    // Store controller reference for drawing
    entity._animController = controller;
    entity._animType = animationType;
  }

  /**
   * Draw a single entity with its current animation.
   *
   * In the WebGPU path, passEncoder must be the active GPURenderPassEncoder
   * owned by renderer.js. Draw commands are recorded onto it; the caller is
   * responsible for beginning and ending the render pass.
   *
   * @param {Object} entity - Entity data object
   * @param {Object} camera - Camera position {x, y}
   * @param {GPURenderPassEncoder|null} [passEncoder=null] - Active render pass
   *   encoder; only used when useGPU is true.
   */
  drawEntity(entity, camera, passEncoder = null) {
    if (!this.loadingComplete) {
      if (!this.useGPU) this.drawEntityFallback(entity, camera);
      return;
    }

    // 3D path — must branch before the 2D screen-space x/y computation
    // below, since a 3D camera has no camera.x/camera.y (it has
    // camera.position/target instead).
    if (camera && camera.mode === "3d") {
      // Resolve entity.render_template (if set) to its entity-definition
      // JSON *before* deciding mesh vs. billboard — an entity whose
      // resolved definition has a `mesh` field routes to the Step 5 mesh
      // path; everything else (no render_template, still loading, or a
      // definition with no mesh) falls through to the Step 4 billboard
      // path unchanged.
      const definition = this._resolveRenderTemplate(entity);
      if (definition && definition.mesh) {
        this.drawEntityMesh(entity, camera, passEncoder, definition);
        return;
      }

      if (!entity._animController) return; // no Canvas 2D fallback in 3D mode
      this.drawEntity3D(entity, camera, passEncoder);
      return;
    }

    // Use interpolated position for smooth movement
    const x = (entity.displayX || entity.x) - camera.x;
    const y = (entity.displayY || entity.y) - camera.y;

    if (!entity._animController) {
      if (!this.useGPU) this.drawEntityFallback(entity, camera);
      return;
    }

    // Find animation config from loaded data
    let animConfig = null;
    for (const { data } of this.animationDataList) {
      if (data[entity._animType]) {
        animConfig = data[entity._animType];
        break;
      }
    }

    const direction = entity.facing || "down";
    const dirConfig = animConfig?.[direction];
    const flipX = dirConfig?.flip_x || false;

    if (this.useGPU) {
      // --- Material path (Workflow B/C) ---
      // Entities that carry a 'material' field use the 4-binding material
      // pipeline.  Loading is asynchronous; Workflow A is used as a fallback
      // on frames before the handle resolves.
      if (entity.material) {
        const matEntityId = entity.id || entity.entity_id;
        const matPath = "assets/data/" + entity.material;

        if (!this._materialHandles.has(matEntityId)) {
          // First encounter — kick off async load; draw Workflow A this frame.
          this._materialHandles.set(matEntityId, null);
          this._materialLoader
            .load(matPath)
            .then((handle) => {
              this._materialHandles.set(matEntityId, handle);
            })
            .catch((err) => {
              console.warn("[EntityRenderer] Material load failed:", err);
            });
        }

        const handle = this._materialHandles.get(matEntityId);
        if (handle) {
          // Choose pipeline variant from material flags + runtime overrides.
          const overrides = this._runtimeOverrides.get(matEntityId) || {};
          let variantKey = "base";
          if (handle.colorRampType === "cosine") {
            variantKey = "cosine";
          } else if (handle.flags.hasColorRamp) {
            variantKey = "ramp";
          } else if ("hue_shift" in overrides) {
            variantKey = "hue";
          } else if (handle.flags.hasOverlay) {
            variantKey = "overlay";
          }

          const matPipeline = this._shaderCache.getMaterialPipeline(
            variantKey,
            this._materialLoader.bindGroupLayout,
          );

          // Build per-frame uniform array (32 floats = 128 bytes).
          const spriteKey = entity._animType || "stand";
          const gpuSheet = this.spriteSheets[spriteKey];
          const frameIndex = entity._animController
            ? entity._animController.currentFrame
            : 0;
          const uvRect =
            gpuSheet && gpuSheet.loaded
              ? gpuSheet.getUVRect(frameIndex)
              : new Float32Array([0, 0, 1, 1]);

          const cW = this._canvas.width;
          const cH = this._canvas.height;
          const fw = animConfig ? animConfig.frame_width : 32;
          const fh = animConfig ? animConfig.frame_height : 32;
          const scaleX = (flipX ? -1 : 1) * (fw / cW);
          const scaleY = fh / cH;
          const tx = (2 * x) / cW - 1;
          const ty = 1 - (2 * y) / cH;

          const overlayIntensity =
            handle.overlays.length > 0 ? handle.overlays[0].intensity : 1.0;
          const intensity =
            overrides["glow_intensity"] ??
            overrides["hue_shift"] ??
            overlayIntensity;
          const rampSteps = overrides["ramp_steps"] ?? 0.0;
          const tint = overrides["tint"] || [1, 1, 1, 1];

          const cosine = handle.cosineParams ||
            overrides["cosine_params"] || {
              a: [0.5, 0.5, 0.5],
              b: [0.5, 0.5, 0.5],
              c: [1.0, 1.0, 1.0],
              d: [0.0, 0.33, 0.67],
            };

          // prettier-ignore
          const matUniforms = new Float32Array([
            scaleX, 0,      0, 0,  // col 0
            0,      scaleY, 0, 0,  // col 1
            0,      0,      1, 0,  // col 2
            tx,     ty,     0, 1,  // col 3
            uvRect[0], uvRect[1], uvRect[2], uvRect[3],  // uv_rect
            0, 0, 1, 1,            // uv_overlay (identity)
            tint[0], tint[1], tint[2], tint[3],          // tint
            intensity,             // intensity
            (performance.now() / 1000.0),                // time
            rampSteps,             // ramp_steps
            0,                     // _pad
            // cosine palette (floats 32-47, zero for non-cosine variants)
            cosine.a[0], cosine.a[1], cosine.a[2], 0,   // pal_a
            cosine.b[0], cosine.b[1], cosine.b[2], 0,   // pal_b
            cosine.c[0], cosine.c[1], cosine.c[2], 0,   // pal_c
            cosine.d[0], cosine.d[1], cosine.d[2], 0,   // pal_d
          ]);

          writeUniformBuffer(gpuDevice, handle.uniformBuffer, matUniforms);

          passEncoder.setPipeline(matPipeline);
          passEncoder.setBindGroup(0, handle.bindGroup);
          passEncoder.setVertexBuffer(0, this._quadVertexBuffer);
          passEncoder.draw(6);
          // Particle emitter (Phase 2.5).
          this._renderParticleSystem(entity, camera, passEncoder);
          return; // do not fall through to Workflow A
        }
        // Handle still loading — fall through to Workflow A this frame.
      }

      // --- Workflow A (legacy sprite path) ---
      const spriteKey = entity._animType;
      const gpuSheet = this.spriteSheets[spriteKey];
      if (!gpuSheet || !gpuSheet.loaded) return;

      const frameIndex = entity._animController.currentFrame;
      const uvRect = gpuSheet.getUVRect(frameIndex);

      // 2D orthographic MVP — maps the unit quad to screen space.
      const cW = this._canvas.width;
      const cH = this._canvas.height;
      const scaleX = (flipX ? -1 : 1) * (animConfig.frame_width / cW);
      const scaleY = animConfig.frame_height / cH;
      const tx = (2 * x) / cW - 1;
      const ty = 1 - (2 * y) / cH;

      // Column-major mat4x4 (WGSL layout):
      // col0=[scaleX,0,0,0] col1=[0,scaleY,0,0] col2=[0,0,1,0] col3=[tx,ty,0,1]
      // prettier-ignore
      const uniforms = new Float32Array([
                scaleX,  0,  0,  0,   // col 0
                0,  scaleY,  0,  0,   // col 1
                0,       0,  1,  0,   // col 2
                tx,     ty,  0,  1,   // col 3
                uvRect[0], uvRect[1], uvRect[2], uvRect[3],  // uv_rect
                1, 1, 1, 1,           // tint
            ]);

      writeUniformBuffer(gpuDevice, this._uniformBuffers[spriteKey], uniforms);

      const pipeline = this._shaderCache.getSpritePipeline();
      passEncoder.setPipeline(pipeline);
      passEncoder.setBindGroup(0, this._bindGroups[spriteKey]);
      passEncoder.setVertexBuffer(0, this._quadVertexBuffer);
      passEncoder.draw(6);
      // Particle emitter (Phase 2.5).
      this._renderParticleSystem(entity, camera, passEncoder);
    }
  }

  /**
   * Draw a camera-facing billboard sprite in 3D space (Step 4 of the
   * 3D coordinate mapping work). The sprite quad's plane is spanned by
   * the camera's world-space right/up vectors rather than a fixed 2D
   * orientation, so it always faces the camera as it orbits — the
   * "2.5D" technique described in docs/graphics/COORDINATE_MAPPING.md.
   *
   * Reuses the same SPRITE_WGSL shader, UV-rect logic, and per-frame
   * animation state as the 2D Workflow A path — only the model matrix
   * differs, and depth testing is enabled (getSpritePipeline3D) so
   * multiple billboards occlude each other correctly by world depth.
   *
   * @param {Object} entity - Must have `_animController`/`_animType` set
   *   by updateEntityAnimation, plus `x`/`y`/`z` (world position),
   *   `size` ([width, height] in world units), and optionally `pivot`
   *   ([fx, fy], default [0.5, 0.5] = centered).
   * @param {Object} camera - 3D camera ({mode: '3d', position, target,
   *   up, fov, near, far}).
   * @param {GPURenderPassEncoder|null} passEncoder
   */
  drawEntity3D(entity, camera, passEncoder) {
    if (!this.useGPU || !passEncoder) return;

    const spriteKey = entity._animType;
    const gpuSheet = this.spriteSheets[spriteKey];
    if (!gpuSheet || !gpuSheet.loaded) return;

    const frameIndex = entity._animController.currentFrame;
    const uvRect = gpuSheet.getUVRect(frameIndex);

    // Lazily create this spriteKey's 3D uniform buffer + bind group,
    // separate from the 2D path's (see the constructor comment on
    // _uniformBuffers3D/_bindGroups3D for why they can't be shared).
    if (!this._bindGroups3D[spriteKey]) {
      const pipeline3D = this._shaderCache.getSpritePipeline3D();
      const uBuf = createUniformBuffer(gpuDevice, 96);
      this._uniformBuffers3D[spriteKey] = uBuf;
      this._bindGroups3D[spriteKey] = gpuSheet.createBindGroup(
        gpuDevice,
        pipeline3D,
        uBuf,
      );
    }

    const aspect = this._canvas.width / this._canvas.height;
    const viewProjection = getViewProjectionMatrix(camera, aspect);
    if (!viewProjection) return; // defensive — caller already checked camera.mode

    // Camera right/up in world space, per Step 2's lookAt convention:
    // row 0 of the view matrix is the camera's world-space right axis,
    // row 1 is world-space up. Column-major storage means "row N" is a
    // strided read (index N, N+4, N+8), not a contiguous one.
    const up3d = camera.up ?? [0, 1, 0];
    const view = lookAt(camera.position, camera.target, up3d);
    const right = [view[0], view[4], view[8]];
    const up = [view[1], view[5], view[9]];

    const size = entity.size || [32, 32];
    const halfW = size[0] / 2;
    const halfH = size[1] / 2;

    // Pivot: [fx, fy] as a fraction of size, matching the existing 2D
    // convention (fy follows image/UV space — 0 = top, 1 = bottom).
    // Convert into local quad space, where the raw quad spans [-1, 1]
    // with +1 = top (see gpuBuffers.js's createQuadVertexBuffer).
    const pivot = entity.pivot || [0.5, 0.5];
    const pivotLocalX = 2 * pivot[0] - 1;
    const pivotLocalY = 1 - 2 * pivot[1];

    const ex = entity.x ?? 0;
    const ey = entity.y ?? 0;
    const ez = entity.z ?? 0;

    // The pivot shifts the quad so the chosen anchor point — not its
    // geometric center — lands on the entity's world position.
    const offsetX = right[0] * halfW * pivotLocalX + up[0] * halfH * pivotLocalY;
    const offsetY = right[1] * halfW * pivotLocalX + up[1] * halfH * pivotLocalY;
    const offsetZ = right[2] * halfW * pivotLocalX + up[2] * halfH * pivotLocalY;

    // Model matrix: local quad X axis -> right * halfW, local Y -> up * halfH,
    // local Z is always 0 for this quad so the third column's contents are
    // irrelevant and left zeroed; translation places the pivot-adjusted
    // quad at the entity's world position.
    // prettier-ignore
    const model = new Float32Array([
      right[0] * halfW, right[1] * halfW, right[2] * halfW, 0,
      up[0] * halfH,    up[1] * halfH,    up[2] * halfH,    0,
      0,                0,                0,                0,
      ex - offsetX,     ey - offsetY,     ez - offsetZ,     1,
    ]);

    const mvp = multiply(viewProjection, model);

    // prettier-ignore
    const uniforms = new Float32Array([
      ...mvp,                                       // mvp (64 B)
      uvRect[0], uvRect[1], uvRect[2], uvRect[3],    // uv_rect
      1, 1, 1, 1,                                    // tint
    ]);

    writeUniformBuffer(gpuDevice, this._uniformBuffers3D[spriteKey], uniforms);

    const pipeline3D = this._shaderCache.getSpritePipeline3D();
    passEncoder.setPipeline(pipeline3D);
    passEncoder.setBindGroup(0, this._bindGroups3D[spriteKey]);
    passEncoder.setVertexBuffer(0, this._quadVertexBuffer);
    passEncoder.draw(6);
  }

  /**
   * Resolve entity.render_template (if set) to its entity-definition
   * JSON, caching the result. This is the link Step 5 adds between a
   * networked entity (which only knows *which* template to use) and the
   * frontend/assets/data/entity/entity-<uuid>.json file that actually
   * describes what it looks like (mesh/parts/material_id — never
   * placement, see the backend Entity.transform3d comment).
   *
   * @param {Object} entity
   * @returns {Object|null} The definition once loaded; `null` if
   *   `render_template` is unset, still loading, or permanently failed
   *   to resolve/fetch — callers must treat `null` as "not ready, fall
   *   back to existing behaviour," not as an error to surface per-frame.
   */
  _resolveRenderTemplate(entity) {
    const key = entity.render_template;
    if (!key) return null;

    if (this._renderTemplates.has(key)) {
      return this._renderTemplates.get(key);
    }

    // Mark as "attempted" immediately, before any async work — otherwise
    // every frame before the fetch resolves (or fails) would see no
    // cache entry and kick off another duplicate fetch for the same key,
    // the exact race renderer.js's getEntityRenderer already had to fix.
    this._renderTemplates.set(key, null);

    let path;
    try {
      path = assetLoader.resolve(key);
    } catch (err) {
      console.error(
        `[EntityRenderer] Cannot resolve render_template '${key}':`,
        err,
      );
      return null; // stays null in the cache — permanent, no retry
    }

    fetch(path)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => {
        this._renderTemplates.set(key, data);
      })
      .catch((err) => {
        console.error(
          `[EntityRenderer] Failed to load entity definition '${key}' (${path}):`,
          err,
        );
        // Leave cached as null — falls back to the billboard path forever
        // rather than retrying a genuinely broken/missing asset every frame.
      });

    return null; // not ready this frame
  }

  /**
   * Draw a static textured 3D mesh (Step 5). Position comes from the
   * entity's own `x`/`y`/`z` (per-instance, already networked via
   * PositionComponent); rotation/scale come from `entity.transform3d`.
   * Neither ever comes from `definition` — the entity-definition file
   * supplies only appearance (`mesh`/`material_id`), never placement,
   * so multiple entities can share one render_template and still be
   * independently positioned and rotated.
   *
   * Reuses the entity's existing material bind group exactly like the
   * 2D material path (drawEntity's Workflow B/C branch) — a mesh just
   * needs UVs that land somewhere sensible on the same kind of 2D
   * texture a sprite entity already uses; no separate 3D material system.
   *
   * @param {Object} entity
   * @param {Object} camera - 3D camera.
   * @param {GPURenderPassEncoder|null} passEncoder
   * @param {Object} definition - Resolved entity-definition JSON (has `.mesh`).
   */
  drawEntityMesh(entity, camera, passEncoder, definition) {
    if (!this.useGPU || !passEncoder) return;

    const meshKey = definition.mesh;

    if (!this._meshes.has(meshKey)) {
      this._meshes.set(meshKey, null); // in-flight marker, see the constructor comment
      let meshPath;
      try {
        meshPath = assetLoader.resolve(meshKey);
      } catch (err) {
        console.error(`[EntityRenderer] Cannot resolve mesh '${meshKey}':`, err);
        return;
      }
      const mesh = new Mesh(gpuDevice);
      mesh
        .load(meshPath)
        .then(() => {
          this._meshes.set(meshKey, mesh);
        })
        .catch((err) => {
          console.error(
            `[EntityRenderer] Failed to load mesh '${meshKey}' (${meshPath}):`,
            err,
          );
        });
      return; // nothing to draw yet this frame
    }

    const mesh = this._meshes.get(meshKey);
    if (!mesh) return; // still loading

    // Material — same lazy-load-and-cache pattern as the 2D material
    // path, keyed by entity id so this entity's handle is reused across
    // frames. Sourced from the *definition's* material_id, not
    // entity.material (that field belongs to the legacy 2D-only path).
    const matEntityId = entity.id || entity.entity_id;
    if (definition.material_id) {
      if (!this._materialHandles.has(matEntityId)) {
        this._materialHandles.set(matEntityId, null);
        const matPath = "assets/data/" + definition.material_id;
        this._materialLoader
          .load(matPath)
          .then((handle) => {
            this._materialHandles.set(matEntityId, handle);
          })
          .catch((err) => {
            console.warn("[EntityRenderer] Mesh material load failed:", err);
          });
      }
    }

    const handle = this._materialHandles.get(matEntityId);
    if (!handle) return; // no material loaded yet — Step 5 requires one

    const aspect = this._canvas.width / this._canvas.height;
    const viewProjection = getViewProjectionMatrix(camera, aspect);
    if (!viewProjection) return; // defensive — caller already checked camera.mode

    const transform3d = entity.transform3d || {};
    const rotation = transform3d.rotation || [0, 0, 0];
    const scale = transform3d.scale || [1, 1, 1];
    const position = [entity.x ?? 0, entity.y ?? 0, entity.z ?? 0];

    const model = compose(position, rotation, scale);
    const mvp = multiply(viewProjection, model);

    // Combiner variant (base/ramp/hue/cosine) selection from material
    // flags isn't wired up for mesh entities yet — always 'base' for now,
    // same as Step 5 left it. Not a Step 8 task: Step 8 only adds the
    // stylization fields below, independent of which combiner runs.
    const variantKey = "base";
    // Step 8: affine UV is a compile-time pipeline choice (see
    // shaderCache.js's buildMeshWgslCommon), so it's part of which
    // pipeline gets requested, not a uniform written below.
    const pipeline = this._shaderCache.getMeshPipeline(
      variantKey,
      this._materialLoader.bindGroupLayout,
      handle.affineUv,
    );

    // Step 8 stylization inputs, each defaulting to a true no-op so a
    // material/camera that sets none of them renders identically to the
    // end of Step 5. vertexColor/colorLevels come from the material
    // (materialLoader.js); fog/ambient come from the camera/scene object
    // (renderer.js's getViewProjectionMatrix jsdoc documents these same
    // fields) since that's the one runtime object already read every frame.
    const vertexColorFlag = handle.vertexColor ? 1 : 0;
    const colorLevels = handle.colorLevels || 0;
    const fogColor = camera.fogColor || [0, 0, 0];
    const fogNear = camera.fogNear || 0;
    const fogFar = camera.fogFar || 0; // <= 0 disables fog entirely
    const ambientColor = camera.ambientColor || [1, 1, 1]; // [1,1,1] = no-op
    // Must match getViewProjectionMatrix's (renderer.js) exact defaults —
    // the fragment shader linearizes NDC depth back to a world-unit
    // distance using these same near/far values, so a mismatch here
    // would silently desync the fog math from the projection actually
    // used to draw this frame.
    const projNear = camera.near ?? 0.1;
    const projFar = camera.far ?? 1000;

    // prettier-ignore
    const matUniforms = new Float32Array([
      ...mvp,               // mvp (64 B)
      0, 0, 1, 1,            // uv_rect — identity: mesh UVs are already
                             // final texture-space coords, not an atlas
                             // sub-rect (see buildMeshWgslCommon's comment)
      0, 0, 1, 1,            // uv_overlay — unused by the mesh path
      1, 1, 1, 1,            // tint
      0,                     // intensity
      (performance.now() / 1000.0), // time
      0,                     // ramp_steps
      0,                     // _pad
      0.5, 0.5, 0.5, 0,      // pal_a (unused unless a 'cosine' material is used)
      0.5, 0.5, 0.5, 0,      // pal_b
      1.0, 1.0, 1.0, 0,      // pal_c
      0.0, 0.33, 0.67, 0,    // pal_d
      // --- Step 8 stylization fields (mesh pipeline only, 64 B) ---
      vertexColorFlag, colorLevels, projNear, projFar, // mesh_params
      fogNear, fogFar, 0, 0,                     // fog_range
      fogColor[0], fogColor[1], fogColor[2], 0,  // fog_color
      ambientColor[0], ambientColor[1], ambientColor[2], 0, // ambient_color
    ]);

    writeUniformBuffer(gpuDevice, handle.uniformBuffer, matUniforms);

    passEncoder.setPipeline(pipeline);
    passEncoder.setBindGroup(0, handle.bindGroup);
    passEncoder.setVertexBuffer(0, mesh.vertexBuffer);
    passEncoder.setIndexBuffer(mesh.indexBuffer, mesh.indexFormat);
    passEncoder.drawIndexed(mesh.indexCount);
  }

  /**
   * Store a named runtime value for an entity's material uniform.
   * Changes are picked up on the next drawEntity call.
   *
   * Supported keys and their effect:
   *   'glow_intensity' — maps to u.intensity (overlay / base variants)
   *   'hue_shift'      — maps to u.intensity and selects 'hue' variant
   *   'tint'           — maps to u.tint; value must be [r, g, b, a]
   *   'ramp_steps'     — maps to u.ramp_steps; ≥2 enables cel-shading
   *   'cosine_params'  — overrides cosine palette; value must be
   *                      {a,b,c,d} each a 3-element [r,g,b] array
   *
   * @param {string} entityId
   * @param {string} key
   * @param {number|number[]|Object} value
   */
  setEntityRuntime(entityId, key, value) {
    const overrides = this._runtimeOverrides.get(entityId) || {};
    overrides[key] = value;
    this._runtimeOverrides.set(entityId, overrides);
  }

  // ------------------------------------------------------------------
  // Lighting helpers (Phase 2.4)
  // ------------------------------------------------------------------

  /**
   * Attach a point light to a specific entity so it is included in the
   * lighting pass each frame.  The light's world position is taken from
   * the entity's interpolated position at draw time.
   *
   * @param {string} entityId
   * @param {number[]} color - [r, g, b] light colour (values 0–1).
   * @param {number} radius - Falloff radius in world pixels.
   */
  registerLight(entityId, color, radius) {
    this._registeredLight = { entityId, color, radius };
  }

  /**
   * Remove a previously registered light from this renderer instance.
   *
   * @param {string} entityId
   */
  unregisterLight(entityId) {
    if (this._registeredLight && this._registeredLight.entityId === entityId) {
      this._registeredLight = null;
    }
  }

  /**
   * Return the registered light entry with the entity's current world
   * position filled in, or null if no light is registered or the entity
   * is not in the provided entity map.
   *
   * Called by renderer.js._gatherLights() each frame.
   *
   * @param {Object} entity - The live entity object from gameState.
   * @returns {{x:number, y:number, color:number[], radius:number}|null}
   */
  getRegisteredLight(entity) {
    if (!this._registeredLight || !entity) return null;
    return {
      x: entity.displayX ?? entity.x,
      y: entity.displayY ?? entity.y,
      color: this._registeredLight.color || [1.0, 1.0, 0.9],
      radius: this._registeredLight.radius || 150,
    };
  }

  // ------------------------------------------------------------------
  // Particle helpers (Phase 2.5)
  // ------------------------------------------------------------------

  /**
   * Dispatch a compute simulation step for this entity's particle system.
   * No-op if no particle system has been created yet.  Must be called on
   * the commandEncoder BEFORE the sprite render pass begins.
   *
   * @param {GPUCommandEncoder} commandEncoder
   * @param {number} dtSeconds - Elapsed time in seconds.
   */
  simulateParticles(commandEncoder, dtSeconds) {
    if (this.useGPU && this._particleSystem) {
      this._particleSystem.simulate(commandEncoder, dtSeconds);
    }
  }

  /**
   * Emit new particles and issue the draw call for this entity's emitter.
   * Called from drawEntity when entity.emitter is set.
   *
   * @param {Object} entity
   * @param {{x:number, y:number}} camera
   * @param {GPURenderPassEncoder} passEncoder
   */
  _renderParticleSystem(entity, camera, passEncoder) {
    if (!entity.emitter || !passEncoder) return;
    if (!this._particleSystem) {
      const maxP = entity.emitter.max_particles || DEFAULT_MAX_PARTICLES;
      this._particleSystem = new ParticleSystem(
        gpuDevice,
        navigator.gpu.getPreferredCanvasFormat(),
        maxP,
      );
    }
    const dtSec = this._lastDeltaTime / 1000.0;
    this._particleSystem.emit(
      entity.displayX ?? entity.x,
      entity.displayY ?? entity.y,
      entity.emitter,
      dtSec,
    );
    this._particleSystem.render(
      passEncoder,
      camera,
      this._canvas.width,
      this._canvas.height,
    );
  }

  /**
   * Draw entity as a simple circle (fallback when sprites unavailable)
   * @param {Object} entity - Entity data object
   * @param {Object} camera - Camera position {x, y}
   */
  drawEntityFallback(entity, camera) {
    const x = (entity.displayX || entity.x) - camera.x;
    const y = (entity.displayY || entity.y) - camera.y;

    this.ctx.beginPath();
    this.ctx.arc(x, y, 16, 0, Math.PI * 2);
    this.ctx.fillStyle = entity.id?.startsWith("player_")
      ? "#4CAF50"
      : "#2196F3";
    this.ctx.fill();

    // Draw state indicator
    if (entity.state === "moving") {
      this.ctx.strokeStyle = "#FFC107";
      this.ctx.lineWidth = 2;
      this.ctx.stroke();
    }
  }

  /**
   * Draw health bar above entity
   * @param {Object} entity - Entity data object
   * @param {number} x - Screen X position
   * @param {number} y - Screen Y position
   */
  drawHealthBar(entity, x, y) {
    if (entity.hp === undefined) return;

    const barWidth = 32;
    const barHeight = 4;
    const barX = x - barWidth / 2;
    const barY = y - 32; // Position above entity

    // Background
    this.ctx.fillStyle = "#333";
    this.ctx.fillRect(barX, barY, barWidth, barHeight);

    // Health
    const healthPercent = entity.hp / entity.max_hp;
    this.ctx.fillStyle = healthPercent > 0.5 ? "#4CAF50" : "#F44336";
    this.ctx.fillRect(barX, barY, barWidth * healthPercent, barHeight);
  }

  /**
   * Draw entity ID label
   * @param {Object} entity - Entity data object
   * @param {number} x - Screen X position
   * @param {number} y - Screen Y position
   */
  drawEntityLabel(entity, x, y) {
    this.ctx.fillStyle = "#fff";
    this.ctx.font = "10px Arial";
    this.ctx.textAlign = "center";
    this.ctx.fillText(entity.id, x, y + 35);
  }

  /**
   * Release all GPU resources held by this renderer.
   * Must be called when the entity is no longer needed.
   */
  destroy() {
    if (this.useGPU) {
      for (const buf of Object.values(this._uniformBuffers)) {
        buf.destroy();
      }
      this._uniformBuffers = {};
      this._bindGroups = {};
      for (const buf of Object.values(this._uniformBuffers3D)) {
        buf.destroy();
      }
      this._uniformBuffers3D = {};
      this._bindGroups3D = {};
      for (const sheet of Object.values(this.spriteSheets)) {
        sheet.destroy?.();
      }
      this.spriteSheets = {};
      for (const mesh of this._meshes.values()) {
        mesh?.destroy();
      }
      this._meshes.clear();
      this._renderTemplates.clear();
      this._materialHandles.clear();
      this._runtimeOverrides.clear();
    }
    this.animationControllers = {};
    this.animationDataList = [];
    this.loadingComplete = false;
  }
}
