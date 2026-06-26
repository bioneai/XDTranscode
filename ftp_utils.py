"""Utility condivise per connessioni FTP/FTPS."""

import ftplib
from ftputil.error import FTPError, PermanentError, TemporaryError

DEFAULT_FTP_LOCAL_TEMP = '/var/lib/xdtranscode/ftp_temp'

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
