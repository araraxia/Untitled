/**
 * Character Creation System
 * Modular character creation flow: Race -> Background -> Personality -> Appearance -> Items -> Name
 * Now integrated with backend race and background system
 * Stats are generated server-side after character creation
 */

/**
 * Character creation state
 */
const characterCreationState = {
    currentStep: 'race',
    selectedRace: null,
    selectedBackground: null,
    personality: {},
    appearance: {},
    stats: {},
    items: [],
    characterName: '',
    // Data loaded from backend
    availableRaces: {},
    availableBackgrounds: {}
};

/**
 * Initialize character creation UI
 * @returns {void}
 */
function initCharacterCreation() {
    console.log('[CharacterCreation] Starting character creation');
    characterCreationState.currentStep = 'race';
    
    // Fetch available races from backend
    if (typeof socket !== 'undefined' && socket) {
        socket.emit('request_races');
        socket.once('races_list', (data) => {
            console.log('[CharacterCreation] Received races:', data.races);
            characterCreationState.availableRaces = data.races;
            showCharacterCreationScreen();
        });
        
        socket.once('error', (error) => {
            console.error('[CharacterCreation] Error fetching races:', error);
            alert('Failed to load character creation data. Please refresh.');
        });
    } else {
        console.error('[CharacterCreation] Socket not available');
        alert('Critical Error in initCharacterCreation().');
    }
}

/**
 * Show the main character creation screen
 * @returns {void}
 */
function showCharacterCreationScreen() {
    // Create overlay
    const overlay = document.createElement('div');
    overlay.id = 'character-creation-overlay';
    overlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.95);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 2000;
    `;

    const container = document.createElement('div');
    container.id = 'character-creation-container';
    container.style.cssText = `
        background: #2a2a2a;
        border: 2px solid #4CAF50;
        border-radius: 8px;
        padding: 30px;
        max-width: 800px;
        width: 90%;
        max-height: 80vh;
        overflow-y: auto;
        color: #fff;
    `;

    overlay.appendChild(container);
    document.body.appendChild(overlay);

    renderCurrentStep(container);
}

/**
 * Render the current step of character creation
 * @param {HTMLElement} container - Container to render into
 * @returns {void}
 */
function renderCurrentStep(container) {
    const step = characterCreationState.currentStep;
    
    switch (step) {
        case 'race':
            renderRaceSelection(container);
            break;
        case 'background':
            renderBackgroundSelection(container);
            break;
        case 'personality':
            renderPersonalitySelection(container);
            break;
        case 'appearance':
            renderAppearanceSelection(container);
            break;
        case 'items':
            renderItemSelection(container);
            break;
        case 'name':
            renderNameInput(container);
            break;
        case 'summary':
            renderSummary(container);
            break;
    }
}

/**
 * Render race selection step
 * @param {HTMLElement} container - Container to render into
 * @returns {void}
 */
function renderRaceSelection(container) {
    container.innerHTML = `
        <h2 style="margin: 0 0 10px 0; color: #4CAF50;">Choose Your Race</h2>
        <p style="color: #aaa; margin-bottom: 20px;">Select a race for your character</p>
        <div id="race-options"></div>
    `;

    const raceOptions = container.querySelector('#race-options');
    
    Object.entries(characterCreationState.availableRaces).forEach(([raceId, race]) => {
        const raceCard = document.createElement('div');
        raceCard.className = 'race-card';
        raceCard.style.cssText = `
            padding: 20px;
            margin-bottom: 15px;
            background: #333;
            border: 2px solid ${characterCreationState.selectedRace === raceId ? '#4CAF50' : '#555'};
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s;
        `;

        raceCard.innerHTML = `
            <h3 style="margin: 0 0 10px 0; color: ${characterCreationState.selectedRace === raceId ? '#4CAF50' : '#fff'};">${race.name}</h3>
            <p style="color: #ccc; margin: 0 0 10px 0;">${race.description}</p>
            <p style="color: #aaa; margin: 0; font-size: 12px; font-style: italic;">${race.lore_text}</p>
        `;

        raceCard.addEventListener('mouseenter', () => {
            if (characterCreationState.selectedRace !== raceId) {
                raceCard.style.borderColor = '#888';
            }
        });

        raceCard.addEventListener('mouseleave', () => {
            if (characterCreationState.selectedRace !== raceId) {
                raceCard.style.borderColor = '#555';
            }
        });

        raceCard.addEventListener('click', () => {
            characterCreationState.selectedRace = raceId;
            
            // Request backgrounds for this race
            if (typeof socket !== 'undefined' && socket) {
                socket.emit('request_backgrounds', { race_id: raceId });
                socket.once('backgrounds_list', (data) => {
                    console.log('[CharacterCreation] Received backgrounds:', data.backgrounds);
                    characterCreationState.availableBackgrounds = data.backgrounds;
                    renderRaceSelection(container);
                });
            }
        });

        raceOptions.appendChild(raceCard);
    });

    // Add next button
    if (characterCreationState.selectedRace && Object.keys(characterCreationState.availableBackgrounds).length > 0) {
        const nextButton = document.createElement('button');
        nextButton.textContent = 'Next: Background';
        nextButton.style.cssText = `
            width: 100%;
            padding: 12px;
            margin-top: 20px;
            background: #4CAF50;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
            font-weight: bold;
        `;
        nextButton.addEventListener('click', () => {
            characterCreationState.currentStep = 'background';
            renderCurrentStep(container);
        });
        container.appendChild(nextButton);
    }
}

/**
 * Render background selection step
 * @param {HTMLElement} container - Container to render into
 * @returns {void}
 */
function renderBackgroundSelection(container) {
    const race = characterCreationState.availableRaces[characterCreationState.selectedRace];
    
    container.innerHTML = `
        <h2 style="margin: 0 0 10px 0; color: #4CAF50;">Choose Your Background</h2>
        <p style="color: #aaa; margin-bottom: 20px;">As a ${race.name}, select your background</p>
        <div id="background-options"></div>
    `;

    const backgroundOptions = container.querySelector('#background-options');
    
    // Show all backgrounds available for selected race
    Object.entries(characterCreationState.availableBackgrounds).forEach(([bgName, bg]) => {
        const bgCard = document.createElement('div');
        bgCard.style.cssText = `
            padding: 20px;
            margin-bottom: 15px;
            background: #333;
            border: 2px solid ${characterCreationState.selectedBackground === bgName ? '#4CAF50' : '#555'};
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s;
        `;

        // Build stat bonuses display
        const statBonuses = [];
        const statFields = [
            'additional_strength', 'additional_dexterity', 'additional_intelligence', 
            'additional_willpower', 'additional_charisma', 'additional_perception',
            'additional_endurance', 'additional_luck', 'additional_speed',
            'additional_soul_power', 'additional_combat_sense'
        ];
        
        statFields.forEach(field => {
            if (bg[field] && bg[field] !== 0) {
                const statName = field.replace('additional_', '').replace(/_/g, ' ');
                const value = bg[field];
                const sign = value > 0 ? '+' : '';
                statBonuses.push(`${statName} ${sign}${value}`);
            }
        });

        bgCard.innerHTML = `
            <h3 style="margin: 0 0 10px 0; color: ${characterCreationState.selectedBackground === bgName ? '#4CAF50' : '#fff'};">${bg.display_name || bgName}</h3>
            <p style="color: #ccc; margin: 0 0 10px 0; font-style: italic; font-size: 13px;">${bg.lore_text || 'A mysterious background.'}</p>
            ${statBonuses.length > 0 ? `
                <div style="font-size: 12px; color: #888; margin-top: 10px;">
                    <strong>Bonuses:</strong> ${statBonuses.join(', ')}
                </div>
            ` : ''}
        `;

        bgCard.addEventListener('mouseenter', () => {
            if (characterCreationState.selectedBackground !== bgName) {
                bgCard.style.borderColor = '#888';
            }
        });

        bgCard.addEventListener('mouseleave', () => {
            if (characterCreationState.selectedBackground !== bgName) {
                bgCard.style.borderColor = '#555';
            }
        });

        bgCard.addEventListener('click', () => {
            characterCreationState.selectedBackground = bgName;
            renderBackgroundSelection(container);
        });

        backgroundOptions.appendChild(bgCard);
    });

    addNavigationButtons(container, 'race', 'personality');
}

/**
 * Render personality selection step
 * @param {HTMLElement} container - Container to render into
 * @returns {void}
 */
function renderPersonalitySelection(container) {
    // For now, use a default set of personality traits
    // TODO: Make this configurable per race if needed
    const personalityTraits = ['ambitious', 'curious', 'stubborn', 'loyal', 'cautious', 'brave', 'cunning', 'compassionate'];
    
    container.innerHTML = `
        <h2 style="margin: 0 0 10px 0; color: #4CAF50;">Define Personality</h2>
        <p style="color: #aaa; margin-bottom: 20px;">Select up to 3 personality traits</p>
        <div id="personality-options"></div>
    `;

    const personalityOptions = container.querySelector('#personality-options');
    
    personalityTraits.forEach(trait => {
        const isSelected = characterCreationState.personality[trait] === true;
        const traitBtn = document.createElement('button');
        traitBtn.textContent = trait.charAt(0).toUpperCase() + trait.slice(1);
        traitBtn.style.cssText = `
            padding: 10px 20px;
            margin: 5px;
            background: ${isSelected ? '#4CAF50' : '#555'};
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
        `;

        traitBtn.addEventListener('click', () => {
            const selectedCount = Object.values(characterCreationState.personality).filter(v => v).length;
            
            if (isSelected) {
                characterCreationState.personality[trait] = false;
            } else if (selectedCount < 3) {
                characterCreationState.personality[trait] = true;
            }
            
            renderPersonalitySelection(container);
        });

        personalityOptions.appendChild(traitBtn);
    });

    addNavigationButtons(container, 'background', 'appearance');
}

/**
 * Render appearance selection step
 * @param {HTMLElement} container - Container to render into
 * @returns {void}
 */
function renderAppearanceSelection(container) {
    // Default appearance options for humans
    // TODO: Make this configurable per race if needed
    const appearanceOptions = {
        skinTone: ['pale', 'fair', 'olive', 'tan', 'brown', 'dark'],
        hairColor: ['black', 'brown', 'blonde', 'red', 'gray', 'white'],
        eyeColor: ['brown', 'blue', 'green', 'hazel', 'gray'],
        bodyType: ['slim', 'average', 'athletic', 'stocky', 'heavy']
    };
    
    container.innerHTML = `
        <h2 style="margin: 0 0 10px 0; color: #4CAF50;">Customize Appearance</h2>
        <p style="color: #aaa; margin-bottom: 20px;">Choose your character's appearance</p>
        <div id="appearance-options"></div>
    `;

    const appearanceOptionsContainer = container.querySelector('#appearance-options');
    
    Object.entries(appearanceOptions).forEach(([category, options]) => {
        const categoryDiv = document.createElement('div');
        categoryDiv.style.marginBottom = '20px';
        
        const label = document.createElement('label');
        label.textContent = category.charAt(0).toUpperCase() + category.slice(1).replace(/([A-Z])/g, ' $1');
        label.style.cssText = 'display: block; color: #4CAF50; margin-bottom: 10px; font-weight: bold;';
        
        const select = document.createElement('select');
        select.style.cssText = `
            width: 100%;
            padding: 10px;
            background: #333;
            border: 1px solid #555;
            border-radius: 4px;
            color: #fff;
            font-size: 14px;
        `;
        
        const defaultOption = document.createElement('option');
        defaultOption.value = '';
        defaultOption.textContent = `Select ${label.textContent}...`;
        select.appendChild(defaultOption);
        
        options.forEach(option => {
            const opt = document.createElement('option');
            opt.value = option;
            opt.textContent = option.charAt(0).toUpperCase() + option.slice(1);
            if (characterCreationState.appearance[category] === option) {
                opt.selected = true;
            }
            select.appendChild(opt);
        });
        
        select.addEventListener('change', (e) => {
            characterCreationState.appearance[category] = e.target.value;
        });
        
        categoryDiv.appendChild(label);
        categoryDiv.appendChild(select);
        appearanceOptionsContainer.appendChild(categoryDiv);
    });

    addNavigationButtons(container, 'personality', 'items');
}

/**
 * Render item selection step
 * @param {HTMLElement} container - Container to render into
 * @returns {void}
 */
function renderItemSelection(container) {
    // For now, use a simple default starting inventory
    // TODO: Make this configurable based on race and background
    const startingItems = ['basic_clothes', 'water_flask', 'travel_rations'];
    
    container.innerHTML = `
        <h2 style="margin: 0 0 10px 0; color: #4CAF50;">Starting Equipment</h2>
        <p style="color: #aaa; margin-bottom: 20px;">These items will be in your inventory</p>
        <div id="item-list" style="
            padding: 20px;
            background: #333;
            border-radius: 8px;
        "></div>
    `;

    const itemList = container.querySelector('#item-list');
    
    startingItems.forEach(item => {
        const itemDiv = document.createElement('div');
        itemDiv.style.cssText = `
            padding: 10px;
            margin-bottom: 8px;
            background: #444;
            border-left: 3px solid #4CAF50;
            border-radius: 4px;
            color: #fff;
        `;
        itemDiv.textContent = item.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
        itemList.appendChild(itemDiv);
    });
    
    characterCreationState.items = startingItems;

    addNavigationButtons(container, 'appearance', 'name');
}

/**
 * Render character name input step
 * @param {HTMLElement} container - Container to render into
 * @returns {void}
 */
function renderNameInput(container) {
    container.innerHTML = `
        <h2 style="margin: 0 0 10px 0; color: #4CAF50;">Name Your Character</h2>
        <p style="color: #aaa; margin-bottom: 20px;">Choose a name for your character</p>
        
        <div style="background: #333; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
            <label for="character-name-input" style="display: block; color: #4CAF50; margin-bottom: 10px; font-weight: bold;">
                Character Name:
            </label>
            <input 
                type="text" 
                id="character-name-input" 
                maxlength="30"
                placeholder="Enter character name..."
                value="${characterCreationState.characterName}"
                style="
                    width: 100%;
                    padding: 12px;
                    background: #444;
                    color: #fff;
                    border: 2px solid #555;
                    border-radius: 4px;
                    font-size: 16px;
                    box-sizing: border-box;
                "
            />
            <p style="color: #888; font-size: 12px; margin-top: 8px; margin-bottom: 0;">
                Note: This is your character's name, not your player name. Maximum 30 characters.
            </p>
        </div>
    `;
    
    const input = container.querySelector('#character-name-input');
    input.focus();
    
    input.addEventListener('input', (e) => {
        characterCreationState.characterName = e.target.value.trim();
        // Re-render navigation buttons to update their state
        const existingButtons = container.querySelector('div[style*="display: flex"]');
        if (existingButtons) {
            existingButtons.remove();
        }
        addNavigationButtons(container, 'items', 'summary');
    });
    
    input.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && characterCreationState.characterName.length > 0) {
            characterCreationState.currentStep = 'summary';
            renderCurrentStep(container);
        }
    });

    addNavigationButtons(container, 'items', 'summary');
}

/**
 * Render final summary and confirmation
 * @param {HTMLElement} container - Container to render into
 * @returns {void}
 */
function renderSummary(container) {
    const race = characterCreationState.availableRaces[characterCreationState.selectedRace];
    const background = characterCreationState.availableBackgrounds[characterCreationState.selectedBackground];
    
    container.innerHTML = `
        <h2 style="margin: 0 0 10px 0; color: #4CAF50;">Character Summary</h2>
        <p style="color: #aaa; margin-bottom: 20px;">Review your character before creation</p>
        
        <div style="background: #333; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
            <div style="margin-bottom: 15px;">
                <strong style="color: #4CAF50;">Name:</strong> <span style="color: #fff;">${characterCreationState.characterName}</span>
            </div>
            <div style="margin-bottom: 15px;">
                <strong style="color: #4CAF50;">Race:</strong> <span style="color: #fff;">${race.name}</span>
            </div>
            <div style="margin-bottom: 15px;">
                <strong style="color: #4CAF50;">Background:</strong> <span style="color: #fff;">${background.display_name || characterCreationState.selectedBackground}</span>
            </div>
            <div style="margin-bottom: 15px;">
                <strong style="color: #4CAF50;">Personality:</strong> 
                <span style="color: #fff;">${Object.entries(characterCreationState.personality)
                    .filter(([_, v]) => v)
                    .map(([k, _]) => k)
                    .join(', ') || 'None selected'}</span>
            </div>
            <div style="margin-bottom: 15px;">
                <strong style="color: #4CAF50;">Appearance:</strong>
                <div style="color: #fff; margin-left: 20px; margin-top: 5px;">
                    ${Object.entries(characterCreationState.appearance).length > 0 
                        ? Object.entries(characterCreationState.appearance)
                            .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v}`)
                            .join('<br>')
                        : 'Default appearance'}
                </div>
            </div>
            <div>
                <strong style="color: #4CAF50;">Stats:</strong>
                <div style="color: #fff; margin-left: 20px; margin-top: 5px;">
                    ${Object.entries(characterCreationState.stats)
                        .map(([k, v]) => {
                            const displayName = k.replace(/_/g, ' ').split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
                            return `${displayName}: ${v}`;
                        })
                        .join('<br>')}
                </div>
            </div>
        </div>
        
        <div style="display: flex; gap: 10px;">
            <button id="back-btn" style="
                flex: 1;
                padding: 12px;
                background: #666;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 16px;
            ">Back</button>
            <button id="create-btn" style="
                flex: 2;
                padding: 12px;
                background: #4CAF50;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 16px;
                font-weight: bold;
            ">Create Character</button>
        </div>
    `;
    
    container.querySelector('#back-btn').addEventListener('click', () => {
        characterCreationState.currentStep = 'name';
        renderCurrentStep(container);
    });
    
    container.querySelector('#create-btn').addEventListener('click', () => {
        finalizeCharacterCreation();
    });
}

/**
 * Add navigation buttons to a step
 * @param {HTMLElement} container - Container to add buttons to
 * @param {string} prevStep - Previous step name
 * @param {string} nextStep - Next step name
 * @returns {void}
 */
function addNavigationButtons(container, prevStep, nextStep) {
    const canProceed = checkStepComplete(characterCreationState.currentStep);
    
    const buttonContainer = document.createElement('div');
    buttonContainer.style.cssText = 'display: flex; gap: 10px; margin-top: 20px;';
    
    const backBtn = document.createElement('button');
    backBtn.textContent = 'Back';
    backBtn.style.cssText = `
        flex: 1;
        padding: 12px;
        background: #666;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 16px;
    `;
    backBtn.addEventListener('click', () => {
        characterCreationState.currentStep = prevStep;
        renderCurrentStep(container);
    });
    
    const nextBtn = document.createElement('button');
    nextBtn.textContent = `Next: ${nextStep.charAt(0).toUpperCase() + nextStep.slice(1)}`;
    nextBtn.style.cssText = `
        flex: 2;
        padding: 12px;
        background: ${canProceed ? '#4CAF50' : '#555'};
        color: white;
        border: none;
        border-radius: 4px;
        cursor: ${canProceed ? 'pointer' : 'not-allowed'};
        font-size: 16px;
        font-weight: bold;
    `;
    nextBtn.disabled = !canProceed;
    nextBtn.addEventListener('click', () => {
        if (canProceed) {
            characterCreationState.currentStep = nextStep;
            renderCurrentStep(container);
        }
    });
    
    buttonContainer.appendChild(backBtn);
    buttonContainer.appendChild(nextBtn);
    container.appendChild(buttonContainer);
}

/**
 * Check if current step is complete
 * @param {string} step - Step to check
 * @returns {boolean}
 */
function checkStepComplete(step) {
    switch (step) {
        case 'race':
            return characterCreationState.selectedRace !== null;
        case 'background':
            return characterCreationState.selectedBackground !== null;
        case 'personality':
            return Object.values(characterCreationState.personality).filter(v => v).length > 0;
        case 'appearance':
            // For now, appearance is optional - always return true
            // TODO: Make this check required fields if appearance becomes mandatory
            return true;
        case 'items':
            return true; // Items always valid
        case 'name':
            return characterCreationState.characterName.length > 0;
        default:
            return false;
    }
}

/**
 * Finalize character creation and send to server
 * @returns {void}
 */
function finalizeCharacterCreation() {
    console.log('[CharacterCreation] Finalizing character:', characterCreationState);
    
    // Show loading overlay
    const container = document.getElementById('character-creation-container');
    container.innerHTML = `
        <div style="text-align: center; padding: 40px;">
            <h2 style="margin: 0 0 20px 0; color: #4CAF50;">Creating Character...</h2>
            <p style="color: #aaa; margin-bottom: 30px;">Please wait while your character is being created.</p>
            <div style="
                border: 4px solid #333;
                border-top: 4px solid #4CAF50;
                border-radius: 50%;
                width: 60px;
                height: 60px;
                animation: spin 1s linear infinite;
                margin: 0 auto;
            "></div>
            <style>
                @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                }
            </style>
        </div>
    `;
    
    const characterData = {
        player_name: characterCreationState.characterName,
        race_id: characterCreationState.selectedRace,
        background_name: characterCreationState.selectedBackground,
        personality: Object.entries(characterCreationState.personality)
            .filter(([_, v]) => v)
            .map(([k, _]) => k),
        appearance: characterCreationState.appearance,
        items: characterCreationState.items
    };
    
    // Send to server via socket and wait for response
    if (window.socket && window.socket.connected) {
        window.socket.emit('new_character', characterData);
        console.log('[CharacterCreation] Sent character data to server:', characterData);
        // Server will respond with 'character_created' event when done
    } else {
        console.error('[CharacterCreation] Socket not connected');
        alert('Connection error. Please refresh and try again.');
        return;
    }
}
