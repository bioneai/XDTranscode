// Public Dashboard JavaScript

let refreshInterval;

async function fetchStatus() {
    try {
        const response = await fetch('/api/public/status');
        const data = await response.json();
        
        updateCpu(data.cpu_percent);
        updateWatchfolders(data.watchfolders);
        updateJobs(data.recent_jobs);
        updateWorkers(data.workers);
    } catch (error) {
        console.error('Errore caricamento status:', error);
    }
}

function updateCpu(cpuPercent) {
    const el = document.getElementById('cpu-indicator');
    if (!el) return;
    const valueEl = el.querySelector('.cpu-value');
    if (!valueEl) return;
    valueEl.textContent = cpuPercent != null ? cpuPercent : '--';
    el.classList.toggle('cpu-high', cpuPercent != null && cpuPercent >= 80);
}

function updateWatchfolders(watchfolders) {
    const grid = document.getElementById('watchfolders-grid');
    const header = document.querySelector('.watchfolder-header');
    grid.innerHTML = '';
    
    if (watchfolders.length === 0) {
        if (header) header.style.display = 'none';
        grid.innerHTML = '<p class="watchfolders-empty">Nessun watchfolder attivo</p>';
        return;
    }
    if (header) header.style.display = 'grid';
    
    const sorted = [...watchfolders].sort((a, b) => (a.priority ?? 10) - (b.priority ?? 10) || a.name.localeCompare(b.name));

    sorted.forEach(wf => {
        const row = document.createElement('div');
        row.className = 'watchfolder-row';
        const statusClass = `status-${wf.status}`;
        
        row.innerHTML = `
            <span class="wf-name" title="${escapeHtml(wf.path)}">${escapeHtml(wf.name)}</span>
            <span class="wf-priority" title="Priorità">${wf.priority ?? 10}</span>
            <span class="wf-status ${statusClass}">${wf.status}</span>
            <span class="wf-stat" title="In attesa"><span class="wf-num wf-pending">${wf.pending}</span></span>
            <span class="wf-stat" title="In elaborazione"><span class="wf-num wf-processing">${wf.processing}</span></span>
            <span class="wf-stat" title="Completati"><span class="wf-num wf-completed">${wf.completed}</span></span>
        `;
        
        grid.appendChild(row);
    });
}

function updateJobs(jobs) {
    const tbody = document.getElementById('jobs-tbody');
    tbody.innerHTML = '';
    
    if (jobs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-secondary);">Nessun job disponibile</td></tr>';
        return;
    }
    
    jobs.forEach(job => {
        const row = document.createElement('tr');
        
        const statusClass = `status-${job.status}`;
        const progress = job.progress || 0;
        const startedAt = job.started_at ? new Date(job.started_at).toLocaleString('it-IT') : '-';
        
        row.innerHTML = `
            <td>${escapeHtml(job.filename)}</td>
            <td>${escapeHtml(job.watchfolder)}</td>
            <td><span class="status-badge ${statusClass}">${job.status}</span></td>
            <td>
                <div class="progress-cell">
                    <span class="progress-pct">${progress}%</span>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: ${progress}%"></div>
                    </div>
                </div>
            </td>
            <td>${startedAt}</td>
            <td>
                <button class="btn btn-small btn-secondary" onclick="showJobDetails(${job.id})">
                    Dettagli
                </button>
                ${buildJobActionButtons(job, 'public')}
            </td>
        `;
        
        tbody.appendChild(row);
    });
}

function updateWorkers(workers) {
    const grid = document.getElementById('workers-grid');
    grid.innerHTML = '';
    
    if (workers.length === 0) {
        grid.innerHTML = '<p style="color: var(--text-secondary);">Nessun worker attivo</p>';
        return;
    }
    
    workers.forEach(worker => {
        const card = document.createElement('div');
        card.className = 'worker-card';
        
        const statusClass = worker.status === 'running' ? 'status-processing' : 'status-idle';
        const activeText = worker.active ? 'Attivo' : 'Inattivo';
        
        card.innerHTML = `
            <h3>${escapeHtml(worker.name)}</h3>
            <div class="watchfolder-status ${statusClass}">${worker.status}</div>
            <p style="color: var(--text-secondary); font-size: 12px; margin-top: 10px;">
                Job corrente: ${worker.current_job_id || 'Nessuno'}
            </p>
        `;
        
        grid.appendChild(card);
    });
}

async function showJobDetails(jobId) {
    try {
        const response = await fetch(`/api/public/jobs/${jobId}`);
        const job = await response.json();
        
        const modal = document.getElementById('job-modal');
        const content = document.getElementById('job-details-content');
        
        const formatBytes = (bytes) => {
            if (!bytes) return 'N/A';
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
        };
        
        const formatDuration = (seconds) => {
            if (!seconds) return 'N/A';
            const h = Math.floor(seconds / 3600);
            const m = Math.floor((seconds % 3600) / 60);
            const s = Math.floor(seconds % 60);
            return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
        };
        
        content.innerHTML = `
            <div style="display: grid; gap: 15px;">
                <div>
                    <strong>File:</strong> ${escapeHtml(job.filename)}
                </div>
                <div>
                    <strong>Watchfolder:</strong> ${escapeHtml(job.watchfolder)}
                </div>
                <div>
                    <strong>Preset:</strong> ${escapeHtml(job.preset)}
                </div>
                <div>
                    <strong>Status:</strong> <span class="status-badge status-${job.status}">${job.status}</span>
                </div>
                <div>
                    <strong>Progress:</strong> ${job.progress}%
                    <div class="progress-bar" style="margin-top: 5px;">
                        <div class="progress-fill" style="width: ${job.progress}%"></div>
                    </div>
                </div>
                <div>
                    <strong>Input Size:</strong> ${formatBytes(job.input_size)}
                </div>
                <div>
                    <strong>Output Size:</strong> ${formatBytes(job.output_size)}
                </div>
                <div>
                    <strong>Input Duration:</strong> ${formatDuration(job.input_duration)}
                </div>
                <div>
                    <strong>Output Duration:</strong> ${formatDuration(job.output_duration)}
                </div>
                <div>
                    <strong>Created:</strong> ${new Date(job.created_at).toLocaleString('it-IT')}
                </div>
                ${job.started_at ? `<div><strong>Started:</strong> ${new Date(job.started_at).toLocaleString('it-IT')}</div>` : ''}
                ${job.completed_at ? `<div><strong>Completed:</strong> ${new Date(job.completed_at).toLocaleString('it-IT')}</div>` : ''}
                ${job.error_message ? `<div style="color: var(--warning-color);"><strong>Error:</strong> ${escapeHtml(job.error_message)}</div>` : ''}
                ${job.input_mediainfo ? `
                <details style="margin-top: 15px;">
                    <summary style="cursor: pointer; font-weight: bold;">MediaInfo file in ingresso</summary>
                    <pre style="background: #1a1a1a; padding: 12px; border-radius: 6px; overflow-x: auto; font-size: 11px; max-height: 200px; overflow-y: auto;">${escapeHtml(job.input_mediainfo)}</pre>
                </details>` : ''}
                ${job.output_mediainfo ? `
                <details style="margin-top: 15px;">
                    <summary style="cursor: pointer; font-weight: bold;">MediaInfo file in uscita</summary>
                    <pre style="background: #1a1a1a; padding: 12px; border-radius: 6px; overflow-x: auto; font-size: 11px; max-height: 200px; overflow-y: auto;">${escapeHtml(job.output_mediainfo)}</pre>
                </details>` : ''}
            </div>
        `;
        
        modal.classList.add('active');
    } catch (error) {
        console.error('Errore caricamento dettagli job:', error);
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Modal close handlers
document.addEventListener('DOMContentLoaded', () => {
    const modal = document.getElementById('job-modal');
    const closeBtn = modal.querySelector('.modal-close');
    
    closeBtn.addEventListener('click', () => {
        modal.classList.remove('active');
    });
    
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.classList.remove('active');
        }
    });
    
    // Initial load
    fetchStatus();
    
    // Auto-refresh every 3 seconds
    refreshInterval = setInterval(fetchStatus, 3000);
});

