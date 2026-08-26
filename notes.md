
# Development Notes

## Procedural Generation

[Video](https://www.youtube.com/watch?v=G6ZHUOSXZDo)

Undetermined cells adjacent to an existing cell exist in a superposition of all possibilities.
Start with the superposition cell that contains the least possibilities.

Psuedo-randomly select what the superposition cell becomes. Collapses the superpositioned cell, adject superposition cells have their possible outcomes updated.

Weights can be assigned to possible outcomes to make it more likely to generate a preferred outcome. This is creating a "low entropy" algorithm, random but vaguely predictable.
If wanting to generate a long straight pathway that forks occasionally, assign high weights to outcomes that continue the current pathway, medium weights to fork outcomes and low weights to outcomes that end the current pathway.

Can "force" generate key cells or structures by having a pre-check before choosing which superposition cell to collapse next. Key cell has a low probility roll, if it succeeds it will attempt to generate a key cell in a valid location. If it fails, can increment a counter to make success more likely next time or eventually hit a dry protection threshold. Can then return to standard generation, and this may help spread out key cells.

## Random Ideas

### Zone based texturing
Link Assets/Floors/Walls to a Zone. Textures in that zone change to a different texture, not the entire texture swapping but almost like if there are layered/channeled textures and the region the zone covers on the asset lowers it's 'opacity' to reveal the second layer/channel. The N64 styled renderer should be capable of this.

**Use cases**
- To make the texture of the floor change in a moving zone bound to entity. You could have the texture of the ground and walls not be visable, and attach 2 different sized movable zones to the playable entity. The larger movable zone applies a dither mask that display the the larger area around the entity with the dithered texture. The second smaller zone around the entity would reveal the full texture of the ground and walls around the entity. This combined with fog around the entity could make a complex 'Fog of war' effect, and additional zones could be added to make a stepped gradient of texture visibility.
- A floor mesh of grass could have a zone drawn in it to make patch of dirt texture appear, making a gradient of textures between the grass and the dirt

### Dynamically generated meshes
Stuff like waving portals or flags.