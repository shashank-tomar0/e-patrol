// Config
const WS_PROTOCOL = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const HOST = window.location.host || '127.0.0.1:8000';
const BASE_URL = `${window.location.protocol}//${HOST}`;

// App State
const state = {
    activeCamera: 1,
    cameraPrivacy: { 1: true, 2: true }, // true = anonymized (skeleton only), false = admin mode
    cameraStates: { 1: 'normal', 2: 'normal' },
    telemetry: {
        1: { density: 15.0, speed: 1.2, skeletons: [], flow_vectors: [], active_anomalies: [] },
        2: { density: 8.0, speed: 0.5, skeletons: [], flow_vectors: [], active_anomalies: [] }
    },
    playbackEvent: null, // Holds event details if playing back history
    playbackFrame: 0,
    wsConnected: false
};

// Joint Connections for Drawing Skeletons (MediaPipe indexes)
const SKELETON_CONNECTIONS = [
    [11, 12], // shoulder to shoulder
    [11, 13], [13, 15], // left arm
    [12, 14], [14, 16], // right arm
    [11, 23], [12, 24], // shoulders to hips
    [23, 24], // hip to hip
    [23, 25], [25, 27], // left leg
    [24, 26], [26, 28]  // right leg
];

// Synth Sound Synthesis for Alerts (Uses Web Audio API - no external assets needed!)
function playAlertSound(severity = 'critical') {
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        
        // Primary warning tone
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);

        if (severity === 'critical') {
            // High-low alarm pattern
            osc.type = 'sawtooth';
            osc.frequency.setValueAtTime(880, ctx.currentTime);
            osc.frequency.linearRampToValueAtTime(440, ctx.currentTime + 0.35);
            gain.gain.setValueAtTime(0.12, ctx.currentTime);
            gain.gain.linearRampToValueAtTime(0.01, ctx.currentTime + 0.4);
            osc.start();
            osc.stop(ctx.currentTime + 0.4);
        } else {
            // Single alert beep
            osc.type = 'sine';
            osc.frequency.setValueAtTime(587.33, ctx.currentTime); // D5 note
            gain.gain.setValueAtTime(0.1, ctx.currentTime);
            gain.gain.linearRampToValueAtTime(0.01, ctx.currentTime + 0.25);
            osc.start();
            osc.stop(ctx.currentTime + 0.3);
        }
    } catch (e) {
        console.warn('Audio Context block:', e);
    }
}

// Voice Alert Dispatcher (TTS)
function speakAlert(text) {
    if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel(); // Cancel any ongoing speech
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 0.92; // Clear, deliberate speed
        utterance.pitch = 0.85; // Deeper, authoritative tone
        
        // Find an English voice if possible
        const voices = window.speechSynthesis.getVoices();
        const voice = voices.find(v => v.lang.startsWith('en-'));
        if (voice) utterance.voice = voice;

        window.speechSynthesis.speak(utterance);
    }
}

// Websocket streams connection
let wsStream1, wsStream2, wsAlerts;

function connectWebSockets() {
    console.log('Connecting WebSockets to:', HOST);
    
    // Alerts stream
    wsAlerts = new WebSocket(`${WS_PROTOCOL}//${HOST}/ws/alerts`);
    wsAlerts.onopen = () => {
        state.wsConnected = true;
        document.getElementById('ping-latency').innerText = '14ms';
        document.getElementById('ping-latency').className = 'm-value status-nominal';
    };
    wsAlerts.onmessage = (event) => {
        const data = jsonParse(event.data);
        if (data && data.event === 'CRITICAL_ALERT') {
            injectAlertItem(data.record);
            playAlertSound(data.record.severity);
        }
    };
    wsAlerts.onerror = (err) => console.error('Alert Socket Error:', err);
    wsAlerts.onclose = () => handleDisconnect();

    // Stream 1
    wsStream1 = new WebSocket(`${WS_PROTOCOL}//${HOST}/ws/stream/1`);
    wsStream1.onmessage = (event) => handleStreamMessage(1, event.data);
    wsStream1.onclose = () => console.log('Stream 1 socket closed');

    // Stream 2
    wsStream2 = new WebSocket(`${WS_PROTOCOL}//${HOST}/ws/stream/2`);
    wsStream2.onmessage = (event) => handleStreamMessage(2, event.data);
    wsStream2.onclose = () => console.log('Stream 2 socket closed');
}

function jsonParse(str) {
    try { return JSON.parse(str); } catch (e) { return null; }
}

function handleDisconnect() {
    state.wsConnected = false;
    document.getElementById('ping-latency').innerText = 'OFFLINE';
    document.getElementById('ping-latency').className = 'm-value status-danger';
    
    // Attempt reconnect in 3s
    setTimeout(connectWebSockets, 3000);
}

function handleStreamMessage(camId, rawData) {
    const data = jsonParse(rawData);
    if (!data) return;

    state.telemetry[camId] = {
        density: data.density,
        speed: data.speed,
        skeletons: data.skeletons,
        flow_vectors: data.flow_vectors,
        active_anomalies: data.active_anomalies
    };

    // If camera is triggering an anomaly, flash the card border in red
    const card = document.getElementById(`cam-card-${camId}`);
    if (data.active_anomalies && data.active_anomalies.length > 0) {
        card.classList.add('alert-active');
        const alertTag = card.querySelector('.cam-status');
        alertTag.innerText = 'CRITICAL DETECTED';
        alertTag.style.background = 'rgba(255, 51, 102, 0.2)';
        alertTag.style.color = '#ff3366';
        alertTag.style.borderColor = '#ff3366';
    } else {
        card.classList.remove('alert-active');
        const alertTag = card.querySelector('.cam-status');
        if (state.cameraPrivacy[camId]) {
            alertTag.innerText = 'PRIVACY MODE';
            alertTag.className = 'cam-status mode-privacy';
            alertTag.style = '';
        } else {
            alertTag.innerText = 'ADMIN VIEW';
            alertTag.className = 'cam-status mode-admin';
            alertTag.style = '';
        }
    }

    // Update Telemetry metrics dashboard panel if this camera is selected
    if (state.activeCamera === camId) {
        updateTelemetryDashboard(data.density, data.speed);
    }
}

function updateTelemetryDashboard(density, speed) {
    document.getElementById('crowd-density-bar').style.width = `${Math.min(100, density)}%`;
    document.getElementById('crowd-density-val').innerText = `${density.toFixed(1)}%`;
    
    document.getElementById('crowd-speed-bar').style.width = `${Math.min(100, (speed / 8.0) * 100)}%`;
    document.getElementById('crowd-speed-val').innerText = `${speed.toFixed(2)} m/s`;
}

// Canvas Rendering
function renderCanvases() {
    for (let camId = 1; camId <= 2; camId++) {
        const canvas = document.getElementById(`canvas-cam-${camId}`);
        if (!canvas) continue;
        const ctx = canvas.getContext('2d');
        
        // Ensure resolution matches client display
        if (canvas.width !== canvas.clientWidth || canvas.height !== canvas.clientHeight) {
            canvas.width = canvas.clientWidth;
            canvas.height = canvas.clientHeight;
        }

        const width = canvas.width;
        const height = canvas.height;
        const data = state.telemetry[camId];
        const isPrivacy = state.cameraPrivacy[camId];

        ctx.clearRect(0, 0, width, height);

        // Draw background
        if (isPrivacy) {
            // Anonymized: Pure deep navy grid space
            ctx.fillStyle = '#03060a';
            ctx.fillRect(0, 0, width, height);
            
            // Neon crosshairs and scan lines in background
            ctx.strokeStyle = 'rgba(0, 255, 204, 0.04)';
            ctx.lineWidth = 1;
            for (let x = 0; x < width; x += 30) {
                ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke();
            }
            for (let y = 0; y < height; y += 30) {
                ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke();
            }
        } else {
            // Admin Mode: CCTV mock background (Blueprint styling + static noise overlay)
            ctx.fillStyle = '#0d1726';
            ctx.fillRect(0, 0, width, height);
            
            // Draw floor contours
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(0, height * 0.7);
            ctx.lineTo(width * 0.4, height * 0.55);
            ctx.lineTo(width, height * 0.75);
            ctx.stroke();
            
            // Simple camera coordinate lines
            ctx.strokeStyle = 'rgba(255, 153, 51, 0.08)';
            ctx.font = '9px monospace';
            ctx.fillStyle = 'rgba(255,153,51,0.4)';
            ctx.fillText(`CAM_0${camId}_RAW_VIDEO_STREAM`, 15, 20);
            ctx.fillText('REC ● 25FPS', width - 85, 20);
        }

        // Draw physical Tripwire boundary for Camera 1 (Subway Platform)
        if (camId === 1) {
            const tripwireY = height * 0.76;
            const hasIntrusion = data.active_anomalies && data.active_anomalies.some(a => a.type === 'intrusion');
            
            // Set style
            ctx.lineWidth = 2.5;
            ctx.strokeStyle = hasIntrusion ? '#ff3366' : '#ffcc00';
            ctx.setLineDash([8, 6]);
            
            ctx.shadowBlur = hasIntrusion ? 12 : 3;
            ctx.shadowColor = ctx.strokeStyle;
            
            // Draw horizontal tripwire line
            ctx.beginPath();
            ctx.moveTo(0, tripwireY);
            ctx.lineTo(width, tripwireY);
            ctx.stroke();
            
            // Reset dash and shadow
            ctx.setLineDash([]);
            ctx.shadowBlur = 0;
            
            // Text Label
            ctx.fillStyle = ctx.strokeStyle;
            ctx.font = 'bold 9px Orbitron';
            ctx.fillText(hasIntrusion ? '🚨 CRITICAL: TRIPWIRE BREACHED' : '⚠️ TRACK INTRUSION TRIPWIRE LIMIT', 15, tripwireY - 8);
        }

        // Draw Optical Flow vectors (small velocity arrows)
        if (data.flow_vectors && data.flow_vectors.length > 0) {
            ctx.lineWidth = 1.5;
            for (const vec of data.flow_vectors) {
                // Map coordinates from 640x480 to canvas w, h
                const sx = (vec.x / 640) * width;
                const sy = (vec.y / 480) * height;
                const dx = (vec.dx / 640) * width * 1.5;
                const dy = (vec.dy / 480) * height * 1.5;

                // Color based on velocity
                ctx.strokeStyle = isPrivacy ? 'rgba(0, 255, 204, 0.35)' : 'rgba(255, 255, 255, 0.15)';
                if (vec.mag > 3.0) {
                    ctx.strokeStyle = 'rgba(255, 51, 102, 0.7)'; // Red for fast movements
                }
                
                ctx.beginPath();
                ctx.moveTo(sx, sy);
                ctx.lineTo(sx + dx, sy + dy);
                ctx.stroke();
            }
        }

        // Draw Skeletons
        if (data.skeletons && data.skeletons.length > 0) {
            for (const skeleton of data.skeletons) {
                const landmarks = skeleton.landmarks;
                
                // Color configuration: glowing neon green/cyan for nominal, red/orange for anomaly
                let neonColor = '#00ffcc';
                if (data.active_anomalies && data.active_anomalies.length > 0) {
                    neonColor = '#ff3366';
                }
                
                // 1. Draw connection lines
                ctx.strokeStyle = neonColor;
                ctx.lineWidth = 3.5;
                ctx.lineCap = 'round';
                ctx.shadowBlur = 8;
                ctx.shadowColor = neonColor;
                
                for (const conn of SKELETON_CONNECTIONS) {
                    const lmStart = landmarks.find(lm => lm.id === conn[0]);
                    const lmEnd = landmarks.find(lm => lm.id === conn[1]);
                    
                    if (lmStart && lmEnd && lmStart.visibility > 0.3 && lmEnd.visibility > 0.3) {
                        const x1 = lmStart.x * width;
                        const y1 = lmStart.y * height;
                        const x2 = lmEnd.x * width;
                        const y2 = lmEnd.y * height;
                        
                        ctx.beginPath();
                        ctx.moveTo(x1, y1);
                        ctx.lineTo(x2, y2);
                        ctx.stroke();
                    }
                }
                ctx.shadowBlur = 0; // reset shadow

                // 2. Draw joints (head circle and points)
                ctx.fillStyle = '#ffffff';
                const head = landmarks.find(lm => lm.id === 0);
                if (head && head.visibility > 0.3) {
                    ctx.beginPath();
                    ctx.arc(head.x * width, head.y * height, 7, 0, 2 * Math.PI);
                    ctx.fill();
                    ctx.strokeStyle = neonColor;
                    ctx.lineWidth = 2;
                    ctx.stroke();
                }

                for (const lm of landmarks) {
                    // Skip head (already drawn as larger circle)
                    if (lm.id === 0) continue;
                    if (lm.visibility > 0.3) {
                        ctx.fillStyle = neonColor;
                        ctx.beginPath();
                        ctx.arc(lm.x * width, lm.y * height, 3, 0, 2 * Math.PI);
                        ctx.fill();
                    }
                }
            }
        }
    }

    // Playback loop rendering (if showing history replay)
    if (state.playbackEvent) {
        renderPlaybackCanvas();
    }

    // Render geospatial Command Map
    renderLayoutMap();

    requestAnimationFrame(renderCanvases);
}

// Draw skeleton replay frames on the active canvas
function renderPlaybackCanvas() {
    const canvas = document.getElementById(`canvas-cam-${state.activeCamera}`);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    
    // Clear overlay area with "PLAYBACK" bar
    ctx.fillStyle = 'rgba(255, 51, 102, 0.08)';
    ctx.fillRect(0, 0, width, height);
    
    ctx.strokeStyle = '#ff3366';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, height * 0.1);
    ctx.lineTo(width, height * 0.1);
    ctx.stroke();
    
    ctx.fillStyle = '#ff3366';
    ctx.font = 'bold 11px Orbitron';
    ctx.fillText('HISTORICAL ARCHIVE REPLAY (ANONYMISED)', 15, height * 0.07);
    ctx.fillText('LOOPING', width - 85, height * 0.07);
}

// Geospatial Patrol Map Blueprint Renderer
function renderLayoutMap() {
    const canvas = document.getElementById('layout-map-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;
    
    // Clear
    ctx.fillStyle = '#03070d';
    ctx.fillRect(0, 0, w, h);
    
    // Draw radar sweeps/grid lines
    ctx.strokeStyle = 'rgba(0, 255, 204, 0.02)';
    ctx.lineWidth = 1;
    for (let x = 0; x < w; x += 25) {
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
    }
    for (let y = 0; y < h; y += 25) {
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
    }
    
    // Draw floor plan contours
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
    ctx.lineWidth = 1.5;
    
    // Outer perimeter
    ctx.strokeRect(w * 0.08, h * 0.08, w * 0.84, h * 0.84);
    
    // Room dividers
    ctx.beginPath();
    ctx.moveTo(w * 0.5, h * 0.08);
    ctx.lineTo(w * 0.5, h * 0.92);
    ctx.stroke();
    
    // Gate door markings
    ctx.clearRect(w * 0.45, h * 0.08 - 2, w * 0.1, 4);
    ctx.clearRect(w * 0.45, h * 0.92 - 2, w * 0.1, 4);
    
    // Label zones
    ctx.fillStyle = 'rgba(255, 255, 255, 0.22)';
    ctx.font = '7.5px Orbitron';
    ctx.fillText('EAST ZONE // SUBWAY PLATFORM 2', w * 0.12, h * 0.18);
    ctx.fillText('WEST ZONE // NORTH ESCALATOR LOBBY', w * 0.53, h * 0.18);
    
    // Map Coordinates
    const c1_x = w * 0.28;
    const c1_y = h * 0.58;
    const c2_x = w * 0.72;
    const c2_y = h * 0.58;
    
    const data1 = state.telemetry[1];
    const data2 = state.telemetry[2];
    
    const t = Date.now() / 1000;
    const pulseRadius = 5 + 4 * Math.sin(t * 8.0);
    
    // Render Camera 1 Heatmap & Node
    if (data1) {
        const rad = Math.max(12, (data1.density / 100.0) * 70);
        const grad = ctx.createRadialGradient(c1_x, c1_y, 2, c1_x, c1_y, rad);
        const color = data1.active_anomalies.length > 0 ? '255, 51, 102' : '0, 255, 204';
        grad.addColorStop(0, `rgba(${color}, 0.25)`);
        grad.addColorStop(1, `rgba(${color}, 0)`);
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(c1_x, c1_y, rad, 0, 2 * Math.PI);
        ctx.fill();
        
        const isAnomaly = data1.active_anomalies.length > 0;
        ctx.fillStyle = isAnomaly ? '#ff3366' : '#00ffcc';
        ctx.shadowBlur = isAnomaly ? 8 : 0;
        ctx.shadowColor = ctx.fillStyle;
        ctx.beginPath();
        ctx.arc(c1_x, c1_y, 4, 0, 2 * Math.PI);
        ctx.fill();
        
        ctx.strokeStyle = ctx.fillStyle;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(c1_x, c1_y, pulseRadius, 0, 2 * Math.PI);
        ctx.stroke();
        ctx.shadowBlur = 0;
        
        ctx.fillStyle = isAnomaly ? '#ff3366' : 'rgba(255, 255, 255, 0.7)';
        ctx.font = 'bold 8px Orbitron';
        ctx.fillText(`CAM 01 ${isAnomaly ? '🚨' : '🟢'}`, c1_x - 18, c1_y - 12);
    }
    
    // Render Camera 2 Heatmap & Node
    if (data2) {
        const rad = Math.max(12, (data2.density / 100.0) * 70);
        const grad = ctx.createRadialGradient(c2_x, c2_y, 2, c2_x, c2_y, rad);
        const color = data2.active_anomalies.length > 0 ? '255, 153, 51' : '0, 255, 204';
        grad.addColorStop(0, `rgba(${color}, 0.25)`);
        grad.addColorStop(1, `rgba(${color}, 0)`);
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(c2_x, c2_y, rad, 0, 2 * Math.PI);
        ctx.fill();
        
        const isAnomaly = data2.active_anomalies.length > 0;
        ctx.fillStyle = isAnomaly ? '#ff9933' : '#00ffcc';
        ctx.shadowBlur = isAnomaly ? 8 : 0;
        ctx.shadowColor = ctx.fillStyle;
        ctx.beginPath();
        ctx.arc(c2_x, c2_y, 4, 0, 2 * Math.PI);
        ctx.fill();
        
        ctx.strokeStyle = ctx.fillStyle;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(c2_x, c2_y, pulseRadius, 0, 2 * Math.PI);
        ctx.stroke();
        ctx.shadowBlur = 0;
        
        ctx.fillStyle = isAnomaly ? '#ff9933' : 'rgba(255, 255, 255, 0.7)';
        ctx.font = 'bold 8px Orbitron';
        ctx.fillText(`CAM 02 ${isAnomaly ? '⚠' : '🟢'}`, c2_x - 18, c2_y - 12);
    }
}

// UI Actions
function togglePrivacy(camId) {
    state.cameraPrivacy[camId] = !state.cameraPrivacy[camId];
    
    const card = document.getElementById(`cam-card-${camId}`);
    const btn = card.querySelector('.btn-toggle-privacy');
    const alertTag = card.querySelector('.cam-status');
    
    if (state.cameraPrivacy[camId]) {
        btn.classList.add('active');
        btn.classList.remove('admin-active');
        btn.innerText = 'Anonymized (Skeletons Only)';
        alertTag.innerText = 'PRIVACY MODE';
        alertTag.className = 'cam-status mode-privacy';
    } else {
        btn.classList.remove('active');
        btn.classList.add('admin-active');
        btn.innerText = 'Security Admin Feed Active';
        alertTag.innerText = 'ADMIN VIEW';
        alertTag.className = 'cam-status mode-admin';
    }
}

async function connectRealFeed(camId) {
    const input = document.getElementById(`stream-src-${camId}`);
    const source = input.value.trim();
    if (!source) {
        alert("Please enter a valid source (e.g. '0' for your webcam, or an RTSP stream URL).");
        return;
    }
    
    // Switch to admin view automatically to see the feed initialization
    if (state.cameraPrivacy[camId]) {
        togglePrivacy(camId);
    }
    
    // Disable input while connecting
    input.disabled = true;
    const btn = input.nextElementSibling;
    const originalText = btn.innerText;
    btn.innerText = "CONNECTING...";
    btn.disabled = true;
    
    try {
        const response = await fetch(`${BASE_URL}/api/camera/configure/${camId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source: source })
        });
        const result = await response.json();
        console.log('Camera configured:', result);
        if (result.status === 'success') {
            btn.innerText = "CONNECTED";
            btn.style.borderColor = "var(--accent-cyan)";
            btn.style.color = "var(--accent-cyan)";
            setTimeout(() => {
                btn.innerText = originalText;
                btn.style.borderColor = "";
                btn.style.color = "";
                btn.disabled = false;
                input.disabled = false;
            }, 2000);
        } else {
            throw new Error(result.error || "Failed connection");
        }
    } catch (e) {
        alert("Failed to connect to feed. Make sure the source is accessible.");
        btn.innerText = "FAILED";
        btn.style.borderColor = "var(--accent-red)";
        btn.style.color = "var(--accent-red)";
        setTimeout(() => {
            btn.innerText = originalText;
            btn.style.borderColor = "";
            btn.style.color = "";
            btn.disabled = false;
            input.disabled = false;
        }, 2000);
    }
}

async function triggerSim(camId, simState) {
    // Highlight active simulation button
    const card = document.getElementById(`cam-card-${camId}`);
    card.querySelectorAll('.btn-sim').forEach(btn => btn.classList.remove('active'));
    
    const targetBtn = card.querySelector(`.btn-sim.${simState}`);
    if (targetBtn) targetBtn.classList.add('active');

    // Trigger on backend
    try {
        const response = await fetch(`${BASE_URL}/api/simulate/${camId}/${simState}`, {
            method: 'POST'
        });
        const result = await response.json();
        console.log('Simulation updated:', result);
    } catch (e) {
        console.error('Failed to trigger simulation:', e);
    }
}

// Telemetry Alert cards injection
function injectAlertItem(record) {
    const container = document.getElementById('alerts-log-container');
    
    // Remove empty msg
    const emptyMsg = container.querySelector('.empty-log-msg');
    if (emptyMsg) emptyMsg.remove();

    const timestamp = new Date(record.timestamp * 1000).toLocaleTimeString();
    
    const alertItem = document.createElement('div');
    alertItem.className = `alert-item level-${record.severity}`;
    alertItem.onclick = () => openModal(record);
    alertItem.innerHTML = `
        <div class="alert-item-header">
            <span class="alert-type">${record.type.toUpperCase()} // ${record.threat_level}</span>
            <span class="alert-time">${timestamp}</span>
        </div>
        <div class="alert-loc">${record.location}</div>
        <div class="alert-desc">${record.summary}</div>
        <div class="alert-footer">
            <span>Threat Score: ${(record.density > 25 ? 0.95 : 0.88).toFixed(2)}</span>
            <span class="click-dossier-hint">VIEW DOSSIER ↗</span>
        </div>
    `;
    
    // Prepend to show newest first
    container.insertBefore(alertItem, container.firstChild);
    
    // Toggle threat header tag
    const headerIndicator = document.getElementById('alert-indicator');
    headerIndicator.innerText = 'THREAT IN SCENE';
    headerIndicator.className = 'tag tag-danger animate-pulse';

    // Broadcast audio speech warning
    const alertSpeechText = `Alert. ${record.type} detected at ${record.location}. Response protocol. ${record.threat_level} threat level.`;
    speakAlert(alertSpeechText);
}

// Incident Dossier Modal
function openModal(record) {
    const modal = document.getElementById('dossier-modal');
    modal.classList.add('active');
    
    document.getElementById('modal-event-id').innerText = `#${record.id}`;
    document.getElementById('modal-alert-type').innerText = record.type.toUpperCase();
    document.getElementById('modal-location').innerText = record.location;
    
    const timeString = new Date(record.timestamp * 1000).toISOString().replace('T', ' ').substring(0, 19) + ' UTC';
    document.getElementById('modal-time').innerText = timeString;
    
    const threatBadge = document.getElementById('modal-threat-level');
    threatBadge.innerText = record.threat_level;
    threatBadge.className = `level-badge level-${record.severity}`;
    
    document.getElementById('modal-summary').innerText = record.summary;
    document.getElementById('modal-visual-analysis').innerText = record.visual_analysis;
    
    // Protocol mapping
    let protocol = 'Monitor scene telemetry bounds.';
    if (record.severity === 'critical') {
        protocol = 'Dispatch station police squad immediately, alert central line dispatcher to hold incoming trains, and activate visual audio alarm guidance.';
    } else if (record.severity === 'high') {
        protocol = 'Sound warnings in station hallway, notify platform supervisors, and zoom tracking cameras.';
    }
    document.getElementById('modal-actions').innerText = protocol;
}

function closeModal() {
    document.getElementById('dossier-modal').classList.remove('active');
}

// Vector DB Search
async function performSearch() {
    const query = document.getElementById('search-input').value;
    try {
        const response = await fetch(`${BASE_URL}/api/search?q=${encodeURIComponent(query)}`);
        const results = await response.json();
        renderSearchResults(results);
    } catch (e) {
        console.error('Search failed:', e);
    }
}

function renderSearchResults(results) {
    const tbody = document.getElementById('search-results-body');
    tbody.innerHTML = '';
    
    if (results.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">No matching safety events found in vector space.</td></tr>`;
        return;
    }

    results.forEach(record => {
        const tr = document.createElement('tr');
        const score = record.similarity_score !== undefined ? record.similarity_score : 1.0;
        const timeStr = new Date(record.timestamp * 1000).toISOString().replace('T', ' ').substring(11, 19);
        
        tr.innerHTML = `
            <td><span class="score-badge">${(score * 100).toFixed(0)}% MATCH</span></td>
            <td>${timeStr}</td>
            <td><strong>${record.location}</strong></td>
            <td><span style="color: ${record.severity === 'critical' ? 'var(--accent-red)' : 'var(--accent-orange)'}">${record.type.toUpperCase()}</span></td>
            <td>${record.summary}</td>
            <td><span style="font-family: var(--font-mono); font-size: 0.72rem;">${record.threat_level}</span></td>
            <td><button class="btn-playback" onclick='replayEvent(${JSON.stringify(record)})'>PLAYBACK</button></td>
        `;
        tbody.appendChild(tr);
    });
}

function replayEvent(record) {
    // Open modal to show full historic dossier
    openModal(record);
    
    // Simulate loading tracking logs on the canvas
    state.playbackEvent = record;
    setTimeout(() => {
        state.playbackEvent = null;
    }, 4000); // Stop playback visual after 4s
}

// Fetch historical database items on startup
async function loadHistoricalLogs() {
    try {
        const response = await fetch(`${BASE_URL}/api/events`);
        const events = await response.json();
        // Load in reverse order to display latest first
        events.slice().reverse().forEach(evt => injectAlertItem(evt));
        renderSearchResults(events); // Show seeded events in search by default
    } catch (e) {
        console.warn('Failed to load historic database:', e);
    }
}

// Setup Event Listeners
document.getElementById('btn-search-trigger').onclick = performSearch;
document.getElementById('search-input').onkeydown = (e) => {
    if (e.key === 'Enter') performSearch();
};

// Clock
setInterval(() => {
    const now = new Date();
    document.getElementById('system-time').innerText = now.toISOString().replace('T', ' ').substring(0, 19) + ' UTC';
}, 1000);

// Initialize
window.onload = () => {
    connectWebSockets();
    loadHistoricalLogs();
    
    // Click events inside canvas selection
    document.getElementById('cam-card-1').onclick = () => {
        state.activeCamera = 1;
        document.getElementById('cam-card-1').style.borderColor = 'var(--accent-cyan)';
        document.getElementById('cam-card-2').style.borderColor = 'var(--border-color)';
        updateTelemetryDashboard(state.telemetry[1].density, state.telemetry[1].speed);
    };
    
    document.getElementById('cam-card-2').onclick = () => {
        state.activeCamera = 2;
        document.getElementById('cam-card-2').style.borderColor = 'var(--accent-cyan)';
        document.getElementById('cam-card-1').style.borderColor = 'var(--border-color)';
        updateTelemetryDashboard(state.telemetry[2].density, state.telemetry[2].speed);
    };

    // Trigger canvas animation loops
    requestAnimationFrame(renderCanvases);
};
