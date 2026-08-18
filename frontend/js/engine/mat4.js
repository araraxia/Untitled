/**
 * mat4 — explicit, dependency-free 4x4 matrix helpers.
 *
 * Flat Float32Array(16), column-major, matching WGSL's mat4x4<f32> layout:
 *   [ m0  m4  m8  m12 ]
 *   [ m1  m5  m9  m13 ]
 *   [ m2  m6  m10 m14 ]
 *   [ m3  m7  m11 m15 ]
 *
 * Euler rotation order (rotationXYZ, compose): intrinsic Z, then Y, then X
 * — the returned matrix is Rx * Ry * Rz applied to a column vector (roll,
 * then pitch, then yaw). Every consumer of Euler rotation in this project
 * must use this exact convention.
 */

/**
 * @returns {Float32Array} 4x4 identity matrix.
 */
function identity() {
  // prettier-ignore
  return new Float32Array([
    1, 0, 0, 0,
    0, 1, 0, 0,
    0, 0, 1, 0,
    0, 0, 0, 1,
  ]);
}

/**
 * WebGPU-convention (0..1 depth range) perspective projection matrix.
 *
 * @param {number} fovYRadians - Vertical field of view, in radians.
 * @param {number} aspect - Viewport width / height.
 * @param {number} near - Near clip distance (> 0).
 * @param {number} far - Far clip distance (> near).
 * @returns {Float32Array}
 */
function perspective(fovYRadians, aspect, near, far) {
  const f = 1.0 / Math.tan(fovYRadians / 2);
  const rangeInv = 1.0 / (near - far);

  // prettier-ignore
  return new Float32Array([
    f / aspect, 0, 0,                       0,
    0,          f, 0,                       0,
    0,          0, far * rangeInv,          -1,
    0,          0, near * far * rangeInv,   0,
  ]);
}

/**
 * View matrix looking from `eye` toward `target`, with `up` as the
 * reference up vector.
 *
 * @param {[number, number, number]} eye
 * @param {[number, number, number]} target
 * @param {[number, number, number]} up
 * @returns {Float32Array}
 */
function lookAt(eye, target, up) {
  const [ex, ey, ez] = eye;

  // zAxis = normalize(eye - target)  (camera looks down -zAxis)
  let zx = ex - target[0];
  let zy = ey - target[1];
  let zz = ez - target[2];
  let zLen = Math.hypot(zx, zy, zz) || 1;
  zx /= zLen;
  zy /= zLen;
  zz /= zLen;

  // xAxis = normalize(cross(up, zAxis))
  let xx = up[1] * zz - up[2] * zy;
  let xy = up[2] * zx - up[0] * zz;
  let xz = up[0] * zy - up[1] * zx;
  let xLen = Math.hypot(xx, xy, xz) || 1;
  xx /= xLen;
  xy /= xLen;
  xz /= xLen;

  // yAxis = cross(zAxis, xAxis) — already unit length (zAxis, xAxis orthonormal)
  const yx = zy * xz - zz * xy;
  const yy = zz * xx - zx * xz;
  const yz = zx * xy - zy * xx;

  // prettier-ignore
  return new Float32Array([
    xx, yx, zx, 0,
    xy, yy, zy, 0,
    xz, yz, zz, 0,
    -(xx * ex + xy * ey + xz * ez),
    -(yx * ex + yy * ey + yz * ez),
    -(zx * ex + zy * ey + zz * ez),
    1,
  ]);
}

/**
 * a * b — both column-major Float32Array(16).
 *
 * @param {Float32Array} a
 * @param {Float32Array} b
 * @returns {Float32Array}
 */
function multiply(a, b) {
  const out = new Float32Array(16);
  for (let col = 0; col < 4; col += 1) {
    for (let row = 0; row < 4; row += 1) {
      let sum = 0;
      for (let k = 0; k < 4; k += 1) {
        sum += a[k * 4 + row] * b[col * 4 + k];
      }
      out[col * 4 + row] = sum;
    }
  }
  return out;
}

/**
 * Model matrix combining translation and non-uniform scale, no rotation.
 * Mirrors the existing 2D scaleX/scaleY/tx/ty inline construction,
 * extended to 3 axes. Kept only for callers that genuinely never rotate —
 * most 3D callers need `compose` instead.
 *
 * @param {number} tx
 * @param {number} ty
 * @param {number} tz
 * @param {number} sx
 * @param {number} sy
 * @param {number} sz
 * @returns {Float32Array}
 */
function translationScale(tx, ty, tz, sx, sy, sz) {
  // prettier-ignore
  return new Float32Array([
    sx, 0,  0,  0,
    0,  sy, 0,  0,
    0,  0,  sz, 0,
    tx, ty, tz, 1,
  ]);
}

/**
 * Rotation matrix from Euler angles (radians). Composition order is
 * intrinsic Z, then Y, then X — the result is Rx * Ry * Rz applied to a
 * column vector. Every caller in this project (sockets, animation
 * keyframes, action clips) must use this exact convention.
 *
 * @param {number} rx
 * @param {number} ry
 * @param {number} rz
 * @returns {Float32Array}
 */
function rotationXYZ(rx, ry, rz) {
  const cx = Math.cos(rx);
  const sx = Math.sin(rx);
  const cy = Math.cos(ry);
  const sy = Math.sin(ry);
  const cz = Math.cos(rz);
  const sz = Math.sin(rz);

  // Rx * Ry * Rz, column-major.
  const m00 = cy * cz;
  const m01 = cy * sz;
  const m02 = -sy;

  const m10 = sx * sy * cz - cx * sz;
  const m11 = sx * sy * sz + cx * cz;
  const m12 = sx * cy;

  const m20 = cx * sy * cz + sx * sz;
  const m21 = cx * sy * sz - sx * cz;
  const m22 = cx * cy;

  // prettier-ignore
  return new Float32Array([
    m00, m10, m20, 0,
    m01, m11, m21, 0,
    m02, m12, m22, 0,
    0,   0,   0,   1,
  ]);
}

/**
 * General-purpose TRS (translate * rotate * scale) model matrix.
 * This is what actually gets used wherever a transform3d/socket/keyframe
 * with position AND rotation needs to become a matrix — `translationScale`
 * alone cannot represent a rotated socket or an animated spin.
 *
 * @param {[number, number, number]} position
 * @param {[number, number, number]} rotationEuler - Radians, [x, y, z].
 * @param {[number, number, number]} scale
 * @returns {Float32Array}
 */
function compose(position, rotationEuler, scale) {
  const [sx, sy, sz] = scale;
  const rot = rotationXYZ(rotationEuler[0], rotationEuler[1], rotationEuler[2]);

  // Apply scale to the rotation matrix's basis columns, then translate.
  // prettier-ignore
  const out = new Float32Array([
    rot[0] * sx,  rot[1] * sx,  rot[2] * sx,  0,
    rot[4] * sy,  rot[5] * sy,  rot[6] * sy,  0,
    rot[8] * sz,  rot[9] * sz,  rot[10] * sz, 0,
    position[0],  position[1],  position[2],  1,
  ]);
  return out;
}
