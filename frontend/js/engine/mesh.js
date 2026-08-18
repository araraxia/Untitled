/**
 * Mesh — a static (non-animated) textured 3D mesh: an interleaved vertex
 * buffer (pos.xyz, normal.xyz, uv.xy, color.rgba = 12 floats/vertex) plus
 * an index buffer, loaded from this project's own JSON format (not a
 * glTF subset — see tools/convert_mesh.py for the Blender authoring
 * pipeline, and docs/graphics/DATA_STRUCTURES.md for the schema).
 *
 * Reuses the existing material combiner fragment shaders (shaderCache.js's
 * 'mesh' pipeline variant) — this class only owns the GPU vertex/index
 * buffers, nothing shader- or material-specific.
 */

/** Floats per vertex: pos(3) + normal(3) + uv(2) + color(4). */
const MESH_FLOATS_PER_VERTEX = 12;

/** Bytes per vertex (12 floats × 4 bytes). */
const MESH_VERTEX_STRIDE = MESH_FLOATS_PER_VERTEX * 4;

/**
 * Vertex buffer attribute layout for the 'mesh' pipeline variant
 * (ShaderCache.getMeshPipeline). Exported so shaderCache.js doesn't need
 * to hand-duplicate these offsets.
 * @type {GPUVertexAttribute[]}
 */
const MESH_VERTEX_ATTRIBUTES = [
  { shaderLocation: 0, offset: 0, format: 'float32x3' }, // pos
  { shaderLocation: 1, offset: 12, format: 'float32x3' }, // normal
  { shaderLocation: 2, offset: 24, format: 'float32x2' }, // uv
  { shaderLocation: 3, offset: 32, format: 'float32x4' }, // color
];

class Mesh {
  /**
   * @param {GPUDevice} device
   */
  constructor(device) {
    this._device = device;
    this._vertexBuffer = null;
    this._indexBuffer = null;
    this._indexFormat = 'uint16';
    this._vertexCount = 0;
    this._indexCount = 0;
  }

  /** @returns {number} */
  get vertexCount() {
    return this._vertexCount;
  }

  /** @returns {number} */
  get indexCount() {
    return this._indexCount;
  }

  /** @returns {GPUIndexFormat} 'uint16' or 'uint32', matching indexBuffer's contents. */
  get indexFormat() {
    return this._indexFormat;
  }

  /** @returns {GPUBuffer|null} */
  get vertexBuffer() {
    return this._vertexBuffer;
  }

  /** @returns {GPUBuffer|null} */
  get indexBuffer() {
    return this._indexBuffer;
  }

  /**
   * Fetch the mesh JSON, pack vertices into an interleaved Float32Array,
   * and upload both vertex and index buffers to the GPU. Must be awaited
   * before drawing.
   *
   * @param {string} meshJsonPath
   * @returns {Promise<void>}
   */
  async load(meshJsonPath) {
    const response = await fetch(meshJsonPath);
    if (!response.ok) {
      throw new Error(
        `[Mesh] Failed to fetch '${meshJsonPath}': ${response.status}`,
      );
    }
    const data = await response.json();

    const vertices = data.vertices || [];
    this._vertexCount = vertices.length;

    const vertexData = new Float32Array(
      vertices.length * MESH_FLOATS_PER_VERTEX,
    );
    vertices.forEach((v, i) => {
      const base = i * MESH_FLOATS_PER_VERTEX;
      const pos = v.pos || [0, 0, 0];
      const normal = v.normal || [0, 1, 0];
      const uv = v.uv || [0, 0];
      // Missing color defaults to [1,1,1,1] (a no-op multiply) — the
      // field is purely opt-in per DATA_STRUCTURES.md, not required.
      const color = v.color || [1, 1, 1, 1];

      vertexData[base + 0] = pos[0];
      vertexData[base + 1] = pos[1];
      vertexData[base + 2] = pos[2];
      vertexData[base + 3] = normal[0];
      vertexData[base + 4] = normal[1];
      vertexData[base + 5] = normal[2];
      vertexData[base + 6] = uv[0];
      vertexData[base + 7] = uv[1];
      vertexData[base + 8] = color[0];
      vertexData[base + 9] = color[1];
      vertexData[base + 10] = color[2];
      vertexData[base + 11] = color[3];
    });

    this._vertexBuffer = this._device.createBuffer({
      size: vertexData.byteLength,
      usage: GPUBufferUsage.VERTEX | GPUBufferUsage.COPY_DST,
      mappedAtCreation: true,
    });
    new Float32Array(this._vertexBuffer.getMappedRange()).set(vertexData);
    this._vertexBuffer.unmap();

    const indices = data.indices || [];
    this._indexCount = indices.length;

    // Uint16 covers up to 65535 distinct vertex indices — plenty for the
    // low-poly assets this task targets; fall back to Uint32 otherwise.
    const useU16 = this._vertexCount <= 65535;
    this._indexFormat = useU16 ? 'uint16' : 'uint32';
    const IndexArrayType = useU16 ? Uint16Array : Uint32Array;

    let indexArray = new IndexArrayType(indices);
    // GPUBuffer sizes must be a multiple of 4 bytes. Uint32Array indices
    // are always aligned; a Uint16Array with an odd index count needs one
    // extra (unused) padding index to reach a 4-byte-aligned byte length.
    if (useU16 && indexArray.byteLength % 4 !== 0) {
      const padded = new Uint16Array(indices.length + 1);
      padded.set(indexArray);
      indexArray = padded;
    }

    this._indexBuffer = this._device.createBuffer({
      size: indexArray.byteLength,
      usage: GPUBufferUsage.INDEX | GPUBufferUsage.COPY_DST,
      mappedAtCreation: true,
    });
    new IndexArrayType(this._indexBuffer.getMappedRange()).set(indexArray);
    this._indexBuffer.unmap();
  }

  /**
   * Release the GPU buffers held by this mesh. Call when no longer needed.
   */
  destroy() {
    if (this._vertexBuffer) {
      this._vertexBuffer.destroy();
      this._vertexBuffer = null;
    }
    if (this._indexBuffer) {
      this._indexBuffer.destroy();
      this._indexBuffer = null;
    }
    this._vertexCount = 0;
    this._indexCount = 0;
  }
}
