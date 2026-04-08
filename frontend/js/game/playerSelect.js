/**
 * Player selection and game state management
 */

/**
 * Show player selection menu and request available players from server
 * @returns {void}
 */
function showPlayerSelectionMenu() {
    console.log('[PlayerSelect] Displaying player selection menu');
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
    
    // Display menu
    menuOverlay.appendChild(menuContainer);
    document.body.appendChild(menuOverlay);
    
    // Player list will be requested automatically when socket connects (see network.js)
    // If already connected, request now
    if (window.socket && window.socket.connected) {
        console.debug('[PlayerSelect] Socket already connected, requesting player list now');
        window.socket.emit('request_player_list');
    } else {
        console.debug('[PlayerSelect] Waiting for socket connection to request player list');
    }
    
    // Set up new player button
    document.getElementById('new-player-btn').addEventListener('click', () => {
        createNewPlayer();
    });
}

function createNewPlayer() {
    console.log('[PlayerSelect] Creating new player');
    // Create input dialog
    const inputDialog = document.createElement('div');
    inputDialog.style.cssText = `
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        background: #2a2a2a;
        border: 2px solid #4CAF50;
        border-radius: 8px;
        padding: 20px;
        z-index: 1001;
        min-width: 300px;
    `;
    
    inputDialog.innerHTML = `
        <h3 style="margin: 0 0 15px 0; color: #4CAF50;">New Player</h3>
        <input type="text" id="player-name-input" placeholder="Enter player name" style="
            width: 100%;
            padding: 10px;
            margin-bottom: 15px;
            background: #333;
            border: 1px solid #555;
            border-radius: 4px;
            color: #fff;
            font-size: 14px;
            box-sizing: border-box;
        ">
        <div style="display: flex; gap: 10px;">
            <button id="create-confirm-btn" style="
                flex: 1;
                padding: 10px;
                background: #4CAF50;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
            ">Create</button>
            <button id="create-cancel-btn" style="
                flex: 1;
                padding: 10px;
                background: #666;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
            ">Cancel</button>
        </div>
    `;
    
    document.body.appendChild(inputDialog);
    
    const input = document.getElementById('player-name-input');
    input.focus();
    
    const submitName = () => {
        const playerName = input.value.trim();
        if (playerName) {
            console.log('[PlayerSelect] Creating new player:', playerName);
            if (window.socket && window.socket.connected) {
                window.socket.emit('new_player', { player_id: playerName });
            }
            inputDialog.remove();
        }
    };
    
    document.getElementById('create-confirm-btn').addEventListener('click', submitName);
    document.getElementById('create-cancel-btn').addEventListener('click', () => {
        inputDialog.remove();
    });
    
    input.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            submitName();
        }
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
            position: relative;
        `;
        
        playerItem.innerHTML = `
            <div style="font-weight: bold; margin-bottom: 5px;">${player.player_id}</div>
            <div style="font-size: 12px; color: #aaa;">
                Entities Controlled: ${player.controlled_entity_ids ? player.controlled_entity_ids.length : 0}
            </div>
            <button class="delete-player-btn" data-player-id="${player.player_id}" style="
                position: absolute;
                top: 10px;
                right: 10px;
                padding: 5px 10px;
                background: #d32f2f;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 12px;
                transition: background 0.2s;
            ">Delete</button>
        `;
        
        const deleteBtn = playerItem.querySelector('.delete-player-btn');
        
        // Delete button hover
        deleteBtn.addEventListener('mouseenter', (e) => {
            e.stopPropagation();
            deleteBtn.style.background = '#b71c1c';
        });
        
        deleteBtn.addEventListener('mouseleave', (e) => {
            e.stopPropagation();
            deleteBtn.style.background = '#d32f2f';
        });
        
        // Delete button click
        deleteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            deletePlayer(player.player_id);
        });
        
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
 * Select a player and request their game state from server
 * @param {string} playerId - The player ID to load
 * @returns {void}
 */
function selectPlayer(playerId) {
    console.log('[PlayerSelect] Player selected:', playerId);
    gameState.selectedPlayerId = playerId;
    
    // Remove menu
    const menu = document.getElementById('player-select-menu');
    if (menu) {
        menu.remove();
    }
    
    // Set loading context
    gameState.context = GameContext.LOADING;
    
    // Request player data and controlled entities from server
    if (window.socket && window.socket.connected) {
        console.log('[PlayerSelect] Requesting player data from server');
        window.socket.emit('load_player', { player_id: playerId });
    } else {
        console.error('[PlayerSelect] Cannot load player: socket not connected');
    }
}

/**
 * Load game state into the client
 * Called when server sends initial game state after player selection
 * @param {Object} data - Initial state data from server
 * @param {Object} [data.world] - World size configuration
 * @param {Object} [data.entities] - Initial entity states
 * @param {string} [data.player_id] - Loaded player ID
 * @param {string[]} [data.controlled_entity_ids] - IDs of entities controlled by player
 * @returns {void}
 */
function loadGameState(data) {
    console.log('[PlayerSelect] Loading game state...', data);
    
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
    
    console.log('[PlayerSelect] Game state loaded. Entities:', Object.keys(gameState.entities).length);
    console.log('[PlayerSelect] Controlled entities:', data.controlled_entity_ids);
    
    // Start render loop now that game is loaded
    requestAnimationFrame(renderLoop);
    console.log('[PlayerSelect] Game render loop started');
}

/**
 * Delete a player with confirmation dialog
 * @param {string} playerId - The player ID to delete
 * @returns {void}
 */
function deletePlayer(playerId) {
    console.log('[PlayerSelect] Delete player requested:', playerId);
    
    // Create confirmation dialog
    const confirmDialog = document.createElement('div');
    confirmDialog.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.8);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 1002;
    `;
    
    confirmDialog.innerHTML = `
        <div style="
            background: #2a2a2a;
            border: 2px solid #d32f2f;
            border-radius: 8px;
            padding: 20px;
            max-width: 400px;
            color: #fff;
        ">
            <h3 style="margin: 0 0 15px 0; color: #d32f2f;">Delete Player?</h3>
            <p style="margin: 0 0 20px 0; color: #ccc;">
                Are you sure you want to delete player "${playerId}"?<br>
                <strong>This action cannot be undone.</strong>
            </p>
            <div style="display: flex; gap: 10px;">
                <button id="delete-confirm-btn" style="
                    flex: 1;
                    padding: 10px;
                    background: #d32f2f;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    cursor: pointer;
                    font-size: 14px;
                ">Delete</button>
                <button id="delete-cancel-btn" style="
                    flex: 1;
                    padding: 10px;
                    background: #666;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    cursor: pointer;
                    font-size: 14px;
                ">Cancel</button>
            </div>
        </div>
    `;
    
    document.body.appendChild(confirmDialog);
    
    document.getElementById('delete-confirm-btn').addEventListener('click', () => {
        console.log('[PlayerSelect] Deleting player:', playerId);
        if (window.socket && window.socket.connected) {
            window.socket.emit('delete_player', { player_id: playerId });
        }
        confirmDialog.remove();
    });
    
    document.getElementById('delete-cancel-btn').addEventListener('click', () => {
        confirmDialog.remove();
    });
}

/**
 * Save current game state to server
 * TODO: Implement game state saving functionality
 * @returns {void}
 */
function saveGameState() {
    console.log('[PlayerSelect] Save game state - NOT YET IMPLEMENTED');
    // TODO: Implement saving functionality
    // - Serialize current game state
    // - Send to server via socket
    // - Handle save confirmation/errors
}
