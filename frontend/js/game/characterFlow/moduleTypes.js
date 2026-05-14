/**
 * Character flow module interface contract.
 *
 * @typedef {Object} CharacterFlowModule
 * @property {string} id
 * @property {(ctx: Object) => Promise<void>|void} init
 * @property {(ctx: Object) => Promise<void>|void} mount
 * @property {(ctx: Object) => Promise<void>|void} unmount
 * @property {(eventName: string, data: Object, ctx: Object) => boolean|void} handleEvent
 * @property {(ctx: Object) => Promise<void>|void} destroy
 */

/**
 * @typedef {Object} CharacterFlowControllerConfig
 * @property {string|null} defaultModuleId
 */

/**
 * @typedef {Object<string, any>} CharacterFlowContext
 */

window.CharacterFlow = window.CharacterFlow || {};
