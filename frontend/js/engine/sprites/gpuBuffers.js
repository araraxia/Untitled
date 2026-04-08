/**
 * GPUBuffer helpers shared across the WebGPU rendering path.
 */

/**
 * Create a uniform buffer.
 *
 * byteSize is rounded up to the next multiple of 256 to satisfy WebGPU's
 * minUniformBufferOffsetAlignment requirement.
 *
 * @param {GPUDevice} device
 * @param {number} byteSize - Minimum number of bytes needed.
 * @returns {GPUBuffer}
 */
function createUniformBuffer(device, byteSize) {
  const alignedSize = Math.ceil(byteSize / 256) * 256;
  return device.createBuffer({
    size: alignedSize,
    usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST,
  });
}

/**
 * Write data into a uniform buffer.
 *
 * @param {GPUDevice} device
 * @param {GPUBuffer} buffer
 * @param {ArrayBufferView} data - e.g. Float32Array containing MVP, uv_rect, tint.
 */
function writeUniformBuffer(device, buffer, data) {
  device.queue.writeBuffer(buffer, 0, data);
}

/**
 * Create a static vertex buffer containing a unit quad as two CCW triangles.
 *
 * Vertex layout: [x, y, u, v] — 4 × f32 = 16 bytes per vertex.
 * 6 vertices × 16 bytes = 96 bytes total.
 *
 * Triangle 0 (bottom-left):  (-1,-1), ( 1,-1), ( 1, 1)
 * Triangle 1 (top-right):    (-1,-1), ( 1, 1), (-1, 1)
 *
 * NDC coordinates cover the full clip-space quad; the MVP matrix in the
 * uniform buffer scales and positions each sprite in screen space.
 *
 * UV (0,0) is top-left, (1,1) is bottom-right, matching WebGPU / Canvas
 * convention where V increases downward.
 *
 * @param {GPUDevice} device
 * @returns {GPUBuffer}
 */
function createQuadVertexBuffer(device) {
  // prettier-ignore
  const vertices = new Float32Array([
    // x      y      u     v
    -1.0, -1.0,   0.0,  1.0,  // bottom-left
     1.0, -1.0,   1.0,  1.0,  // bottom-right
     1.0,  1.0,   1.0,  0.0,  // top-right

    -1.0, -1.0,   0.0,  1.0,  // bottom-left
     1.0,  1.0,   1.0,  0.0,  // top-right
    -1.0,  1.0,   0.0,  0.0,  // top-left
  ]);

  const buffer = device.createBuffer({
    size: vertices.byteLength, // 96 bytes
    usage: GPUBufferUsage.VERTEX | GPUBufferUsage.COPY_DST,
    mappedAtCreation: true,
  });
  new Float32Array(buffer.getMappedRange()).set(vertices);
  buffer.unmap();

  return buffer;
}
