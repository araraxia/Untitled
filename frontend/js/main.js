/**
 * Main game entry point
 */

// Game contexts - determines what input actions do
const GameContext = {
    LOADING: 'loading',
    PLAYER_SELECT: 'player_select',
    MENU: 'menu',
    IN_GAME: 'in_game',
    INVENTORY: 'inventory',
    DIALOGUE: 'dialogue',
    PAUSED: 'paused'
};

// Game state
const gameState = {
    entities: {},
    player: null,
    selectedPlayerId: null, // Currently selected player ID
    camera: { x: 0, y: 0, zoom: 1 },
    worldSize: { width: 1000, height: 1000 },
    paused: false,
    context: GameContext.PLAYER_SELECT // Start with player selection
};

// Initialize game
/**
 * Initialize all game systems and start the game loop
 * @returns {Promise<void>}
 */
async function init() {
    console.log('[Main] Initializing game...');
    
    // Show loading indicator
    document.body.style.cursor = 'wait';
    
    // Initialize renderer (wait for it to load animations)
    await initRenderer();
    console.log('[Main] Renderer initialized');
    
    // Initialize network connection -> network.js
    initNetwork();
    console.log('[Main] Network connection initializing...');
    
    // Initialize input handlers
    initInput();
    console.log('[Main] Input handlers initialized');
    
    // Initialize UI
    initUI();
    console.log('[Main] UI initialized');
    
    // Show player selection menu
    showPlayerSelectionMenu();
    console.log('[Main] Player selection menu displayed');
    // Note: Render loop will start after player selection in loadGameState()
    
    // Reset cursor after initialization
    document.body.style.cursor = 'default';
}

// Handle initial state from server
/**
 * Process initial game state received from the server
 * Delegates to loadGameState in playerSelect.js
 * @param {Object} data - Initial state data from server
 * @returns {void}
 */
function handleInitialState(data) {
    loadGameState(data);
}

// Main render loop (60fps)
let lastFrameTime = null;
/**
 * Main render loop called by requestAnimationFrame
 * @param {number} timestamp - High-resolution timestamp from requestAnimationFrame
 * @returns {void}
 */
function renderLoop(timestamp) {
    // Initialize lastFrameTime on first frame
    if (lastFrameTime === null) {
        lastFrameTime = timestamp;
        requestAnimationFrame(renderLoop);
        return;
    }
    
    const deltaTime = (timestamp - lastFrameTime) / 1000; // seconds for interpolation
    const deltaTimeMs = timestamp - lastFrameTime; // milliseconds for animations
    lastFrameTime = timestamp;
    
    // If paused, render once and stop the loop
    if (gameState.paused) {
        render(gameState, 0);
        return; // Don't continue the loop
    }
    
    // Update interpolation
    updateInterpolation(deltaTime);
    
    // Render frame
    render(gameState, deltaTimeMs);
    
    // Continue loop
    requestAnimationFrame(renderLoop);
}

// Handle state updates from server
/**
 * Process state update delta from the server
 * @param {Object} data - State update data
 * @param {number} data.tick - Server tick number
 * @param {Object} data.delta - Changes to apply
 * @param {Object} [data.delta.entities] - Updated entity states
 * @param {string[]} [data.delta.removed] - Entity IDs to remove
 * @returns {void}
 */
function handleStateUpdate(data) {
    // Skip updates when paused
    if (gameState.paused) return;
    
    // Hide loading indicator once we receive first state
    const loadingIndicator = document.getElementById('loading-indicator');
    if (loadingIndicator) {
        loadingIndicator.style.display = 'none';
    }
    const { tick, delta } = data;
    
    // Update entities
    if (delta.entities) {
        for (const [entityId, entityData] of Object.entries(delta.entities)) {
            if (!gameState.entities[entityId]) {
                gameState.entities[entityId] = {};
            }
            
            // Store previous state for interpolation
            const entity = gameState.entities[entityId];
            entity.prevX = entity.x || entityData.x;
            entity.prevY = entity.y || entityData.y;
            
            // Ensure entity has required properties for animation system
            if (entityData.state === undefined) entityData.state = 'idle';
            if (entityData.facing === undefined && !entity.facing) entityData.facing = 'down';
            
            // Update with new state
            Object.assign(entity, entityData);
            
            // Track player
            if (entityId.startsWith('player_')) {
                gameState.player = entity;
                // Center camera on player
                gameState.camera.x = entity.x - (canvas.width / 2);
                gameState.camera.y = entity.y - (canvas.height / 2);
            }
        }
    }
    
    // Remove entities
    if (delta.removed) {
        for (const entityId of delta.removed) {
            delete gameState.entities[entityId];
        }
    }
    
    // Update UI
    updateUI(gameState);
}

// Start the game when page loads
window.addEventListener('load', init);
