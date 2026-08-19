
# Development Notes

## Procedural Generation

[Video](https://www.youtube.com/watch?v=G6ZHUOSXZDo)

Undetermined cells adjacent to an existing cell exist in a superposition of all possibilities.
Start with the superposition cell that contains the least possibilities.

Psuedo-randomly select what the superposition cell becomes. Collapses the superpositioned cell, adject superposition cells have their possible outcomes updated.

Weights can be assigned to possible outcomes to make it more likely to generate a preferred outcome. This is creating a "low entropy" algorithm, random but vaguely predictable.
If wanting to generate a long straight pathway that forks occasionally, assign high weights to outcomes that continue the current pathway, medium weights to fork outcomes and low weights to outcomes that end the current pathway.

Can "force" generate key cells or structures by having a pre-check before choosing which superposition cell to collapse next. Key cell has a low probility roll, if it succeeds it will attempt to generate a key cell in a valid location. If it fails, can increment a counter to make success more likely next time or eventually hit a dry protection threshold. Can then return to standard generation, and this may help spread out key cells.