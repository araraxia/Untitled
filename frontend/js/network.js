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
    
    socket.on('connect', () => {
        console.log('Connected to server');
    });
    
    socket.on('disconnect', () => {
        console.log('Disconnected from server');
    });
    
    socket.on('connection_response', (data) => {
        console.log('Connection response:', data);
    });
    
    socket.on('initial_state', (data) => {
        console.log('Received initial state:', data);
        handleInitialState(data);
    });
    
    socket.on('state_update', (data) => {
        handleStateUpdate(data);
    });
    
    console.log('Network initialized');
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
