/**
 * Client-side interpolation for smooth rendering
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

function lerp(start, end, alpha) {
    return start + (end - start) * alpha;
}
