/**
 * UI system for overlays and menus
 */

function initUI() {
    console.log('UI initialized');
}

function updateUI(gameState) {
    // Update player stats
    if (gameState.player) {
        const player = gameState.player;
        document.getElementById('hp-value').textContent = `${player.hp || 100}/${player.max_hp || 100}`;
        document.getElementById('ap-value').textContent = player.action_points || 100;
    }
    
    // Update party panel
    updatePartyPanel(gameState);
}

function updatePartyPanel(gameState) {
    const partyPanel = document.getElementById('party-members');
    partyPanel.innerHTML = '';
    
    for (const [entityId, entity] of Object.entries(gameState.entities)) {
        if (entityId.startsWith('party_')) {
            const memberDiv = document.createElement('div');
            memberDiv.className = 'party-member';
            memberDiv.textContent = `${entityId}: ${entity.state || 'idle'}`;
            memberDiv.onclick = () => selectPartyMember(entityId);
            partyPanel.appendChild(memberDiv);
        }
    }
}

function selectPartyMember(memberId) {
    selectedPartyMember = memberId;
    console.log('Selected party member:', memberId);
}

function showCommandMenu(x, y, memberId) {
    // Remove existing menu
    const existingMenu = document.querySelector('.context-menu');
    if (existingMenu) {
        existingMenu.remove();
    }
    
    // Create menu
    const menu = document.createElement('div');
    menu.className = 'context-menu';
    menu.style.left = x + 'px';
    menu.style.top = y + 'px';
    
    const commands = [
        { label: 'Follow Player', type: 'follow', params: { target_id: 'player_1' } },
        { label: 'Hold Position', type: 'hold_position' },
        { label: 'Attack Target', type: 'attack_target' },
        { label: 'Move Here', type: 'move_to', params: { target: { x: mouseX, y: mouseY } } }
    ];
    
    commands.forEach(cmd => {
        const item = document.createElement('div');
        item.className = 'context-menu-item';
        item.textContent = cmd.label;
        item.onclick = () => {
            sendPartyCommand(memberId, cmd.type, cmd.params || {});
            menu.remove();
        };
        menu.appendChild(item);
    });
    
    document.body.appendChild(menu);
    
    // Close menu on click outside
    setTimeout(() => {
        document.addEventListener('click', function closeMenu() {
            menu.remove();
            document.removeEventListener('click', closeMenu);
        });
    }, 100);
}
