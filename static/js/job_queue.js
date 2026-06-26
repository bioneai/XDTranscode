/** Azioni manuali coda job (condiviso dashboard pubblica e admin). */

const JOB_ACTION_MESSAGES = {
    pause: 'Mettere in pausa questo job?',
    cancel: 'Fermare e annullare questo job?',
    requeue: 'Rimettere in coda questo job?',
    resume: 'Riprendere la transcodifica da capo?',
};

function jobApiBase(scope) {
    return scope === 'admin' ? '/api/admin/jobs' : '/api/public/jobs';
}

async function jobAction(action, jobId, scope) {
    const apiBase = jobApiBase(scope);
    const message = JOB_ACTION_MESSAGES[action] || null;
    if (message && !confirm(message)) {
        return;
    }
    try {
        const response = await fetch(`${apiBase}/${jobId}/${action}`, { method: 'POST' });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            alert(data.error || 'Operazione non riuscita');
            return;
        }
        if (scope === 'admin' && typeof loadJobs === 'function') {
            await loadJobs();
        } else if (typeof fetchStatus === 'function') {
            fetchStatus();
        }
    } catch (error) {
        alert('Errore di connessione');
    }
}

function buildJobActionButtons(job, scope) {
    const parts = [];
    if (job.status === 'pending' || job.status === 'processing') {
        parts.push(`<button type="button" class="btn btn-small btn-secondary" onclick="jobAction('pause', ${job.id}, '${scope}')">Pausa</button>`);
        parts.push(`<button type="button" class="btn btn-small" style="background: var(--warning-color); color: white;" onclick="jobAction('cancel', ${job.id}, '${scope}')">Stop</button>`);
    }
    if (job.status === 'paused') {
        parts.push(`<button type="button" class="btn btn-small btn-primary" onclick="jobAction('resume', ${job.id}, '${scope}')">Riprendi</button>`);
        parts.push(`<button type="button" class="btn btn-small" style="background: var(--warning-color); color: white;" onclick="jobAction('cancel', ${job.id}, '${scope}')">Stop</button>`);
    }
    if (job.status === 'cancelled' || job.status === 'failed') {
        parts.push(`<button type="button" class="btn btn-small btn-primary" onclick="jobAction('requeue', ${job.id}, '${scope}')">Riaccoda</button>`);
    }
    if (!parts.length) {
        return '';
    }
    return `<div class="action-buttons" style="display: flex; flex-wrap: wrap; gap: 4px;">${parts.join('')}</div>`;
}
