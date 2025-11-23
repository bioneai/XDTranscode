import os
import subprocess
import threading
import time
import shutil
from sqlalchemy.orm import Session
from models import TranscodeJob, Worker, FileStatus
from datetime import datetime
import json
import re

class TranscoderWorker:
    def __init__(self, db_session_factory):
        self.db_session_factory = db_session_factory
        self.worker_threads = {}  # worker_id -> thread
        self.running = {}  # worker_id -> bool
        
    def start_worker(self, worker_id):
        """Avvia worker thread"""
        if worker_id in self.worker_threads:
            return  # Già attivo
        
        self.running[worker_id] = True
        thread = threading.Thread(target=self._worker_loop, args=(worker_id,), daemon=True)
        thread.start()
        self.worker_threads[worker_id] = thread
        
        db_session = self.db_session_factory()
        try:
            worker = db_session.query(Worker).filter(Worker.id == worker_id).first()
            if worker:
                worker.status = 'running'
                db_session.commit()
        finally:
            db_session.close()
    
    def stop_worker(self, worker_id):
        """Ferma worker thread"""
        if worker_id not in self.running:
            return
        
        self.running[worker_id] = False
        
        db_session = self.db_session_factory()
        try:
            worker = db_session.query(Worker).filter(Worker.id == worker_id).first()
            if worker:
                worker.status = 'idle'
                db_session.commit()
        finally:
            db_session.close()
    
    def _worker_loop(self, worker_id):
        """Loop principale worker"""
        while self.running.get(worker_id, False):
            try:
                db_session = self.db_session_factory()
                try:
                    # Cerca job pending
                    job = db_session.query(TranscodeJob).filter(
                        TranscodeJob.status == FileStatus.PENDING,
                        TranscodeJob.worker_id.is_(None)
                    ).first()
                    
                    if job:
                        # Assegna job al worker
                        job.worker_id = worker_id
                        job.status = FileStatus.PROCESSING
                        job.started_at = datetime.utcnow()
                        db_session.commit()
                        
                        # Processa job
                        self._process_job(job.id)
                    
                finally:
                    db_session.close()
                
                time.sleep(2)  # Poll ogni 2 secondi
                
            except Exception as e:
                print(f"Errore worker {worker_id}: {str(e)}")
                time.sleep(5)
    
    def _process_job(self, job_id):
        """Processa job di transcodifica"""
        db_session = self.db_session_factory()
        try:
            job = db_session.query(TranscodeJob).filter(TranscodeJob.id == job_id).first()
            if not job:
                return
            
            # Verifica esistenza file
            if not os.path.exists(job.input_path):
                job.status = FileStatus.FAILED
                job.error_message = f"File input non trovato: {job.input_path}"
                job.completed_at = datetime.utcnow()
                db_session.commit()
                return
            
            # Verifica permessi lettura file input
            if not os.access(job.input_path, os.R_OK):
                job.status = FileStatus.FAILED
                job.error_message = f"Permessi insufficienti per leggere il file: {job.input_path}"
                job.completed_at = datetime.utcnow()
                db_session.commit()
                return
            
            # Verifica/crea directory output
            output_dir = os.path.dirname(job.output_path)
            if output_dir and not os.path.exists(output_dir):
                try:
                    os.makedirs(output_dir, exist_ok=True)
                except Exception as e:
                    job.status = FileStatus.FAILED
                    job.error_message = f"Impossibile creare directory output: {str(e)}"
                    job.completed_at = datetime.utcnow()
                    db_session.commit()
                    return
            
            # Verifica permessi scrittura directory output
            if output_dir and not os.access(output_dir, os.W_OK):
                job.status = FileStatus.FAILED
                job.error_message = f"Permessi insufficienti per scrivere nella directory: {output_dir}"
                job.completed_at = datetime.utcnow()
                db_session.commit()
                return
            
            # Costruisci comando FFmpeg
            ffmpeg_cmd = self._build_ffmpeg_command(job)
            
            # Esegui transcodifica
            try:
                process = subprocess.Popen(
                    ffmpeg_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    errors='replace'  # Gestisce errori di encoding
                )
            except Exception as e:
                job.status = FileStatus.FAILED
                job.error_message = f"Errore avvio FFmpeg: {str(e)}"
                job.completed_at = datetime.utcnow()
                db_session.commit()
                return
            
            # Monitora progresso
            self._monitor_progress(process, job_id)
            
            # Attendi completamento
            stdout, stderr = process.communicate()
            
            db_session = self.db_session_factory()
            job = db_session.query(TranscodeJob).filter(TranscodeJob.id == job_id).first()
            
            if process.returncode == 0 and os.path.exists(job.output_path):
                job.status = FileStatus.COMPLETED
                job.progress = 100
                job.output_size = os.path.getsize(job.output_path) if os.path.exists(job.output_path) else None
                
                # Sposta file originale in archivio se configurato
                if job.watchfolder and job.watchfolder.archive_path:
                    self._archive_original_file(job)
            else:
                job.status = FileStatus.FAILED
                # Estrai messaggio errore più significativo
                error_msg = self._extract_error_message(stderr, process.returncode)
                job.error_message = error_msg
            
            job.completed_at = datetime.utcnow()
            db_session.commit()
            
        except Exception as e:
            db_session.rollback()
            job = db_session.query(TranscodeJob).filter(TranscodeJob.id == job_id).first()
            if job:
                job.status = FileStatus.FAILED
                job.error_message = str(e)
                job.completed_at = datetime.utcnow()
                db_session.commit()
        finally:
            db_session.close()
    
    def _build_ffmpeg_command(self, job):
        """Costruisce comando FFmpeg per transcodifica"""
        preset = job.preset
        
        cmd = ['ffmpeg', '-i', job.input_path]
        
        # Video codec e bitrate
        cmd.extend(['-c:v', preset.video_codec])
        cmd.extend(['-b:v', preset.video_bitrate])
        
        # Audio codec, bitrate, sample rate, channels
        cmd.extend(['-c:a', preset.audio_codec])
        if preset.audio_bitrate:
            cmd.extend(['-b:a', preset.audio_bitrate])
        cmd.extend(['-ar', preset.audio_sample_rate])
        cmd.extend(['-ac', preset.audio_channels])
        
        # Parametri aggiuntivi
        if preset.ffmpeg_params:
            params = preset.ffmpeg_params.split()
            cmd.extend(params)
        
        # Output
        cmd.extend(['-y', job.output_path])
        
        return cmd
    
    def _monitor_progress(self, process, job_id):
        """Monitora progresso transcodifica"""
        db_session = self.db_session_factory()
        try:
            job = db_session.query(TranscodeJob).filter(TranscodeJob.id == job_id).first()
            if not job:
                return
            
            # Estrai durata input se disponibile
            if not job.input_duration:
                duration = self._get_video_duration(job.input_path)
                if duration:
                    job.input_duration = duration
                    db_session.commit()
            
            # Pattern per estrarre tempo da FFmpeg stderr
            time_pattern = re.compile(r'time=(\d+):(\d+):(\d+\.\d+)')
            
            while process.poll() is None:
                # Leggi stderr (FFmpeg usa stderr per output)
                line = process.stderr.readline()
                if not line:
                    time.sleep(0.5)
                    continue
                
                # Estrai tempo corrente
                match = time_pattern.search(line)
                if match and job.input_duration:
                    hours = int(match.group(1))
                    minutes = int(match.group(2))
                    seconds = float(match.group(3))
                    current_time = hours * 3600 + minutes * 60 + seconds
                    
                    progress = int((current_time / job.input_duration) * 100)
                    progress = min(100, max(0, progress))
                    
                    job.progress = progress
                    db_session.commit()
                
                time.sleep(0.1)
                
        except Exception as e:
            print(f"Errore monitoraggio progresso: {str(e)}")
        finally:
            db_session.close()
    
    def _get_video_duration(self, video_path):
        """Ottiene durata video usando FFprobe"""
        try:
            # Verifica permessi prima di eseguire ffprobe
            if not os.access(video_path, os.R_OK):
                return None
                
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, errors='replace')
            if result.returncode == 0:
                data = json.loads(result.stdout)
                duration = float(data['format'].get('duration', 0))
                return duration
        except Exception as e:
            print(f"Errore ottenimento durata video {video_path}: {str(e)}")
        return None
    
    def _archive_original_file(self, job):
        """Sposta il file originale nella cartella di archivio dopo transcodifica completata"""
        try:
            archive_path = job.watchfolder.archive_path
            if not archive_path:
                return
            
            # Crea directory archivio se non esiste
            if not os.path.exists(archive_path):
                os.makedirs(archive_path, exist_ok=True)
            
            # Verifica permessi scrittura directory archivio
            if not os.access(archive_path, os.W_OK):
                print(f"Permessi insufficienti per archiviare in {archive_path}")
                return
            
            # Verifica che il file originale esista ancora
            if not os.path.exists(job.input_path):
                print(f"File originale non trovato per archiviazione: {job.input_path}")
                return
            
            # Costruisci percorso destinazione
            original_filename = os.path.basename(job.input_path)
            destination_path = os.path.join(archive_path, original_filename)
            
            # Se file già esiste, aggiungi timestamp
            if os.path.exists(destination_path):
                base_name, ext = os.path.splitext(original_filename)
                timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
                destination_path = os.path.join(archive_path, f"{base_name}_{timestamp}{ext}")
            
            # Sposta file
            shutil.move(job.input_path, destination_path)
            print(f"File originale archiviato: {job.input_path} -> {destination_path}")
            
        except Exception as e:
            print(f"Errore archiviazione file originale {job.input_path}: {str(e)}")
            # Non fallisce il job se l'archiviazione fallisce
    
    def _extract_error_message(self, stderr, returncode):
        """Estrae messaggio errore significativo da output FFmpeg"""
        if not stderr:
            return f"Errore FFmpeg (codice: {returncode})"
        
        # Cerca errori comuni
        stderr_lower = stderr.lower()
        
        if 'permission denied' in stderr_lower:
            return "Errore permessi: impossibile accedere al file. Verifica i permessi del file e della directory."
        
        if 'no such file or directory' in stderr_lower:
            return "File o directory non trovato. Verifica che il percorso sia corretto."
        
        if 'invalid data found' in stderr_lower:
            return "File video corrotto o formato non supportato."
        
        if 'cannot open' in stderr_lower:
            return "Impossibile aprire il file. Verifica permessi e che il file non sia in uso."
        
        # Prendi ultime righe significative
        lines = stderr.strip().split('\n')
        error_lines = [line for line in lines if 'error' in line.lower() or 'failed' in line.lower()]
        
        if error_lines:
            return error_lines[-1][:500]
        
        # Altrimenti ultime 500 caratteri
        return stderr[-500:].strip() if len(stderr) > 500 else stderr.strip()

