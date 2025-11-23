// Public Dashboard JavaScript

let refreshInterval;

async function fetchStatus() {
    try {
        const response = await fetch('/api/public/status');
        const data = await response.json();
        
        updateWatchfolders(data.watchfolders);
        updateJobs(data.recent_jobs);
        updateWorkers(data.workers);
    } catch (error) {
        console.error('Errore caricamento status:', error);
    }
}

function updateWatchfolders(watchfolders) {
    const grid = document.getElementById('watchfolders-grid');
    grid.innerHTML = '';
    
    if (watchfolders.length === 0) {
        grid.innerHTML = '<p style="color: var(--text-secondary);">Nessun watchfolder attivo</p>';
        return;
    }
    
    watchfolders.forEach(wf => {
        const card = document.createElement('div');
        card.className = 'watchfolder-card';
        
        const statusClass = `status-${wf.status}`;
        const activeText = wf.active ? 'Attivo' : 'Inattivo';
        
        card.innerHTML = `
            <h3>${escapeHtml(wf.name)}</h3>
            <div class="watchfolder-status ${statusClass}">${wf.status}</div>
            <p style="color: var(--text-secondary); font-size: 12px; margin-bottom: 15px;">
                ${escapeHtml(wf.path)}
            </p>
            <div class="watchfolder-stats">
                <div class="stat-item">
                    <div class="stat-value">${wf.total_files}</div>
                    <div class="stat-label">Totali</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value" style="color: var(--warning-color);">${wf.pending}</div>
                    <div class="stat-label">In Attesa</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value" style="color: var(--accent-color);">${wf.processing}</div>
                    <div class="stat-label">In Elaborazione</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value" style="color: var(--success-color);">${wf.completed}</div>
                    <div class="stat-label">Completati</div>
                </div>
            </div>
        `;
        
        grid.appendChild(card);
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
                <div style="display: flex; align-items: center; gap: 10px;">
                    <span>${progress}%</span>
                    <div class="progress-bar" style="flex: 1;">
                        <div class="progress-fill" style="width: ${progress}%"></div>
                    </div>
                </div>
            </td>
            <td>${startedAt}</td>
            <td>
                <button class="btn btn-small btn-secondary" onclick="showJobDetails(${job.id})">
                    Dettagli
                </button>
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

