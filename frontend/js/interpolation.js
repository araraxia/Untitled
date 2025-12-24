/**
 * Client-side interpolation for smooth rendering
 */

/**
 * Initialize interpolation display position for a new entity
 * @param {string} entityId - Entity identifier
 * @param {Object} entityData - Entity state data
 * @param {number} [entityData.x] - Entity X position
 * @param {number} [entityData.y] - Entity Y position
 * @returns {void}
 */
function initEntityInterpolation(entityId, entityData) {
    // Initialize display position for new entities
    if (entityData.x !== undefined && entityData.y !== undefined) {
        entityData.displayX = entityData.x;
        entityData.displayY = entityData.y;
    }
}

/**
 * Update interpolated positions for all entities
 * Smoothly interpolates entity display positions toward their actual positions
 * @param {number} deltaTime - Time elapsed since last update in seconds
 * @returns {void}
 */
function updateInterpolation(deltaTime) {
    const interpolationSpeed = 10; // Higher = faster interpolation
    
    for (const entity of Object.values(gameState.entities)) {
        if (entity.x !== undefined && entity.y !== undefined) {
            // Initialize display position if not set
            if (entity.displayX === undefined) {
                entity.displayX = entity.x;
                entity.displayY = entity.y;
            }
            
            // Interpolate toward target position
            entity.displayX = lerp(entity.displayX, entity.x, interpolationSpeed * deltaTime);
            entity.displayY = lerp(entity.displayY, entity.y, interpolationSpeed * deltaTime);
        }
    }
}

/**
 * Linear interpolation between two values
 * @param {number} start - Starting value
 * @param {number} end - Target value
 * @param {number} alpha - Interpolation factor (0-1)
 * @returns {number} Interpolated value
 */
function lerp(start, end, alpha) {
    return start + (end - start) * alpha;
}
