/**
 * Canvas rendering system
 */

/** @type {HTMLCanvasElement} */
let canvas;
/** @type {CanvasRenderingContext2D} */
let ctx;
/** @type {EntityRenderer} */
let entityRenderer;

async function initRenderer() {
    console.log('[Renderer] initRenderer called');
    canvas = document.getElementById('game-canvas');
    ctx = canvas.getContext('2d');
    
    // Set canvas size
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);
    
    // Initialize entity renderer
    entityRenderer = new EntityRenderer(ctx);
    await entityRenderer.loadAnimationData('assets/data/human_animations.json');
    
    console.log('Renderer initialized');
}

function resizeCanvas(width = window.innerWidth, height = window.innerHeight) {
    console.log('[Renderer] resizeCanvas called - size:', width, 'x', height);
    canvas.width = width;
    canvas.height = height;
}

function render(gameState, deltaTime) {
    console.log('[Renderer] render called - deltaTime:', deltaTime, 'entities:', Object.keys(gameState.entities || {}).length);
    // Clear canvas
    ctx.fillStyle = '#2a2a2a';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    // Draw grid
    drawGrid(gameState.camera);
    
    // Draw entities using EntityRenderer
    if (entityRenderer) {
        entityRenderer.renderEntities(gameState, deltaTime);
    }
    
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
}
