

# Player Inputs

### Diverting Controls In Dif Scenarios (Menu/Character/Etc.)
Divert at `backend.game_loop.process_player_actions`.
What logic applied to inputs/actions can be determined by `frontend.js.input.gameState.context` which should have a value of `frontend.js.main.GameContext.value: const dict.value` 

Will need to probably merge `backend.game_loop.process_party_commands` into it.
