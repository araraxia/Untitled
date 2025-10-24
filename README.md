# Real-Time Simulation Game

A real-time simulation game with Rimworld-style controls and Dwarf Fortress-inspired world simulation, built with Python backend and JavaScript frontend.

## Architecture Overview

### Backend (Python + Flask + SocketIO)
- **Simulation Engine**: Continuous world simulation with entity AI
- **WebSocket Server**: Real-time bidirectional communication with clients
- **State Management**: Efficient entity tracking and spatial partitioning
- **Tick System**: Decoupled simulation rate (~10 tps) from render rate
- **Dual Control System**: Deep player character control + party command interface

### Frontend (JavaScript + Canvas/WebGL)
- **Rendering Engine**: 60fps rendering with interpolation
- **Input Handler**: Keyboard for player character + mouse for party/Rimworld-style commands
- **Client Prediction**: Immediate UI feedback with server reconciliation
- **State Synchronization**: Handles delta updates from server
- **UI Modes**: Action-depth mode (player character) vs command mode (party members)

## Project Structure

```
game-project/
├── backend/
│   ├── __init__.py
│   ├── app.py                 # Flask + SocketIO setup
│   ├── simulation/
│   │   ├── __init__.py
│   │   ├── world.py           # World state manager
│   │   ├── entity.py          # Entity base class
│   │   ├── player.py          # Player character with deep action system
│   │   ├── party.py           # Party management and AI
│   │   ├── systems.py         # ECS-style systems (movement, AI, etc)
│   │   ├── actions.py         # Action system (attack, use item, interact, etc)
│   │   └── spatial.py         # Spatial partitioning for efficient queries
│   ├── game_loop.py           # Main simulation loop
│   └── config.py              # Game configuration
├── frontend/
│   ├── index.html
│   ├── css/
│   │   └── style.css
│   └── js/
│       ├── main.js            # Entry point
│       ├── renderer.js        # Canvas rendering
│       ├── input.js           # Dual input: keyboard (player) + mouse (party)
│       ├── ui.js              # UI overlays (action menu, inventory, party commands)
│       ├── network.js         # WebSocket client
│       └── interpolation.js   # State interpolation
├── requirements.txt
├── .gitignore
└── README.md
```

## Key Design Patterns

### 1. Dual Control System
```python
# Player Character: Deep action control (Elona/Rogue-like)
player.execute_action('attack', target=enemy, weapon=sword)
player.execute_action('use_item', item=potion, on_self=True)
player.execute_action('read_scroll', scroll=teleport_scroll)
player.execute_action('talk', npc=shopkeeper)

# Party Members: High-level commands (Rimworld-style)
party_member.command('follow', target=player)
party_member.command('attack', target=enemy)
party_member.command('defend', position=(x, y))
party_member.command('gather', resource_type='wood')
```

### 2. Input Modes
```javascript
// Keyboard controls player character directly
if (key === 'z') player_attack();
if (key === 'i') open_inventory();
if (key === 'e') interact_with_adjacent();

// Mouse/UI for party commands
on_right_click_party_member(member) {
    show_command_menu(['Follow', 'Hold Position', 'Attack Target']);
}
```

### 3. Tick-Based Simulation
```python
# Simulation runs at fixed rate (e.g., 10 TPS)
TICK_RATE = 5  # ticks per second
TICK_DURATION = 1.0 / TICK_RATE

while running:
    process_player_actions()      # Direct control
    process_party_commands()      # High-level AI
    process_world_entities()      # Background simulation
    update_world_state()
    broadcast_deltas_to_clients()
    sleep_until_next_tick()
```

### 4. State Delta Broadcasting
Only send what changed:
```python
{
    "tick": 1234,
    "entities": {
        "e_001": {"x": 10.5, "y": 20.3, "state": "moving"},
        "e_002": {"hp": 85}
    },
    "removed": ["e_003"]
}
```

### 3. Client-Side Interpolation
```javascript
// Smooth movement between server updates
function interpolateEntity(entity, serverState, alpha) {
    entity.displayX = lerp(entity.x, serverState.x, alpha);
    entity.displayY = lerp(entity.y, serverState.y, alpha);
}
```

### 4. Command Queue Pattern
```javascript
// Player Character: Direct actions
socket.emit('player_action', {
    type: 'attack',
    target_id: 'enemy_1',
    weapon_slot: 0
});

// Party Member: High-level command
socket.emit('party_command', {
    member_id: 'party_1',
    type: 'move_to',
    target: {x: 100, y: 200}
});

// Server processes in next tick
player_action_queue.append(action)
party_command_queue.append(command)
```

## Core Systems to Implement

### Phase 1: Foundation
- [ ] Basic Flask + SocketIO server
- [ ] Simple canvas renderer
- [ ] Player character with keyboard movement
- [ ] Client-server sync
- [ ] Basic tile-based map

### Phase 2: Player Character System
- [ ] Deep action system (attack, use, interact, talk)
- [ ] Inventory and equipment
- [ ] Skill/stat system
- [ ] Turn-based action resolution
- [ ] Item interaction (pickup, drop, use)

### Phase 3: Party System
- [ ] Party member entities
- [ ] Command interface (follow, attack, defend, gather)
- [ ] Party AI (execute high-level commands)
- [ ] Formation system
- [ ] Party member UI (health, status, orders)

### Phase 4: Entity System & World
- [ ] Multiple entities with AI
- [ ] Pathfinding (A* algorithm)
- [ ] Action queue per entity
- [ ] Spatial partitioning (quadtree/grid)
- [ ] Dynamic world events
- [ ] Time system (day/night, seasons)

### Phase 5: Player Interaction Polish
- [ ] Selection system (click to select party members)
- [ ] Command interface (right-click menu for party)
- [ ] Camera controls (follow player, pan, zoom)
- [ ] UI overlays (player stats, inventory, party commands)
- [ ] Pause/speed controls
- [ ] Context-sensitive action menu for player

### Phase 6: Polish
- [ ] Save/load system
- [ ] Performance optimization
- [ ] Visual feedback (animations, particles)
- [ ] Sound effects
- [ ] Settings menu
- [ ] Combat log/message system

## Technical Considerations

### Performance Targets
- **Simulation**: 10 ticks/second (100ms per tick)
- **Rendering**: 60 fps (16.6ms per frame)
- **Network**: <50ms latency for localhost
- **Entity count**: 100-1000 active entities

### Optimization Strategies
1. **Spatial Partitioning**: Only update/send visible entities
2. **Dirty Flagging**: Track what changed, only broadcast deltas
3. **Entity Sleeping**: Inactive entities don't process every tick
4. **LOD System**: Distant entities update less frequently
5. **Object Pooling**: Reuse entity objects instead of creating new ones

### State Synchronization
- Server is authoritative (prevents cheating)
- Client predicts player actions for responsiveness
- Server reconciliation on mismatch
- Interpolation for smooth visuals despite network jitter

## Development Workflow

### Setup

#### Desktop Application (PyWebView)
```bash
# Windows
setup.bat          # Run automated setup
run.bat           # Run the game

# Or manually
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

#### Web Browser Mode (Development)
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Run server
python backend/app.py

# Open browser to http://localhost:5000
```

### Key Dependencies
```
Flask==3.0.0
Flask-SocketIO==5.3.5
python-socketio==5.10.0
eventlet==0.33.3
pywebview==5.0.5  # For desktop client
```

### Debugging
- Use Flask debug mode for hot reloading
- Browser DevTools for client debugging
- `console.log()` for WebSocket message inspection
- Server-side logging for simulation state

## Design Decisions

### Why WebSockets?
- Bidirectional communication (server can push updates)
- Low latency for real-time gameplay
- Efficient for frequent small messages
- Better than polling for continuous simulation

### Why Python Backend?
- Excellent for complex simulation logic
- Rich ecosystem for AI/pathfinding (NumPy, NetworkX)
- Easy to prototype and iterate
- Strong typing with type hints for maintainability

### Why Canvas Rendering?
- Direct pixel control for tile-based graphics
- Good performance for 2D rendering
- Simple API for prototyping
- Can upgrade to WebGL later if needed

## Common Patterns for This Genre

### Player Character Action System
```python
class PlayerCharacter:
    def execute_action(self, action_type, **kwargs):
        action = ActionFactory.create(action_type, **kwargs)
        if action.can_execute(self):
            action.execute(self)
            self.consume_action_points(action.cost)
            return action.result
        return None

# Rich action set
actions = [
    'move', 'attack', 'defend', 'use_item', 'equip', 'unequip',
    'pickup', 'drop', 'talk', 'read', 'cast_spell', 'rest',
    'search', 'disarm_trap', 'open_door', 'close_door'
]
```

### Party Command System
```python
class PartyMember:
    def receive_command(self, command_type, **kwargs):
        # Translate high-level command to action queue
        if command_type == 'follow':
            self.ai_mode = 'follow'
            self.follow_target = kwargs['target']
        elif command_type == 'attack':
            path = find_path(self.pos, kwargs['target'].pos)
            for waypoint in path[:-1]:
                self.action_queue.add(MoveAction(waypoint))
            self.action_queue.add(AttackAction(kwargs['target']))
        elif command_type == 'defend':
            self.ai_mode = 'defend'
            self.defend_position = kwargs['position']

# Simple command set
commands = ['follow', 'hold_position', 'attack_target', 'defend_area', 'gather_resource']
```

### Entity AI Loop
```python
for entity in active_entities:
    if entity.action_queue.empty():
        decide_next_action(entity)
    current_action = entity.action_queue.peek()
    if current_action.is_complete():
        entity.action_queue.pop()
    else:
        current_action.update(delta_time)
```

### Pathfinding Integration
```python
def move_to_command(entity, target):
    path = find_path(entity.pos, target)
    for waypoint in path:
        entity.action_queue.add(MoveAction(waypoint))
```

### Viewport Culling
```python
def get_visible_entities(camera_bounds):
    return spatial_index.query(camera_bounds)
# Only send these to client
```

## Next Steps

1. **Start with minimal prototype**: Single player entity, basic movement
2. **Add second entity with AI**: Test simulation vs rendering separation
3. **Implement basic pathfinding**: Make AI navigate obstacles
4. **Add interaction system**: Click to command, simple tasks
5. **Expand world simulation**: Add resources, needs, goals

## Resources

- **Pathfinding**: A* algorithm, hierarchical pathfinding for large maps
- **ECS Pattern**: Entity-Component-System for flexible entity design
- **Spatial Indexing**: Quadtree or uniform grid for collision/visibility
- **Game Loop**: Fixed timestep vs variable timestep considerations
- **Networking**: Client prediction and server reconciliation techniques

## Notes for Claude Code

When implementing this project:
- Focus on getting the basic game loop working first
- Use type hints throughout Python code for clarity
- Keep simulation logic separate from networking code
- Test with single entity before scaling to many
- Profile early to identify bottlenecks
- Consider using dataclasses for game state structures
- Implement save/load early (helps with testing)

## Architecture Decisions to Make

1. **Map representation**: 2D array, hex grid, or continuous space?
2. **Entity state**: Pure ECS or object-oriented entities?
3. **Rendering**: Tile-based sprites or programmatic drawing?
4. **Pathfinding**: Pre-computed navigation mesh or dynamic A*?
5. **Save format**: JSON, SQLite, or custom binary format?

---

**Goal**: Create a foundation that's simple enough to understand but flexible enough to grow into a complex simulation game like Rimworld or Dwarf Fortress.