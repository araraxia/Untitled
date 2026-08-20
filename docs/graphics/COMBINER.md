# Graphics System — Multi-Texture Combiner & Parameter Maps

## Concept: N64-Inspired Combiner

The Nintendo 64's **Reality Display Processor (RDP)** had a programmable **Color Combiner**: a fixed arithmetic unit that blended up to two texture samples, a flat colour, and a vertex colour using the formula:

```text
output = (A − B) × C + D
```

where A, B, C, and D are each configurable inputs (texture 0 sample, texture 1 sample, a uniform constant, vertex colour, etc.). This let artists produce effects like tinted sprites, masked overlays, and environment-mapped surfaces without a general-purpose shader language.

The modern equivalent is a **WGSL fragment shader** running on the GPU in a WebGPU context. The combiner inputs become **texture bindings** and **uniform buffer** fields. The formula becomes an arbitrary expression in shader code, which is strictly more powerful.

---

## Terminology Map

| Informal description | Proper graphics term |
| --- | --- |
| "Custom pixel map" | **Data texture** / **parameter map** (a texture where channels store arbitrary per-pixel parameters, not necessarily displayable colour) |
| "Two overlapping images impacting output pixels" | **Multi-texture compositing** — sampling multiple textures in one fragment shader |
| "Predefined variable inputs" | **Uniform variables** — values set by the CPU and constant across a draw call |
| "Output pixel" | **Fragment** (the per-pixel output of a fragment shader before blending) |

---

## Parameter Maps

A parameter map is a standard PNG image whose pixel channel values are read by the shader as arbitrary per-pixel scalars, not displayed colours. Each RGBA channel stores a different parameter in the 0–255 → 0.0–1.0 range.

### Why One Image Instead of Four

A GPU texture sample reads all four channels in a single instruction. Four separate textures would cost four sample instructions plus four texture binds. **Channel packing** gives four independent masks for the price of one.

### Channel Assignment Example (Lantern)

| Channel | What the artist paints | What the shader reads |
| --- | --- | --- |
| **R** | White on metal, black on glass | Specular intensity |
| **G** | White over the flame/glass area | Emissive mask — controls glow overlay strength |
| **B** | Flat mid-grey, slight directional bias | Normal offset — fakes surface depth |
| **A** | White inside the glass pane, black outside | Shape mask — boundary of the glass surface |

### Creating a Parameter Map

In any image editor (Photoshop, GIMP, Krita), paint each mask as a separate greyscale layer, then use the Python packing tool to combine them into one RGBA PNG:

```text
python tools/pack_param_map.py \
  -r src/lantern_specular.png \
  -g src/lantern_emissive.png \
  -b src/lantern_normal.png \
  -a src/lantern_shape.png \
  -o frontend/assets/images/param_maps/lantern_params.png
```

See `tools/pack_param_map.py`. Any channel can be omitted; missing channels default to solid black.

---

## Combiner Shader Sketch

```wgsl
// Fragment shader sketch (WGSL)
struct Uniforms {
    tint : vec4<f32>,
    time : f32,
};
@group(0) @binding(0) var<uniform> u : Uniforms;
@group(0) @binding(1) var u_albedo    : texture_2d<f32>;
@group(0) @binding(2) var u_param_map : texture_2d<f32>;
@group(0) @binding(3) var u_sampler   : sampler;

@fragment
fn fs_main(@location(0) uv: vec2<f32>) -> @location(0) vec4<f32> {
    let albedo = textureSample(u_albedo,    u_sampler, uv);
    let params = textureSample(u_param_map, u_sampler, uv);

    // N64-style combiner: output = (A - B) * C + D
    // Example: tint masked sprites by emissive channel
    return (albedo - vec4<f32>(0.0)) * u.tint * params.g + albedo;
}
```

---

## Material JSON

Materials map each combiner slot to a named source. The renderer reads this at load time to build the bind group layout.

```json
{
  "albedo":    "assets/sprites/human_atlas.png",
  "param_map": "assets/param_maps/human_params.png",
  "combiner": {
    "A": "albedo",
    "B": "zero",
    "C": "u_tint",
    "D": "albedo"
  }
}
```

---

## Implementation Reference

| File | Responsibility |
| --- | --- |
| `client/engine/shader_cache.py` | Compiles and caches `GPURenderPipeline` variants; one pipeline per unique material flag combination |
| `client/engine/material_loader.py` | Reads `material/*.json`, constructs a `GPUBindGroup` per material at load time |
| `tools/pack_param_map.py` | CLI tool that packs greyscale channel images into a single RGBA param map PNG |

> These were originally JS files (`frontend/js/engine/sprites/shaderCache.js`, `materialLoader.js`) under the deleted PyWebView/browser client. The native `wgpu-py` client (`client/engine/`) ported the same responsibilities to Python; see [ARCHITECTURE.md](../../ARCHITECTURE.md).

See [RENDER_WORKFLOWS.md](RENDER_WORKFLOWS.md) for per-effect WGSL shader code and [DATA_STRUCTURES.md](DATA_STRUCTURES.md) for the full material JSON schema.
