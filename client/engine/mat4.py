"""mat4 -- explicit, dependency-free 4x4 matrix helpers.

Direct Python port of frontend/js/engine/mat4.js (see that file's own
header comment) -- same layout, same math, same function set. Ported
verbatim per .github/prompts/wgpu-py-migration.prompt.md's Step 4 and
Constraints (no numpy/pyglm; a flat, column-major, hand-built list of
16 floats, matching WGSL's mat4x4<f32> layout):

    [ m0  m4  m8  m12 ]
    [ m1  m5  m9  m13 ]
    [ m2  m6  m10 m14 ]
    [ m3  m7  m11 m15 ]

Euler rotation order (rotation_xyz, compose): intrinsic Z, then Y, then
X -- the returned matrix is Rx * Ry * Rz applied to a column vector
(roll, then pitch, then yaw). Every consumer of Euler rotation in this
project must use this exact convention -- it must match mat4.js's
convention exactly, since both clients need to agree on how a
transform3d/socket/keyframe rotation is interpreted.

KEEP docs/graphics/MAT4.md IN SYNC -- any change to this file's
function set, matrix layout, or Euler rotation convention must update
that doc in the same change.
"""

import math
from typing import Sequence

Vec3 = Sequence[float]
Mat4 = list[float]


def identity() -> Mat4:
    """4x4 identity matrix."""
    return [
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        0.0, 0.0, 0.0, 1.0,
    ]


def perspective(fov_y_radians: float, aspect: float, near: float, far: float) -> Mat4:
    """WebGPU-convention (0..1 depth range) perspective projection matrix.

    Args:
        fov_y_radians: Vertical field of view, in radians.
        aspect: Viewport width / height.
        near: Near clip distance (> 0).
        far: Far clip distance (> near).
    """
    f = 1.0 / math.tan(fov_y_radians / 2)
    range_inv = 1.0 / (near - far)

    return [
        f / aspect, 0.0, 0.0, 0.0,
        0.0, f, 0.0, 0.0,
        0.0, 0.0, far * range_inv, -1.0,
        0.0, 0.0, near * far * range_inv, 0.0,
    ]


def look_at(eye: Vec3, target: Vec3, up: Vec3) -> Mat4:
    """View matrix looking from `eye` toward `target`, with `up` as the
    reference up vector.
    """
    ex, ey, ez = eye

    # z_axis = normalize(eye - target)  (camera looks down -z_axis)
    zx = ex - target[0]
    zy = ey - target[1]
    zz = ez - target[2]
    z_len = math.hypot(zx, zy, zz) or 1.0
    zx /= z_len
    zy /= z_len
    zz /= z_len

    # x_axis = normalize(cross(up, z_axis))
    xx = up[1] * zz - up[2] * zy
    xy = up[2] * zx - up[0] * zz
    xz = up[0] * zy - up[1] * zx
    x_len = math.hypot(xx, xy, xz) or 1.0
    xx /= x_len
    xy /= x_len
    xz /= x_len

    # y_axis = cross(z_axis, x_axis) -- already unit length (z_axis, x_axis orthonormal)
    yx = zy * xz - zz * xy
    yy = zz * xx - zx * xz
    yz = zx * xy - zy * xx

    return [
        xx, yx, zx, 0.0,
        xy, yy, zy, 0.0,
        xz, yz, zz, 0.0,
        -(xx * ex + xy * ey + xz * ez),
        -(yx * ex + yy * ey + yz * ez),
        -(zx * ex + zy * ey + zz * ez),
        1.0,
    ]


def multiply(a: Mat4, b: Mat4) -> Mat4:
    """a * b -- both column-major, 16-element lists."""
    out = [0.0] * 16
    for col in range(4):
        for row in range(4):
            total = 0.0
            for k in range(4):
                total += a[k * 4 + row] * b[col * 4 + k]
            out[col * 4 + row] = total
    return out


def translation_scale(
    tx: float, ty: float, tz: float, sx: float, sy: float, sz: float
) -> Mat4:
    """Model matrix combining translation and non-uniform scale, no
    rotation. Mirrors the existing 2D scale/translate inline
    construction, extended to 3 axes. Kept only for callers that
    genuinely never rotate -- most 3D callers need `compose` instead.
    """
    return [
        sx, 0.0, 0.0, 0.0,
        0.0, sy, 0.0, 0.0,
        0.0, 0.0, sz, 0.0,
        tx, ty, tz, 1.0,
    ]


def rotation_xyz(rx: float, ry: float, rz: float) -> Mat4:
    """Rotation matrix from Euler angles (radians). Composition order is
    intrinsic Z, then Y, then X -- the result is Rx * Ry * Rz applied to
    a column vector. Every caller in this project (sockets, animation
    keyframes, action clips) must use this exact convention.
    """
    cx = math.cos(rx)
    sx = math.sin(rx)
    cy = math.cos(ry)
    sy = math.sin(ry)
    cz = math.cos(rz)
    sz = math.sin(rz)

    # Rx * Ry * Rz, column-major.
    m00 = cy * cz
    m01 = cy * sz
    m02 = -sy

    m10 = sx * sy * cz - cx * sz
    m11 = sx * sy * sz + cx * cz
    m12 = sx * cy

    m20 = cx * sy * cz + sx * sz
    m21 = cx * sy * sz - sx * cz
    m22 = cx * cy

    return [
        m00, m10, m20, 0.0,
        m01, m11, m21, 0.0,
        m02, m12, m22, 0.0,
        0.0, 0.0, 0.0, 1.0,
    ]


def compose(position: Vec3, rotation_euler: Vec3, scale: Vec3) -> Mat4:
    """General-purpose TRS (translate * rotate * scale) model matrix.
    This is what actually gets used wherever a transform3d/socket/
    keyframe with position AND rotation needs to become a matrix --
    `translation_scale` alone cannot represent a rotated socket or an
    animated spin.

    Args:
        position: [x, y, z]
        rotation_euler: Radians, [x, y, z].
        scale: [x, y, z]
    """
    sx, sy, sz = scale
    rot = rotation_xyz(rotation_euler[0], rotation_euler[1], rotation_euler[2])

    # Apply scale to the rotation matrix's basis columns, then translate.
    return [
        rot[0] * sx, rot[1] * sx, rot[2] * sx, 0.0,
        rot[4] * sy, rot[5] * sy, rot[6] * sy, 0.0,
        rot[8] * sz, rot[9] * sz, rot[10] * sz, 0.0,
        position[0], position[1], position[2], 1.0,
    ]


def compose_with_pivot(position: Vec3, rotation_euler: Vec3, scale: Vec3, pivot: Vec3) -> Mat4:
    """Same TRS composition as `compose()`, except rotation and scale
    pivot around *pivot* (a point in the same local space as
    *position*, e.g. a socket's own local coordinates) instead of the
    local origin -- `T(position) * T(pivot) * R * S * T(-pivot)`.

    Built for animated parts whose mesh-space origin (wherever the
    artist happened to set it in Blender) doesn't coincide with the
    point the animation should actually rotate/scale around -- a wing
    hinging at its shoulder socket rather than at the wing mesh's own
    center, for example. `pivot = [0, 0, 0]` collapses the pivot
    translate/untranslate pair to identity, making this exactly
    `compose()`'s own result -- callers with no origin set can pass
    `[0.0, 0.0, 0.0]` with zero behavior change.
    """
    if pivot[0] == 0.0 and pivot[1] == 0.0 and pivot[2] == 0.0:
        return compose(position, rotation_euler, scale)

    pre_pivot = translation_scale(-pivot[0], -pivot[1], -pivot[2], 1.0, 1.0, 1.0)
    rotate_scale = compose([0.0, 0.0, 0.0], rotation_euler, scale)
    post_pivot = translation_scale(
        pivot[0] + position[0], pivot[1] + position[1], pivot[2] + position[2], 1.0, 1.0, 1.0
    )
    return multiply(post_pivot, multiply(rotate_scale, pre_pivot))
