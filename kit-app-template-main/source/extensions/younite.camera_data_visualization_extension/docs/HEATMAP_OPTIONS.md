# Heatmap Visualization Options in Omniverse

This document summarizes approaches for implementing heatmap-style occupancy visualization in Omniverse/USD.

## Implemented: displayColor Primvar (Current)

**How it works:** A subdivided grid mesh (e.g. 64×64 quads) with per-vertex `displayColor` primvar. Each frame we update the color array directly on the USD prim.

**Pros:**
- No texture files; colors written directly to USD stage
- Reliable updates (no texture caching issues)
- Uses standard USD primvars ([Primvars Overview](https://openusd.org/dev/user_guides/primvars.html))
- Works with Omniverse viewport without special APIs

**Cons:**
- Replaces the original mesh geometry (subdivides the quad into a grid)
- Vertex count scales with resolution (64×64 → 4225 vertices)

---

## Option 2: Dynamic Texture on Plane

**How it works:** Write heatmap image to PNG, bind via UsdUVTexture to a material on the plane.

**Pros:** Simple concept; reuses existing plane mesh.

**Cons:** Omniverse may cache textures; overwriting the file often does not trigger a viewport refresh. Alternating file paths can cause flashing. **Not reliable in practice.**

---

## Option 3: Point Instancer / Scatter Plot

**How it works:** Place many small colored quads or discs at each detection position. Color intensity = recency/density.

**Pros:** Very reliable; each point is a USD prim. No texture or primvar complexity.

**Cons:** Heavy if many points; less "smooth" heatmap look; requires managing many prims.

---

## Option 4: Volume / VDB

**How it works:** Create a 3D or 2D volume grid and render it as a volume.

**Pros:** Smooth, professional heatmap look.

**Cons:** More complex; requires volume rendering support; heavier compute.

---

## Option 5: Custom Shader with Buffer

**How it works:** Pass heatmap data to a custom MDL/Shader as a buffer or uniform; shader samples it.

**Pros:** Flexible; can do advanced effects.

**Cons:** Requires custom shader authoring; Omniverse shader APIs may not expose runtime buffers easily.

---

## Recommendation

The **displayColor primvar** approach (implemented in `heatmap_runner.py`) is the most reliable for dynamic heatmaps in Omniverse without custom shaders or heavy prim management. It aligns with USD's [Primitive Variables (Primvars)](https://openusd.org/dev/user_guides/primvars.html) and the [NVIDIA Omniverse Primvars overview](https://www.nvidia.com/en-us/on-demand/session/omniverse2020-om1460/).
