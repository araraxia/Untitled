/**
 * Represents a single animation sequence
 */
class Animation {
    /**
     * Creates a new Animation
     * @param {string} name - Name of the animation
     * @param {number} startFrame - Starting frame index in the sprite sheet
     * @param {number} frameCount - Total number of frames in this animation
     * @param {number} frameTime - Duration of each frame in milliseconds
     * @param {boolean} [loop=true] - Whether the animation should loop
     */
    constructor(name, startFrame, frameCount, frameTime, loop = true) {
        console.log('[Animation] Constructor called - name:', name, 'startFrame:', startFrame, 'frameCount:', frameCount, 'frameTime:', frameTime, 'loop:', loop);
        this.name = name;
        this.startFrame = startFrame;
        this.frameCount = frameCount;
        this.frameTime = frameTime;
        this.loop = loop;
    }
}

/**
 * Controls and manages sprite animations
 * Handles animation playback, frame updates, and rendering
 */
class AnimationController {
    /**
     * Creates a new AnimationController
     * @param {SpriteSheet} spriteSheet - The sprite sheet to use for rendering
     * @param {Object.<string, Animation>} animations - Object mapping animation names to Animation instances
     */
    constructor(spriteSheet, animations) {
        console.log('[AnimationController] Constructor called - animationCount:', Object.keys(animations).length);
        this.spriteSheet = spriteSheet;
        this.animations = animations; // Object with animation names as keys
        this.currentAnimation = null;
        this.currentFrame = 0;
        this.timeAccumulator = 0;
    }
    
    /**
     * Play a specific animation by name
     * @param {string} animationName - Name of the animation to play
     */
    play(animationName) {
        console.log('[AnimationController] play called - animationName:', animationName);
        if (this.currentAnimation?.name === animationName) return;
        
        this.currentAnimation = this.animations[animationName];
        if (this.currentAnimation) {
            this.currentFrame = this.currentAnimation.startFrame;
            this.timeAccumulator = 0;
        }
    }
    
    /**
     * Update the animation state based on elapsed time
     * @param {number} deltaTime - Time elapsed since last update in milliseconds
     */
    update(deltaTime) {
        console.log('[AnimationController] update called - deltaTime:', deltaTime, 'currentFrame:', this.currentFrame);
        if (!this.currentAnimation) return;
        
        this.timeAccumulator += deltaTime;
        
        if (this.timeAccumulator >= this.currentAnimation.frameTime) {
            this.timeAccumulator -= this.currentAnimation.frameTime;
            this.currentFrame++;
            
            const maxFrame = this.currentAnimation.startFrame + 
                           this.currentAnimation.frameCount;
            
            if (this.currentFrame >= maxFrame) {
                if (this.currentAnimation.loop) {
                    this.currentFrame = this.currentAnimation.startFrame;
                } else {
                    this.currentFrame = maxFrame - 1;
                }
            }
        }
    }
    
    /**
     * Draw the current animation frame
     * @param {CanvasRenderingContext2D} ctx - The canvas 2D rendering context
     * @param {number} x - X position to draw at
     * @param {number} y - Y position to draw at
     * @param {boolean} [flipX=false] - Whether to flip horizontally
     */
    draw(ctx, x, y, flipX = false) {
        console.log('[AnimationController] draw called - pos:', x + ',' + y, 'frame:', this.currentFrame, 'flipX:', flipX);
        this.spriteSheet.drawFrame(ctx, this.currentFrame, x, y, flipX);
    }
}
