/**
 * A class for managing and rendering sprite sheets.
 * Handles loading sprite sheet images and drawing individual frames from the sheet.
 */
class SpriteSheet {
    /**
     * Creates a new SpriteSheet instance.
     * @param {string} imagePath - Path to the sprite sheet image file
     * @param {number} frameWidth - Width of each frame in pixels
     * @param {number} frameHeight - Height of each frame in pixels
     * @param {number} columns - Number of columns in the sprite sheet
     * @param {number} rows - Number of rows in the sprite sheet
     */
    constructor(imagePath, frameWidth, frameHeight, columns, rows) {
        console.log('[SpriteSheet] Constructor called - path:', imagePath, 'frameSize:', frameWidth + 'x' + frameHeight, 'grid:', columns + 'x' + rows);
        this.image = new Image();
        this.image.src = imagePath;
        this.frameWidth = frameWidth;
        this.frameHeight = frameHeight;
        this.columns = columns;
        this.rows = rows;
        this.loaded = false;
        
        this.image.onload = () => {
            this.loaded = true;
        };
    }
    
    /**
     * Draws a specific frame from the sprite sheet onto a canvas context.
     * @param {CanvasRenderingContext2D} ctx - The canvas 2D rendering context
     * @param {number} frameIndex - The index of the frame to draw (0-based, left-to-right, top-to-bottom)
     * @param {number} x - The x-coordinate on the canvas where the frame should be drawn
     * @param {number} y - The y-coordinate on the canvas where the frame should be drawn
     * @param {boolean} [flipX=false] - Whether to flip the frame horizontally
     */
    drawFrame(ctx, frameIndex, x, y, flipX = false) {
        console.log('[SpriteSheet] drawFrame called - frameIndex:', frameIndex, 'pos:', x + ',' + y, 'flipX:', flipX);
        if (!this.loaded) return;
        
        const column = frameIndex % this.columns;
        const row = Math.floor(frameIndex / this.columns);
        
        const sourceX = column * this.frameWidth;
        const sourceY = row * this.frameHeight;
        
        ctx.save();
        
        if (flipX) {
            ctx.translate(x + this.frameWidth, y);
            ctx.scale(-1, 1);
            ctx.drawImage(
                this.image,
                sourceX, sourceY, this.frameWidth, this.frameHeight,
                0, 0, this.frameWidth, this.frameHeight
            );
        } else {
            ctx.drawImage(
                this. image,
                sourceX, sourceY, this.frameWidth, this.frameHeight,
                x, y, this.frameWidth, this.frameHeight
            );
        }
        
        ctx.restore();
    }
}
