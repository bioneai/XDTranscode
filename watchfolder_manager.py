import os
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from sqlalchemy.orm import Session
from models import WatchFolder, TranscodeJob, FileStatus
from datetime import datetime

class WatchFolderHandler(FileSystemEventHandler):
    def __init__(self, watchfolder_id, db_session_factory):
        self.watchfolder_id = watchfolder_id
        self.db_session_factory = db_session_factory
        self.allowed_extensions = ['.mp4', '.mov', '.avi', '.mxf', '.mkv', '.mts', '.m2ts']
    
    def on_created(self, event):
        if not event.is_directory:
            file_path = event.src_path
            file_ext = os.path.splitext(file_path)[1].lower()
            
            if file_ext in self.allowed_extensions:
                self.process_file(file_path)
    
    def process_file(self, file_path):
        """Crea job di transcodifica per il file rilevato"""
        db_session = self.db_session_factory()
        try:
            # Verifica che il file esista e non sia in fase di scrittura
            if not os.path.exists(file_path):
                return
            
            # Attendi che il file sia completamente scritto
            time.sleep(2)
            
            # Verifica dimensione file
            try:
                file_size = os.path.getsize(file_path)
            except OSError as e:
                print(f"Errore accesso file {file_path}: {str(e)}")
                return
            
            if file_size == 0:
                return
            
            # Verifica permessi lettura
            if not os.access(file_path, os.R_OK):
                print(f"Permessi insufficienti per file {file_path}")
                return
            
            # Recupera watchfolder
            watchfolder = db_session.query(WatchFolder).filter(
                WatchFolder.id == self.watchfolder_id
            ).first()
            
            if not watchfolder or not watchfolder.active:
                return
            
            # Verifica se job già esistente per questo file
            existing = db_session.query(TranscodeJob).filter(
                TranscodeJob.input_path == file_path,
                TranscodeJob.status.in_([FileStatus.PENDING, FileStatus.PROCESSING])
            ).first()
            
            if existing:
                return
            
            # Crea output path
            output_dir = watchfolder.output_path if watchfolder.output_path else os.path.dirname(file_path)
            
            # Verifica/crea directory output
            if not os.path.exists(output_dir):
                try:
                    os.makedirs(output_dir, exist_ok=True)
                except OSError as e:
                    print(f"Errore creazione directory output {output_dir}: {str(e)}")
                    return
            
            # Verifica permessi scrittura directory output
            if not os.access(output_dir, os.W_OK):
                print(f"Permessi insufficienti per scrivere in {output_dir}")
                return
            
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            container = watchfolder.preset.container if watchfolder.preset else 'mxf'
            preset_name = watchfolder.preset.name.lower().replace(' ', '_') if watchfolder.preset else 'default'
            output_filename = f"{base_name}_{preset_name}.{container}"
            output_path = os.path.join(output_dir, output_filename)
            
            # Crea job
            job = TranscodeJob(
                watchfolder_id=self.watchfolder_id,
                preset_id=watchfolder.preset_id,
                input_filename=os.path.basename(file_path),
                input_path=file_path,
                output_path=output_path,
                status=FileStatus.PENDING,
                input_size=file_size
            )
            
            db_session.add(job)
            db_session.commit()
            
        except Exception as e:
            db_session.rollback()
            print(f"Errore processando file {file_path}: {str(e)}")
        finally:
            db_session.close()

class WatchFolderManager:
    def __init__(self, db_session_factory):
        self.db_session_factory = db_session_factory
        self.observers = {}  # watchfolder_id -> Observer (per local)
        self.ftp_watchers = {}  # watchfolder_id -> FTPWatcher (per FTP)
    
    def start_watchfolder(self, watchfolder_id):
        """Avvia monitoraggio watchfolder"""
        db_session = self.db_session_factory()
        try:
            watchfolder = db_session.query(WatchFolder).filter(
                WatchFolder.id == watchfolder_id
            ).first()
            
            if not watchfolder:
                return
            
            watch_type = watchfolder.watch_type or 'local'
            
            if watch_type == 'ftp':
                # Avvia watcher FTP
                if watchfolder_id in self.ftp_watchers:
                    return  # Già attivo
                
                # Verifica parametri FTP
                if not watchfolder.ftp_host or not watchfolder.ftp_username:
                    watchfolder.status = 'error'
                    db_session.commit()
                    return
                
                from ftp_watcher import FTPWatcher
                ftp_watcher = FTPWatcher(watchfolder_id, self.db_session_factory)
                ftp_watcher.start()
                self.ftp_watchers[watchfolder_id] = ftp_watcher
                
            else:
                # Avvia watcher locale
                if watchfolder_id in self.observers:
                    return  # Già attivo
                
                if not os.path.exists(watchfolder.path):
                    watchfolder.status = 'error'
                    db_session.commit()
                    return
                
                # Crea handler e observer
                handler = WatchFolderHandler(watchfolder_id, self.db_session_factory)
                observer = Observer()
                observer.schedule(handler, watchfolder.path, recursive=False)
                observer.start()
                
                self.observers[watchfolder_id] = observer
            
            watchfolder.status = 'monitoring'
            db_session.commit()
            
        except Exception as e:
            print(f"Errore avviando watchfolder {watchfolder_id}: {str(e)}")
            if 'watchfolder' in locals():
                watchfolder.status = 'error'
                db_session.commit()
        finally:
            db_session.close()
    
    def stop_watchfolder(self, watchfolder_id):
        """Ferma monitoraggio watchfolder"""
        # Ferma watcher locale se presente
        if watchfolder_id in self.observers:
            observer = self.observers[watchfolder_id]
            observer.stop()
            observer.join()
            del self.observers[watchfolder_id]
        
        # Ferma watcher FTP se presente
        if watchfolder_id in self.ftp_watchers:
            ftp_watcher = self.ftp_watchers[watchfolder_id]
            ftp_watcher.stop()
            del self.ftp_watchers[watchfolder_id]
        
        db_session = self.db_session_factory()
        try:
            watchfolder = db_session.query(WatchFolder).filter(
                WatchFolder.id == watchfolder_id
            ).first()
            if watchfolder:
                watchfolder.status = 'idle'
                db_session.commit()
        finally:
            db_session.close()
    
    def stop_all(self):
        """Ferma tutti i watchfolder"""
        for watchfolder_id in list(self.observers.keys()):
            self.stop_watchfolder(watchfolder_id)
        for watchfolder_id in list(self.ftp_watchers.keys()):
            self.stop_watchfolder(watchfolder_id)

