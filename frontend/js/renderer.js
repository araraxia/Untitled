/**
 * Canvas rendering system
 */

let canvas, ctx;

function initRenderer() {
    canvas = document.getElementById('game-canvas');
    ctx = canvas.getContext('2d');
    
    // Set canvas size
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);
    
    console.log('Renderer initialized');
}

function resizeCanvas() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
}

function render(gameState, deltaTime) {
    // Clear canvas
    ctx.fillStyle = '#2a2a2a';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    // Draw grid
    drawGrid(gameState.camera);
    
    // Draw entities
    for (const [entityId, entity] of Object.entries(gameState.entities)) {
        drawEntity(entity, gameState.camera);
    }
    
    // Draw debug info
    drawDebugInfo(gameState);
}

function drawGrid(camera) {
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

function drawEntity(entity, camera) {
    // Use interpolated position
    const x = (entity.displayX || entity.x) - camera.x;
    const y = (entity.displayY || entity.y) - camera.y;
    
    // Draw entity as a circle
    ctx.beginPath();
    ctx.arc(x, y, 16, 0, Math.PI * 2);
    
    // Color based on entity type
    if (entity.id && entity.id.startsWith('player_')) {
        ctx.fillStyle = '#4CAF50';
    } else {
        ctx.fillStyle = '#2196F3';
    }
    
    ctx.fill();
    
    // Draw state indicator
    if (entity.state === 'moving') {
        ctx.strokeStyle = '#FFC107';
        ctx.lineWidth = 2;
        ctx.stroke();
    }
    
    // Draw health bar if HP is defined
    if (entity.hp !== undefined) {
        const barWidth = 32;
        const barHeight = 4;
        const barX = x - barWidth / 2;
        const barY = y - 24;
        
        // Background
        ctx.fillStyle = '#333';
        ctx.fillRect(barX, barY, barWidth, barHeight);
        
        // Health
        const healthPercent = entity.hp / entity.max_hp;
        ctx.fillStyle = healthPercent > 0.5 ? '#4CAF50' : '#F44336';
        ctx.fillRect(barX, barY, barWidth * healthPercent, barHeight);
    }
    
    // Draw entity ID
    ctx.fillStyle = '#fff';
    ctx.font = '10px Arial';
    ctx.textAlign = 'center';
    ctx.fillText(entity.id, x, y + 30);
}

function drawDebugInfo(gameState) {
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
