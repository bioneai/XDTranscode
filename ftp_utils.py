"""Utility condivise per connessioni FTP/FTPS."""

import os
import ftplib
from ftputil.error import FTPError, PermanentError, TemporaryError

from models import FileStatus, OPERATION_MODE_DOWNLOAD_ONLY

DEFAULT_FTP_LOCAL_TEMP = '/var/lib/xdtranscode/ftp_temp'

# Estensioni video accettate da watchfolder locali e FTP
VIDEO_EXTENSIONS = (
    '.mp4', '.m4v', '.mov', '.avi', '.mxf', '.mkv', '.mts', '.m2ts',
)

# Eccezioni FTP da intercettare (ftputil.FTPError non esiste come attributo del modulo)
FTP_EXCEPTIONS = (
    FTPError,
    PermanentError,
    TemporaryError,
    ftplib.error_perm,
    ftplib.error_temp,
    ftplib.error_proto,
    ftplib.error_reply,
    OSError,
    ConnectionError,
    TimeoutError,
)


def ftp_session_factory(timeout_sec=30):
    """Factory sessione ftplib con timeout e modalità passiva."""

    class Session(ftplib.FTP):
        def __init__(self, host, user, password, port=21):
            super().__init__()
            self.connect(host, port, timeout=timeout_sec)
            self.login(user, password)
            self.set_pasv(True)

    return Session


def normalize_ftp_remote_path(remote_path):
    """Normalizza path remoto per server che non accettano slash iniziale."""
    path = (remote_path or '/').strip()
    if path in ('', '/'):
        return '/'
    return path.strip('/')


def chdir_ftp(ftp, remote_path):
    """Cambia directory remota gestendo path assoluti e relativi."""
    path = normalize_ftp_remote_path(remote_path)
    if path == '/':
        return
    for part in path.split('/'):
        if part:
            ftp.chdir(part)


def test_ftp_connection(host, username, password, port=21, remote_path='/', timeout=30):
    """
    Verifica connessione FTP.
    Ritorna (ok: bool, message: str).
    """
    import ftputil

    if not host or not username:
        return False, 'Host e username FTP obbligatori'

    try:
        session_cls = ftp_session_factory(timeout)
        with ftputil.FTPHost(
            host,
            username,
            password or '',
            port=port or 21,
            session_factory=session_cls,
        ) as ftp:
            chdir_ftp(ftp, remote_path)
        return True, 'Connessione FTP riuscita'
    except PermanentError as e:
        msg = str(e).strip()
        if '530' in msg or 'login' in msg.lower():
            return False, f'Login FTP fallito: {msg}'
        return False, f'Errore FTP permanente: {msg}'
    except FTP_EXCEPTIONS as e:
        return False, f'Errore connessione FTP: {type(e).__name__}: {e}'
    except Exception as e:
        return False, f'Errore connessione FTP: {type(e).__name__}: {e}'


def is_download_only_watchfolder(watchfolder):
    """True se il watchfolder FTP è in modalità solo download."""
    return (
        (watchfolder.watch_type or 'local') == 'ftp'
        and (watchfolder.operation_mode or 'transcode') == OPERATION_MODE_DOWNLOAD_ONLY
    )


def job_blocks_ftp_redetection(job):
    """Indica se un job esistente impedisce di rilevare di nuovo lo stesso file su FTP."""
    if job.status in (
        FileStatus.PENDING,
        FileStatus.PROCESSING,
        FileStatus.PAUSED,
        FileStatus.COMPLETED,
    ):
        return True
    if job.status in (FileStatus.FAILED, FileStatus.CANCELLED):
        if job.input_path and os.path.exists(job.input_path):
            return True
    return False


def download_with_progress(ftp, remote_name, local_path, total_size=0, progress_callback=None):
    """Scarica un file FTP aggiornando il progresso via callback(percent)."""
    bytes_received = 0
    last_reported = -1

    def callback(chunk):
        nonlocal bytes_received, last_reported
        bytes_received += len(chunk)
        if not progress_callback:
            return
        if total_size and total_size > 0:
            percent = min(99, int(bytes_received * 100 / total_size))
        else:
            percent = min(99, bytes_received // (1024 * 1024))
        if percent > last_reported:
            last_reported = percent
            progress_callback(percent)

    ftp.download(remote_name, local_path, callback=callback)
    if progress_callback:
        progress_callback(100)
