
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
