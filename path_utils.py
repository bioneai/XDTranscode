"""Permessi condivisi per directory/file generati dal servizio."""

import os

SHARED_DIR_MODE = 0o2775
SHARED_FILE_MODE = 0o664


def configure_shared_umask():
    """File 664 e directory 775 per il gruppo del servizio."""
    os.umask(0o002)


def ensure_shared_directory(path):
    """Crea una directory scrivibile dal gruppo (es. xdtranscode)."""
    if not path:
        return
    os.makedirs(path, mode=SHARED_DIR_MODE, exist_ok=True)
    try:
        os.chmod(path, SHARED_DIR_MODE)
    except OSError:
        pass


def ensure_shared_file(path):
    """Rende un file generato dall'app leggibile/scrivibile dal gruppo."""
    if not path or not os.path.exists(path):
        return
    try:
        os.chmod(path, SHARED_FILE_MODE)
    except OSError:
        pass
