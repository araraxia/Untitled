/**
 * Canvas rendering system
 */

/** @type {HTMLCanvasElement} */
let canvas;
/** @type {HTMLCanvasElement|null} */
let overlayCanvas = null;
/** @type {CanvasRenderingContext2D} */
let ctx;
/** @type {Map<string, EntityRenderer>} */
let entityRenderers = new Map();
/** @type {GPUDevice|null} */
let gpuDevice = null;
/** @type {GPUCanvasContext|null} */
let gpuContext = null;
/** @type {boolean} */
let useGPU = false;

/**
 * Offscreen scene texture — base sprite pass renders here so the
 * lighting pass can sample it.  Null until WebGPU is initialised.
 * @type {GPUTexture|null}
 */
let sceneTexture = null;

/**
 * Lighting pass (Phase 2.4).  Null until initLightingPass() is called.
 * When set, renderer.js uses a two-pass approach:
 *   Pass 1 — sprites → sceneTexture
 *   Pass 2 — LightingPass → swap chain
 * @type {LightingPass|null}
 */
let lightingPass = null;

/**
 * Depth texture for the sprite pass (Pass 1). Created once WebGPU is
 * ready, independent of whether the lighting pass is active. Only
 * depth-tested pipelines (e.g. ShaderCache.getSpritePipeline3D — 3D
 * billboards) actually read/write it; the existing 2D sprite pipeline
 * has no depthStencil state and is unaffected by this attachment's mere
 * presence on the pass.
 * @type {GPUTexture|null}
 */
let depthTexture = null;

async function initWebGPU() {
  if (!navigator.gpu) {
    console.warn(
      "[Renderer] WebGPU not available in this browser — staying on Canvas 2D path",
    );
    return false;
  }

  const adapter = await navigator.gpu.requestAdapter();
  if (!adapter) {
    console.warn(
      "[Renderer] No WebGPU adapter found — staying on Canvas 2D path",
    );
    return false;
  }

  gpuDevice = await adapter.requestDevice();
  gpuContext = canvas.getContext("webgpu");
  if (!gpuContext) {
    console.warn(
      "[Renderer] Failed to get WebGPU context — staying on Canvas 2D path",
    );
    return false;
  }
  gpuContext.configure({
    device: gpuDevice,
    format: navigator.gpu.getPreferredCanvasFormat(),
    alphaMode: "premultiplied",
  });

  console.log("[Renderer] WebGPU initialised — device:", gpuDevice);
  useGPU = true;
  return true;
}

/**
 * Allocate (or reallocate) the offscreen scene texture.
 * Called once after WebGPU init and again on every canvas resize.
 *
 * @param {number} width
 * @param {number} height
 * @returns {GPUTexture}
 */
function createSceneTexture(width, height) {
  return gpuDevice.createTexture({
    size: [width, height],
    format: navigator.gpu.getPreferredCanvasFormat(),
    usage: GPUTextureUsage.RENDER_ATTACHMENT | GPUTextureUsage.TEXTURE_BINDING,
  });
}

/**
 * Allocate (or reallocate) the depth texture used by the sprite pass.
 * Matches the "depth24plus" format depth-tested pipelines are compiled
 * against (see shaderCache.js's DEPTH_FORMAT).
 *
 * @param {number} width
 * @param {number} height
 * @returns {GPUTexture}
 */
function createDepthTexture(width, height) {
  return gpuDevice.createTexture({
    size: [width, height],
    format: "depth24plus",
    usage: GPUTextureUsage.RENDER_ATTACHMENT,
  });
}

/**
 * Initialise the LightingPass and allocate the first scene texture.
 * Safe to call multiple times — re-creates resources if already active.
 */
function initLightingPass() {
  if (sceneTexture) sceneTexture.destroy();
  sceneTexture = createSceneTexture(canvas.width, canvas.height);
  lightingPass = new LightingPass(
    gpuDevice,
    navigator.gpu.getPreferredCanvasFormat(),
  );
  lightingPass.setSceneTexture(sceneTexture);
  console.log("[Renderer] LightingPass initialised");
}

async function initRenderer() {
  console.log("[Renderer] initRenderer called");
  canvas = document.getElementById("game-canvas");
  overlayCanvas = document.getElementById("overlay-canvas");

  // Set canvas size before acquiring any context
  resizeCanvas();
  // Not `window.addEventListener("resize", resizeCanvas)` directly: the
  // browser invokes resize listeners with a UIEvent as the first
  // argument, which would silently override resizeCanvas's `width =
  // window.innerWidth` default parameter with the Event object itself —
  // exactly what produced "Failed to read the 'size' property ... Value
  // is not of type 'unsigned long'" from createTexture on an actual
  // window resize. Call with no arguments so the defaults are used.
  window.addEventListener("resize", () => resizeCanvas());

  // Try WebGPU first — getContext('webgpu') must precede getContext('2d')
  // on the same element; a canvas is locked to the first context type acquired.
  const gpuReady = await initWebGPU();

  if (gpuReady) {
    // WebGPU owns game-canvas; use the transparent overlay for 2D HUD/grid.
    ctx = overlayCanvas.getContext("2d");
    // Initialise the lighting pass (Phase 2.4).
    initLightingPass();
    // Depth texture for the sprite pass (3D billboards/meshes).
    depthTexture = createDepthTexture(canvas.width, canvas.height);
  } else {
    // No WebGPU — fall back to Canvas 2D on the main canvas.
    ctx = canvas.getContext("2d");
  }

  console.log("Renderer initialized");
}

/**
 * Get or create an EntityRenderer for a specific entity
 * @param {string} entityId - The entity ID
 * @param {Array<string>} animationDataPaths - List of animation data paths from entity
 * @returns {Promise<EntityRenderer>}
 */
async function getEntityRenderer(entityId, animationDataPaths) {
  if (!entityRenderers.has(entityId)) {
    const renderer = new EntityRenderer(
      ctx,
      entityId,
      animationDataPaths,
      useGPU,
    );
    // Register immediately, before awaiting the load — renderEntities()
    // calls getEntityRenderer() every frame, and loadAllAnimationData()
    // can easily take several frames (fetch + image decode + texture
    // upload). Without registering first, every one of those in-between
    // frames would see entityRenderers.has(entityId) === false and kick
    // off another full construct-and-load for the same entity, endlessly
    // duplicating the fetch/GPU work. drawEntity()'s own loadingComplete
    // guard already handles "not ready yet" safely, so it's fine for
    // other code to see this entry before its data has finished loading.
    entityRenderers.set(entityId, renderer);
    await renderer.loadAllAnimationData();
  }

  return entityRenderers.get(entityId);
}

/**
 * Render all entities in the game state
 * @param {Object} gameState - Current game state
 * @param {number} deltaTime - Time elapsed since last frame (milliseconds)
 * @param {GPURenderPassEncoder|null} [passEncoder=null] - Active WebGPU render
 *   pass encoder; threaded through to EntityRenderer.drawEntity when useGPU
 *   is true.
 */
async function renderEntities(gameState, deltaTime, passEncoder = null) {
  // Destroy renderers for entities no longer in game state
  for (const [entityId, renderer] of entityRenderers) {
    if (!gameState.entities[entityId]) {
      renderer.destroy();
      entityRenderers.delete(entityId);
    }
  }

  // Update and draw all entity animations
  for (const [entityId, entity] of Object.entries(gameState.entities)) {
    // Get animation data paths from entity (fallback to default if not provided)
    const animationDataPaths = entity.animation_data_paths || [
      "assets/data/human_animations.json",
    ];

    // Get or create renderer for this entity
    const renderer = await getEntityRenderer(entityId, animationDataPaths);

    // Update animation
    renderer.updateEntityAnimation(entityId, entity, deltaTime);

    // Draw entity
    renderer.drawEntity(entity, gameState.camera, passEncoder);
  }
}

function resizeCanvas(width = window.innerWidth, height = window.innerHeight) {
  console.log("[Renderer] resizeCanvas called - size:", width, "x", height);
  canvas.width = width;
  canvas.height = height;
  if (overlayCanvas) {
    overlayCanvas.width = width;
    overlayCanvas.height = height;
  }
  // Reallocate the offscreen scene texture at the new dimensions.
  if (useGPU && lightingPass) {
    if (sceneTexture) sceneTexture.destroy();
    sceneTexture = createSceneTexture(width, height);
    lightingPass.setSceneTexture(sceneTexture);
  }
  // Reallocate the depth texture at the new dimensions.
  if (useGPU && depthTexture) {
    depthTexture.destroy();
    depthTexture = createDepthTexture(width, height);
  }
}

/**
 * Compute the view-projection matrix for a 3D camera.
 *
 * `camera` is the same object passed through gameState.camera — it may
 * carry either 2D fields ({x, y, zoom}) or 3D fields ({mode: '3d',
 * position, target, up, fov, near, far}). This function only ever
 * returns non-null for `camera.mode === '3d'`; the existing 2D path in
 * EntityRenderer.drawEntity builds its own inline orthographic MVP and
 * must not be rerouted through here.
 *
 * `camera` may also carry optional Step 8 stylization fields, read
 * directly by EntityRenderer.drawEntityMesh (not by this function) since
 * they feed the mesh material uniform buffer, not the view-projection
 * matrix. Listed here because `camera` is the one runtime scene object
 * the renderer already reads every frame, and these fields all default
 * to a true no-op when absent:
 *   - fogColor: [r, g, b] — colour the mesh path fades toward with distance
 *   - fogNear, fogFar: number — fog is fully disabled when fogFar <= 0
 *     (the default when omitted); no visual change vs. pre-Step-8 output
 *   - ambientColor: [r, g, b] — multiplies final mesh colour; default/
 *     omitted is [1, 1, 1], a no-op tint
 *
 * @param {Object} camera
 * @param {number} aspect - Viewport width / height.
 * @returns {Float32Array|null} View-projection matrix, or null in 2D mode.
 */
function getViewProjectionMatrix(camera, aspect) {
  if (!camera || camera.mode !== "3d") return null;

  const fov = camera.fov ?? Math.PI / 4;
  const near = camera.near ?? 0.1;
  const far = camera.far ?? 1000;
  const up = camera.up ?? [0, 1, 0];

  const projection = perspective(fov, aspect, near, far);
  const view = lookAt(camera.position, camera.target, up);
  return multiply(projection, view);
}

async function render(gameState, deltaTime) {
  if (useGPU) {
    // --- WebGPU path ---
    const commandEncoder = gpuDevice.createCommandEncoder();
    const swapChainView = gpuContext.getCurrentTexture().createView();

    // Compute pass: simulate all active particle systems (Phase 2.5).
    // Must run before the render pass so the GPU sees updated positions.
    for (const [, er] of entityRenderers) {
      er.simulateParticles(commandEncoder, deltaTime / 1000.0);
    }

    // Pass 1 — render sprites into the scene texture (when lighting is
    // active) or directly to the swap chain (when lighting is disabled).
    const pass1View = lightingPass ? sceneTexture.createView() : swapChainView;

    const passEncoder = commandEncoder.beginRenderPass({
      colorAttachments: [
        {
          view: pass1View,
          clearValue: { r: 42 / 255, g: 42 / 255, b: 42 / 255, a: 1 },
          loadOp: "clear",
          storeOp: "store",
        },
      ],
      // Present even though the existing 2D sprite pipeline doesn't declare
      // depthStencil state (so it neither reads nor writes it, unaffected).
      // Only depth-tested pipelines — e.g. getSpritePipeline3D() for 3D
      // billboards — actually use this attachment.
      depthStencilAttachment: depthTexture
        ? {
            view: depthTexture.createView(),
            depthClearValue: 1.0,
            depthLoadOp: "clear",
            depthStoreOp: "store",
          }
        : undefined,
    });

    await renderEntities(gameState, deltaTime, passEncoder);

    passEncoder.end();

    // Pass 2 — lighting: accumulate point lights from game state and
    // runtime-registered sources, then composite onto the swap chain.
    if (lightingPass) {
      const lights = _gatherLights(gameState);
      lightingPass.updateLights(
        lights,
        gameState.camera,
        canvas.width,
        canvas.height,
      );
      lightingPass.render(commandEncoder, swapChainView);
    }

    gpuDevice.queue.submit([commandEncoder.finish()]);

    // Canvas 2D overlay: debug info still uses ctx
    drawDebugInfo(gameState);
  } else {
    // --- Canvas 2D path ---
    // Clear canvas
    ctx.fillStyle = "#2a2a2a";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Draw grid
    drawGrid(gameState.camera);

    // Draw all entities
    await renderEntities(gameState, deltaTime);

    // Draw debug info
    drawDebugInfo(gameState);
  }
}

/**
 * Collect the active light list for the current frame from two sources:
 *
 *  1. Entities in gameState whose data contains a `light` component
 *     `{ color: [r,g,b], radius: number }` (backend-driven).
 *  2. Runtime lights registered on each EntityRenderer via
 *     `registerLight()` (frontend-driven overrides).
 *
 * @param {Object} gameState
 * @returns {Array<{x:number, y:number, color:number[], radius:number}>}
 */
function _gatherLights(gameState) {
  const lights = [];

  // Backend-driven lights: entities with a `light` component.
  for (const entity of Object.values(gameState.entities || {})) {
    if (entity.light) {
      lights.push({
        x: entity.displayX ?? entity.x,
        y: entity.displayY ?? entity.y,
        color: entity.light.color || [1.0, 1.0, 0.9],
        radius: entity.light.radius || 150,
      });
    }
  }

  // Frontend-registered lights: attached via EntityRenderer.registerLight().
  for (const [entityId, er] of entityRenderers) {
    const entity = (gameState.entities || {})[entityId];
    if (!entity) continue;
    const regLight = er.getRegisteredLight(entity);
    if (regLight) lights.push(regLight);
  }

  return lights;
}

function drawGrid(camera) {
  const gridSize = 32;
  ctx.strokeStyle = "rgba(255, 255, 255, 0.1)";
  ctx.lineWidth = 1;

  // Vertical lines
  const startX = Math.floor(camera.x / gridSize) * gridSize;
  for (let x = startX; x < camera.x + canvas.width; x += gridSize) {
    const screenX = x - camera.x;
    ctx.beginPath();
    ctx.moveTo(screenX, 0);
    ctx.lineTo(screenX, canvas.height);
    ctx.stroke();
  }

  // Horizontal lines
  const startY = Math.floor(camera.y / gridSize) * gridSize;
  for (let y = startY; y < camera.y + canvas.height; y += gridSize) {
    const screenY = y - camera.y;
    ctx.beginPath();
    ctx.moveTo(0, screenY);
    ctx.lineTo(canvas.width, screenY);
    ctx.stroke();
  }
}

// Legacy function - kept for backwards compatibility but no longer used
function drawEntity(entity, camera) {
  console.log("[Renderer] drawEntity called (legacy) - entity:", entity.id);
  // This function is now handled by EntityRenderer
  // Kept here for reference or fallback purposes
  console.warn("Legacy drawEntity called - should use EntityRenderer instead");
}

function drawDebugInfo(gameState) {
  ctx.fillStyle = "#fff";
  ctx.font = "12px monospace";
  ctx.textAlign = "left";

  const cam = gameState.camera;
  const cameraLine =
    cam && cam.mode === "3d"
      ? `Camera (3D): ${cam.position.map((v) => v.toFixed(1)).join(", ")}`
      : `Camera: ${Math.round(cam.x)}, ${Math.round(cam.y)}`;

  const info = [
    `Entities: ${Object.keys(gameState.entities).length}`,
    cameraLine,
    `Player: ${gameState.player ? `${Math.round(gameState.player.x)}, ${Math.round(gameState.player.y)}` : "None"}`,
  ];

  info.forEach((line, index) => {
    ctx.fillText(line, 10, canvas.height - 50 + index * 15);
  });

  // Draw pause indicator
  if (gameState.paused) {
    ctx.save();
    ctx.fillStyle = "rgba(0, 0, 0, 0.7)";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.fillStyle = "#FFD700";
    ctx.font = "bold 48px monospace";
    ctx.textAlign = "center";
    ctx.fillText("PAUSED", canvas.width / 2, canvas.height / 2);

    ctx.font = "16px monospace";
    ctx.fillStyle = "#fff";
    ctx.fillText(
      "Press SPACE or P to resume",
      canvas.width / 2,
      canvas.height / 2 + 40,
    );
    ctx.fillText(
      "Check console for logs",
      canvas.width / 2,
      canvas.height / 2 + 65,
    );
    ctx.restore();
  }
}
