/**
 * Canvas rendering system
 */

/** @type {HTMLCanvasElement} */
let canvas;
/** @type {CanvasRenderingContext2D} */
let ctx;
/** @type {Map<string, EntityRenderer>} */
let entityRenderers = new Map();

async function initRenderer() {
    console.log('[Renderer] initRenderer called');
    canvas = document.getElementById('game-canvas');
    ctx = canvas.getContext('2d');
    
    // Set canvas size
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);
    
    console.log('Renderer initialized');
}

/**
 * Get or create an EntityRenderer for a specific entity
 * @param {string} entityId - The entity ID
 * @param {Array<string>} animationDataPaths - List of animation data paths from entity
 * @returns {Promise<EntityRenderer>}
 */
async function getEntityRenderer(entityId, animationDataPaths) {
    console.log('[Renderer] getEntityRenderer called - entityId:', entityId);
    
    if (!entityRenderers.has(entityId)) {
        const renderer = new EntityRenderer(ctx, entityId, animationDataPaths);
        await renderer.loadAllAnimationData();
        entityRenderers.set(entityId, renderer);
    }
    
    return entityRenderers.get(entityId);
}

/**
 * Render all entities in the game state
 * @param {Object} gameState - Current game state
 * @param {number} deltaTime - Time elapsed since last frame (milliseconds)
 */
async function renderEntities(gameState, deltaTime) {
    console.log('[Renderer] renderEntities called - entityCount:', Object.keys(gameState.entities).length, 'deltaTime:', deltaTime);
    
    // Update and draw all entity animations
    for (const [entityId, entity] of Object.entries(gameState.entities)) {
        // Get animation data paths from entity (fallback to default if not provided)
        const animationDataPaths = entity.animation_data_paths || ['assets/data/human_animations.json'];
        
        // Get or create renderer for this entity
        const renderer = await getEntityRenderer(entityId, animationDataPaths);
        
        // Update animation
        renderer.updateEntityAnimation(entityId, entity, deltaTime);
        
        // Draw entity
        renderer.drawEntity(entity, gameState.camera);
    }
}

function resizeCanvas(width = window.innerWidth, height = window.innerHeight) {
    console.log('[Renderer] resizeCanvas called - size:', width, 'x', height);
    canvas.width = width;
    canvas.height = height;
}

async function render(gameState, deltaTime) {
    console.log('[Renderer] render called - deltaTime:', deltaTime, 'entities:', Object.keys(gameState.entities || {}).length);
    // Clear canvas
    ctx.fillStyle = '#2a2a2a';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    // Draw grid
    drawGrid(gameState.camera);
    
    // Draw all entities
    await renderEntities(gameState, deltaTime);
    
    // Draw debug info
    drawDebugInfo(gameState);
}

function drawGrid(camera) {
    console.log('[Renderer] drawGrid called - camera:', camera);
    const gridSize = 32;
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
    ctx.lineWidth = 1;
    
    // Vertical lines
    const startX = Math.floor(camera.x / gridSize) * gridSize;
    for (let x = startX; x < camera.x + canvas.width; x += gridSize) {
        const screenX = x - camera.x;
        ctx.beginPath();
        ctx.moveTo(screenX, 0);
        ctx.lineTo(screenX, canvas.height);
        ctx.stroke();
    }
    
    // Horizontal lines
    const startY = Math.floor(camera.y / gridSize) * gridSize;
    for (let y = startY; y < camera.y + canvas.height; y += gridSize) {
        const screenY = y - camera.y;
        ctx.beginPath();
        ctx.moveTo(0, screenY);
        ctx.lineTo(canvas.width, screenY);
        ctx.stroke();
    }
}

// Legacy function - kept for backwards compatibility but no longer used
function drawEntity(entity, camera) {
    console.log('[Renderer] drawEntity called (legacy) - entity:', entity.id);
    // This function is now handled by EntityRenderer
    // Kept here for reference or fallback purposes
    console.warn('Legacy drawEntity called - should use EntityRenderer instead');
}

function drawDebugInfo(gameState) {
    console.log('[Renderer] drawDebugInfo called');
    ctx.fillStyle = '#fff';
    ctx.font = '12px monospace';
    ctx.textAlign = 'left';
    
    const info = [
        `Entities: ${Object.keys(gameState.entities).length}`,
        `Camera: ${Math.round(gameState.camera.x)}, ${Math.round(gameState.camera.y)}`,
        `Player: ${gameState.player ? `${Math.round(gameState.player.x)}, ${Math.round(gameState.player.y)}` : 'None'}`
    ];
    
    info.forEach((line, index) => {
        ctx.fillText(line, 10, canvas.height - 50 + (index * 15));
    });
    
    // Draw pause indicator
    if (gameState.paused) {
        ctx.save();
        ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        
        ctx.fillStyle = '#FFD700';
        ctx.font = 'bold 48px monospace';
        ctx.textAlign = 'center';
        ctx.fillText('PAUSED', canvas.width / 2, canvas.height / 2);
        
        ctx.font = '16px monospace';
        ctx.fillStyle = '#fff';
        ctx.fillText('Press SPACE or P to resume', canvas.width / 2, canvas.height / 2 + 40);
        ctx.fillText('Check console for logs', canvas.width / 2, canvas.height / 2 + 65);
        ctx.restore();
    }
}
