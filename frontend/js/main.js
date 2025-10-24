/**
 * Main game entry point
 */

// Game state
const gameState = {
    entities: {},
    player: null,
    camera: { x: 0, y: 0, zoom: 1 },
    worldSize: { width: 1000, height: 1000 }
};

// Initialize game
function init() {
    console.log('Initializing game...');
    
    // Initialize renderer
    initRenderer();
    
    // Initialize network connection
    initNetwork();
    
    // Initialize input handlers
    initInput();
    
    // Initialize UI
    initUI();
    
    // Start render loop
    requestAnimationFrame(renderLoop);
}

// Main render loop (60fps)
let lastFrameTime = 0;
function renderLoop(timestamp) {
    const deltaTime = (timestamp - lastFrameTime) / 1000;
    lastFrameTime = timestamp;
    
    // Update interpolation
    updateInterpolation(deltaTime);
    
    // Render frame
    render(gameState, deltaTime);
    
    // Continue loop
    requestAnimationFrame(renderLoop);
}

// Handle state updates from server
function handleStateUpdate(data) {
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
