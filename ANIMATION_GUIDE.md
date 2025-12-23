# Quick Reference: Adding New Animations

## Adding a New Animation Type

### 1. Add to JSON ([assets/data/human_animations.json](assets/data/human_animations.json))

```json
{
  "new_animation_name": {
    "default_sprite_sheet": "sprite_filename.png",
    "default_sprite_version": "v00",
    "duration_type": "fixed",
    "frame_width": 64,
    "frame_height": 64,
    "frame_count": 8,
    "frame_duration": 150,
    "down": {
      "start_frame_index": 0
    },
    "up": {
      "start_frame_index": 8
    },
    "left": {
      "start_frame_index": 16,
      "flip_x": true
    },
    "right": {
      "start_frame_index": 16,
      "flip_x": false
    }
  }
}
```

### 2. Update Entity State Logic

In your game logic, set the entity state that should trigger the animation:

```javascript
// Example: Adding an "attack" animation
if (entity.isAttacking) {
    entity.state = 'attacking';  // EntityRenderer will look for 'attack' animation
    entity.facing = 'down';       // Direction
}
```

### 3. Optional: Custom Animation Selection

If you need custom logic, modify [entityRenderer.js](js/entityRenderer.js):

```javascript
updateEntityAnimation(entityId, entity, deltaTime) {
    // Custom logic here
    let animationType = 'stand';
    if (entity.state === 'moving') animationType = 'walk';
    if (entity.state === 'attacking') animationType = 'attack';
    if (entity.state === 'casting') animationType = 'cast';
    
    // Rest stays the same...
}
```

## Animation State Mapping

Current mappings in EntityRenderer:
- `entity.state === 'moving'` → 'walk' animation
- `entity.state !== 'moving'` → 'stand' animation

To add more:
```javascript
// In EntityRenderer.updateEntityAnimation()
let animationType;
switch(entity.state) {
    case 'moving': animationType = 'walk'; break;
    case 'attacking': animationType = 'attack'; break;
    case 'casting': animationType = 'cast'; break;
    case 'dead': animationType = 'death'; break;
    default: animationType = 'stand';
}
```

## Triggering Animations from Input

### Current Pattern (State-Based):
```javascript
// In input.js or your game logic
if (keys['w']) {
    // Set entity state
    gameState.player.state = 'moving';
    gameState.player.facing = 'up';
    
    // Send to server
    sendPlayerAction('move', {
        direction: { x: 0, y: -1 },
        facing: 'up'
    });
}

// When key released
if (!keys['w']) {
    gameState.player.state = 'idle';
    // facing stays the same
}
```

### For Action Animations (Attack, Cast, etc.):
```javascript
// In input.js
if (keys[' ']) { // Spacebar for attack
    gameState.player.state = 'attacking';
    sendPlayerAction('attack', {
        facing: gameState.player.facing
    });
    
    // Reset to idle after animation completes
    setTimeout(() => {
        if (gameState.player.state === 'attacking') {
            gameState.player.state = 'idle';
        }
    }, 500); // Match animation duration
}
```

## Variable Frame Durations

The JSON format supports variable frame durations:

```json
{
  "complex_animation": {
    "duration_type": "variable",
    "frame_duration": [100, 80, 120, 100, 90, 110, 100, 150],
    "frame_count": 8
  }
}
```

**Note**: Currently EntityRenderer averages these values. To fully implement:
1. Modify AnimationController to accept array of frame durations
2. Update frame timing logic to use current frame's specific duration

## Sprite Sheet Layout

Standard layout (8x8 grid):
```
Row 0: Stand animations (down, up, left, right frames 0-7)
Row 1: Stand animations continued (frames 8-15)
Row 2: Stand animations continued (frames 16-23)
Row 3: Stand animations continued (frames 24-31)
Row 4-7: Walk animations (down starts at 32, up at 40, left/right at 48)
```

Frame index calculation:
- Frame 0 = Row 0, Column 0
- Frame 8 = Row 1, Column 0
- Frame 32 = Row 4, Column 0

## Testing Your Animation

1. Add animation to JSON
2. Place sprite sheet in `assets/images/sprites/human/base/`
3. Update entity state in console:
   ```javascript
   gameState.player.state = 'your_animation_name';
   ```
4. Watch it play!

## Common Issues

**Animation not playing:**
- Check console for "Animation type 'name' not found"
- Verify JSON syntax is valid
- Check sprite sheet path is correct

**Wrong frames showing:**
- Verify start_frame_index in JSON
- Check sprite sheet has enough frames
- Verify columns/rows in SpriteSheet constructor (default 8x8)

**Animation too fast/slow:**
- Adjust frame_duration in JSON (milliseconds per frame)
- Lower = faster, higher = slower

**Facing wrong direction:**
- Check flip_x settings in JSON
- Verify entity.facing is being set correctly
