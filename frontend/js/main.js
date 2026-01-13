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
    
    // Initialize network connection
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
    
    // Start render loop
    requestAnimationFrame(renderLoop);
    console.log('[Main] Game loop started');
    
    // Reset cursor after initialization
    document.body.style.cursor = 'default';
}

/**
 * Show player selection menu and request available players from server
 * @returns {void}
 */
function showPlayerSelectionMenu() {
    gameState.context = GameContext.PLAYER_SELECT;
    
    // Create menu overlay
    const menuOverlay = document.createElement('div');
    menuOverlay.id = 'player-select-menu';
    menuOverlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.9);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 1000;
    `;
    
    const menuContainer = document.createElement('div');
    menuContainer.style.cssText = `
        background: #2a2a2a;
        border: 2px solid #4CAF50;
        border-radius: 8px;
        padding: 30px;
        max-width: 500px;
        width: 90%;
        color: #fff;
    `;
    
    menuContainer.innerHTML = `
        <h2 style="margin: 0 0 20px 0; text-align: center; color: #4CAF50;">Select Player</h2>
        <div id="player-list" style="margin-bottom: 20px;">
            <p style="text-align: center; color: #888;">Loading players...</p>
        </div>
        <button id="new-player-btn" style="
            width: 100%;
            padding: 10px;
            background: #4CAF50;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
            margin-top: 10px;
        ">Create New Player</button>
    `;
    
    menuOverlay.appendChild(menuContainer);
    document.body.appendChild(menuOverlay);
    
    // Request available players from server
    if (window.socket && window.socket.connected) {
        window.socket.emit('request_player_list');
    }
    
    // Set up new player button
    document.getElementById('new-player-btn').addEventListener('click', () => {
        selectPlayer('00000000-0000-0000-0000-000000000000'); // Default player ID
    });
}

/**
 * Populate player list with available players
 * @param {Array<Object>} players - List of player data
 * @returns {void}
 */
function populatePlayerList(players) {
    const playerList = document.getElementById('player-list');
    if (!playerList) return;
    
    if (!players || players.length === 0) {
        playerList.innerHTML = '<p style="text-align: center; color: #888;">No saved players found</p>';
        return;
    }
    
    playerList.innerHTML = '';
    
    players.forEach(player => {
        const playerItem = document.createElement('div');
        playerItem.style.cssText = `
            padding: 15px;
            margin-bottom: 10px;
            background: #333;
            border: 1px solid #555;
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.2s;
        `;
        
        playerItem.innerHTML = `
            <div style="font-weight: bold; margin-bottom: 5px;">${player.player_id}</div>
            <div style="font-size: 12px; color: #aaa;">
                Entities Controlled: ${player.controlled_entity_ids ? player.controlled_entity_ids.length : 0}
            </div>
        `;
        
        playerItem.addEventListener('mouseenter', () => {
            playerItem.style.background = '#444';
            playerItem.style.borderColor = '#4CAF50';
        });
        
        playerItem.addEventListener('mouseleave', () => {
            playerItem.style.background = '#333';
            playerItem.style.borderColor = '#555';
        });
        
        playerItem.addEventListener('click', () => {
            selectPlayer(player.player_id);
        });
        
        playerList.appendChild(playerItem);
    });
}

/**
 * Select a player and load their controlled entities
 * @param {string} playerId - The player ID to load
 * @returns {void}
 */
function selectPlayer(playerId) {
    console.log('[Main] Player selected:', playerId);
    gameState.selectedPlayerId = playerId;
    
    // Remove menu
    const menu = document.getElementById('player-select-menu');
    if (menu) {
        menu.remove();
    }
    
    // Request player data and controlled entities from server
    if (window.socket && window.socket.connected) {
        window.socket.emit('load_player', { player_id: playerId });
    }
    
    gameState.context = GameContext.LOADING;
}

// Handle initial state from server
/**
 * Process initial game state received from the server
 * @param {Object} data - Initial state data from server
 * @param {Object} [data.world] - World size configuration
 * @param {Object} [data.entities] - Initial entity states
 * @param {string} [data.player_id] - Loaded player ID
 * @param {string[]} [data.controlled_entity_ids] - IDs of entities controlled by player
 * @returns {void}
 */
function handleInitialState(data) {
    console.log('[Main] Processing initial state...', data);
    
    // Hide loading indicator
    const loadingIndicator = document.getElementById('loading-indicator');
    if (loadingIndicator) {
        loadingIndicator.style.display = 'none';
    }
    
    // Set up the game world
    if (data.world) {
        gameState.worldSize = data.world;
    }
    
    // Store player info
    if (data.player_id) {
        gameState.selectedPlayerId = data.player_id;
    }
    
    // Initialize all entities
    if (data.entities) {
        gameState.entities = {};
        for (const [entityId, entityData] of Object.entries(data.entities)) {
            // Ensure entity has required properties for animation system
            if (!entityData.state) entityData.state = 'idle';
            if (!entityData.facing) entityData.facing = 'down';
            
            gameState.entities[entityId] = entityData;
            
            // Find the first controlled entity as the primary focus
            if (data.controlled_entity_ids && data.controlled_entity_ids.includes(entityId)) {
                if (!gameState.player) {
                    gameState.player = entityData;
                    // Center camera on first controlled entity
                    gameState.camera.x = entityData.x - (window.innerWidth / 2);
                    gameState.camera.y = entityData.y - (window.innerHeight / 2);
                }
            }
            // Fallback to player type
            else if (entityData.type === 'player' && !gameState.player) {
                gameState.player = entityData;
                // Center camera on player
                gameState.camera.x = entityData.x - (window.innerWidth / 2);
                gameState.camera.y = entityData.y - (window.innerHeight / 2);
            }
            
            // Initialize interpolation for this entity
            initEntityInterpolation(entityId, entityData);
        }
    }
    
    // Switch to in-game context
    gameState.context = GameContext.IN_GAME;
    
    console.log('[Main] Initial state processed. Entities:', Object.keys(gameState.entities).length);
    console.log('[Main] Controlled entities:', data.controlled_entity_ids);
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
