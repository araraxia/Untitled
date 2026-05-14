/**
 * WebSocket network client
 */

/** @type {Socket} */
let socket;

/**
 * Character flow callbacks.
 * Network layer forwards onboarding-related events through this object.
 */
const characterFlowCallbacks = {
  onSaveList: null,
  onNewPlayerInitialized: null,
  onCharacterCreated: null,
  onRacesList: null,
  onBackgroundsList: null,
  onCharacterFlowError: null,
};

/**
 * Register character flow callbacks.
 *
 * @param {Object} callbacks - Callback map.
 * @param {Function|null} [callbacks.onSaveList]
 * @param {Function|null} [callbacks.onNewPlayerInitialized]
 * @param {Function|null} [callbacks.onCharacterCreated]
 * @param {Function|null} [callbacks.onRacesList]
 * @param {Function|null} [callbacks.onBackgroundsList]
 * @param {Function|null} [callbacks.onCharacterFlowError]
 * @returns {void}
 */
function setCharacterFlowCallbacks(callbacks) {
  if (!callbacks || typeof callbacks !== 'object') {
    return;
  }

  characterFlowCallbacks.onSaveList = callbacks.onSaveList || null;
  characterFlowCallbacks.onNewPlayerInitialized =
    callbacks.onNewPlayerInitialized || null;
  characterFlowCallbacks.onCharacterCreated =
    callbacks.onCharacterCreated || null;
  characterFlowCallbacks.onRacesList = callbacks.onRacesList || null;
  characterFlowCallbacks.onBackgroundsList =
    callbacks.onBackgroundsList || null;
  characterFlowCallbacks.onCharacterFlowError =
    callbacks.onCharacterFlowError || null;
}

/**
 * Invoke a registered character flow callback safely.
 *
 * @param {'onSaveList'|'onNewPlayerInitialized'|'onCharacterCreated'|'onRacesList'|'onBackgroundsList'|'onCharacterFlowError'} callbackName
 * @param {Object} payload
 * @returns {void}
 */
function invokeCharacterFlowCallback(callbackName, payload) {
  const callback = characterFlowCallbacks[callbackName];
  if (typeof callback !== 'function') {
    return;
  }

  try {
    callback(payload);
  } catch (error) {
    console.error(
      `[Network] Character flow callback failed: ${callbackName}`,
      error,
    );
  }
}

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

  socket.on("connect", () => {
    console.log("[Network] Connected to server");

    // If we're in player select context, request the save list
    if (gameState && gameState.context === GameContext.PLAYER_SELECT) {
      console.log("[Network] Auto-requesting save list after connection");
      socket.emit("request_save_list");
    }
  });

  socket.on("disconnect", () => {
    console.log("[Network] Disconnected from server");
  });

  socket.on("connection_response", (data) => {
    console.log("[Network] Connection response:", data);
  });

  socket.on("initial_state", (data) => {
    console.log("[Network] Received initial state:", data);
    handleInitialState(data);
  });

  socket.on("state_update", (data) => {
    handleStateUpdate(data);
  });

  socket.on("save_list", (data) => {
    console.log("[Network] Received save list:", data);
    invokeCharacterFlowCallback('onSaveList', data);
  });

  socket.on('races_list', (data) => {
    invokeCharacterFlowCallback('onRacesList', data);
  });

  socket.on('backgrounds_list', (data) => {
    invokeCharacterFlowCallback('onBackgroundsList', data);
  });

  socket.on("save_complete", (data) => {
    console.log("[Network] Save complete:", data);
    if (data.status === "error") {
      console.error("[Network] Save failed:", data.message);
    }
  });

  socket.on("autosave_complete", (data) => {
    console.debug("[Network] Autosave:", data.status, "at tick", data.tick);
  });

  socket.on("player_loaded", (data) => {
    console.log("[Network] Player loaded:", data);
    handleInitialState(data);
  });

  socket.on("error", (data) => {
    console.error("[Network] Server error:", data.message);
    invokeCharacterFlowCallback('onCharacterFlowError', data);
  });

  socket.on("player_deleted", (data) => {
    console.log("[Network] Player deleted:", data.player_id);
    // Refresh the save list
    socket.emit("request_save_list");
  });

  socket.on("new_player_initialized", (data) => {
    console.log("[Network] New player initialized:", data.player_id);
    invokeCharacterFlowCallback('onNewPlayerInitialized', data);
  });

  socket.on("character_created", (data) => {
    console.log("[Network] Character created successfully:", data);
    invokeCharacterFlowCallback('onCharacterCreated', data);
  });

  console.log("[Network] Network initialized");
}

/**
 * Send a player action to the server
 * @param {string} actionType - Type of action (e.g., 'move', 'attack', 'interact')
 * @param {Object} [params={}] - Additional parameters for the action
 * @returns {void}
 */
function sendPlayerAction(actionType, params = {}) {
  socket.emit("player_action", {
    type: actionType,
    ...params,
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
  socket.emit("party_command", {
    member_id: memberId,
    type: commandType,
    ...params,
  });
}
