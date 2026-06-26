"""Azioni manuali sulla coda job (pausa, stop, riaccoda)."""

import os
from datetime import datetime

from models import TranscodeJob, FileStatus


REQUEUEABLE = frozenset({
    FileStatus.PAUSED,
    FileStatus.CANCELLED,
    FileStatus.FAILED,
})

PAUSABLE = frozenset({
    FileStatus.PENDING,
    FileStatus.PROCESSING,
})

CANCELLABLE = frozenset({
    FileStatus.PENDING,
    FileStatus.PROCESSING,
    FileStatus.PAUSED,
})


def _clear_worker_assignment(job):
    job.worker_id = None


def _remove_partial_output(job):
    if job.output_path and os.path.exists(job.output_path):
        try:
            os.remove(job.output_path)
        except OSError:
            pass


def pause_job(job):
    """Mette in pausa un job (in coda o in elaborazione)."""
    if job.status not in PAUSABLE:
        raise ValueError(f'Job non mettibile in pausa (stato: {job.status.value})')
    job.status = FileStatus.PAUSED
    _clear_worker_assignment(job)
    job.completed_at = None


def cancel_job(job):
    """Ferma/annulla un job."""
    if job.status not in CANCELLABLE:
        raise ValueError(f'Job non annullabile (stato: {job.status.value})')
    was_active = job.status == FileStatus.PROCESSING
    job.status = FileStatus.CANCELLED
    _clear_worker_assignment(job)
    job.completed_at = datetime.utcnow()
    if was_active or job.progress:
        _remove_partial_output(job)


def requeue_job(job):
    """Rimette in coda un job pausato, annullato o fallito."""
    if job.status not in REQUEUEABLE:
        raise ValueError(f'Job non riaccodabile (stato: {job.status.value})')
    if not os.path.exists(job.input_path):
        raise ValueError(f'File input non trovato: {job.input_path}')
    if not os.access(job.input_path, os.R_OK):
        raise ValueError('Permessi insufficienti per leggere il file input')

    _remove_partial_output(job)
    job.status = FileStatus.PENDING
    job.worker_id = None
    job.progress = 0
    job.error_message = None
    job.started_at = None
    job.completed_at = None
    job.output_size = None
    job.output_duration = None
    job.output_mediainfo = None


def resume_job(job):
    """Riprende un job in pausa (ricomincia la transcodifica da capo)."""
    if job.status != FileStatus.PAUSED:
        raise ValueError(f'Solo i job in pausa possono essere ripresi (stato: {job.status.value})')
    requeue_job(job)
