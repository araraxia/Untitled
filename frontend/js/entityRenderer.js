/**
 * EntityRenderer - Handles rendering of game entities with sprite animations
 * Manages sprite sheets, animations, and visual effects for all entity types
 */
class EntityRenderer {
    /**
     * Creates a new EntityRenderer instance
     * @param {CanvasRenderingContext2D} ctx - The canvas 2D rendering context
     */
    constructor(ctx) {
        console.log('[EntityRenderer] Constructor called');
        this.ctx = ctx;
        this.spriteSheets = {};
        this.animationControllers = {};
        this.animationData = null;
        this.loadingComplete = false;
    }

    /**
     * Load animation data from a JSON file
     * @param {string} animationDataPath - Path to the animation JSON file
     * @returns {Promise<void>}
     */
    async loadAnimationData(animationDataPath) {
        console.log('[EntityRenderer] loadAnimationData called - path:', animationDataPath);
        try {
            const response = await fetch(animationDataPath);
            this.animationData = await response.json();
            console.log('Animation data loaded:', animationDataPath);
            
            // Preload sprite sheets for each animation type
            await this.preloadSpriteAnimations();
            this.loadingComplete = true;
        } catch (error) {
            console.error('Failed to load animation data:', error);
        }
    }

    /**
     * Preload all sprite animations defined in animation data
     * @returns {Promise<void>}
     */
    async preloadSpriteAnimations() {
        console.log('[EntityRenderer] preloadSpriteSheets called');
        const promises = [];
        // Iterate over each animation type and load its sprite sheet
        for (const [animName, animConfig] of Object.entries(this.animationData)) {
            if (animName === 'base_model_path') continue;
            
            const spritePath = this.animationData.base_model_path + "/" + animConfig.default_sprite_version + '/' + animConfig.default_sprite_sheet;
            
            // Create sprite sheet if not already loaded
            if (!this.spriteSheets[animName]) {
                this.spriteSheets[animName] = new SpriteSheet(
                    'assets/' + spritePath,
                    animConfig.frame_width,
                    animConfig.frame_height,
                    8, // columns - standard 8 columns for character sprites
                    8  // rows - standard 8 rows for character sprites
                );
                
                // Wait for sprite sheet to load
                promises.push(new Promise((resolve) => {
                    const checkLoaded = () => {
                        if (this.spriteSheets[animName].loaded) {
                            resolve();
                        } else {
                            setTimeout(checkLoaded, 50);
                        }
                    };
                    checkLoaded();
                }));
            }
        }
        
        await Promise.all(promises);
        console.log('All sprite sheets loaded');
    }

    /**
     * Get or create an animation controller for an entity
     * @param {string} entityId - Unique identifier for the entity
     * @param {string} animationType - Type of animation (e.g., 'stand', 'walk')
     * @returns {AnimationController}
     */
    getAnimationController(entityId, animationType = 'stand') {
        console.log('[EntityRenderer] getAnimationController called - entityId:', entityId, 'animationType:', animationType);
        const controllerId = `${entityId}_${animationType}`;
        
        if (!this.animationControllers[controllerId]) {
            const animConfig = this.animationData[animationType];
            if (!animConfig) {
                console.warn(`Animation type '${animationType}' not found`);
                return null;
            }
            
            const spriteSheet = this.spriteSheets[animationType];
            if (!spriteSheet) {
                console.warn(`Sprite sheet for '${animationType}' not loaded`);
                return null;
            }
            
            // Create animations for all directions
            const animations = {};
            const directions = ['down', 'up', 'left', 'right'];
            
            directions.forEach(dir => {
                const dirConfig = animConfig[dir];
                if (dirConfig) {
                    // Handle frame duration (fixed or variable)
                    let frameDuration;
                    if (animConfig.duration_type === 'variable' && Array.isArray(animConfig.frame_duration)) {
                        // For variable duration, use average for now (can be enhanced later)
                        frameDuration = animConfig.frame_duration.reduce((a, b) => a + b, 0) / animConfig.frame_duration.length;
                    } else {
                        frameDuration = animConfig.frame_duration;
                    }
                    
                    const animName = `${animationType}_${dir}`;
                    animations[animName] = new Animation(
                        animName,
                        dirConfig.start_frame_index,
                        animConfig.frame_count,
                        frameDuration,
                        true // loop
                    );
                }
            });
            
            this.animationControllers[controllerId] = new AnimationController(spriteSheet, animations);
        }
        
        return this.animationControllers[controllerId];
    }

    /**
     * Update entity animation state based on entity data
     * @param {string} entityId - Unique identifier for the entity
     * @param {Object} entity - Entity data object
     * @param {number} deltaTime - Time elapsed since last update (milliseconds)
     */
    updateEntityAnimation(entityId, entity, deltaTime) {
        console.log('[EntityRenderer] updateEntityAnimation called - entityId:', entityId, 'state:', entity.state, 'deltaTime:', deltaTime);
        // Determine animation type based on entity state
        const animationType = entity.state === 'moving' ? 'walk' : 'stand';
        const direction = entity.facing || 'down';
        
        // Get or create animation controller
        const controller = this.getAnimationController(entityId, animationType);
        if (!controller) return;
        
        // Play the appropriate direction animation (use full animation name)
        const animationName = `${animationType}_${direction}`;
        controller.play(animationName);
        
        // Update animation
        controller.update(deltaTime);
        
        // Store controller reference for drawing
        entity._animController = controller;
        entity._animType = animationType;
    }

    /**
     * Draw a single entity with its current animation
     * @param {Object} entity - Entity data object
     * @param {Object} camera - Camera position {x, y}
     */
    drawEntity(entity, camera) {
        console.log('[EntityRenderer] drawEntity called - entityId:', entity.id, 'loadingComplete:', this.loadingComplete);
        if (!this.loadingComplete) {
            // Fallback to simple circle if animations not loaded
            this.drawEntityFallback(entity, camera);
            return;
        }

        // Use interpolated position for smooth movement
        const x = (entity.displayX || entity.x) - camera.x;
        const y = (entity.displayY || entity.y) - camera.y;
        
        // Draw using animation controller if available
        if (entity._animController) {
            const animConfig = this.animationData[entity._animType];
            const direction = entity.facing || 'down';
            const dirConfig = animConfig?.[direction];
            const flipX = dirConfig?.flip_x || false;
            
            // Center the sprite on the entity position
            const drawX = x - animConfig.frame_width / 2;
            const drawY = y - animConfig.frame_height / 2;
            
            entity._animController.draw(this.ctx, drawX, drawY, flipX);
            
            // Draw state indicator
            if (entity.state === 'moving') {
                this.ctx.strokeStyle = '#FFC107';
                this.ctx.lineWidth = 2;
                this.ctx.beginPath();
                this.ctx.arc(x, y, 18, 0, Math.PI * 2);
                this.ctx.stroke();
            }
        } else {
            // Fallback if animation controller not set up
            this.drawEntityFallback(entity, camera);
        }
        
        // Draw health bar if HP is defined
        this.drawHealthBar(entity, x, y);
        
        // Draw entity ID
        this.drawEntityLabel(entity, x, y);
    }

    /**
     * Draw entity as a simple circle (fallback when sprites unavailable)
     * @param {Object} entity - Entity data object
     * @param {Object} camera - Camera position {x, y}
     */
    drawEntityFallback(entity, camera) {
        console.log('[EntityRenderer] drawEntityFallback called - entityId:', entity.id);
        const x = (entity.displayX || entity.x) - camera.x;
        const y = (entity.displayY || entity.y) - camera.y;
        
        this.ctx.beginPath();
        this.ctx.arc(x, y, 16, 0, Math.PI * 2);
        this.ctx.fillStyle = entity.id?.startsWith('player_') ? '#4CAF50' : '#2196F3';
        this.ctx.fill();
        
        // Draw state indicator
        if (entity.state === 'moving') {
            this.ctx.strokeStyle = '#FFC107';
            this.ctx.lineWidth = 2;
            this.ctx.stroke();
        }
    }

    /**
     * Draw health bar above entity
     * @param {Object} entity - Entity data object
     * @param {number} x - Screen X position
     * @param {number} y - Screen Y position
     */
    drawHealthBar(entity, x, y) {
        console.log('[EntityRenderer] drawHealthBar called - entityId:', entity.id, 'hp:', entity.hp, 'max_hp:', entity.max_hp);
        if (entity.hp === undefined) return;
        
        const barWidth = 32;
        const barHeight = 4;
        const barX = x - barWidth / 2;
        const barY = y - 32; // Position above entity
        
        // Background
        this.ctx.fillStyle = '#333';
        this.ctx.fillRect(barX, barY, barWidth, barHeight);
        
        // Health
        const healthPercent = entity.hp / entity.max_hp;
        this.ctx.fillStyle = healthPercent > 0.5 ? '#4CAF50' : '#F44336';
        this.ctx.fillRect(barX, barY, barWidth * healthPercent, barHeight);
    }

    /**
     * Draw entity ID label
     * @param {Object} entity - Entity data object
     * @param {number} x - Screen X position
     * @param {number} y - Screen Y position
     */
    drawEntityLabel(entity, x, y) {
        console.log('[EntityRenderer] drawEntityLabel called - entityId:', entity.id);
        this.ctx.fillStyle = '#fff';
        this.ctx.font = '10px Arial';
        this.ctx.textAlign = 'center';
        this.ctx.fillText(entity.id, x, y + 35);
    }

    /**
     * Update and draw all entities in the game state
     * @param {Object} gameState - Current game state
     * @param {number} deltaTime - Time elapsed since last frame (milliseconds)
     */
    renderEntities(gameState, deltaTime) {
        console.log('[EntityRenderer] renderEntities called - entityCount:', Object.keys(gameState.entities).length, 'deltaTime:', deltaTime);
        // Update all entity animations
        for (const [entityId, entity] of Object.entries(gameState.entities)) {
            this.updateEntityAnimation(entityId, entity, deltaTime);
        }
        
        // Draw all entities
        for (const [entityId, entity] of Object.entries(gameState.entities)) {
            this.drawEntity(entity, gameState.camera);
        }
    }
}
