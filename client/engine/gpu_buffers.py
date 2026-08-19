"""GPUBuffer helpers shared across the wgpu rendering path.

Port of frontend/js/engine/sprites/gpuBuffers.js -- Step 7 of
.github/prompts/wgpu-py-migration.prompt.md. Float data is packed with
the standard-library `array` module (`array.array('f', ...)`), not
numpy -- per the Constraints section, this project hand-rolls its own
data packing rather than pulling in a general-purpose numeric library;
`array` is buffer-protocol-compatible and is exactly what
device.queue.write_buffer()/GPUBuffer.write_mapped() need.
"""

import array

import wgpu


def create_uniform_buffer(device, byte_size: int):
    """Create a uniform buffer.

    byte_size is rounded up to the next multiple of 256 to satisfy
    WebGPU's minUniformBufferOffsetAlignment requirement.
    """
    aligned_size = -(-byte_size // 256) * 256  # ceil division, no float rounding
    return device.create_buffer(
        size=aligned_size,
        usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
    )


def write_uniform_buffer(device, buffer, data) -> None:
    """Write data into a uniform buffer.

    Args:
        device: GPUDevice.
        buffer: GPUBuffer.
        data: A buffer-protocol object, e.g. array.array('f', [...])
            containing MVP, uv_rect, tint, etc.
    """
    device.queue.write_buffer(buffer, 0, data)


def create_quad_vertex_buffer(device):
    """Create a static vertex buffer containing a unit quad as two CCW
    triangles.

    Vertex layout: [x, y, u, v] -- 4 x f32 = 16 bytes per vertex.
    6 vertices x 16 bytes = 96 bytes total.

    Triangle 0 (bottom-left):  (-1,-1), ( 1,-1), ( 1, 1)
    Triangle 1 (top-right):    (-1,-1), ( 1, 1), (-1, 1)

    NDC coordinates cover the full clip-space quad; the MVP matrix in
    the uniform buffer scales and positions each sprite in screen space.

    UV (0,0) is top-left, (1,1) is bottom-right, matching WebGPU /
    Canvas convention where V increases downward.
    """
    vertices = array.array(
        "f",
        [
            # x      y      u     v
            -1.0, -1.0, 0.0, 1.0,  # bottom-left
            1.0, -1.0, 1.0, 1.0,  # bottom-right
            1.0, 1.0, 1.0, 0.0,  # top-right
            -1.0, -1.0, 0.0, 1.0,  # bottom-left
            1.0, 1.0, 1.0, 0.0,  # top-right
            -1.0, 1.0, 0.0, 0.0,  # top-left
        ],
    )

    buffer = device.create_buffer(
        size=vertices.itemsize * len(vertices),  # 96 bytes
        usage=wgpu.BufferUsage.VERTEX | wgpu.BufferUsage.COPY_DST,
        mapped_at_creation=True,
    )
    buffer.write_mapped(vertices)
    buffer.unmap()

    return buffer
