/**
 * Character flow module registry.
 */

window.CharacterFlow = window.CharacterFlow || {};

/** @type {Map<string, CharacterFlowModule>} */
const modules = new Map();

/**
 * Register a character flow module.
 *
 * @param {CharacterFlowModule} module
 * @returns {void}
 */
function registerCharacterFlowModule(module) {
  if (!module || typeof module !== 'object') {
    throw new Error('[CharacterFlow] Module must be an object.');
  }

  if (typeof module.id !== 'string' || module.id.trim() === '') {
    throw new Error('[CharacterFlow] Module must have a non-empty string id.');
  }

  if (modules.has(module.id)) {
    throw new Error(
      `[CharacterFlow] Module with id "${module.id}" is already registered.`,
    );
  }

  modules.set(module.id, module);
}

/**
 * Get a character flow module by id.
 *
 * @param {string} moduleId
 * @returns {CharacterFlowModule|null}
 */
function getCharacterFlowModule(moduleId) {
  return modules.get(moduleId) || null;
}

/**
 * List all registered character flow modules.
 *
 * @returns {CharacterFlowModule[]}
 */
function listCharacterFlowModules() {
  return Array.from(modules.values());
}

window.CharacterFlow.registerCharacterFlowModule = registerCharacterFlowModule;
window.CharacterFlow.getCharacterFlowModule = getCharacterFlowModule;
window.CharacterFlow.listCharacterFlowModules = listCharacterFlowModules;
