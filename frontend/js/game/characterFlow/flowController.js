/**
 * Character flow controller.
 */

window.CharacterFlow = window.CharacterFlow || {};

/******************************************************************************
 * Controller state
 *****************************************************************************/

/** @type {CharacterFlowControllerConfig} */
let controllerConfig = {
  defaultModuleId: null,
};

/** @type {CharacterFlowContext} */
let controllerContext = {};

/** @type {string|null} */
let activeModuleId = null;

/** @type {CharacterFlowModule|null} */
let activeModule = null;

/******************************************************************************
 * Public API
 *****************************************************************************/

/**
 * Initialize the character flow controller.
 *
 * @param {CharacterFlowControllerConfig} config
 * @param {CharacterFlowContext} context
 * @returns {Promise<void>}
 */
async function initCharacterFlowController(config, context) {
  controllerConfig = {
    defaultModuleId:
      config && typeof config.defaultModuleId === "string"
        ? config.defaultModuleId
        : null,
  };
  controllerContext = context || {};

  if (controllerConfig.defaultModuleId) {
    await activateCharacterFlowModule(controllerConfig.defaultModuleId);
  }
}

/**
 * Activate a character flow module by id.
 *
 * @param {string} moduleId
 * @returns {Promise<void>}
 */
async function activateCharacterFlowModule(moduleId) {
  if (typeof moduleId !== "string" || moduleId.trim() === "") {
    throw new Error(
      "[CharacterFlow] activateCharacterFlowModule requires a module id.",
    );
  }

  const nextModule = window.CharacterFlow.getCharacterFlowModule(moduleId);
  if (!nextModule) {
    throw new Error(`[CharacterFlow] Unknown module id "${moduleId}".`);
  }

  if (activeModuleId === moduleId) {
    return;
  }

  if (activeModule && typeof activeModule.unmount === "function") {
    await activeModule.unmount(controllerContext);
  }

  if (
    activeModule &&
    typeof activeModule.destroy === "function" &&
    typeof nextModule.id === "string" &&
    activeModuleId !== nextModule.id
  ) {
    await activeModule.destroy(controllerContext);
  }

  activeModule = nextModule;
  activeModuleId = moduleId;

  if (typeof activeModule.init === "function") {
    await activeModule.init(controllerContext);
  }

  if (typeof activeModule.mount === "function") {
    await activeModule.mount(controllerContext);
  }
}

/**
 * Dispatch an event to the active character flow module.
 *
 * @param {string} eventName
 * @param {Object} payload
 * @returns {boolean}
 */
function dispatchCharacterFlowEvent(eventName, payload) {
  if (!activeModule || typeof activeModule.handleEvent !== "function") {
    return false;
  }

  const handled = activeModule.handleEvent(
    eventName,
    payload || {},
    controllerContext,
  );

  return handled === true;
}

/**
 * Get the currently active character flow module id.
 *
 * @returns {string|null}
 */
function getActiveCharacterFlowModuleId() {
  return activeModuleId;
}

window.CharacterFlow.initCharacterFlowController = initCharacterFlowController;
window.CharacterFlow.activateCharacterFlowModule = activateCharacterFlowModule;
window.CharacterFlow.dispatchCharacterFlowEvent = dispatchCharacterFlowEvent;
window.CharacterFlow.getActiveCharacterFlowModuleId =
  getActiveCharacterFlowModuleId;
