/**
 * WebSocket network client
 */

let socket;

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
    
    socket.on('state_update', (data) => {
        handleStateUpdate(data);
    });
    
    console.log('Network initialized');
}

function sendPlayerAction(actionType, params = {}) {
    socket.emit('player_action', {
        type: actionType,
        ...params
    });
}

function sendPartyCommand(memberId, commandType, params = {}) {
    socket.emit('party_command', {
        member_id: memberId,
        type: commandType,
        ...params
    });
}
