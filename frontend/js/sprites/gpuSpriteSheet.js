/**
 * GPUSpriteSheet — WebGPU counterpart to SpriteSheet.
 *
 * Constructor signature mirrors SpriteSheet so EntityRenderer can swap
 * between the two paths without changing call sites.
 *
 * Bind group layout produced by createBindGroup() matches the sprite
 * pipeline defined in shaderCache.js (group 0):
 *   binding 0 — uniform buffer  (mvp / uv_rect / tint)
 *   binding 1 — texture_2d<f32> (albedo atlas)
 *   binding 2 — sampler
 */
class GPUSpriteSheet {
  /**
   * @param {GPUDevice} device
   * @param {string} imagePath - Path to the sprite atlas image.
   * @param {number} frameWidth - Width of one frame in pixels.
   * @param {number} frameHeight - Height of one frame in pixels.
   * @param {number} columns - Number of columns in the atlas grid.
   * @param {number} rows - Number of rows in the atlas grid.
   */
  constructor(device, imagePath, frameWidth, frameHeight, columns, rows) {
    console.log(
      '[GPUSpriteSheet] Constructor called - path:', imagePath,
      'frameSize:', frameWidth + 'x' + frameHeight,
      'grid:', columns + 'x' + rows,
    );
    this._device = device;
    this._imagePath = imagePath;
    this._frameWidth = frameWidth;
    this._frameHeight = frameHeight;
    this._columns = columns;
    this._rows = rows;

    this._texture = null;
    this._sampler = null;
    this._loaded = false;
  }

  /** @returns {boolean} True once load() has completed successfully. */
  get loaded() {
    return this._loaded;
  }

  /**
   * Fetch the atlas image, upload it to a GPUTexture, and create the sampler.
   * Must be awaited before calling getUVRect or createBindGroup.
   * @returns {Promise<void>}
   */
  async load() {
    console.log('[GPUSpriteSheet] load() - fetching:', this._imagePath);

    const response = await fetch(this._imagePath);
    const blob = await response.blob();
    const bitmap = await createImageBitmap(blob);

    this._texture = this._device.createTexture({
      size: [bitmap.width, bitmap.height, 1],
      format: 'rgba8unorm',
      usage:
        GPUTextureUsage.TEXTURE_BINDING |
        GPUTextureUsage.COPY_DST |
        GPUTextureUsage.RENDER_ATTACHMENT,
    });

    this._device.queue.copyExternalImageToTexture(
      { source: bitmap },
      { texture: this._texture },
      [bitmap.width, bitmap.height],
    );

    this._sampler = this._device.createSampler({
      minFilter: 'linear',
      magFilter: 'nearest',
    });

    this._loaded = true;
    console.log('[GPUSpriteSheet] load() complete -', this._imagePath);
  }

  /**
   * Compute the UV sub-rect for a given frame index.
   * Uses the same column/row arithmetic as SpriteSheet.drawFrame.
   *
   * @param {number} frameIndex - 0-based, left-to-right, top-to-bottom.
   * @returns {Float32Array} [u0, v0, u1, v1]
   */
  getUVRect(frameIndex) {
    const column = frameIndex % this._columns;
    const row = Math.floor(frameIndex / this._columns);

    const u0 = column / this._columns;
    const v0 = row / this._rows;
    const u1 = u0 + 1 / this._columns;
    const v1 = v0 + 1 / this._rows;

    return new Float32Array([u0, v0, u1, v1]);
  }

  /**
   * Create a GPUBindGroup for one draw call.
   *
   * The bind group is inexpensive to create and is intended to be created
   * once per sprite sheet (reusing the same uniformBuffer every frame) —
   * call this after load() resolves, store the result, and reuse it.
   *
   * @param {GPUDevice} device
   * @param {GPURenderPipeline} pipeline - The sprite pipeline from ShaderCache.
   * @param {GPUBuffer} uniformBuffer - Pre-allocated uniform buffer (binding 0).
   * @returns {GPUBindGroup}
   */
  createBindGroup(device, pipeline, uniformBuffer) {
    return device.createBindGroup({
      layout: pipeline.getBindGroupLayout(0),
      entries: [
        { binding: 0, resource: { buffer: uniformBuffer } },
        { binding: 1, resource: this._texture.createView() },
        { binding: 2, resource: this._sampler },
      ],
    });
  }
}
