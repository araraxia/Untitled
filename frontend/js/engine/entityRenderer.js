/**
 * EntityRenderer - Handles rendering of game entities with sprite animations
 * Manages sprite sheets, animations, and visual effects for all entity types
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
    console.log(
      "[EntityRenderer] Constructor called - entityId:",
      entityId,
      "paths:",
      animationDataPaths,
      "useGPU:",
      useGPU,
    );
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
    console.log(
      "[EntityRenderer] loadAllAnimationData called - paths:",
      this.animationDataPaths,
    );
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

      console.log(
        "Animation data loaded and sorted by Z-index:",
        this.animationDataList.map((d) => ({ path: d.path, z: d.zIndex })),
      );

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
    console.log("[EntityRenderer] preloadAllSpriteAnimations called");
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
            gpuSheet.load().then(() => {
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
            }),
          );
        }
      }
    }

    await Promise.all(promises);
    console.log("All sprite sheets loaded");
  }

  /**
   * Get or create an animation controller for an entity
   * @param {string} entityId - Unique identifier for the entity
   * @param {string} animationType - Type of animation (e.g., 'stand', 'walk')
   * @returns {AnimationController}
   */
  getAnimationController(entityId, animationType = "stand") {
    console.log(
      "[EntityRenderer] getAnimationController called - entityId:",
      entityId,
      "animationType:",
      animationType,
    );
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
    console.log(
      "[EntityRenderer] updateEntityAnimation called - entityId:",
      entityId,
      "state:",
      entity.state,
      "deltaTime:",
      deltaTime,
    );
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
    console.log(
      "[EntityRenderer] drawEntity called - entityId:",
      entity.id,
      "loadingComplete:",
      this.loadingComplete,
    );
    if (!this.loadingComplete) {
      if (!this.useGPU) this.drawEntityFallback(entity, camera);
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
    console.log(
      "[EntityRenderer] drawEntityFallback called - entityId:",
      entity.id,
    );
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
    console.log(
      "[EntityRenderer] drawHealthBar called - entityId:",
      entity.id,
      "hp:",
      entity.hp,
      "max_hp:",
      entity.max_hp,
    );
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
    console.log(
      "[EntityRenderer] drawEntityLabel called - entityId:",
      entity.id,
    );
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
      for (const sheet of Object.values(this.spriteSheets)) {
        sheet.destroy?.();
      }
      this.spriteSheets = {};
      this._materialHandles.clear();
      this._runtimeOverrides.clear();
    }
    this.animationControllers = {};
    this.animationDataList = [];
    this.loadingComplete = false;
  }
}
