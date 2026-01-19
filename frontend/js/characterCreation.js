/**
 * Character Creation System
 * Modular character creation flow: Race -> Background -> Personality -> Appearance -> Stats -> Items
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
    items: []
};

/**
 * Race definitions - modular system for adding new races
 */
const RACES = {
    human: {
        id: 'human',
        name: 'Human',
        description: 'Versatile and adaptable, humans are the most common race.',
        backgrounds: ['soldier', 'merchant', 'farmer', 'scholar', 'craftsman'],
        personalityTraits: ['ambitious', 'curious', 'stubborn', 'loyal', 'cautious'],
        appearanceOptions: {
            skinTone: ['pale', 'fair', 'olive', 'tan', 'brown', 'dark'],
            hairColor: ['black', 'brown', 'blonde', 'red', 'gray', 'white'],
            eyeColor: ['brown', 'blue', 'green', 'hazel', 'gray'],
            bodyType: ['slim', 'average', 'athletic', 'stocky', 'heavy']
        },
        statModifiers: {
            strength: 0,
            dexterity: 0,
            constitution: 0,
            intelligence: 0,
            wisdom: 0,
            charisma: 0
        },
        baseStats: {
            strength: 10,
            dexterity: 10,
            constitution: 10,
            intelligence: 10,
            wisdom: 10,
            charisma: 10
        },
        startingItems: ['basic_clothes', 'bread', 'water_flask']
    }
    // Additional races can be added here following the same structure
};

/**
 * Background definitions - modular system
 */
const BACKGROUNDS = {
    soldier: {
        id: 'soldier',
        name: 'Soldier',
        description: 'Trained in combat and military discipline.',
        statBonuses: { strength: 2, constitution: 1 },
        startingItems: ['sword', 'shield', 'leather_armor']
    },
    merchant: {
        id: 'merchant',
        name: 'Merchant',
        description: 'Skilled in trade and persuasion.',
        statBonuses: { charisma: 2, intelligence: 1 },
        startingItems: ['coin_purse', 'fine_clothes', 'ledger']
    },
    farmer: {
        id: 'farmer',
        name: 'Farmer',
        description: 'Hardworking and resilient.',
        statBonuses: { constitution: 2, wisdom: 1 },
        startingItems: ['hoe', 'seeds', 'simple_clothes']
    },
    scholar: {
        id: 'scholar',
        name: 'Scholar',
        description: 'Learned and wise, knowledgeable in many subjects.',
        statBonuses: { intelligence: 2, wisdom: 1 },
        startingItems: ['book', 'quill', 'ink', 'parchment']
    },
    craftsman: {
        id: 'craftsman',
        name: 'Craftsman',
        description: 'Skilled artisan with steady hands.',
        statBonuses: { dexterity: 2, intelligence: 1 },
        startingItems: ['tools', 'crafting_materials', 'workshop_key']
    }
};

/**
 * Initialize character creation UI
 * @returns {void}
 */
function initCharacterCreation() {
    console.log('[CharacterCreation] Starting character creation');
    characterCreationState.currentStep = 'race';
    showCharacterCreationScreen();
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
        case 'stats':
            renderStatSelection(container);
            break;
        case 'items':
            renderItemSelection(container);
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
    
    Object.values(RACES).forEach(race => {
        const raceCard = document.createElement('div');
        raceCard.className = 'race-card';
        raceCard.style.cssText = `
            padding: 20px;
            margin-bottom: 15px;
            background: #333;
            border: 2px solid ${characterCreationState.selectedRace === race.id ? '#4CAF50' : '#555'};
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s;
        `;

        raceCard.innerHTML = `
            <h3 style="margin: 0 0 10px 0; color: ${characterCreationState.selectedRace === race.id ? '#4CAF50' : '#fff'};">${race.name}</h3>
            <p style="color: #ccc; margin: 0;">${race.description}</p>
        `;

        raceCard.addEventListener('mouseenter', () => {
            if (characterCreationState.selectedRace !== race.id) {
                raceCard.style.borderColor = '#888';
            }
        });

        raceCard.addEventListener('mouseleave', () => {
            if (characterCreationState.selectedRace !== race.id) {
                raceCard.style.borderColor = '#555';
            }
        });

        raceCard.addEventListener('click', () => {
            characterCreationState.selectedRace = race.id;
            renderRaceSelection(container);
        });

        raceOptions.appendChild(raceCard);
    });

    // Add next button
    if (characterCreationState.selectedRace) {
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
    const race = RACES[characterCreationState.selectedRace];
    
    container.innerHTML = `
        <h2 style="margin: 0 0 10px 0; color: #4CAF50;">Choose Your Background</h2>
        <p style="color: #aaa; margin-bottom: 20px;">As a ${race.name}, select your background</p>
        <div id="background-options"></div>
    `;

    const backgroundOptions = container.querySelector('#background-options');
    
    // Only show backgrounds available for selected race
    race.backgrounds.forEach(bgId => {
        const bg = BACKGROUNDS[bgId];
        const bgCard = document.createElement('div');
        bgCard.style.cssText = `
            padding: 20px;
            margin-bottom: 15px;
            background: #333;
            border: 2px solid ${characterCreationState.selectedBackground === bg.id ? '#4CAF50' : '#555'};
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s;
        `;

        bgCard.innerHTML = `
            <h3 style="margin: 0 0 10px 0; color: ${characterCreationState.selectedBackground === bg.id ? '#4CAF50' : '#fff'};">${bg.name}</h3>
            <p style="color: #ccc; margin: 0 0 10px 0;">${bg.description}</p>
            <div style="font-size: 12px; color: #888;">
                <strong>Bonuses:</strong> ${Object.entries(bg.statBonuses).map(([stat, bonus]) => `${stat} +${bonus}`).join(', ')}
            </div>
        `;

        bgCard.addEventListener('mouseenter', () => {
            if (characterCreationState.selectedBackground !== bg.id) {
                bgCard.style.borderColor = '#888';
            }
        });

        bgCard.addEventListener('mouseleave', () => {
            if (characterCreationState.selectedBackground !== bg.id) {
                bgCard.style.borderColor = '#555';
            }
        });

        bgCard.addEventListener('click', () => {
            characterCreationState.selectedBackground = bg.id;
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
    const race = RACES[characterCreationState.selectedRace];
    
    container.innerHTML = `
        <h2 style="margin: 0 0 10px 0; color: #4CAF50;">Define Personality</h2>
        <p style="color: #aaa; margin-bottom: 20px;">Select up to 3 personality traits</p>
        <div id="personality-options"></div>
    `;

    const personalityOptions = container.querySelector('#personality-options');
    
    race.personalityTraits.forEach(trait => {
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
    const race = RACES[characterCreationState.selectedRace];
    
    container.innerHTML = `
        <h2 style="margin: 0 0 10px 0; color: #4CAF50;">Customize Appearance</h2>
        <p style="color: #aaa; margin-bottom: 20px;">Choose your character's appearance</p>
        <div id="appearance-options"></div>
    `;

    const appearanceOptions = container.querySelector('#appearance-options');
    
    Object.entries(race.appearanceOptions).forEach(([category, options]) => {
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
        appearanceOptions.appendChild(categoryDiv);
    });

    addNavigationButtons(container, 'personality', 'stats');
}

/**
 * Render stat selection step
 * @param {HTMLElement} container - Container to render into
 * @returns {void}
 */
function renderStatSelection(container) {
    const race = RACES[characterCreationState.selectedRace];
    const background = BACKGROUNDS[characterCreationState.selectedBackground];
    
    // Initialize stats if not already set
    if (Object.keys(characterCreationState.stats).length === 0) {
        characterCreationState.stats = { ...race.baseStats };
    }
    
    container.innerHTML = `
        <h2 style="margin: 0 0 10px 0; color: #4CAF50;">Allocate Stats</h2>
        <p style="color: #aaa; margin-bottom: 10px;">Distribute points among your character's attributes</p>
        <p style="color: #888; margin-bottom: 20px; font-size: 12px;">
            Base: ${race.name} | Background: ${background.name} (bonuses already applied)
        </p>
        <div id="stat-options"></div>
    `;

    const statOptions = container.querySelector('#stat-options');
    
    Object.entries(characterCreationState.stats).forEach(([stat, value]) => {
        const bgBonus = background.statBonuses[stat] || 0;
        const raceModifier = race.statModifiers[stat] || 0;
        const totalValue = value + bgBonus + raceModifier;
        
        const statRow = document.createElement('div');
        statRow.style.cssText = `
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 10px;
            margin-bottom: 10px;
            background: #333;
            border-radius: 4px;
        `;
        
        statRow.innerHTML = `
            <div style="flex: 1;">
                <strong style="color: #4CAF50;">${stat.charAt(0).toUpperCase() + stat.slice(1)}:</strong>
                <span style="color: #fff; margin-left: 10px;">${totalValue}</span>
                ${bgBonus > 0 ? `<span style="color: #888; font-size: 12px;"> (+${bgBonus} from background)</span>` : ''}
            </div>
            <div>
                <button class="stat-decrease" data-stat="${stat}" style="
                    padding: 5px 12px;
                    margin: 0 5px;
                    background: #d32f2f;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    cursor: pointer;
                ">-</button>
                <button class="stat-increase" data-stat="${stat}" style="
                    padding: 5px 12px;
                    background: #4CAF50;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    cursor: pointer;
                ">+</button>
            </div>
        `;
        
        statOptions.appendChild(statRow);
    });
    
    // Add event listeners for stat adjustment
    container.querySelectorAll('.stat-increase').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const stat = e.target.dataset.stat;
            if (characterCreationState.stats[stat] < 18) {
                characterCreationState.stats[stat]++;
                renderStatSelection(container);
            }
        });
    });
    
    container.querySelectorAll('.stat-decrease').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const stat = e.target.dataset.stat;
            if (characterCreationState.stats[stat] > 3) {
                characterCreationState.stats[stat]--;
                renderStatSelection(container);
            }
        });
    });

    addNavigationButtons(container, 'appearance', 'items');
}

/**
 * Render item selection step
 * @param {HTMLElement} container - Container to render into
 * @returns {void}
 */
function renderItemSelection(container) {
    const race = RACES[characterCreationState.selectedRace];
    const background = BACKGROUNDS[characterCreationState.selectedBackground];
    
    const allItems = [...race.startingItems, ...background.startingItems];
    
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
    
    allItems.forEach(item => {
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
    
    characterCreationState.items = allItems;

    addNavigationButtons(container, 'stats', 'summary');
}

/**
 * Render final summary and confirmation
 * @param {HTMLElement} container - Container to render into
 * @returns {void}
 */
function renderSummary(container) {
    const race = RACES[characterCreationState.selectedRace];
    const background = BACKGROUNDS[characterCreationState.selectedBackground];
    
    container.innerHTML = `
        <h2 style="margin: 0 0 10px 0; color: #4CAF50;">Character Summary</h2>
        <p style="color: #aaa; margin-bottom: 20px;">Review your character before creation</p>
        
        <div style="background: #333; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
            <div style="margin-bottom: 15px;">
                <strong style="color: #4CAF50;">Race:</strong> <span style="color: #fff;">${race.name}</span>
            </div>
            <div style="margin-bottom: 15px;">
                <strong style="color: #4CAF50;">Background:</strong> <span style="color: #fff;">${background.name}</span>
            </div>
            <div style="margin-bottom: 15px;">
                <strong style="color: #4CAF50;">Personality:</strong> 
                <span style="color: #fff;">${Object.entries(characterCreationState.personality)
                    .filter(([_, v]) => v)
                    .map(([k, _]) => k)
                    .join(', ')}</span>
            </div>
            <div style="margin-bottom: 15px;">
                <strong style="color: #4CAF50;">Appearance:</strong>
                <div style="color: #fff; margin-left: 20px; margin-top: 5px;">
                    ${Object.entries(characterCreationState.appearance)
                        .map(([k, v]) => `${k}: ${v}`)
                        .join('<br>')}
                </div>
            </div>
            <div>
                <strong style="color: #4CAF50;">Stats:</strong>
                <div style="color: #fff; margin-left: 20px; margin-top: 5px;">
                    ${Object.entries(characterCreationState.stats)
                        .map(([k, v]) => {
                            const bgBonus = background.statBonuses[k] || 0;
                            const raceModifier = race.statModifiers[k] || 0;
                            const total = v + bgBonus + raceModifier;
                            return `${k}: ${total}`;
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
        characterCreationState.currentStep = 'items';
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
            const race = RACES[characterCreationState.selectedRace];
            return Object.keys(race.appearanceOptions).every(
                key => characterCreationState.appearance[key]
            );
        case 'stats':
            return true; // Stats always valid
        case 'items':
            return true; // Items always valid
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
    
    const race = RACES[characterCreationState.selectedRace];
    const background = BACKGROUNDS[characterCreationState.selectedBackground];
    
    // Calculate final stats
    const finalStats = {};
    Object.entries(characterCreationState.stats).forEach(([stat, value]) => {
        finalStats[stat] = value + (background.statBonuses[stat] || 0) + (race.statModifiers[stat] || 0);
    });
    
    const characterData = {
        race: characterCreationState.selectedRace,
        background: characterCreationState.selectedBackground,
        personality: Object.entries(characterCreationState.personality)
            .filter(([_, v]) => v)
            .map(([k, _]) => k),
        appearance: characterCreationState.appearance,
        stats: finalStats,
        items: characterCreationState.items
    };
    
    // TODO: Send to server via socket
    if (window.socket && window.socket.connected) {
        window.socket.emit('create_character', characterData);
    }
    
    // Close character creation
    const overlay = document.getElementById('character-creation-overlay');
    if (overlay) {
        overlay.remove();
    }
    
    console.log('[CharacterCreation] Character created:', characterData);
}
