/**
 * Dual input system: Keyboard for player, mouse for party
 */

/** @type {Object.<string, boolean>} */
const keys = {};
/** @type {number} */
let mouseX = 0;
/** @type {number} */
let mouseY = 0;
/** @type {string|null} */
let selectedPartyMember = null;
/** @type {Object|null} */
let keyConfig = null;

/**
 * Initialize input handlers for keyboard and mouse
 * Sets up event listeners for:
 * - Keyboard: Configurable keys for player movement and actions
 * - Mouse: Click to select entities, right-click for context menu
 * - Starts input processing loop at configurable rate
 * @returns {Promise<void>}
 */
async function initInput() {
    // Load key configuration
    await loadKeyConfig();
    
    // Keyboard input for player character
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    
    // Mouse input for party commands
    canvas.addEventListener('mousemove', handleMouseMove);
    canvas.addEventListener('mousedown', handleMouseDown);
    canvas.addEventListener('contextmenu', handleContextMenu);
    
    // Start input processing loop with configured rate
    const pollingRate = keyConfig?.settings?.inputPollingRate || 16;
    setInterval(processInput, pollingRate);
    
    console.log('[Input] Input initialized with config:', keyConfig);
}

/**
 * Load key configuration from JSON file
 * @returns {Promise<void>}
 */
async function loadKeyConfig() {
    try {
        const response = await fetch('assets/data/input_config.json');
        keyConfig = await response.json();
        console.log('[Input] Key configuration loaded:', keyConfig);
    } catch (error) {
        console.error('[Input] Failed to load key config, using defaults:', error);
        // Fallback to default configuration
        keyConfig = {
            movement: {
                up: ['w', 'arrowup'],
                down: ['s', 'arrowdown'],
                left: ['a', 'arrowleft'],
                right: ['d', 'arrowright']
            },
            actions: {
                interact: ['e'],
                inventory: ['i', 'tab'],
                menu: ['escape']
            },
            mouse: {
                select: 0,
                contextMenu: 2
            },
            settings: {
                inputPollingRate: 16
            }
        };
    }
}

/**
 * Check if any of the configured keys for an action are pressed
 * @param {string} action - Action name (e.g., 'up', 'down', 'left', 'right')
 * @param {string} category - Category of action (default: 'movement')
 * @returns {boolean} True if any key for this action is pressed
 */
function isActionPressed(action, category = 'movement') {

    // Exit early if config is missing
    if (!keyConfig || !keyConfig[category] || !keyConfig[category][action]) {
        return false;
    }
    
    const actionKeys = keyConfig[category][action];
    return actionKeys.some(key => keys[key.toLowerCase()]);
}

/**
 * Toggle debug pause state
 * Pauses/unpauses the game loop and server updates
 * Can be expanded with additional debug features
 * @returns {void}
 */
function toggleDebugPause() {
    const wasPaused = gameState.paused;
    gameState.paused = !gameState.paused;
    
    // Update context based on pause state
    if (gameState.paused) {
        gameState.previousContext = gameState.context;
        gameState.context = GameContext.PAUSED;
    } else {
        gameState.context = gameState.previousContext || GameContext.IN_GAME;
    }
    
    console.log(`[Input] Game ${gameState.paused ? 'PAUSED' : 'RESUMED'} - Context: ${gameState.context}`);
    
    // If unpausing, restart the render loop
    if (wasPaused && !gameState.paused) {
        lastFrameTime = performance.now(); // Reset to current time to avoid delta jump
        requestAnimationFrame(renderLoop);
    }
}

/**
 * Handle keyboard key press events
 * @param {KeyboardEvent} e - Keyboard event
 * @returns {void}
 */
function handleKeyDown(e) {
    const key = e.key.toLowerCase();
    
    // Check for pause toggle (only trigger once per key press)
    if (!keys[key] && keyConfig?.actions?.pause?.includes(key)) {
        toggleDebugPause();
    }
    
    keys[key] = true;
}

/**
 * Handle keyboard key release events
 * @param {KeyboardEvent} e - Keyboard event
 * @returns {void}
 */
function handleKeyUp(e) {
    keys[e.key.toLowerCase()] = false;
}

/**
 * Handle mouse movement and track cursor position
 * @param {MouseEvent} e - Mouse event
 * @returns {void}
 */
function handleMouseMove(e) {
    const rect = canvas.getBoundingClientRect();
    mouseX = e.clientX - rect.left;
    mouseY = e.clientY - rect.top;
}

/**
 * Handle mouse button press events
 * Left-click selects entities within 16 pixels of cursor
 * @param {MouseEvent} e - Mouse event
 * @returns {void}
 */
function handleMouseDown(e) {
    if (e.button === 0) { // Left click
        // Select entity at mouse position
        const worldX = mouseX + gameState.camera.x;
        const worldY = mouseY + gameState.camera.y;
        
        for (const [entityId, entity] of Object.entries(gameState.entities)) {
            const dx = entity.x - worldX;
            const dy = entity.y - worldY;
            const distance = Math.sqrt(dx * dx + dy * dy);
            
            if (distance < 16) {
                selectedPartyMember = entityId;
                console.log('Selected:', entityId);
                break;
            }
        }
    }
}

/**
 * Handle right-click context menu for party commands
 * @param {MouseEvent} e - Mouse event
 * @returns {void}
 */
function handleContextMenu(e) {
    e.preventDefault();
    
    if (selectedPartyMember) {
        showCommandMenu(e.clientX, e.clientY, selectedPartyMember);
    }
}

/**
 * Process keyboard input and send movement commands
 * Called at configured polling rate to check key states and send player actions
 * Handles configurable keys for 8-directional movement
 * @returns {void}
 */
function processInput() {
    if (!keyConfig) return; // Wait for config to load
    if (gameState.paused) return; // Don't process input when paused
    
    // Handle input based on current context
    switch (gameState.context) {
        case GameContext.IN_GAME:
            processGameplayInput();
            break;
        case GameContext.MENU:
            processMenuInput();
            break;
        case GameContext.INVENTORY:
            processInventoryInput();
            break;
        case GameContext.DIALOGUE:
            processDialogueInput();
            break;
        case GameContext.PAUSED:
            // No input processing while paused
            break;
        default:
            break;
    }
}

/**
 * Process input for gameplay context
 * @returns {void}
 */
function processGameplayInput() {
    // Process keyboard input for player movement
    let dx = 0;
    let dy = 0;
    
    if (isActionPressed('up')) dy -= 1;
    if (isActionPressed('down')) dy += 1;
    if (isActionPressed('left')) dx -= 1;
    if (isActionPressed('right')) dx += 1;
    
    // Normalize diagonal movement
    if (dx !== 0 && dy !== 0) {
        dx *= 0.707;
        dy *= 0.707;
    }
    
    // Determine facing direction for animation
    let facing = null;
    if (dy < 0) facing = 'up';
    else if (dy > 0) facing = 'down';
    else if (dx < 0) facing = 'left';
    else if (dx > 0) facing = 'right';
    
    // Send movement command if moving
    if (dx !== 0 || dy !== 0) {
        sendPlayerAction('move', {
            direction: { x: dx, y: dy },
            facing: facing // Include facing direction for animation
        });
    } else {
        // Stop moving - keep last facing direction
        sendPlayerAction('move', {
            direction: { x: 0, y: 0 }
        });
    }
}

/**
 * Process input for menu context
 * @returns {void}
 */
function processMenuInput() {
    // TODO: Implement menu navigation
    // Arrow keys for navigation, Enter to select, Escape to close
}

/**
 * Process input for inventory context
 * @returns {void}
 */
function processInventoryInput() {
    // TODO: Implement inventory navigation
    // Arrow keys for item selection, E to use, Escape to close
}

/**
 * Process input for dialogue context
 * @returns {void}
 */
function processDialogueInput() {
    // TODO: Implement dialogue options
    // Number keys or arrow keys to select dialogue options, Enter to confirm
}
