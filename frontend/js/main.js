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
async function init() {
    console.log('Initializing game...');
    
    // Show loading indicator
    document.body.style.cursor = 'wait';
    
    // Initialize renderer (wait for it to load animations)
    await initRenderer();
    console.log('Renderer initialized');
    
    // Initialize network connection
    initNetwork();
    console.log('Network connection initializing...');
    
    // Initialize input handlers
    initInput();
    console.log('Input handlers initialized');
    
    // Initialize UI
    initUI();
    console.log('UI initialized');
    
    // Start render loop
    requestAnimationFrame(renderLoop);
    console.log('Game loop started');
    
    // Reset cursor after initialization
    document.body.style.cursor = 'default';
}

// Handle initial state from server
function handleInitialState(data) {
    console.log('Processing initial state...', data);
    
    // Hide loading indicator
    const loadingIndicator = document.getElementById('loading-indicator');
    if (loadingIndicator) {
        loadingIndicator.style.display = 'none';
    }
    
    // Set up the game world
    if (data.world) {
        gameState.worldSize = data.world;
    }
    
    // Initialize all entities
    if (data.entities) {
        gameState.entities = {};
        for (const [entityId, entityData] of Object.entries(data.entities)) {
            // Ensure entity has required properties for animation system
            if (!entityData.state) entityData.state = 'idle';
            if (!entityData.facing) entityData.facing = 'down';
            
            gameState.entities[entityId] = entityData;
            
            // Find the player entity
            if (entityData.type === 'player') {
                gameState.player = entityData;
                // Center camera on player
                gameState.camera.x = entityData.x - (window.innerWidth / 2);
                gameState.camera.y = entityData.y - (window.innerHeight / 2);
            }
            
            // Initialize interpolation for this entity
            initEntityInterpolation(entityId, entityData);
        }
    }
    
    console.log('Initial state processed. Entities:', Object.keys(gameState.entities).length);
}

// Main render loop (60fps)
let lastFrameTime = 0;
function renderLoop(timestamp) {
    const deltaTime = (timestamp - lastFrameTime) / 1000; // seconds for interpolation
    const deltaTimeMs = timestamp - lastFrameTime; // milliseconds for animations
    lastFrameTime = timestamp;
    
    // Update interpolation
    updateInterpolation(deltaTime);
    
    // Render frame (pass milliseconds for animation system)
    render(gameState, deltaTimeMs);
    
    // Continue loop
    requestAnimationFrame(renderLoop);
}

// Handle state updates from server
function handleStateUpdate(data) {
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
