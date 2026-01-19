/**
 * WebSocket network client
 */

/** @type {Socket} */
let socket;

/**
 * Initialize WebSocket connection and set up event handlers
 * Connects to the server and registers handlers for:
 * - connect: Connection established
 * - disconnect: Connection lost
 * - connection_response: Server confirmation
 * - initial_state: Initial game state from server
 * - state_update: Game state updates from server
 * @returns {void}
 */
function initNetwork() {
    // Connect to server
    socket = io();
    
    // Make socket globally accessible for player selection
    window.socket = socket;
    
    socket.on('connect', () => {
        console.log('[Network] Connected to server');
        
        // If we're in player select context, request the player list
        if (gameState && gameState.context === GameContext.PLAYER_SELECT) {
            console.log('[Network] Auto-requesting player list after connection');
            socket.emit('request_player_list');
        }
    });
    
    socket.on('disconnect', () => {
        console.log('[Network] Disconnected from server');
    });
    
    socket.on('connection_response', (data) => {
        console.log('[Network] Connection response:', data);
    });
    
    socket.on('initial_state', (data) => {
        console.log('[Network] Received initial state:', data);
        handleInitialState(data);
    });
    
    socket.on('state_update', (data) => {
        handleStateUpdate(data);
    });
    
    socket.on('player_list', (data) => {
        console.log('[Network] Received player list:', data);
        populatePlayerList(data.players);
    });
    
    socket.on('player_loaded', (data) => {
        console.log('[Network] Player loaded:', data);
        handleInitialState(data);
    });
    
    socket.on('error', (data) => {
        console.error('[Network] Server error:', data.message);
        alert('Error: ' + data.message);
    });
    
    socket.on('player_deleted', (data) => {
        console.log('[Network] Player deleted:', data.player_id);
        // Refresh the player list
        socket.emit('request_player_list');
    });
    
    socket.on('new_player_initialized', (data) => {
        console.log('[Network] New player initialized:', data.player_id);
        // Load the character creation screen
        
    });

    console.log('[Network] Network initialized');
}

/**
 * Send a player action to the server
 * @param {string} actionType - Type of action (e.g., 'move', 'attack', 'interact')
 * @param {Object} [params={}] - Additional parameters for the action
 * @returns {void}
 */
function sendPlayerAction(actionType, params = {}) {
    socket.emit('player_action', {
        type: actionType,
        ...params
    });
}

/**
 * Send a command to a party member
 * @param {string} memberId - ID of the party member to command
 * @param {string} commandType - Type of command (e.g., 'move_to', 'attack', 'follow')
 * @param {Object} [params={}] - Additional parameters for the command
 * @returns {void}
 */
function sendPartyCommand(memberId, commandType, params = {}) {
    socket.emit('party_command', {
        member_id: memberId,
        type: commandType,
        ...params
    });
}
