// Admin Dashboard JavaScript

let currentSection = 'watchfolders';
let presets = [];

// Navigation
document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const section = btn.dataset.section;
        switchSection(section);
    });
});

function switchSection(section) {
    currentSection = section;
    
    // Update nav buttons
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    document.querySelector(`[data-section="${section}"]`).classList.add('active');
    
    // Update sections
    document.querySelectorAll('.admin-section').forEach(s => s.classList.add('hidden'));
    document.getElementById(`${section}-section`).classList.remove('hidden');
    
    // Load section data
    loadSectionData(section);
}

// Load data for current section
async function loadSectionData(section) {
    switch(section) {
        case 'watchfolders':
            await loadWatchfolders();
            break;
        case 'presets':
            await loadPresets();
            break;
        case 'workers':
            await loadWorkers();
            break;
        case 'jobs':
            await loadJobs();
            break;
        case 'logs':
            await loadLogs();
            break;
    }
}

// Watchfolders
async function loadWatchfolders() {
    try {
        const response = await fetch('/api/admin/watchfolders');
        const data = await response.json();
        
        const tbody = document.getElementById('watchfolders-tbody');
        tbody.innerHTML = '';
        
        data.forEach(wf => {
            const row = document.createElement('tr');
            const watchTypeLabel = wf.watch_type === 'ftp' ? 'FTP' : 'Locale';
            const pathDisplay = wf.watch_type === 'ftp' 
                ? `${escapeHtml(wf.ftp_host || '')}${wf.ftp_remote_path ? ':' + escapeHtml(wf.ftp_remote_path) : ''}`
                : escapeHtml(wf.path);
            
            row.innerHTML = `
                <td>${escapeHtml(wf.name)}</td>
                <td>${pathDisplay} <span style="color: var(--text-secondary); font-size: 11px;">(${watchTypeLabel})</span></td>
                <td>${escapeHtml(wf.output_path || '-')}</td>
                <td>${escapeHtml(wf.archive_path || '-')}</td>
                <td>${wf.preset_id || '-'}</td>
                <td><span class="status-badge status-${wf.status}">${wf.status}</span></td>
                <td>
                    <label class="toggle-switch">
                        <input type="checkbox" ${wf.active ? 'checked' : ''} 
                               onchange="toggleWatchfolder(${wf.id}, this.checked)">
                        <span class="toggle-slider"></span>
                    </label>
                </td>
                <td>
                    <div class="action-buttons">
                        <button class="btn btn-small btn-primary" onclick="editWatchfolder(${wf.id})">Modifica</button>
                        <button class="btn btn-small btn-secondary" onclick="deleteWatchfolder(${wf.id})">Elimina</button>
                    </div>
                </td>
            `;
            tbody.appendChild(row);
        });
    } catch (error) {
        console.error('Errore caricamento watchfolders:', error);
    }
}

document.getElementById('add-watchfolder-btn').addEventListener('click', () => {
    editWatchfolder(null);
});

async function editWatchfolder(id) {
    const modal = document.getElementById('watchfolder-modal');
    const form = document.getElementById('watchfolder-form');
    const title = document.getElementById('watchfolder-modal-title');
    
    // Load presets
    await loadPresetsForSelect();
    
    if (id) {
        // Edit mode
        const response = await fetch(`/api/admin/watchfolders`);
        const watchfolders = await response.json();
        const wf = watchfolders.find(w => w.id === id);
        
        if (wf) {
            title.textContent = 'Modifica Watchfolder';
            document.getElementById('watchfolder-id').value = wf.id;
            document.getElementById('watchfolder-name').value = wf.name;
            document.getElementById('watchfolder-type').value = wf.watch_type || 'local';
            toggleWatchfolderType();
            document.getElementById('watchfolder-path').value = wf.path || '';
            document.getElementById('watchfolder-output-path').value = wf.output_path || '';
            document.getElementById('watchfolder-archive-path').value = wf.archive_path || '';
            document.getElementById('watchfolder-ftp-host').value = wf.ftp_host || '';
            document.getElementById('watchfolder-ftp-port').value = wf.ftp_port || 21;
            document.getElementById('watchfolder-ftp-username').value = wf.ftp_username || '';
            document.getElementById('watchfolder-ftp-password').value = ''; // Non mostrare password esistente
            document.getElementById('watchfolder-ftp-remote-path').value = wf.ftp_remote_path || '/';
            document.getElementById('watchfolder-ftp-local-temp').value = wf.ftp_local_temp || '/tmp/xdcam_ftp';
            document.getElementById('watchfolder-preset-id').value = wf.preset_id || '';
            document.getElementById('watchfolder-active').checked = wf.active;
        }
    } else {
        // New mode
        title.textContent = 'Nuovo Watchfolder';
        form.reset();
        document.getElementById('watchfolder-id').value = '';
        document.getElementById('watchfolder-type').value = 'local';
        toggleWatchfolderType();
        document.getElementById('watchfolder-active').checked = true;
        document.getElementById('watchfolder-ftp-port').value = 21;
        document.getElementById('watchfolder-ftp-remote-path').value = '/';
        document.getElementById('watchfolder-ftp-local-temp').value = '/tmp/xdcam_ftp';
    }
    
    modal.classList.add('active');
}

document.getElementById('watchfolder-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const id = document.getElementById('watchfolder-id').value;
    const watchType = document.getElementById('watchfolder-type').value;
    const data = {
        name: document.getElementById('watchfolder-name').value,
        watch_type: watchType,
        path: watchType === 'local' ? document.getElementById('watchfolder-path').value : '',
        output_path: document.getElementById('watchfolder-output-path').value,
        archive_path: document.getElementById('watchfolder-archive-path').value,
        preset_id: document.getElementById('watchfolder-preset-id').value || null,
        active: document.getElementById('watchfolder-active').checked
    };
    
    // Aggiungi campi FTP se tipo FTP
    if (watchType === 'ftp') {
        data.ftp_host = document.getElementById('watchfolder-ftp-host').value;
        data.ftp_port = parseInt(document.getElementById('watchfolder-ftp-port').value) || 21;
        data.ftp_username = document.getElementById('watchfolder-ftp-username').value;
        const password = document.getElementById('watchfolder-ftp-password').value;
        if (password) {  // Invia password solo se modificata
            data.ftp_password = password;
        }
        data.ftp_remote_path = document.getElementById('watchfolder-ftp-remote-path').value || '/';
        data.ftp_local_temp = document.getElementById('watchfolder-ftp-local-temp').value || '/tmp/xdcam_ftp';
    }
    
    try {
        const url = id ? `/api/admin/watchfolders/${id}` : '/api/admin/watchfolders';
        const method = id ? 'PUT' : 'POST';
        
        const response = await fetch(url, {
            method,
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            document.getElementById('watchfolder-modal').classList.remove('active');
            await loadWatchfolders();
        } else {
            const error = await response.json();
            alert('Errore: ' + (error.error || 'Errore sconosciuto'));
        }
    } catch (error) {
        alert('Errore: ' + error.message);
    }
});

async function toggleWatchfolder(id, active) {
    const response = await fetch(`/api/admin/watchfolders/${id}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({active})
    });
    
    if (response.ok) {
        await loadWatchfolders();
    }
}

async function deleteWatchfolder(id) {
    if (!confirm('Sei sicuro di voler eliminare questo watchfolder?')) return;
    
    const response = await fetch(`/api/admin/watchfolders/${id}`, {
        method: 'DELETE'
    });
    
    if (response.ok) {
        await loadWatchfolders();
    }
}

// Presets
async function loadPresets() {
    try {
        const response = await fetch('/api/admin/presets');
        presets = await response.json();
        
        const tbody = document.getElementById('presets-tbody');
        tbody.innerHTML = '';
        
        presets.forEach(p => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${escapeHtml(p.name)}</td>
                <td>${escapeHtml(p.video_codec)}</td>
                <td>${escapeHtml(p.video_bitrate)}</td>
                <td>${escapeHtml(p.audio_codec)}</td>
                <td>${escapeHtml(p.container)}</td>
                <td>
                    <div class="action-buttons">
                        <button class="btn btn-small btn-primary" onclick="editPreset(${p.id})">Modifica</button>
                        <button class="btn btn-small btn-secondary" onclick="deletePreset(${p.id})">Elimina</button>
                    </div>
                </td>
            `;
            tbody.appendChild(row);
        });
    } catch (error) {
        console.error('Errore caricamento presets:', error);
    }
}

async function loadPresetsForSelect() {
    if (presets.length === 0) {
        await loadPresets();
    }
    
    const select = document.getElementById('watchfolder-preset-id');
    select.innerHTML = '<option value="">Nessuno</option>';
    presets.forEach(p => {
        const option = document.createElement('option');
        option.value = p.id;
        option.textContent = p.name;
        select.appendChild(option);
    });
}

document.getElementById('add-preset-btn').addEventListener('click', () => {
    editPreset(null);
});

async function editPreset(id) {
    const modal = document.getElementById('preset-modal');
    const form = document.getElementById('preset-form');
    const title = document.getElementById('preset-modal-title');
    
    if (id) {
        const preset = presets.find(p => p.id === id);
        if (preset) {
            title.textContent = 'Modifica Preset';
            document.getElementById('preset-id').value = preset.id;
            document.getElementById('preset-name').value = preset.name;
            document.getElementById('preset-description').value = preset.description || '';
            document.getElementById('preset-video-codec').value = preset.video_codec;
            document.getElementById('preset-video-bitrate').value = preset.video_bitrate;
            document.getElementById('preset-audio-codec').value = preset.audio_codec;
            document.getElementById('preset-audio-bitrate').value = preset.audio_bitrate || '';
            document.getElementById('preset-audio-sample-rate').value = preset.audio_sample_rate;
            document.getElementById('preset-audio-channels').value = preset.audio_channels;
            document.getElementById('preset-container').value = preset.container;
            document.getElementById('preset-ffmpeg-params').value = preset.ffmpeg_params || '';
        }
    } else {
        title.textContent = 'Nuovo Preset';
        form.reset();
        document.getElementById('preset-id').value = '';
    }
    
    modal.classList.add('active');
}

document.getElementById('preset-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const id = document.getElementById('preset-id').value;
    const data = {
        name: document.getElementById('preset-name').value,
        description: document.getElementById('preset-description').value,
        video_codec: document.getElementById('preset-video-codec').value,
        video_bitrate: document.getElementById('preset-video-bitrate').value,
        audio_codec: document.getElementById('preset-audio-codec').value,
        audio_bitrate: document.getElementById('preset-audio-bitrate').value,
        audio_sample_rate: document.getElementById('preset-audio-sample-rate').value,
        audio_channels: document.getElementById('preset-audio-channels').value,
        container: document.getElementById('preset-container').value,
        ffmpeg_params: document.getElementById('preset-ffmpeg-params').value
    };
    
    try {
        const url = id ? `/api/admin/presets/${id}` : '/api/admin/presets';
        const method = id ? 'PUT' : 'POST';
        
        const response = await fetch(url, {
            method,
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            document.getElementById('preset-modal').classList.remove('active');
            await loadPresets();
        } else {
            const error = await response.json();
            alert('Errore: ' + (error.error || 'Errore sconosciuto'));
        }
    } catch (error) {
        alert('Errore: ' + error.message);
    }
});

async function deletePreset(id) {
    if (!confirm('Sei sicuro di voler eliminare questo preset?')) return;
    
    const response = await fetch(`/api/admin/presets/${id}`, {
        method: 'DELETE'
    });
    
    if (response.ok) {
        await loadPresets();
    }
}

// Workers
async function loadWorkers() {
    try {
        const response = await fetch('/api/admin/workers');
        const data = await response.json();
        
        const tbody = document.getElementById('workers-tbody');
        tbody.innerHTML = '';
        
        data.forEach(w => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${escapeHtml(w.name)}</td>
                <td><span class="status-badge status-${w.status}">${w.status}</span></td>
                <td>${w.current_job_id || '-'}</td>
                <td>${w.max_concurrent_jobs}</td>
                <td>
                    <label class="toggle-switch">
                        <input type="checkbox" ${w.active ? 'checked' : ''} 
                               onchange="toggleWorker(${w.id}, this.checked)">
                        <span class="toggle-slider"></span>
                    </label>
                </td>
                <td>
                    <div class="action-buttons">
                        <button class="btn btn-small btn-primary" onclick="editWorker(${w.id})">Modifica</button>
                    </div>
                </td>
            `;
            tbody.appendChild(row);
        });
    } catch (error) {
        console.error('Errore caricamento workers:', error);
    }
}

document.getElementById('add-worker-btn').addEventListener('click', () => {
    editWorker(null);
});

async function editWorker(id) {
    const modal = document.getElementById('worker-modal');
    const form = document.getElementById('worker-form');
    const title = document.getElementById('worker-modal-title');
    
    if (id) {
        const response = await fetch('/api/admin/workers');
        const workers = await response.json();
        const w = workers.find(worker => worker.id === id);
        
        if (w) {
            title.textContent = 'Modifica Worker';
            document.getElementById('worker-id').value = w.id;
            document.getElementById('worker-name').value = w.name;
            document.getElementById('worker-max-concurrent').value = w.max_concurrent_jobs;
            document.getElementById('worker-active').checked = w.active;
        }
    } else {
        title.textContent = 'Nuovo Worker';
        form.reset();
        document.getElementById('worker-id').value = '';
        document.getElementById('worker-active').checked = true;
    }
    
    modal.classList.add('active');
}

document.getElementById('worker-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const id = document.getElementById('worker-id').value;
    const data = {
        name: document.getElementById('worker-name').value,
        max_concurrent_jobs: parseInt(document.getElementById('worker-max-concurrent').value),
        active: document.getElementById('worker-active').checked
    };
    
    try {
        const url = id ? `/api/admin/workers/${id}` : '/api/admin/workers';
        const method = id ? 'PUT' : 'POST';
        
        const response = await fetch(url, {
            method,
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            document.getElementById('worker-modal').classList.remove('active');
            await loadWorkers();
        } else {
            const error = await response.json();
            alert('Errore: ' + (error.error || 'Errore sconosciuto'));
        }
    } catch (error) {
        alert('Errore: ' + error.message);
    }
});

async function toggleWorker(id, active) {
    const response = await fetch(`/api/admin/workers/${id}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({active})
    });
    
    if (response.ok) {
        await loadWorkers();
    }
}

// Jobs
async function loadJobs() {
    try {
        const response = await fetch('/api/admin/jobs');
        const data = await response.json();
        
        const tbody = document.getElementById('jobs-tbody-admin');
        tbody.innerHTML = '';
        
        data.forEach(job => {
            const row = document.createElement('tr');
            const statusClass = `status-${job.status}`;
            const created = new Date(job.created_at).toLocaleString('it-IT');
            
            row.innerHTML = `
                <td>${escapeHtml(job.input_filename)}</td>
                <td>${job.watchfolder_id || '-'}</td>
                <td><span class="status-badge ${statusClass}">${job.status}</span></td>
                <td>
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <span>${job.progress}%</span>
                        <div class="progress-bar" style="flex: 1;">
                            <div class="progress-fill" style="width: ${job.progress}%"></div>
                        </div>
                    </div>
                </td>
                <td>${created}</td>
                <td>${job.error_message ? escapeHtml(job.error_message.substring(0, 50)) + '...' : '-'}</td>
            `;
            tbody.appendChild(row);
        });
    } catch (error) {
        console.error('Errore caricamento jobs:', error);
    }
}

// Logout
document.getElementById('logout-btn').addEventListener('click', async () => {
    await fetch('/admin/logout', {method: 'POST'});
    window.location.href = '/admin';
});

// Modal close handlers
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.modal-close').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.target.closest('.modal').classList.remove('active');
        });
    });
    
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.classList.remove('active');
            }
        });
    });
    
    document.getElementById('watchfolder-cancel').addEventListener('click', () => {
        document.getElementById('watchfolder-modal').classList.remove('active');
    });
    
    document.getElementById('preset-cancel').addEventListener('click', () => {
        document.getElementById('preset-modal').classList.remove('active');
    });
    
    document.getElementById('worker-cancel').addEventListener('click', () => {
        document.getElementById('worker-modal').classList.remove('active');
    });
    
    // Initial load
    loadSectionData(currentSection);
    
    // Auto-refresh every 5 seconds
    setInterval(() => {
        loadSectionData(currentSection);
    }, 5000);
});

function toggleWatchfolderType() {
    const watchType = document.getElementById('watchfolder-type').value;
    const localFields = document.getElementById('local-fields');
    const ftpFields = document.getElementById('ftp-fields');
    const pathInput = document.getElementById('watchfolder-path');
    
    if (watchType === 'ftp') {
        localFields.style.display = 'none';
        ftpFields.style.display = 'block';
        pathInput.removeAttribute('required');
    } else {
        localFields.style.display = 'block';
        ftpFields.style.display = 'none';
        pathInput.setAttribute('required', 'required');
    }
}

// Logs
async function loadLogs() {
    const lines = document.getElementById('logs-lines').value;
    try {
        const response = await fetch(`/api/admin/logs?lines=${lines}`);
        const data = await response.json();
        
        const content = document.getElementById('logs-content');
        if (data.logs && data.logs.length > 0) {
            content.innerHTML = data.logs.map(line => {
                const logLine = escapeHtml(line.trim());
                let className = 'log-line';
                
                if (logLine.includes('ERROR') || logLine.includes('CRITICAL')) {
                    className += ' log-error';
                } else if (logLine.includes('WARNING') || logLine.includes('WARN')) {
                    className += ' log-warning';
                } else if (logLine.includes('INFO')) {
                    className += ' log-info';
                } else if (logLine.includes('DEBUG')) {
                    className += ' log-debug';
                }
                
                return `<div class="${className}">${logLine}</div>`;
            }).join('');
            
            // Scroll to bottom
            content.scrollTop = content.scrollHeight;
        } else {
            content.innerHTML = '<p style="color: var(--text-secondary);">Nessun log disponibile</p>';
        }
    } catch (error) {
        console.error('Errore caricamento log:', error);
        document.getElementById('logs-content').innerHTML = 
            '<p style="color: var(--error-color);">Errore caricamento log: ' + error.message + '</p>';
    }
}

function refreshLogs() {
    loadLogs();
}

function downloadLogs() {
    window.location.href = '/api/admin/logs/download';
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

