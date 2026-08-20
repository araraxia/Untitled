# Graphics System — Coordinate Mapping

## UV Coordinates

In WebGPU each sprite quad has **UV coordinates** (also called **texture coordinates**): normalised (0–1) values that map the corners of the quad to positions in a texture. The fragment shader receives the interpolated UV at each pixel and uses it to sample textures.

For sprite atlas frames, the UV rectangle is computed from the frame index:

```text
u0 = (frameCol * frameWidth)  / atlasWidth
v0 = (frameRow * frameHeight) / atlasHeight
u1 = u0 + frameWidth  / atlasWidth
v1 = v0 + frameHeight / atlasHeight
```

---

## 2D (Current Target)

The vertex shader receives the world-space position of each quad vertex and transforms it via a combined **Model-View-Projection (MVP)** matrix to clip space, passed as a uniform buffer field.

For a 2D top-down or side-scrolling game the MVP degenerates to a simple translation + scale (no perspective divide needed). The camera position and zoom level are folded into the matrix on the CPU each frame.

---

## 2.5D / 3D

> Implemented — see [ROADMAP.md](../../ROADMAP.md) Phase 10 (steps 1–11 of 14 done). Kept as "Future" framing below only where it describes work still ahead (e.g. Area/Scene camera authoring, Phase 11); billboarding and the mesh draw path described here are live in `client/engine/`.

The same parameter map textures can be applied to 3D mesh surfaces using standard UV mapping. In the vertex shader, `(u, v)` values are interpolated across triangles and passed to the fragment shader, which samples the textures at those coordinates — the combiner logic is identical to the 2D case.

**Billboarding** (sprites that always face the camera) is achieved by constructing the quad's model matrix from the camera's right and up vectors rather than a fixed orientation. This gives 2.5D sprites in a 3D world without requiring 3D meshes per entity.

WebGPU exposes compute shaders, a lower-overhead draw call model, and explicit resource management — all of which benefit a simulation with many entities, and all of which are relevant for future 3D work.
