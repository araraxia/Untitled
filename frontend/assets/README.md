# Game Assets

This directory contains all game assets including fonts, images, audio, and data files.

## Directory Structure

```
assets/
├── fonts/          # Font files (.ttf, .woff, .woff2)
├── images/         # Image assets
│   ├── sprites/    # Character and object sprites
│   └── ui/         # UI elements and icons
├── audio/          # Sound and music
│   ├── sfx/        # Sound effects
│   └── music/      # Background music
└── data/           # JSON game data files
```

## Usage

### In CSS (Fonts)
```css
@font-face {
    font-family: 'GameFont';
    src: url('/assets/fonts/game-font.ttf') format('truetype');
}
```

### In JavaScript (Images)
```javascript
const playerImage = new Image();
playerImage.src = '/assets/images/sprites/player.png';
```

### In JavaScript (Audio)
```javascript
const jumpSound = new Audio('/assets/audio/sfx/jump.mp3');
jumpSound.play();
```

### In JavaScript (Data)
```javascript
fetch('/assets/data/items.json')
    .then(response => response.json())
    .then(data => console.log(data));
```

## Supported Formats

### Fonts
- TrueType (.ttf)
- Web Open Font Format (.woff, .woff2)

### Images
- PNG (recommended for sprites with transparency)
- JPEG (for backgrounds)
- SVG (for scalable UI elements)
- WebP (modern format with better compression)

### Audio
- MP3 (best browser support)
- OGG (open format)
- WAV (uncompressed, high quality)

### Data
- JSON (game configuration, item definitions, etc.)
