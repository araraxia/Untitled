
# Development Notes

## Player Controls

### Diverting Controls In Dif Scenarios (Menu/Character/Etc.)

Divert at `backend.game_loop.process_player_actions`.
What logic applied to inputs/actions can be determined by `frontend.js.input.gameState.context` which should have a value of `frontend.js.main.GameContext.value: const dict.value`

Will need to probably merge `backend.game_loop.process_party_commands` into it.

## Object Management

### World

> File pending.

### Area

> area.py

!!! CURRENTLY WORKING HERE !!!

### PlayerCharacter

> player.py

### Entity

> entity.py

## Misc Notes

Left off defining Objects such as areas and worlds. Need to be able to load and save current world/area data. One folder per player save with unique name, contents follow consistent schema (world.json, area-0001.json, etc.)

## Procedural Generation

[Video](https://www.youtube.com/watch?v=G6ZHUOSXZDo)

Undetermined cells adjacent to an existing cell exist in a superposition of all possibilities.
Start with the superposition cell that contains the least possibilities.

Psuedo-randomly select what the superposition cell becomes. Collapses the superpositioned cell, adject superposition cells have their possible outcomes updated.

Weights can be assigned to possible outcomes to make it more likely to generate a preferred outcome. This is creating a "low entropy" algorithm, random but vaguely predictable.
If wanting to generate a long straight pathway that forks occasionally, assign high weights to outcomes that continue the current pathway, medium weights to fork outcomes and low weights to outcomes that end the current pathway.

Can "force" generate key cells or structures by having a pre-check before choosing which superposition cell to collapse next. Key cell has a low probility roll, if it succeeds it will attempt to generate a key cell in a valid location. If it fails, can increment a counter to make success more likely next time or eventually hit a dry protection threshold. Can then return to standard generation, and this may help spread out key cells.
