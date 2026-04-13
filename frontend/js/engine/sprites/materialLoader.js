/**
 * MaterialLoader — builds GPUBindGroup objects from material JSON files.
 *
 * Bind group layout (slots 0–3, shared structurally with material
 * pipelines compiled by ShaderCache):
 *   binding 0 — GPUBuffer (uniform)       per-draw uniforms
 *   binding 1 — texture_2d<f32>           albedo sprite atlas
 *   binding 2 — texture_2d<f32>           param map OR 256×1 color ramp
 *                                         (fallback: 1×1 black)
 *                                         slot is mutually exclusive:
 *                                           overlay/base → param map
 *                                           ramp variant → color ramp LUT
 *   binding 3 — GPUSampler                shared sampler
 *
 * Uniform buffer layout (MATERIAL_UNIFORM_BYTES = 192):
 *   mvp(64) + uv_rect(16) + uv_overlay(16) + tint(16)
 *   + intensity(4) + time(4) + ramp_steps(4) + _pad(4)
 *   + pal_a(16) + pal_b(16) + pal_c(16) + pal_d(16)
 */

/** Logical size of the material uniform struct, in bytes. */
const MATERIAL_UNIFORM_BYTES = 192;

/**
 * Aligned to WebGPU minUniformBufferOffsetAlignment (256 bytes).
 * @type {number}
 */
const MATERIAL_UNIFORM_ALIGNED = Math.ceil(MATERIAL_UNIFORM_BYTES / 256) * 256;

/**
 * @typedef {Object} MaterialHandle
 * @property {string} id
 * @property {GPUBindGroup} bindGroup
 * @property {GPUBuffer} uniformBuffer
 * @property {{
 *   hasParamMap: boolean,
 *   hasOverlay: boolean,
 *   hasColorRamp: boolean,
 * }} flags
 * @property {Array<{
 *   atlas: string|null,
 *   animationId: string|null,
 *   blendMode: string,
 *   intensity: number,
 * }>} overlays
 * @property {'texture'|'cosine'|null} colorRampType
 *   How the color ramp is expressed: 'texture' = 256×1 LUT uploaded to
 *   binding 2; 'cosine' = procedural palette params in MatUniforms;
 *   null = no color ramp.
 * @property {{a:number[],b:number[],c:number[],d:number[]}|null} cosineParams
 *   Cosine palette parameters a/b/c/d as 3-element arrays [r,g,b].  Only
 *   set when colorRampType === 'cosine', otherwise null.
 */

class MaterialLoader {
  /**
   * @param {GPUDevice} device
   * @param {AssetLoader} [loader] - Optional asset registry for key-based
   *   path resolution.  When provided, material JSON fields that look like
   *   asset keys (no '/' in the value) are resolved through the registry.
   *   Falls back to prepending 'assets/' when a key is not registered.
   *   If omitted, the global `assetLoader` instance is used when available.
   */
  constructor(device, loader) {
    this._device = device;

    // Use the injected loader, or fall back to the global instance.
    // eslint-disable-next-line no-undef
    this._assetLoader =
      loader || (typeof assetLoader !== "undefined" ? assetLoader : null);

    /** @type {Map<string, MaterialHandle>} */
    this._handles = new Map();

    this._bindGroupLayout = this._createBindGroupLayout();
    this._sampler = this._createSampler();
    this._fallbackParamTexture = this._create1x1BlackTexture();
  }

  /**
   * Explicit GPUBindGroupLayout used for all material bind groups.
   * Pass to ShaderCache when creating material pipelines to guarantee
   * object-level layout compatibility.
   *
   * @returns {GPUBindGroupLayout}
   */
  get bindGroupLayout() {
    return this._bindGroupLayout;
  }

  // ------------------------------------------------------------------
  // Public API
  // ------------------------------------------------------------------

  /**
   * Fetch and parse a material JSON file, upload textures, and build
   * a GPUBindGroup. Returns the cached handle on subsequent calls for
   * the same material id.
   *
   * @param {string} materialJsonPath - Server-root-relative path, e.g.
   *   'assets/data/material/material-example-lantern.json'.
   * @returns {Promise<MaterialHandle>}
   */
  async load(materialJsonPath) {
    const response = await fetch(materialJsonPath);
    if (!response.ok) {
      throw new Error(
        `[MaterialLoader] Fetch failed for ${materialJsonPath}` +
          ` (${response.status})`,
      );
    }
    const json = await response.json();

    if (this._handles.has(json.id)) {
      return this._handles.get(json.id);
    }

    // Resolve atlas path — material JSON may use 'atlas' or 'base_atlas'.
    const atlasPath = this._resolvePath(json.atlas || json.base_atlas);
    const albedoTex = await this._loadTexture(atlasPath);

    const hasParamMap = Boolean(json.param_map);
    const paramTex = hasParamMap
      ? await this._loadTexture(this._resolvePath(json.param_map))
      : this._fallbackParamTexture;

    // --- color_ramp (Phase 2.3) ---
    // Binding 2 is dual-purpose: param map for overlay/base variants,
    // or 256×1 colour ramp LUT for the ramp variant.  They are mutually
    // exclusive per material — option 5 (both) is deferred.
    const hasColorRamp = Boolean(json.color_ramp);
    let colorRampType = null;
    let cosineParams = null;
    let rampTex = null;

    if (json.color_ramp) {
      colorRampType = json.color_ramp.type || "texture";
      if (colorRampType === "cosine") {
        cosineParams = {
          a: json.color_ramp.a || [0.5, 0.5, 0.5],
          b: json.color_ramp.b || [0.5, 0.5, 0.5],
          c: json.color_ramp.c || [1.0, 1.0, 1.0],
          d: json.color_ramp.d || [0.0, 0.33, 0.67],
        };
      } else if (colorRampType === "texture" && json.color_ramp.texture) {
        rampTex = await this._loadTexture(
          this._resolvePath(json.color_ramp.texture),
        );
      }
    }

    // Slot 2: colour ramp LUT when loaded, otherwise the param map
    // (or 1×1 black fallback when neither is present).
    const binding2Tex = rampTex || paramTex;

    const uniformBuffer = this._device.createBuffer({
      size: MATERIAL_UNIFORM_ALIGNED,
      usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST,
    });

    const bindGroup = this._device.createBindGroup({
      layout: this._bindGroupLayout,
      entries: [
        { binding: 0, resource: { buffer: uniformBuffer } },
        { binding: 1, resource: albedoTex.createView() },
        { binding: 2, resource: binding2Tex.createView() },
        { binding: 3, resource: this._sampler },
      ],
    });

    const hasOverlay = Array.isArray(json.overlays) && json.overlays.length > 0;

    const overlays = (json.overlays || []).map((o) => ({
      type: o.type || "animation",
      atlas: o.atlas || null,
      animationId: o.animation_id || o.animation_clip || null,
      blendMode: o.blend_mode || "additive",
      intensity: typeof o.intensity === "number" ? o.intensity : 1.0,
    }));

    /** @type {MaterialHandle} */
    const handle = {
      id: json.id,
      bindGroup,
      uniformBuffer,
      flags: { hasParamMap, hasOverlay, hasColorRamp },
      overlays,
      colorRampType,
      cosineParams,
    };

    this._handles.set(json.id, handle);
    console.log("[MaterialLoader] Loaded material:", json.id);
    return handle;
  }

  /**
   * Return a previously loaded handle by material id, or null.
   *
   * @param {string} materialId
   * @returns {MaterialHandle|null}
   */
  get(materialId) {
    return this._handles.get(materialId) || null;
  }

  // ------------------------------------------------------------------
  // Private helpers
  // ------------------------------------------------------------------

  /** Create the explicit bind group layout for all material shaders. */
  _createBindGroupLayout() {
    return this._device.createBindGroupLayout({
      entries: [
        {
          binding: 0,
          visibility: GPUShaderStage.VERTEX | GPUShaderStage.FRAGMENT,
          buffer: { type: "uniform" },
        },
        {
          binding: 1,
          visibility: GPUShaderStage.FRAGMENT,
          texture: { sampleType: "float" },
        },
        {
          binding: 2,
          visibility: GPUShaderStage.FRAGMENT,
          texture: { sampleType: "float" },
        },
        {
          binding: 3,
          visibility: GPUShaderStage.FRAGMENT,
          sampler: { type: "filtering" },
        },
      ],
    });
  }

  /** Shared sampler used across all material bind groups. */
  _createSampler() {
    return this._device.createSampler({
      minFilter: "linear",
      magFilter: "nearest",
    });
  }

  /**
   * 1×1 opaque black RGBA texture — placeholder when no param map is
   * defined, ensuring the bind group slot is always populated.
   */
  _create1x1BlackTexture() {
    const tex = this._device.createTexture({
      size: [1, 1, 1],
      format: "rgba8unorm",
      usage: GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_DST,
    });
    this._device.queue.writeTexture(
      { texture: tex },
      new Uint8Array([0, 0, 0, 255]),
      { bytesPerRow: 4 },
      [1, 1],
    );
    return tex;
  }

  /**
   * Fetch an image at *url* and upload it as a GPUTexture.
   *
   * @param {string} url
   * @returns {Promise<GPUTexture>}
   */
  async _loadTexture(url) {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`[MaterialLoader] Failed to fetch texture: ${url}`);
    }
    const blob = await response.blob();
    const bitmap = await createImageBitmap(blob);

    const tex = this._device.createTexture({
      size: [bitmap.width, bitmap.height, 1],
      format: "rgba8unorm",
      usage:
        GPUTextureUsage.TEXTURE_BINDING |
        GPUTextureUsage.COPY_DST |
        GPUTextureUsage.RENDER_ATTACHMENT,
    });
    this._device.queue.copyExternalImageToTexture(
      { source: bitmap },
      { texture: tex },
      [bitmap.width, bitmap.height],
    );
    return tex;
  }

  /**
   * Resolve a material-JSON field value to a server-rooted URL.
   *
   * Resolution order:
   *   1. Already a URL/path (contains '/') — returned unchanged.
   *   2. Looks like an asset key (no '/') and AssetLoader is available
   *      → resolved via AssetLoader.resolve().
   *   3. Fallback — prepend 'assets/'.
   *
   * @param {string} value - Asset key or raw path from material JSON.
   * @returns {string}
   */
  _resolvePath(value) {
    if (!value) return "";

    // Already a full path or URL.
    if (value.includes("/") || value.startsWith("http")) return value;

    // Try AssetLoader key resolution.
    if (this._assetLoader) {
      if (this._assetLoader.has(value)) {
        return this._assetLoader.resolve(value);
      }
      console.warn(
        `[MaterialLoader] Asset key "${value}" not found in AssetLoader;` +
          " falling back to assets/ prefix.",
      );
    }

    return "assets/" + value;
  }
}
