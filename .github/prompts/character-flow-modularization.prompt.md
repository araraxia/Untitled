---
agent: agent
description: Remove the legacy hard-wired character select and structured character creation flow from core startup paths, then replace it with a modular character-flow system that can be swapped or extended without editing engine core files.
tools:
  - read_file
  - create_file
  - replace_string_in_file
  - multi_replace_string_in_file
  - grep_search
  - file_search
  - get_errors
  - run_in_terminal
---

# Task: Character Flow Modularization (Legacy Flow Removal)

You are refactoring the game startup and character onboarding flow.
The current character select and structured character creator were built
as a legacy, tightly coupled flow and must be removed from core wiring.

Replace the old flow with a modular system where character-flow modules
can be registered, selected, and swapped without editing core engine
startup or network internals.

Complete all steps in order. Each step must leave the application in a
runnable state before proceeding to the next.

---

## Required Reading

Read these files before writing any code:

- `ROADMAP.md` — current architecture direction and phase boundaries
- `frontend/index.html` — current script load order and legacy game UI scripts
- `frontend/js/game/main.js` — startup flow (`init`, context switching, render loop)
- `frontend/js/engine/network.js` — SocketIO event handlers and coupling points
- `frontend/js/game/playerSelect.js` — legacy player select implementation
- `frontend/js/game/characterCreation.js` — legacy structured creator flow
- `backend/app.py` — SocketIO handlers currently mixing engine and onboarding concerns
- `backend/game/new_game.py` — character creation domain logic
- `backend/game/entities/player.py` — player controller and persistence fields
- `backend/save_manager.py` — save slot listing/loading/deletion behavior
- `config/game.json` — location for modular character-flow config keys

---

## Constraints

- Follow PEP 8 for all Python: 4-space indent, max 79 characters per
  line.
- Use Python type hints throughout. All new public functions and classes
  must be fully typed.
- Follow the Airbnb JavaScript style guide for all JS: 2-space indent,
  single quotes, semicolons.
- All new JS classes and public functions must have JSDoc comments.
- SocketIO naming must follow project conventions:
  client -> server uses `request_*`, server -> client uses descriptive
  snake_case event names, payload keys use snake_case.
- Do not break the existing `state_update` payload contract.
- Engine core files must not contain legacy character creator/select UI
  logic after this migration.
- Remove dead legacy wiring that is no longer used (`request_player_list`
  and paired `player_list` event path).
- Run `python -c "from backend.app import app; print('app ok')"` after
  each Python step.

---

## Step 1 — Audit Legacy Coupling

Before writing any code, produce a short summary covering:

1. Which startup calls in `main.js` assume the current character flow.
2. Which handlers in `network.js` directly manipulate onboarding UI.
3. Which handlers in `backend/app.py` are specifically onboarding and
   should be moved out of app core.
4. Which event names and payload schemas are currently used by player
   select and character creation.
5. Which parts of `playerSelect.js` and `characterCreation.js` are
   reusable domain behavior vs. UI-coupled legacy implementation.

Do not create or edit any files in this step. Output findings, then
proceed.

---

## Step 2 — Define Frontend Module Contracts

**New files:**

- `frontend/js/game/characterFlow/moduleTypes.js`
- `frontend/js/game/characterFlow/moduleRegistry.js`
- `frontend/js/game/characterFlow/flowController.js`

Create a frontend modular contract for character-flow plugins.

### `moduleTypes.js`

Define the base module interface in JSDoc form:

```js
/**
 * @typedef {Object} CharacterFlowModule
 * @property {string} id
 * @property {(ctx: Object) => Promise<void>|void} init
 * @property {(ctx: Object) => Promise<void>|void} mount
 * @property {(ctx: Object) => Promise<void>|void} unmount
 * @property {(eventName: string, data: Object, ctx: Object) => boolean|void} handleEvent
 * @property {(ctx: Object) => Promise<void>|void} destroy
 */
```

### `moduleRegistry.js`

Implement:

- `registerCharacterFlowModule(module)`
- `getCharacterFlowModule(moduleId)`
- `listCharacterFlowModules()`
- Duplicate registration protection with clear error messages.

### `flowController.js`

Implement module lifecycle and switching:

- `initCharacterFlowController(config, context)`
- `activateCharacterFlowModule(moduleId)`
- `dispatchCharacterFlowEvent(eventName, payload)`
- `getActiveCharacterFlowModuleId()`

The controller is the only entry point the rest of the game uses.

---

## Step 3 — Extract Backend Onboarding Service

**New file:** `backend/game/character_flow_service.py`  
**Files to modify:** `backend/app.py`

Create a dedicated backend service module to own onboarding/character
flow SocketIO behavior.

### `character_flow_service.py`

Implement a service (class or functional module) that owns:

- save slot listing request path (`request_save_list` -> `save_list`)
- race listing (`request_races` -> `races_list`)
- background listing (`request_backgrounds` -> `backgrounds_list`)
- player shell creation (`new_player` -> `new_player_initialized`)
- character creation (`new_character` -> `character_created`)
- onboarding error emission (`error` with consistent message payload)

Add a single registration function for app wiring, for example:

```python
def register_character_flow_handlers(socketio, game_loop, logger) -> None:
    ...
```

### `backend/app.py`

- Remove inline onboarding handler implementations and delegate to
  the new registration function.
- Remove dead legacy handler path:
  `request_player_list` and `player_list`.
- Keep app startup behavior unchanged for gameplay loop and `load_player`.

Verify:

```bash
python -c "from backend.app import app; print('app ok')"
```

---

## Step 4 — Decouple Network Layer from Onboarding UI

**File to modify:** `frontend/js/engine/network.js`

Refactor `network.js` so it does not directly perform onboarding DOM
operations.

Add callback registration methods for character flow events, similar to
other event callback patterns:

```js
setCharacterFlowCallbacks({
  onSaveList,
  onNewPlayerInitialized,
  onCharacterCreated,
  onRacesList,
  onBackgroundsList,
  onCharacterFlowError,
});
```

`network.js` should only receive socket events and forward payloads to
registered callbacks. No UI creation/removal logic should remain there.

---

## Step 5 — Implement Default Modular Flow Modules

**New files:**

- `frontend/js/game/characterFlow/modules/saveSlotSelectModule.js`
- `frontend/js/game/characterFlow/modules/structuredCreatorModule.js`

**Files to modify:**

- `frontend/js/game/main.js`
- `frontend/index.html`

Implement two default modules to preserve current behavior while using
new modular architecture:

1. `saveSlotSelectModule` — handles save list display and player select.
2. `structuredCreatorModule` — handles the existing structured creator
   sequence (race -> background -> personality -> appearance -> items ->
   name -> summary).

In `main.js`:

- Initialize the character flow controller during startup.
- Register default modules.
- Activate initial module from config.
- Route character-flow socket events from `network.js` into
  `dispatchCharacterFlowEvent(...)`.

In `index.html`:

- Add script tags for new character-flow files.
- Remove direct legacy script dependency ordering assumptions.

---

## Step 6 — Remove Legacy Monolithic Files from Core Wiring

**Files to modify:**

- `frontend/index.html`
- `frontend/js/game/main.js`
- `frontend/js/game/playerSelect.js`
- `frontend/js/game/characterCreation.js`

Remove legacy coupling so core does not directly call legacy globals like
`showPlayerSelectionMenu()` or `initCharacterCreation()`.

Migration target:

- Either delete legacy files, or reduce them to compatibility shims that
  delegate into registered modules.
- No startup path may depend on direct legacy globals.
- No duplicated onboarding logic may exist in both legacy and modular
  files.

---

## Step 7 — Add Config-Driven Module Selection

**File to modify:** `config/game.json`

Add a character-flow config block, for example:

```json
"character_flow": {
  "enabled": true,
  "default_module": "save_slot_select",
  "modules": [
    "save_slot_select",
    "structured_creator"
  ]
}
```

Load this config in startup flow and use it to:

- determine which modules register
- select the initial active module
- allow future module replacement without startup code edits

---

## Step 8 — Verification and Cleanup

**Files to review:** all touched files

Verification checklist:

1. App imports successfully:
   ```bash
   python -c "from backend.app import app; print('app ok')"
   ```
2. Player select still works through modular flow.
3. Character creation still works through modular flow.
4. SocketIO events are forwarded via callback/controller flow, not direct
   onboarding UI code in `network.js`.
5. No remaining references to removed dead event path:
   `request_player_list` / `player_list`.
6. Legacy direct startup callsites are removed from `main.js`.

After verification, produce a concise migration summary listing:

- removed legacy coupling points
- new modular extension points
- remaining risks and follow-up tasks
