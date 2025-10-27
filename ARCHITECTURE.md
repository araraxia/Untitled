# Real-Time Simulation Game - Repository Explanation

## 🎮 Overview

This is a **real-time simulation game** inspired by Rimworld and Dwarf Fortress. It runs as a **standalone desktop application** using PyWebView, with a Python backend handling game logic and a JavaScript/HTML frontend for rendering and user interaction.

---

## 🏗️ Architecture

### **Three-Layer Architecture:**

1. **Desktop Application Layer** (`main.py`)
2. **Backend Simulation Layer** (Python Flask + SocketIO)
3. **Frontend Rendering Layer** (JavaScript + HTML Canvas)

---

## 📁 File-by-File Breakdown

### 🚀 **Entry Point**

#### **`main.py`** - Desktop Application Launcher
- **Purpose**: Launches the game as a standalone desktop window
- **What it does**:
  - Creates a PyWebView window (native OS webview)
  - Starts the Flask backend server in a background thread
  - Starts the game simulation loop
  - Waits for server to be ready before opening window
  - Handles server health checks
- **Key Features**:
  - GPU acceleration disabled for compatibility
  - Server readiness detection
  - Clean threading model (daemon threads)

---

### ⚙️ **Backend (Python)**

#### **`backend/app.py`** - Flask Web Server & WebSocket Handler
- **Purpose**: HTTP server + WebSocket communication hub
- **What it does**:
  - Serves the HTML/CSS/JS frontend files
  - Manages WebSocket connections for real-time communication
  - Routes player actions and party commands to game loop
  - Broadcasts game state updates to clients
  - Sends initial full game state when client connects
- **Key Routes**:
  - `/` → Serves index.html
  - `/css/...` → Serves CSS files
  - `/js/...` → Serves JavaScript files
- **WebSocket Events**:
  - `connect` → Send initial game state
  - `player_action` → Queue player movement/actions
  - `party_command` → Queue party member commands
  - `state_update` → Broadcast world changes (emitted)

#### **`backend/game_loop.py`** - Simulation Engine
- **Purpose**: Main game tick loop (runs at 10 TPS - ticks per second)
- **What it does**:
  - Processes player action queue
  - Processes party command queue
  - Updates all entities in the world
  - Computes state deltas (what changed)
  - Broadcasts changes via SocketIO
  - Maintains tick timing (100ms per tick)
- **Architecture Pattern**: Fixed timestep game loop
- **Performance**: Protects against slow frames with time checks

#### **`backend/config.py`** - Configuration Constants
- **Settings**:
  - `TICK_RATE = 10` → Simulation runs at 10 updates/second
  - `WORLD_WIDTH/HEIGHT = 1000` → Game world size
  - `HOST = "0.0.0.0"` → Server bind address
  - `PORT = 5000` → Server port
  - `SPATIAL_GRID_SIZE = 32` → Grid cell size for spatial optimization

---

### 🌍 **Simulation Layer** (`backend/simulation/`)

#### **`world.py`** - World State Manager
- **Purpose**: Central authority for all game state
- **Responsibilities**:
  - Manages all entities (dictionary: `entity_id → Entity`)
  - Tracks player character
  - Maintains spatial partitioning grid
  - Tracks dirty entities (what changed this tick)
  - Generates state deltas for network transmission
  - Creates initial player at world center
- **Optimization**: Only sends changed entities, not entire world state

#### **`entity.py`** - Base Entity Class
- **Purpose**: Base class for all game objects
- **Properties**:
  - Position (`x`, `y`)
  - Velocity (`vx`, `vy`)
  - State (`idle`, `moving`, `attacking`, etc.)
  - Dirty flag (needs network update?)
- **Methods**:
  - `update()` → Moves entity based on velocity
  - `serialize()` → Converts to JSON for network
  - `receive_command()` → Override for AI/party members

#### **`player.py`** - Player Character
- **Purpose**: Player-controlled character with deep action system
- **Extends**: `Entity` with additional features
- **Extra Properties**:
  - HP and max HP
  - Action points (for turn-based actions)
  - Inventory and equipment
- **Actions**:
  - `move` → WASD keyboard movement
  - `attack` → Target enemy (placeholder)
  - `use_item` → Consume item (placeholder)
- **Control Style**: Direct, deep control (like roguelikes/Elona)

#### **`party.py`** - Party Members & AI
- **Purpose**: Manages party members with high-level AI
- **PartyMember Class**:
  - AI modes: follow, hold_position, attack, move_to
  - Command queue for pathfinding
  - Autonomous behavior based on mode
- **PartyManager Class**:
  - Centralized party member registry
  - Add/remove party members
- **Control Style**: High-level commands (like Rimworld)

#### **`actions.py`** - Action System
- **Purpose**: Defines discrete player actions
- **Pattern**: Command pattern with validation
- **Action Types**:
  - `MoveAction` → Teleport/move to position
  - `AttackAction` → Attack a target
  - `UseItemAction` → Use inventory item
- **Features**:
  - Action point costs
  - Pre-execution validation
  - Factory pattern for creation

#### **`systems.py`** - ECS-Style Systems
- **Purpose**: Entity processing systems (ECS pattern)
- **Systems**:
  - `MovementSystem` → Updates positions from velocities
  - `AISystem` → Processes entity AI (placeholder)
  - `CombatSystem` → Resolves attacks (placeholder)
- **Pattern**: Iterate over entities, apply logic

#### **`spatial.py`** - Spatial Partitioning Grid
- **Purpose**: Optimize entity queries (O(n) → O(1))
- **How it works**:
  - Divides world into 32×32 grid cells
  - Entities registered to cells
  - Query by area/radius (only check nearby cells)
- **Use Cases**:
  - Collision detection
  - Line-of-sight checks
  - Finding nearby entities
- **Performance**: Essential for 100s-1000s of entities

---

### 🎨 **Frontend (JavaScript)**

#### **`frontend/index.html`** - Game Interface
- **Structure**:
  - `<canvas>` → Game rendering surface
  - UI overlays (player stats, party panel, controls help)
  - Socket.IO client library (CDN)
- **Layout**: Full-screen canvas with fixed UI panels

#### **`frontend/css/style.css`** - Styling
- **Dark theme** (#1a1a1a background)
- Semi-transparent UI panels
- Grid layout for stats/party members
- Context menus for party commands

#### **`frontend/js/main.js`** - Frontend Entry Point
- **Purpose**: Initializes and coordinates all frontend systems
- **Game State Object**:
  - `entities` → All visible entities
  - `player` → Reference to player entity
  - `camera` → Viewport position
  - `worldSize` → World dimensions
- **Initialization Flow**:
  1. Initialize renderer (canvas)
  2. Connect to server (WebSocket)
  3. Set up input handlers
  4. Initialize UI
  5. Start render loop (60 FPS)
- **Handles**:
  - `handleInitialState()` → Loads full world from server
  - `handleStateUpdate()` → Applies incremental updates

#### **`frontend/js/renderer.js`** - Canvas Rendering
- **Purpose**: Draws the game at 60 FPS
- **Renders**:
  - Grid background
  - All entities (circles with colors)
  - Health bars
  - Entity IDs
  - Debug info (entity count, camera position)
- **Optimizations**:
  - Only draws visible entities (viewport culling)
  - Uses interpolated positions (smooth movement)

#### **`frontend/js/network.js`** - WebSocket Client
- **Purpose**: Bidirectional server communication
- **Receives**:
  - `connect` → Connection established
  - `initial_state` → Full world state on join
  - `state_update` → Incremental changes (delta)
- **Sends**:
  - `player_action` → Keyboard input (WASD)
  - `party_command` → Mouse clicks on party members
- **Uses**: Socket.IO library for WebSocket abstraction

#### **`frontend/js/input.js`** - Dual Input System
- **Keyboard** → Player character control (WASD/arrows)
- **Mouse** → Party member commands (click, right-click)
- **How it works**:
  - Tracks key states in dictionary
  - 60 FPS input polling loop
  - Sends movement vectors to server
  - Detects entity clicks
  - Shows context menu on right-click

#### **`frontend/js/ui.js`** - UI System
- **Updates**:
  - Player stats (HP, action points)
  - Party member list
- **Features**:
  - Party member selection
  - Context menu for commands
  - Command options: Follow, Hold Position, Attack, Move

#### **`frontend/js/interpolation.js`** - Smooth Movement
- **Purpose**: Eliminates "jerky" movement from 10 TPS simulation
- **How it works**:
  - Lerp (linear interpolation) between positions
  - Renders at 60 FPS using `displayX`/`displayY`
  - Server updates at 10 TPS → looks smooth
- **Result**: Butter-smooth visuals despite low tick rate

---

## 🔧 **Setup & Utility Files**

#### **`requirements.txt`** - Python Dependencies
- `Flask` → Web server
- `Flask-SocketIO` → WebSocket support
- `python-socketio` → SocketIO protocol
- `pywebview` → Desktop window wrapper
- `python-engineio`, `simple-websocket` → WebSocket backends

#### **`setup.bat`** - Windows Setup Script
- Creates Python virtual environment
- Installs all dependencies
- One-click setup

#### **`run.bat`** - Windows Launcher
- Activates virtual environment
- Runs `main.py`
- Opens desktop window

#### **`run_browser.py`** - Web Browser Mode (Alternative)
- For testing without PyWebView
- Opens system browser to `localhost:5000`
- Useful for debugging with browser DevTools

---

## 🔄 **How Everything Works Together**

### **Startup Sequence:**
1. `run.bat` → Activates venv → Runs `main.py`
2. `main.py` → Starts Flask server in thread
3. Flask creates `GameLoop` instance
4. `GameLoop.run()` starts in separate thread (10 TPS tick)
5. PyWebView window opens pointing to `http://127.0.0.1:5000`
6. Frontend loads, connects via WebSocket
7. Server sends initial game state
8. Frontend starts rendering at 60 FPS

### **Game Loop (Every 100ms):**
1. Process player action queue
2. Process party command queue
3. Update all entities (movement, AI)
4. Mark dirty entities
5. Generate state delta
6. Broadcast delta to all clients
7. Sleep until next tick

### **Rendering Loop (Every 16.6ms):**
1. Interpolate entity positions
2. Clear canvas
3. Draw grid
4. Draw all entities
5. Draw UI overlays
6. Request next frame

### **Player Input Flow:**
```
User presses W
  ↓
input.js detects keydown
  ↓
Sends player_action{type:'move', direction:{x:0,y:-1}}
  ↓
WebSocket to server
  ↓
app.py receives, queues action
  ↓
game_loop.py processes on next tick
  ↓
player.execute_action() sets velocity
  ↓
world.update() moves player
  ↓
Delta sent to all clients
  ↓
Frontend interpolates movement
  ↓
Smooth animation on screen
```

---

## 🎯 **Key Design Patterns**

1. **Client-Server Architecture**: Authority on server, rendering on client
2. **Delta Updates**: Only send what changed (bandwidth optimization)
3. **Client Interpolation**: Smooth 60 FPS from 10 TPS updates
4. **Dual Control**: Direct keyboard (player) + command mouse (party)
5. **ECS-Inspired**: Entities + Systems (but not pure ECS)
6. **Spatial Partitioning**: Grid-based optimization
7. **Dirty Flag Pattern**: Track what needs network updates

---

## 🚀 **Current Features**

✅ Desktop application (PyWebView)  
✅ Real-time multiplayer architecture (ready for multiple clients)  
✅ Player character with WASD movement  
✅ 10 TPS simulation, 60 FPS rendering  
✅ Smooth interpolation  
✅ Entity system  
✅ Spatial partitioning  
✅ WebSocket communication  
✅ UI overlays  

---

## 🎮 **To Play:**

1. Run `setup.bat` (first time only)
2. Run `run.bat`
3. Use **WASD** or **arrow keys** to move your character
4. See your player as a **green circle** in the center
5. Grid world with smooth camera following

---

## 📊 **Performance Characteristics**

### **Backend**
- **Tick Rate**: 10 TPS (100ms per tick)
- **Target Entity Count**: 100-1000 active entities
- **Memory**: ~50-100 MB for typical game state
- **CPU**: Single-threaded simulation loop

### **Frontend**
- **Frame Rate**: 60 FPS (16.6ms per frame)
- **Canvas Resolution**: Full window
- **Network Traffic**: ~1-10 KB/s (delta updates only)
- **Latency**: <50ms on localhost

### **Network Protocol**
- **Transport**: WebSocket (Socket.IO)
- **Update Strategy**: Delta compression
- **Initial State**: Full world on connect
- **Incremental Updates**: Only changed entities

---

## 🔮 **Future Expansion Ideas**

### **Phase 1: Core Gameplay**
- [ ] Combat system (melee, ranged)
- [ ] Inventory management
- [ ] Item system (weapons, armor, consumables)
- [ ] Enemy AI and spawning
- [ ] Death and respawn

### **Phase 2: Party System**
- [ ] Recruit party members
- [ ] Party AI (follow, attack, defend)
- [ ] Formation system
- [ ] Party member equipment
- [ ] Command interface (Rimworld-style)

### **Phase 3: World Simulation**
- [ ] Procedural world generation
- [ ] Day/night cycle
- [ ] Weather system
- [ ] Resource gathering
- [ ] Crafting system
- [ ] Building placement

### **Phase 4: Advanced Features**
- [ ] Pathfinding (A* algorithm)
- [ ] Line-of-sight and fog of war
- [ ] Quest system
- [ ] NPC dialogue
- [ ] Save/load system
- [ ] Settings menu

### **Phase 5: Polish**
- [ ] Sprite graphics (replace circles)
- [ ] Animations
- [ ] Particle effects
- [ ] Sound effects and music
- [ ] Tutorial system
- [ ] Achievement system

---

## 🛠️ **Development Tips**

### **Adding a New Entity Type**
1. Create class in `backend/simulation/` extending `Entity`
2. Override `update()` for custom behavior
3. Override `serialize()` for network data
4. Add rendering logic in `frontend/js/renderer.js`

### **Adding a New Action**
1. Create action class in `backend/simulation/actions.py`
2. Add to `ActionFactory.create()`
3. Add handler in `PlayerCharacter.execute_action()`
4. Add input binding in `frontend/js/input.js`

### **Debugging**
- **Backend**: Check terminal output for Python errors
- **Frontend**: Open browser DevTools (F12) in PyWebView
- **Network**: Monitor WebSocket messages in DevTools
- **Performance**: Use `console.log()` for timing

### **Testing Without Desktop Window**
```bash
python run_browser.py
```
Opens in your default browser for easier debugging.

---

## 📚 **Technology Stack**

### **Backend**
- **Python 3.8+**
- **Flask** - Web framework
- **Flask-SocketIO** - WebSocket support
- **Threading** - Concurrent execution

### **Frontend**
- **HTML5 Canvas** - 2D rendering
- **JavaScript ES6+** - Game logic
- **Socket.IO Client** - Real-time communication
- **CSS3** - Styling

### **Desktop**
- **PyWebView** - Native window wrapper
- **Edge WebView2** (Windows) - Rendering engine

---

## 🐛 **Common Issues & Solutions**

### **Black Screen on Startup**
- **Cause**: GPU acceleration issues
- **Solution**: Disabled in `main.py` with environment variables

### **Port 5000 Already in Use**
- **Cause**: Another application using port
- **Solution**: Change `PORT` in `backend/config.py`

### **Player Not Moving**
- **Cause**: WebSocket not connected
- **Solution**: Check browser console for connection errors

### **Choppy Movement**
- **Cause**: Interpolation not working
- **Solution**: Check `interpolation.js` is loaded

---

## 📖 **Further Reading**

- [Flask Documentation](https://flask.palletsprojects.com/)
- [Socket.IO Documentation](https://socket.io/docs/)
- [PyWebView Documentation](https://pywebview.flowrl.com/)
- [Game Loop Patterns](https://gameprogrammingpatterns.com/game-loop.html)
- [Entity Component System](https://en.wikipedia.org/wiki/Entity_component_system)

---

This is a **solid foundation** for a complex simulation game, ready to expand with combat, inventory, AI, and world simulation features! 🎉
