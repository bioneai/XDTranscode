import os
import time
import threading
import logging
import ftplib
import ftputil
from models import WatchFolder, TranscodeJob, FileStatus
from datetime import datetime


def _ftp_session_with_timeout(timeout_sec=30):
    """Session factory con timeout connessione per evitare blocchi."""

    class Session(ftplib.FTP):
        def __init__(self, host, user, password, port=21):
            super().__init__()
            self.connect(host, port, timeout=timeout_sec)
            self.login(user, password)

    return Session

# Configura logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('xdcam_transcoder.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('FTPWatcher')

class FTPWatcher:
    def __init__(self, watchfolder_id, db_session_factory):
        self.watchfolder_id = watchfolder_id
        self.db_session_factory = db_session_factory
        self.running = False
        self.thread = None
        self.allowed_extensions = ['.mp4', '.mov', '.avi', '.mxf', '.mkv', '.mts', '.m2ts']
        self.known_files = set()  # Traccia file già processati
        self.pending_files = {}   # filename_lower -> ultimo size visto (attesa upload completo)
    
    def start(self):
        """Avvia monitoraggio FTP"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._watch_loop, daemon=True)
        self.thread.start()
    
    def stop(self):
        """Ferma monitoraggio FTP"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
    
    def _watch_loop(self):
        """Loop principale per monitoraggio FTP"""
        db_session = self.db_session_factory()
        try:
            watchfolder = db_session.query(WatchFolder).filter(
                WatchFolder.id == self.watchfolder_id
            ).first()
            
            if not watchfolder or not watchfolder.active:
                return
            
            logger.info(f"Avvio monitoraggio FTP per watchfolder {watchfolder.name} (ID: {self.watchfolder_id})")
            logger.info(f"FTP Host: {watchfolder.ftp_host}:{watchfolder.ftp_port}")
            logger.info(f"FTP Remote Path: {watchfolder.ftp_remote_path}")
            
            # Aggiorna status
            watchfolder.status = 'monitoring'
            db_session.commit()
        finally:
            db_session.close()
        
        while self.running:
            try:
                self._check_ftp_files()
                time.sleep(30)  # Controlla ogni 30 secondi (attesa upload lunghi)
            except (ftputil.FTPError, OSError, ConnectionError, TimeoutError) as e:
                error_msg = f"Errore FTP watchfolder {self.watchfolder_id}: {type(e).__name__}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                db_session = self.db_session_factory()
                try:
                    watchfolder = db_session.query(WatchFolder).filter(
                        WatchFolder.id == self.watchfolder_id
                    ).first()
                    if watchfolder:
                        watchfolder.status = 'error'
                        db_session.commit()
                finally:
                    db_session.close()
                time.sleep(30)  # Attendi in caso di errore
            except Exception as e:
                error_msg = f"Errore generico FTP watchfolder {self.watchfolder_id}: {type(e).__name__}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                db_session = self.db_session_factory()
                try:
                    watchfolder = db_session.query(WatchFolder).filter(
                        WatchFolder.id == self.watchfolder_id
                    ).first()
                    if watchfolder:
                        watchfolder.status = 'error'
                        db_session.commit()
                finally:
                    db_session.close()
                time.sleep(30)  # Attendi in caso di errore
    
    def _check_ftp_files(self):
        """Controlla nuovi file su FTP"""
        db_session = self.db_session_factory()
        try:
            watchfolder = db_session.query(WatchFolder).filter(
                WatchFolder.id == self.watchfolder_id
            ).first()
            
            if not watchfolder or not watchfolder.active:
                return
            
            logger.info(f"FTP check: connessione a {watchfolder.ftp_host}:{watchfolder.ftp_port}...")
            
            # Connetti a FTP (timeout 30s per evitare blocchi su server irraggiungibili)
            try:
                ftp_password = watchfolder.ftp_password or ''
                session_cls = _ftp_session_with_timeout(30)
                with ftputil.FTPHost(
                    watchfolder.ftp_host,
                    watchfolder.ftp_username,
                    ftp_password,
                    port=watchfolder.ftp_port or 21,
                    session_factory=session_cls
                ) as ftp:
                    # Imposta timeout più lungo per connessioni lente
                    ftp.timeout = 60
                    logger.info(f"FTP connesso a {watchfolder.ftp_host}")
                    
                    # Cambia directory remota
                    remote_path = watchfolder.ftp_remote_path or '/'
                    if remote_path != '/':
                        logger.debug(f"Cambio directory a: {remote_path}")
                        ftp.chdir(remote_path)
                    
                    # Lista file - listdir (compatibile) con fallback mlsd
                    files_info = []
                    try:
                        try:
                            files = ftp.listdir(ftp.curdir)
                        except Exception:
                            files = ftp.listdir('.')
                        for filename in files:
                            if filename in ('.', '..') or '/' in filename:
                                continue
                            try:
                                if ftp.path.isfile(filename):
                                    size = ftp.path.getsize(filename)
                                    files_info.append({'name': filename, 'size': size, 'modify': ''})
                            except Exception:
                                files_info.append({'name': filename, 'size': 0, 'modify': ''})
                    except Exception as listdir_err:
                        logger.info(f"listdir fallito ({listdir_err}), provo mlsd")
                        try:
                            for item in ftp.mlsd(ftp.curdir):
                                name, facts = item
                                if name in ('.', '..'):
                                    continue
                                ftype = (facts.get('type') or '').lower()
                                if ftype in ('dir', 'cdir', 'pdir'):
                                    continue
                                if ftype == 'file' or not ftype:
                                    try:
                                        sz = facts.get('size', 0)
                                        size = int(sz) if sz else 0
                                    except (TypeError, ValueError):
                                        size = 0
                                    files_info.append({'name': name, 'size': size, 'modify': facts.get('modify', '')})
                        except Exception as mlsd_err:
                            logger.error(f"Anche mlsd fallito: {mlsd_err}")
                            raise
                    
                    logger.info(f"FTP watchfolder {self.watchfolder_id}: trovati {len(files_info)} file in {remote_path}")
                    
                    # Verifica file nel database una volta per tutti (case-insensitive)
                    existing_filenames_lower = set()
                    check_db_session = self.db_session_factory()
                    try:
                        existing_jobs = check_db_session.query(TranscodeJob).filter(
                            TranscodeJob.watchfolder_id == self.watchfolder_id
                        ).all()
                        existing_filenames_lower = {job.input_filename.lower() for job in existing_jobs}
                    finally:
                        check_db_session.close()
                    
                    for file_info in files_info:
                        if not self.running:
                            break
                        
                        filename = file_info['name']
                        file_size = file_info.get('size', 0)
                        if isinstance(file_size, str):
                            try:
                                file_size = int(file_size)
                            except (TypeError, ValueError):
                                file_size = 0
                        
                        # Verifica estensione
                        file_ext = os.path.splitext(filename)[1].lower()
                        if file_ext not in self.allowed_extensions:
                            continue
                        
                        # Verifica se già processato (case-insensitive)
                        filename_lower = filename.lower()
                        if filename_lower in self.known_files or filename_lower in existing_filenames_lower:
                            if filename_lower not in self.known_files:
                                self.known_files.add(filename_lower)
                            if filename_lower in self.pending_files:
                                del self.pending_files[filename_lower]
                            continue
                        
                        # Verifica se è un file (non directory) - skip per path con /
                        if '/' in filename:
                            continue
                        try:
                            if not ftp.path.isfile(filename):
                                continue
                        except Exception:
                            continue
                        # Regola: size stabile su due controlli consecutivi (30s) = upload completo
                        if filename_lower in self.pending_files:
                            prev_size = self.pending_files[filename_lower]
                            if file_size == prev_size and file_size > 0:
                                # Size invariato da ultimo check: upload completato
                                del self.pending_files[filename_lower]
                                logger.info(f"Nuovo file rilevato su FTP (size stabile): {filename} ({file_size} bytes)")
                                self._process_ftp_file(watchfolder, ftp, filename, file_size)
                                self.known_files.add(filename_lower)
                            else:
                                # Size cambiato: ancora in upload
                                self.pending_files[filename_lower] = file_size
                                logger.info(f"File {filename} in upload ({prev_size} -> {file_size} bytes), prossimo check tra 30s")
                        else:
                            # Primo avvistamento: salva size e aspetta prossimo ciclo
                            self.pending_files[filename_lower] = file_size
                            logger.info(f"File {filename} rilevato ({file_size} bytes), attendo verifica size tra 30s")
            
            except ftputil.FTPError as e:
                logger.error(f"Errore connessione FTP a {watchfolder.ftp_host}:{watchfolder.ftp_port} - {str(e)}")
                raise
            except Exception as e:
                logger.error(f"Errore durante controllo file FTP: {str(e)}", exc_info=True)
                raise
        
        finally:
            db_session.close()
    
    def _process_ftp_file(self, watchfolder, ftp, filename, file_size_remote=0):
        """Processa file da FTP"""
        db_session = self.db_session_factory()
        try:
            # Verifica se job già esistente
            existing = db_session.query(TranscodeJob).filter(
                TranscodeJob.input_filename == filename,
                TranscodeJob.watchfolder_id == self.watchfolder_id,
                TranscodeJob.status.in_([FileStatus.PENDING, FileStatus.PROCESSING])
            ).first()
            
            if existing:
                return
            
            # Crea directory temporanea locale se non esiste
            local_temp = watchfolder.ftp_local_temp or '/tmp/xdcam_ftp'
            if not os.path.exists(local_temp):
                os.makedirs(local_temp, exist_ok=True)
            
            # Path locale temporaneo per download
            local_file_path = os.path.join(local_temp, filename)
            
            # Verifica se file già scaricato (potrebbe essere in corso)
            if os.path.exists(local_file_path):
                # Verifica dimensione - se è stabile da 5 secondi, procedi
                time.sleep(5)
                size1 = os.path.getsize(local_file_path)
                time.sleep(2)
                size2 = os.path.getsize(local_file_path)
                if size1 != size2:
                    return  # File ancora in download
            
            # Download file da FTP
            try:
                logger.info(f"Download file {filename} da FTP a {local_file_path}")
                ftp.download(filename, local_file_path)
                file_size = os.path.getsize(local_file_path)
                logger.info(f"Download completato: {filename} ({file_size} bytes)")
            except Exception as e:
                logger.error(f"Errore download file {filename} da FTP: {str(e)}", exc_info=True)
                return
            
            # Verifica dimensione file (file_size già impostato dal download)
            if not os.path.exists(local_file_path):
                return
            file_size = os.path.getsize(local_file_path)
            if file_size == 0:
                os.remove(local_file_path)
                return
            
            # Crea output path
            output_dir = watchfolder.output_path if watchfolder.output_path else local_temp
            if not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)
            
            base_name = os.path.splitext(filename)[0]
            container = watchfolder.preset.container if watchfolder.preset else 'mxf'
            preset_name = watchfolder.preset.name.lower().replace(' ', '_') if watchfolder.preset else 'default'
            output_filename = f"{base_name}_{preset_name}.{container}"
            output_path = os.path.join(output_dir, output_filename)
            
            # Crea job
            job = TranscodeJob(
                watchfolder_id=self.watchfolder_id,
                preset_id=watchfolder.preset_id,
                input_filename=filename,
                input_path=local_file_path,
                output_path=output_path,
                status=FileStatus.PENDING,
                input_size=file_size
            )
            
            db_session.add(job)
            db_session.commit()
            
            logger.info(f"File FTP {filename} scaricato e job {job.id} creato")
            
        except Exception as e:
            db_session.rollback()
            logger.error(f"Errore processando file FTP {filename}: {str(e)}", exc_info=True)
        finally:
            db_session.close()

