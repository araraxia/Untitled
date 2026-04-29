/**
 * AssetLoader — maps short asset keys to server-relative file paths.
 *
 * Material JSON, entity JSON, and other data files reference assets by
 * a plain string key (e.g. 'lantern_atlas') rather than a raw file path.
 * At runtime AssetLoader resolves those keys to the actual URLs that the
 * browser can fetch.
 *
 * Usage:
 *   assetLoader.register('lantern_atlas', 'assets/images/sprites/objects/lantern_atlas.png');
 *   const url = assetLoader.resolve('lantern_atlas');
 *   // → 'assets/images/sprites/objects/lantern_atlas.png'
 *
 * A single shared instance is exported as `window.assetLoader` for use
 * by MaterialLoader and other engine modules that run in the browser
 * global scope.
 */

class AssetLoader {
  constructor() {
    /** @type {Map<string, string>} */
    this._registry = new Map();
  }

  /**
   * Register an asset key with its server-relative path.
   * Re-registering the same key overwrites the previous entry.
   *
   * @param {string} key - Short identifier (e.g. 'lantern_atlas').
   * @param {string} path - Server-relative URL
   *   (e.g. 'assets/images/sprites/objects/lantern_atlas.png').
   */
  register(key, path) {
    this._registry.set(key, path);
  }

  /**
   * Register multiple assets at once from a plain object map.
   *
   * @param {Record<string, string>} map - { key: path } entries.
   */
  registerAll(map) {
    for (const [key, path] of Object.entries(map)) {
      this._registry.set(key, path);
    }
  }

  /**
   * Resolve an asset key to its registered path.
   *
   * If the value already looks like a URL (contains '/' or starts with
   * 'http') it is returned unchanged — this preserves backward
   * compatibility with old material JSON that embeds raw paths.
   *
   * @param {string} key - Registered asset key or a raw path.
   * @returns {string} Resolved server-relative path.
   * @throws {Error} If the key is not registered and does not look
   *   like a raw path.
   */
  resolve(key) {
    if (!key) throw new Error("[AssetLoader] resolve() called with empty key");

    // Already a path — pass through.
    if (key.includes("/") || key.startsWith("http")) return key;

    const path = this._registry.get(key);
    if (path === undefined) {
      throw new Error(`[AssetLoader] Unknown asset key: "${key}"`);
    }
    return path;
  }

  /**
   * Return true if \`key\` is registered.
   *
   * @param {string} key
   * @returns {boolean}
   */
  has(key) {
    return this._registry.has(key);
  }

  /**
   * Remove a single key from the registry.
   *
   * @param {string} key
   */
  unregister(key) {
    this._registry.delete(key);
  }

  /**
   * Fetch the asset manifest JSON and register all entries.
   * Entries already registered via registerAll() are NOT overwritten.
   *
   * @param {string} manifestUrl - URL to manifest.json relative to origin.
   * @returns {Promise<void>}
   */
  async loadManifest(manifestUrl) {
    let manifest;
    try {
      const response = await fetch(manifestUrl);
      if (!response.ok) {
        console.warn(
          `[AssetLoader] Failed to fetch manifest (${response.status}): ${manifestUrl}`,
        );
        return;
      }
      manifest = await response.json();
    } catch (err) {
      console.warn("[AssetLoader] Could not load manifest:", err);
      return;
    }

    const categories = ["images", "animations", "materials", "audio"];
    let registered = 0;
    for (const category of categories) {
      const entries = manifest[category];
      if (!entries || typeof entries !== "object") continue;
      for (const [id, entry] of Object.entries(entries)) {
        if (this._registry.has(id)) continue;
        if (entry && typeof entry.path === "string") {
          this.register(id, entry.path);
          registered += 1;
        }
      }
    }
    console.log(
      `[AssetLoader] Manifest loaded: ${registered} entries registered from ${manifestUrl}`,
    );
  }
}

// ------------------------------------------------------------------
// Shared instance + built-in asset registrations
// ------------------------------------------------------------------

/**
 * Global AssetLoader instance. All engine modules that need asset
 * resolution import this reference.
 *
 * @type {AssetLoader}
 */
const assetLoader = new AssetLoader();

// Example / lantern assets — placeholders until real atlases are added.
assetLoader.registerAll({
  // Lantern
  lantern_atlas: "assets/images/sprites/objects/lantern_atlas.png",
  lantern_params: "assets/images/param_maps/lantern_params.png",
  glow_pulse_atlas: "assets/images/effects/glow/lantern_glow.png",

  // Human / player
  human_atlas: "assets/images/sprites/human/human_atlas.png",
  human_params: "assets/images/param_maps/human_params.png",

  // Colour ramp LUTs
  fire_ramp: "assets/images/color_ramps/fire_ramp.png",
  ice_ramp: "assets/images/color_ramps/ice_ramp.png",
  poison_ramp: "assets/images/color_ramps/poison_ramp.png",
});

// Load manifest asynchronously. Modules that depend on manifest assets
// must await assetLoader.manifestReady before resolving keys.
assetLoader.manifestReady = assetLoader.loadManifest("assets/manifest.json");
