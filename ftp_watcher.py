import os
import time
import threading
import logging
import ftputil
from models import WatchFolder, TranscodeJob, FileStatus
from ftp_utils import (
    DEFAULT_FTP_LOCAL_TEMP,
    FTP_EXCEPTIONS,
    chdir_ftp,
    ftp_session_factory,
)

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
        self.known_files = set()
        self.pending_files = {}
        self.last_error = None

    def start(self):
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._watch_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)

    def _set_watchfolder_status(self, status):
        db_session = self.db_session_factory()
        try:
            watchfolder = db_session.query(WatchFolder).filter(
                WatchFolder.id == self.watchfolder_id
            ).first()
            if watchfolder:
                watchfolder.status = status
                db_session.commit()
        finally:
            db_session.close()

    def _watch_loop(self):
        db_session = self.db_session_factory()
        try:
            watchfolder = db_session.query(WatchFolder).filter(
                WatchFolder.id == self.watchfolder_id
            ).first()

            if not watchfolder or not watchfolder.active:
                return

            logger.info(
                f"Avvio monitoraggio FTP per watchfolder {watchfolder.name} (ID: {self.watchfolder_id})"
            )
            logger.info(f"FTP Host: {watchfolder.ftp_host}:{watchfolder.ftp_port}")
            logger.info(f"FTP Remote Path: {watchfolder.ftp_remote_path}")
        finally:
            db_session.close()

        while self.running:
            try:
                self._check_ftp_files()
                self.last_error = None
                time.sleep(30)
            except FTP_EXCEPTIONS as e:
                self.last_error = str(e)
                error_msg = (
                    f"Errore FTP watchfolder {self.watchfolder_id}: "
                    f"{type(e).__name__}: {self.last_error}"
                )
                logger.error(error_msg, exc_info=True)
                self._set_watchfolder_status('error')
                time.sleep(30)
            except Exception as e:
                self.last_error = str(e)
                error_msg = (
                    f"Errore generico FTP watchfolder {self.watchfolder_id}: "
                    f"{type(e).__name__}: {self.last_error}"
                )
                logger.error(error_msg, exc_info=True)
                self._set_watchfolder_status('error')
                time.sleep(30)

    def _check_ftp_files(self):
        db_session = self.db_session_factory()
        try:
            watchfolder = db_session.query(WatchFolder).filter(
                WatchFolder.id == self.watchfolder_id
            ).first()

            if not watchfolder or not watchfolder.active:
                return

            logger.info(
                f"FTP check: connessione a {watchfolder.ftp_host}:{watchfolder.ftp_port}..."
            )

            ftp_password = watchfolder.ftp_password or ''
            session_cls = ftp_session_factory(30)
            with ftputil.FTPHost(
                watchfolder.ftp_host,
                watchfolder.ftp_username,
                ftp_password,
                port=watchfolder.ftp_port or 21,
                session_factory=session_cls,
            ) as ftp:
                ftp.timeout = 60
                logger.info(f"FTP connesso a {watchfolder.ftp_host}")

                remote_path = watchfolder.ftp_remote_path or '/'
                chdir_ftp(ftp, remote_path)
                self._set_watchfolder_status('monitoring')

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
                                files_info.append({
                                    'name': name,
                                    'size': size,
                                    'modify': facts.get('modify', ''),
                                })
                    except Exception as mlsd_err:
                        logger.error(f"Anche mlsd fallito: {mlsd_err}")
                        raise

                logger.info(
                    f"FTP watchfolder {self.watchfolder_id}: "
                    f"trovati {len(files_info)} file in {remote_path}"
                )

                existing_filenames_lower = set()
                check_db_session = self.db_session_factory()
                try:
                    existing_jobs = check_db_session.query(TranscodeJob).filter(
                        TranscodeJob.watchfolder_id == self.watchfolder_id
                    ).all()
                    existing_filenames_lower = {
                        job.input_filename.lower() for job in existing_jobs
                    }
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

                    file_ext = os.path.splitext(filename)[1].lower()
                    if file_ext not in self.allowed_extensions:
                        continue

                    filename_lower = filename.lower()
                    if (
                        filename_lower in self.known_files
                        or filename_lower in existing_filenames_lower
                    ):
                        if filename_lower not in self.known_files:
                            self.known_files.add(filename_lower)
                        if filename_lower in self.pending_files:
                            del self.pending_files[filename_lower]
                        continue

                    if '/' in filename:
                        continue
                    try:
                        if not ftp.path.isfile(filename):
                            continue
                    except Exception:
                        continue

                    if filename_lower in self.pending_files:
                        prev_size = self.pending_files[filename_lower]
                        if file_size == prev_size and file_size > 0:
                            del self.pending_files[filename_lower]
                            logger.info(
                                f"Nuovo file rilevato su FTP (size stabile): "
                                f"{filename} ({file_size} bytes)"
                            )
                            self._process_ftp_file(watchfolder, ftp, filename, file_size)
                            self.known_files.add(filename_lower)
                        else:
                            self.pending_files[filename_lower] = file_size
                            logger.info(
                                f"File {filename} in upload "
                                f"({prev_size} -> {file_size} bytes), prossimo check tra 30s"
                            )
                    else:
                        self.pending_files[filename_lower] = file_size
                        logger.info(
                            f"File {filename} rilevato ({file_size} bytes), "
                            f"attendo verifica size tra 30s"
                        )

        finally:
            db_session.close()

    def _process_ftp_file(self, watchfolder, ftp, filename, file_size_remote=0):
        db_session = self.db_session_factory()
        try:
            existing = db_session.query(TranscodeJob).filter(
                TranscodeJob.input_filename == filename,
                TranscodeJob.watchfolder_id == self.watchfolder_id,
                TranscodeJob.status.in_([
                    FileStatus.PENDING,
                    FileStatus.PROCESSING,
                    FileStatus.PAUSED,
                ]),
            ).first()

            if existing:
                return

            local_temp = watchfolder.ftp_local_temp or DEFAULT_FTP_LOCAL_TEMP
            os.makedirs(local_temp, exist_ok=True)

            local_file_path = os.path.join(local_temp, filename)

            if os.path.exists(local_file_path):
                time.sleep(5)
                size1 = os.path.getsize(local_file_path)
                time.sleep(2)
                size2 = os.path.getsize(local_file_path)
                if size1 != size2:
                    return

            try:
                logger.info(f"Download file {filename} da FTP a {local_file_path}")
                ftp.download(filename, local_file_path)
                file_size = os.path.getsize(local_file_path)
                logger.info(f"Download completato: {filename} ({file_size} bytes)")
            except Exception as e:
                logger.error(
                    f"Errore download file {filename} da FTP: {str(e)}",
                    exc_info=True,
                )
                return

            if not os.path.exists(local_file_path):
                return
            file_size = os.path.getsize(local_file_path)
            if file_size == 0:
                os.remove(local_file_path)
                return

            output_dir = watchfolder.output_path if watchfolder.output_path else local_temp
            os.makedirs(output_dir, exist_ok=True)

            base_name = os.path.splitext(filename)[0]
            container = watchfolder.preset.container if watchfolder.preset else 'mxf'
            preset_name = (
                watchfolder.preset.name.lower().replace(' ', '_')
                if watchfolder.preset
                else 'default'
            )
            output_filename = f"{base_name}_{preset_name}.{container}"
            output_path = os.path.join(output_dir, output_filename)

            job = TranscodeJob(
                watchfolder_id=self.watchfolder_id,
                preset_id=watchfolder.preset_id,
                input_filename=filename,
                input_path=local_file_path,
                output_path=output_path,
                status=FileStatus.PENDING,
                input_size=file_size,
            )

            db_session.add(job)
            db_session.commit()

            logger.info(f"File FTP {filename} scaricato e job {job.id} creato")

        except Exception as e:
            db_session.rollback()
            logger.error(
                f"Errore processando file FTP {filename}: {str(e)}",
                exc_info=True,
            )
        finally:
            db_session.close()
