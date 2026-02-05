// Fireplace Control App

let statusInterval;
let isConnected = false;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    setConnectionState(false);  // Start disconnected until we confirm connection
    refreshStatus();
    loadApiKeys();
    statusInterval = setInterval(refreshStatus, 5000);
    initDropdown();
});

// ==========================================
// User Menu Dropdown
// ==========================================

function initDropdown() {
    const toggle = document.getElementById('user-menu-toggle');
    const dropdown = document.getElementById('user-dropdown');
    if (!toggle || !dropdown) return;

    toggle.addEventListener('click', (e) => {
        e.stopPropagation();
        const isOpen = dropdown.classList.toggle('open');
        toggle.setAttribute('aria-expanded', isOpen);
    });

    document.addEventListener('click', (e) => {
        if (!dropdown.contains(e.target) && e.target !== toggle) {
            dropdown.classList.remove('open');
            toggle.setAttribute('aria-expanded', 'false');
        }
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            dropdown.classList.remove('open');
            toggle.setAttribute('aria-expanded', 'false');
        }
    });
}

// ==========================================
// Connection State
// ==========================================

function setConnectionState(connected) {
    isConnected = connected;
    const banner = document.getElementById('connection-banner');
    const container = document.querySelector('.container');
    const fireplace = document.getElementById('pixel-fireplace');

    if (connected) {
        banner.classList.remove('disconnected');
        banner.classList.add('connected');
        container.classList.remove('disconnected-state');
        fireplace.classList.remove('disconnected');
    } else {
        banner.classList.add('disconnected');
        banner.classList.remove('connected');
        container.classList.add('disconnected-state');
        fireplace.classList.add('disconnected');
        // Turn off fireplace visual when disconnected
        updateFireplaceVisual(false, 0, false, false);
    }
}

// ==========================================
// Pixel Fireplace Visual
// ==========================================

function updateFireplaceVisual(power, flameLevel, pilot, burner2) {
    const fireplace = document.getElementById('pixel-fireplace');
    const pilotLight = document.getElementById('pilot-light');

    // Power state (flames visible)
    if (power) {
        fireplace.classList.add('on');
        // Set flame height based on level (0.3 min to 1.0 max for visual appeal)
        const flameHeight = 0.3 + (flameLevel / 100) * 0.7;
        fireplace.style.setProperty('--flame-height', flameHeight);
    } else {
        fireplace.classList.remove('on');
    }

    // Burner 2 state
    if (burner2) {
        fireplace.classList.add('burner2-on');
    } else {
        fireplace.classList.remove('burner2-on');
    }

    // Pilot light
    if (pilot) {
        pilotLight.classList.add('on');
    } else {
        pilotLight.classList.remove('on');
    }
}

// ==========================================
// API Helper
// ==========================================

async function api(method, endpoint, body = null) {
    const options = {
        method,
        headers: {
            'Content-Type': 'application/json',
        },
    };
    if (body) {
        options.body = JSON.stringify(body);
    }

    const response = await fetch(endpoint, options);

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Request failed' }));
        throw new Error(error.detail || 'Request failed');
    }

    return response.json();
}

// ==========================================
// Status
// ==========================================

function updateIndicator(id, isOn, isPilot) {
    const indicator = document.getElementById('indicator-' + id);
    const item = document.getElementById('status-item-' + id);
    if (!indicator || !item) return;

    indicator.classList.remove('on', 'pilot-on', 'flashing');
    if (isOn) {
        indicator.classList.add(isPilot ? 'pilot-on' : 'on');
        item.classList.add('active');
    } else {
        item.classList.remove('active');
    }
}

function resetIndicators() {
    ['power', 'flame', 'burner2', 'pilot'].forEach(id => {
        const indicator = document.getElementById('indicator-' + id);
        const item = document.getElementById('status-item-' + id);
        if (indicator) indicator.classList.remove('on', 'pilot-on');
        if (item) item.classList.remove('active');
    });
}

function updateToggles(status) {
    const powerToggle = document.getElementById('power-toggle');
    const powerLabel = document.getElementById('power-toggle-label');
    const burner2Toggle = document.getElementById('burner2-toggle');
    const burner2Label = document.getElementById('burner2-toggle-label');

    if (powerToggle) {
        powerToggle.setAttribute('aria-checked', status.power ? 'true' : 'false');
        powerLabel.textContent = status.power ? 'ON' : 'OFF';
    }

    if (burner2Toggle) {
        burner2Toggle.setAttribute('aria-checked', status.burner2 ? 'true' : 'false');
        burner2Label.textContent = status.burner2 ? 'ON' : 'OFF';
    }
}

async function refreshStatus() {
    try {
        const status = await api('GET', '/api/status');

        setConnectionState(true);

        document.getElementById('status-power').textContent = status.power ? 'ON' : 'OFF';
        document.getElementById('status-power').className = 'value ' + (status.power ? 'on' : 'off');

        document.getElementById('status-flame').textContent = status.flame_level + '%';

        document.getElementById('status-burner2').textContent = status.burner2 ? 'ON' : 'OFF';
        document.getElementById('status-burner2').className = 'value ' + (status.burner2 ? 'on' : 'off');

        document.getElementById('status-pilot').textContent = status.pilot ? 'ON' : 'OFF';
        document.getElementById('status-pilot').className = 'value ' + (status.pilot ? 'on' : 'off');

        document.getElementById('status-message').textContent = '';

        // Update indicators
        updateIndicator('power', status.power, false);
        updateIndicator('flame', status.power, false);
        updateIndicator('burner2', status.burner2, false);
        updateIndicator('pilot', status.pilot, true);

        // Update toggles
        updateToggles(status);

        // Update pixel fireplace visual
        updateFireplaceVisual(status.power, status.flame_level, status.pilot, status.burner2);

        // Update slider if power is on
        if (status.power) {
            document.getElementById('flame-slider').value = status.flame_level;
            document.getElementById('flame-value').textContent = status.flame_level;
        }
    } catch (error) {
        setConnectionState(false);

        // Reset status values to show disconnected state
        document.getElementById('status-power').textContent = '--';
        document.getElementById('status-power').className = 'value';
        document.getElementById('status-flame').textContent = '--';
        document.getElementById('status-burner2').textContent = '--';
        document.getElementById('status-burner2').className = 'value';
        document.getElementById('status-pilot').textContent = '--';
        document.getElementById('status-pilot').className = 'value';
        document.getElementById('status-message').textContent = '';

        // Reset indicators and toggles
        resetIndicators();
        updateToggles({ power: false, burner2: false });
    }
}

// ==========================================
// Toggle Controls
// ==========================================

async function togglePower() {
    const toggle = document.getElementById('power-toggle');
    const isOn = toggle.getAttribute('aria-checked') === 'true';
    const indicator = document.getElementById('indicator-power');

    try {
        if (isOn) {
            await api('POST', '/api/power/off');
            if (indicator) indicator.classList.add('flashing');
            setTimeout(refreshStatus, 1000);
        } else {
            await api('POST', '/api/power/on');
            if (indicator) indicator.classList.add('flashing');
            setTimeout(refreshStatus, 2000);
        }
    } catch (error) {
        alert('Failed to toggle power: ' + error.message);
    }
}

async function toggleBurner2() {
    const toggle = document.getElementById('burner2-toggle');
    const isOn = toggle.getAttribute('aria-checked') === 'true';

    try {
        if (isOn) {
            await api('POST', '/api/burner2/off');
        } else {
            await api('POST', '/api/burner2/on');
        }
        setTimeout(refreshStatus, 500);
    } catch (error) {
        alert('Failed to toggle burner 2: ' + error.message);
    }
}

// ==========================================
// Flame Level
// ==========================================

function updateFlameDisplay(value) {
    document.getElementById('flame-value').textContent = value;
    // Update pixel fireplace flames in real-time as slider moves
    const fireplace = document.getElementById('pixel-fireplace');
    if (fireplace.classList.contains('on')) {
        const flameHeight = 0.3 + (value / 100) * 0.7;
        fireplace.style.setProperty('--flame-height', flameHeight);
    }
}

async function setFlameLevel(level) {
    try {
        await api('POST', `/api/flame/${level}`);
    } catch (error) {
        alert('Failed to set flame level: ' + error.message);
    }
}

// ==========================================
// API Keys
// ==========================================

async function loadApiKeys() {
    const container = document.getElementById('api-keys-list');
    if (!container) return;  // API keys not enabled

    try {
        const data = await api('GET', '/api/keys');

        if (data.keys.length === 0) {
            container.innerHTML = '<p style="color: #666;">No API keys created yet.</p>';
            return;
        }

        container.innerHTML = data.keys.map(key => `
            <div class="api-key-item">
                <div class="key-info">
                    <div class="key-name">${escapeHtml(key.name)}</div>
                    <div class="key-meta">
                        ${key.key_prefix}... | Created: ${formatDate(key.created_at)}
                        ${key.last_used ? ' | Last used: ' + formatDate(key.last_used) : ''}
                    </div>
                </div>
                <button class="btn btn-small btn-delete" onclick="deleteApiKey(${key.id})">Delete</button>
            </div>
        `).join('');
    } catch (error) {
        // API keys endpoint not available (ENABLE_API_KEYS=false)
    }
}

async function createApiKey() {
    const nameInput = document.getElementById('key-name');
    const name = nameInput.value.trim();

    if (!name) {
        alert('Please enter a name for the API key');
        return;
    }

    try {
        const data = await api('POST', '/api/keys', { name });

        // Show the new key
        document.getElementById('new-key-value').textContent = data.key;
        document.getElementById('new-key-display').style.display = 'block';

        // Clear input and refresh list
        nameInput.value = '';
        loadApiKeys();
    } catch (error) {
        alert('Failed to create API key: ' + error.message);
    }
}

async function deleteApiKey(keyId) {
    if (!confirm('Are you sure you want to delete this API key?')) {
        return;
    }

    try {
        await api('DELETE', `/api/keys/${keyId}`);
        loadApiKeys();
    } catch (error) {
        alert('Failed to delete API key: ' + error.message);
    }
}

function copyKey() {
    const key = document.getElementById('new-key-value').textContent;
    navigator.clipboard.writeText(key).then(() => {
        alert('Key copied to clipboard!');
    }).catch(() => {
        alert('Failed to copy. Please select and copy manually.');
    });
}

// ==========================================
// Helpers
// ==========================================

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDate(isoString) {
    const date = new Date(isoString);
    return date.toLocaleDateString();
}
