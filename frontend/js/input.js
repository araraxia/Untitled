/**
 * Dual input system: Keyboard for player, mouse for party
 */

const keys = {};
let mouseX = 0;
let mouseY = 0;
let selectedPartyMember = null;

function initInput() {
    // Keyboard input for player character
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    
    // Mouse input for party commands
    canvas.addEventListener('mousemove', handleMouseMove);
    canvas.addEventListener('mousedown', handleMouseDown);
    canvas.addEventListener('contextmenu', handleContextMenu);
    
    // Start input processing loop
    setInterval(processInput, 16); // ~60fps
    
    console.log('Input initialized');
}

function handleKeyDown(e) {
    keys[e.key.toLowerCase()] = true;
}

function handleKeyUp(e) {
    keys[e.key.toLowerCase()] = false;
}

function handleMouseMove(e) {
    const rect = canvas.getBoundingClientRect();
    mouseX = e.clientX - rect.left;
    mouseY = e.clientY - rect.top;
}

function handleMouseDown(e) {
    if (e.button === 0) { // Left click
        // Select entity at mouse position
        const worldX = mouseX + gameState.camera.x;
        const worldY = mouseY + gameState.camera.y;
        
        for (const [entityId, entity] of Object.entries(gameState.entities)) {
            const dx = entity.x - worldX;
            const dy = entity.y - worldY;
            const distance = Math.sqrt(dx * dx + dy * dy);
            
            if (distance < 16) {
                selectedPartyMember = entityId;
                console.log('Selected:', entityId);
                break;
            }
        }
    }
}

function handleContextMenu(e) {
    e.preventDefault();
    
    if (selectedPartyMember) {
        showCommandMenu(e.clientX, e.clientY, selectedPartyMember);
    }
}

function processInput() {
    // Process keyboard input for player movement
    let dx = 0;
    let dy = 0;
    
    if (keys['w'] || keys['arrowup']) dy -= 1;
    if (keys['s'] || keys['arrowdown']) dy += 1;
    if (keys['a'] || keys['arrowleft']) dx -= 1;
    if (keys['d'] || keys['arrowright']) dx += 1;
    
    // Normalize diagonal movement
    if (dx !== 0 && dy !== 0) {
        dx *= 0.707;
        dy *= 0.707;
    }
    
    // Send movement command if moving
    if (dx !== 0 || dy !== 0) {
        sendPlayerAction('move', {
            direction: { x: dx, y: dy }
        });
    } else {
        // Stop moving
        sendPlayerAction('move', {
            direction: { x: 0, y: 0 }
        });
    }
}
