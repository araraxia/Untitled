---
agent: agent
description: Implement the data-driven UI framework that renders over the WebGPU canvas (Phase 7 of ROADMAP.md). Covers HUD renderer, UI component system, theme loading, inventory panel, and dialogue box.
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

# Task: UI Framework (Phase 7)

You are implementing the UI framework for this project. This is Phase 7
of `ROADMAP.md`. Phase 3 (ECS Overhaul) and Phase 5 (Asset Pipeline)
are prerequisites and are complete.

Complete all steps in order. Each step must leave the application in a
runnable state before proceeding to the next.

---

## Required Reading

Read these files before writing any code:

- `ROADMAP.md` — Phase 7 specification (sections 7.1–7.3)
- `frontend/index.html` — page structure; note `#overlay-canvas` and
  `#ui-overlay`; new UI scripts will be added here
- `frontend/js/engine/renderer.js` — `overlayCanvas` and `ctx` variables;
  the overlay Canvas 2D context is already initialised here; understand
  how the render loop calls into the HUD before wiring `HUDRenderer`
- `frontend/js/game/ui.js` — existing DOM-based UI helpers (`updateUI`,
  `updatePartyPanel`, `showCommandMenu`); these will be migrated to the
  new system incrementally — do not delete them until the new system
  replaces their functionality
- `frontend/js/game/main.js` — `GameContext` enum, `gameState`, `initUI()`
  call, render loop wiring; all new UI modules must initialise through
  `initUI()` and update through `gameState`
- `frontend/js/engine/assetLoader.js` — `AssetLoader`; theme JSON will
  be loaded through it using the manifest system
- `frontend/assets/manifest.json` — current asset registry; new entries
  for the theme JSON file will be added here
- `frontend/css/style.css` — existing styles; do not replicate layout
  logic in CSS that will be owned by the JS layout engine
- `config/engine.json` — runtime config; `ui_theme_asset` key will be
  added here

---

## Constraints

- Follow the Airbnb JavaScript style guide for all JS: 2-space indent,
  single quotes, semicolons.
- All new JS classes and public functions must have JSDoc comments.
- No DOM manipulation inside the HUD render path. All HUD drawing must
  go through the overlay Canvas 2D context (`overlayCanvas` / `ctx`
  in `renderer.js`). DOM nodes are only permitted for `InventoryPanel`
  and `DialogueBox` (which are modal overlays sitting in `#ui-overlay`).
- The layout engine must be pure JS — no CSS flexbox, no HTML elements
  for layout. Positions and sizes are computed in JS and drawn with
  Canvas 2D primitives.
- Theme data is loaded from a JSON asset via `AssetLoader`; hard-coded
  colour or font values are not permitted in any new file.
- `UIComponent` z-order must be respected: components with higher
  `zOrder` values are drawn on top.
- All SocketIO event handlers for UI data (`inventory_update`,
  `dialogue_start`, `dialogue_end`) must be registered in
  `frontend/js/engine/network.js` and dispatch to registered callbacks.
  Do not add `socket.on(...)` calls directly inside UI files.
- File naming: new JS files use camelCase (`hudRenderer.js`,
  `uiComponent.js`, etc.).
- Run `python -c "from backend.app import app; print('app ok')"` after
  any Python changes to confirm no import errors.

---

## Step 1 — Audit Current State

Before writing any code, read the key files listed above and produce a
short summary covering:

1. How `overlayCanvas` is currently created and sized in `renderer.js`,
   and whether there is already any drawing code targeting it.
2. What `initUI()` in `ui.js` currently does (or does not do), and which
   DOM elements it relies on.
3. What game-state data flows into `updateUI()` today, and what fields
   are used.
4. What SocketIO events in `network.js` are currently registered, and
   which (if any) carry inventory or dialogue payloads.
5. What entries currently exist in `manifest.json`, and the schema used
   for each entry.
6. Which `GameContext` values in `main.js` already have handling logic
   and which (`INVENTORY`, `DIALOGUE`) do not.

Do not create or edit any files in this step. Output findings, then
proceed.

---

## Step 2 — Theme Asset (Phase 7.2 prerequisite)

**Files to modify:** `config/engine.json`,
`frontend/assets/manifest.json`  
**New file:** `frontend/assets/data/ui_theme.json`

### `frontend/assets/data/ui_theme.json`

Create the default theme file. It must contain at minimum:

```json
{
  "colors": {
    "background": "#1a1a2e",
    "surface": "#16213e",
    "border": "#0f3460",
    "accent": "#e94560",
    "text": "#eaeaea",
    "textMuted": "#888888",
    "healthFull": "#4caf50",
    "healthLow": "#f44336",
    "apFull": "#2196f3",
    "apLow": "#9c27b0"
  },
  "fonts": {
    "body": "16px 'Press Start 2P', monospace",
    "small": "12px 'Press Start 2P', monospace",
    "large": "20px 'Press Start 2P', monospace",
    "tooltip": "11px 'Press Start 2P', monospace"
  },
  "layout": {
    "padding": 8,
    "borderWidth": 2,
    "cornerRadius": 4,
    "hudMargin": 12
  }
}
```

### `config/engine.json`

Add:

```json
"ui_theme_asset": "ui_theme"
```

### `frontend/assets/manifest.json`

Register the theme as a data asset using the same schema as existing
entries. The logical asset ID must be `"ui_theme"` and the path must
point to `assets/data/ui_theme.json`.

---

## Step 3 — HUD Renderer (Phase 7.1)

**New file:** `frontend/js/engine/hudRenderer.js`  
**Files to modify:** `frontend/index.html`, `frontend/js/engine/renderer.js`,
`frontend/js/game/main.js`

### `frontend/js/engine/hudRenderer.js`

```js
/**
 * HUDRenderer — draws all 2-D HUD elements onto the overlay canvas
 * once per render frame using Canvas 2D.
 *
 * Usage:
 *   const hud = new HUDRenderer(overlayCanvas, theme);
 *   // each frame:
 *   hud.update(gameState);
 *   hud.draw();
 */
```

The class must expose:

```js
class HUDRenderer {
  /**
   * @param {HTMLCanvasElement} canvas - The overlay canvas element.
   * @param {object} theme - Parsed ui_theme.json object.
   */
  constructor(canvas, theme) { ... }

  /**
   * Sync HUD state from the current game state snapshot.
   * Call once per frame before draw().
   * @param {object} gameState
   */
  update(gameState) { ... }

  /**
   * Draw all HUD elements onto the overlay canvas.
   * Clears the canvas first, then draws in z-order.
   */
  draw() { ... }
}
```

Initial HUD elements to implement (drawn with Canvas 2D, no DOM):

- **HP bar** — labelled `HP`, fills left→right using `healthFull` /
  `healthLow` colour based on `hp / max_hp` ratio (low = below 0.3)
- **AP bar** — labelled `AP`, same style using `apFull` / `apLow`
- **Party indicators** — one small icon row per party member showing
  name and HP ratio; click hit-testing is not required in this step

Position all elements relative to `canvas.width` / `canvas.height` so
the HUD reflows when the window resizes. Use the `hudMargin` and
`padding` values from the theme `layout` block.

### Wiring into the render loop

In `renderer.js`, after the WebGPU (or Canvas 2D fallback) draw call,
call `hudRenderer.draw()` if a module-level `hudRenderer` variable is
set. Expose a `setHUDRenderer(instance)` function so `main.js` can
inject it.

### Wiring into `main.js`

In `initUI()` (or a new `initHUD()` called from `initUI()`):

1. Load the theme via `AssetLoader` using the asset ID from
   `engine.json`'s `ui_theme_asset`.
2. Instantiate `HUDRenderer` with the overlay canvas and loaded theme.
3. Call `setHUDRenderer(hudInstance)`.

Call `hudRenderer.update(gameState)` from the existing `gameState`
update path (wherever `updateUI(gameState)` is currently called).

### `frontend/index.html`

Add the script tag for `hudRenderer.js` in the Engine section, before
`renderer.js`.

### Verify

Open the application and confirm the HP bar and AP bar appear on the
overlay canvas above the game world. No console errors.

---

## Step 4 — UI Component System (Phase 7.2)

**New file:** `frontend/js/engine/uiComponent.js`  
**Files to modify:** `frontend/index.html`

### `frontend/js/engine/uiComponent.js`

Implement the following class hierarchy. All classes live in this single
file.

#### `UIComponent` (base)

```js
class UIComponent {
  /**
   * @param {object} opts
   * @param {number} opts.x
   * @param {number} opts.y
   * @param {number} opts.width
   * @param {number} opts.height
   * @param {boolean} [opts.visible=true]
   * @param {number}  [opts.zOrder=0]
   */
  constructor(opts) { ... }

  /** Compute child layout. Override in containers. */
  layout() {}

  /**
   * Draw this component onto ctx.
   * @param {CanvasRenderingContext2D} ctx
   * @param {object} theme
   */
  draw(ctx, theme) {}

  /**
   * Hit-test a point. Returns true if (px, py) is inside this component.
   * @param {number} px
   * @param {number} py
   * @returns {boolean}
   */
  contains(px, py) { ... }
}
```

#### Leaf components

| Class         | Description                                                                                                                                                                                                                                                                                                    |
| ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Label`       | Draws a text string. Supports `text`, `font` (theme key), `color` (theme key), `align` (`'left'` / `'center'` / `'right'`).                                                                                                                                                                                    |
| `ProgressBar` | Draws a filled bar. Supports `value` (0–1), `fillColor` (theme key), `bgColor` (theme key), `label` (optional overlay text).                                                                                                                                                                                   |
| `Icon`        | Draws a sprite frame from a loaded `GPUSpriteSheet` (or a placeholder rect if the sheet is not available). Supports `assetId`, `frame`.                                                                                                                                                                        |
| `Button`      | A `Panel` with a `Label` child. Fires an `onClick` callback. Supports `label`, `onClick`.                                                                                                                                                                                                                      |
| `Panel`       | A rectangular container. Supports `children: UIComponent[]`, `direction` (`'row'` / `'column'`), `gap`, `padding`. Implements a simple flexbox-inspired layout in `layout()`: distributes children along `direction` with `gap` spacing, offsetting each child's `x`/`y` relative to the panel's own position. |

#### `UIManager`

```js
class UIManager {
  constructor() { ... }

  /**
   * Register a root-level component.
   * @param {UIComponent} component
   */
  add(component) { ... }

  /**
   * Remove a root-level component.
   * @param {UIComponent} component
   */
  remove(component) { ... }

  /**
   * Draw all registered components sorted by zOrder (ascending).
   * @param {CanvasRenderingContext2D} ctx
   * @param {object} theme
   */
  draw(ctx, theme) { ... }

  /**
   * Forward a pointer event to the topmost component whose hit-test passes.
   * @param {'click'|'mousemove'} type
   * @param {number} x
   * @param {number} y
   */
  handlePointer(type, x, y) { ... }
}
```

Expose a module-level singleton: `const uiManager = new UIManager();`

### Integrate with `HUDRenderer`

Refactor the HP bar, AP bar, and party indicators from Step 3 to use
`ProgressBar`, `Label`, and `Panel` components registered on `uiManager`
rather than raw Canvas 2D calls in `HUDRenderer.draw()`.

`HUDRenderer.draw()` should now call `uiManager.draw(ctx, theme)`.

`HUDRenderer.update()` should update the `value` and `text` properties
on the existing component instances rather than recreating them each
frame.

### `frontend/index.html`

Add the script tag for `uiComponent.js` before `hudRenderer.js`.

---

## Step 5 — Inventory Panel (Phase 7.3)

**New file:** `frontend/js/game/inventoryPanel.js`  
**Files to modify:** `frontend/js/engine/network.js`,
`frontend/js/game/main.js`, `frontend/index.html`

### `frontend/js/game/inventoryPanel.js`

The inventory panel is a DOM overlay (inside `#ui-overlay`) displayed
when `gameState.context === GameContext.INVENTORY`.

```js
/**
 * InventoryPanel — DOM-based modal overlay for the player inventory.
 *
 * Data contract (received via SocketIO `inventory_update` event):
 * {
 *   items: Array<{
 *     id:       string,
 *     name:     string,
 *     icon:     string,   // asset ID
 *     quantity: number,
 *     slot:     number    // 0-based grid index
 *   }>
 * }
 */
```

Requirements:

- Grid layout: 5 columns × N rows, each cell 64 × 64 px. Cell count is
  fixed at 40 (5 × 8); empty cells render as styled empty slots.
- Each occupied cell shows the item icon (an `<img>` whose `src` is
  resolved via `AssetLoader`) and a quantity badge if `quantity > 1`.
- Hovering a cell shows a tooltip (`<div class="ui-tooltip">`) with
  `name` and any additional fields present in the payload.
- Clicking a cell fires an `item_use` SocketIO event with `{ item_id }`.
- Drag-and-drop between cells: on `dragend`, emit `item_move` with
  `{ item_id, from_slot, to_slot }` to the server.
- Opening / closing is controlled by `show()` / `hide()` methods.
  `hide()` must set `gameState.context` back to `GameContext.IN_GAME`.

### SocketIO events

In `network.js`, register:

```js
socket.on("inventory_update", (data) => {
  if (onInventoryUpdate) onInventoryUpdate(data);
});
```

Expose `setInventoryUpdateCallback(fn)` so `inventoryPanel.js` can
register its handler without touching `network.js` internals.

### Wiring into `main.js`

- Instantiate `InventoryPanel` in `initUI()` and assign to a module-level
  `inventoryPanel` variable.
- In the keyboard input handler (in `input.js` or `main.js`), toggle
  `inventoryPanel.show()` / `inventoryPanel.hide()` on the `I` key when
  `context` is `IN_GAME` or `INVENTORY`.
- Set `gameState.context = GameContext.INVENTORY` when the panel opens.

### `frontend/index.html`

Add the script tag for `inventoryPanel.js` after `ui.js`.

---

## Step 6 — Dialogue Box (Phase 7.3)

**New file:** `frontend/js/game/dialogueBox.js`  
**Files to modify:** `frontend/js/engine/network.js`,
`frontend/js/game/main.js`, `frontend/index.html`

### Dialogue script format

Dialogue trees are delivered from the server as JSON. Define the schema
as follows and document it in a comment at the top of `dialogueBox.js`:

```json
{
  "id": "npc_merchant_01",
  "nodes": {
    "start": {
      "speaker": "Merchant",
      "text": "Welcome, traveller. What do you need?",
      "choices": [
        { "label": "Show me your wares.", "next": "shop" },
        { "label": "Nevermind.", "next": null }
      ]
    },
    "shop": {
      "speaker": "Merchant",
      "text": "Ah, take a look!",
      "choices": []
    }
  }
}
```

A `next` value of `null` closes the dialogue. A node with an empty
`choices` array also closes the dialogue after the player dismisses it
(press `Enter` or `Space`).

### `frontend/js/game/dialogueBox.js`

The dialogue box is a DOM overlay (inside `#ui-overlay`).

Requirements:

- Displays the current node's `speaker` name and `text`.
- Renders each choice as a button; clicking or pressing the number key
  (1–4) selects it.
  - Selecting a choice emits a `dialogue_choice` SocketIO event with
    `{ dialogue_id, choice_index }`, then advances to `next` locally.
  - If `next` is `null`, call `hide()`.
- Text advances with a typewriter effect (character-by-character reveal
  at a configurable WPM; default 300 WPM). Pressing `Enter` or `Space`
  skips to the full text instantly.
- `show(scriptData)` opens the box at node `"start"`.
- `hide()` removes the overlay and sets `gameState.context` back to
  `GameContext.IN_GAME`.

### SocketIO events

In `network.js`, register:

```js
socket.on("dialogue_start", (data) => {
  if (onDialogueStart) onDialogueStart(data);
});
socket.on("dialogue_end", () => {
  if (onDialogueEnd) onDialogueEnd();
});
```

Expose `setDialogueStartCallback(fn)` and `setDialogueEndCallback(fn)`.

### Wiring into `main.js`

Instantiate `DialogueBox` in `initUI()`. Register it as the
`onDialogueStart` callback via `setDialogueStartCallback`. Set
`gameState.context = GameContext.DIALOGUE` when dialogue opens.

### `frontend/index.html`

Add the script tag for `dialogueBox.js` after `inventoryPanel.js`.

---

## Step 7 — Backend SocketIO Events

**File to modify:** `backend/app.py`

Add the following SocketIO event handlers. These are stubs that emit
test payloads for frontend development; they will be replaced with real
game data in a later phase.

```python
@socketio.on('item_use')
def handle_item_use(data):
    """Handle player using an item from inventory."""
    ...

@socketio.on('item_move')
def handle_item_move(data):
    """Handle player moving an item between inventory slots."""
    ...

@socketio.on('dialogue_choice')
def handle_dialogue_choice(data):
    """Handle player making a dialogue choice."""
    ...
```

Also add a debug-only `send_test_inventory` event that emits a
hard-coded `inventory_update` payload (5 test items across different
slots) so the frontend inventory panel can be exercised without a full
game session.

Verify:

```bash
python -c "from backend.app import app; print('app ok')"
```

---

## Step 8 — ROADMAP Update

**File to modify:** `ROADMAP.md`

Mark Phase 7 as complete in the phase progress table and add the prompt
file reference at the bottom of the Phase 7 section:

```text
**Prompt file:** `.github/prompts/ui-framework.prompt.md`
```
