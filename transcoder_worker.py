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
import shlex
import logging
from fractions import Fraction

logger = logging.getLogger("XDCAMTranscoder.Worker")

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
        extra_params = []
        if preset.ffmpeg_params:
            # Usa shlex per supportare quoting e parametri complessi
            sanitized = self._sanitize_ffmpeg_params_string(preset.ffmpeg_params)
            extra_params = shlex.split(sanitized)
            # Normalizza token con spazi/continuazioni "shell-style" (es. "\ -c:v" -> "-c:v")
            normalized = []
            for tok in extra_params:
                t = tok.strip()
                if not t or t == "\\":
                    continue
                if t != tok:
                    logger.warning("Normalizzo token ffmpeg_params: %r -> %r", tok, t)
                normalized.append(t)
            extra_params = normalized

        # Preset speciali: burn-in timecode sorgente
        if getattr(preset, "name", "") == "H264_LOWRES_TC":
            drawtext = self._build_timecode_drawtext(job.input_path)
            extra_params = self._inject_drawtext_into_params(extra_params, drawtext)

        if extra_params:
            cmd.extend(extra_params)
        
        # Output
        cmd.extend(['-y', job.output_path])
        
        return cmd

    def _sanitize_ffmpeg_params_string(self, s: str) -> str:
        """
        Rende più robusto il parsing di ffmpeg_params inseriti via UI:
        - rimuove continuazioni stile shell (backslash seguito da whitespace/newline)
        - sostituisce newline con spazi
        Nota: NON tocca backslash seguiti da ':' (usati nei filtri tipo drawtext).
        """
        if not s:
            return s
        # Normalizza newline
        s = s.replace("\r\n", "\n")
        # Rimuove "\" come continuation prima di newline
        s = re.sub(r"\\\s*\n", " ", s)
        # Rimuove "\" seguito da spazi/tab (continuation spesso salvata come "\ -c:v")
        s = re.sub(r"\\[ \t]+", " ", s)
        # Converte eventuali newline residue in spazi
        s = s.replace("\n", " ")
        return s.strip()

    def _build_timecode_drawtext(self, input_path: str) -> str:
        """
        Ritorna un filtro drawtext che brucia a video il timecode embedded della sorgente.
        Fallback: 00:00:00:00 se timecode assente/non leggibile.
        """
        timecode, fps = self._get_source_timecode_and_fps(input_path)

        # Font "sicuro" su Ubuntu; fallback a font=monospace se manca
        fontfile = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
        use_fontfile = os.path.exists(fontfile)

        # Escape ":" per drawtext (FFmpeg filtergraph)
        tc_escaped = self._escape_timecode_for_drawtext(timecode)
        rate_str = self._format_fps_for_drawtext(fps)

        base = []
        if use_fontfile:
            base.append(f"fontfile={fontfile}")
        else:
            logger.warning("Font file non trovato (%s). Uso font=monospace.", fontfile)
            base.append("font=monospace")

        # IMPORTANTE (FFmpeg 4.4): il valore deve essere quotato, altrimenti ':' spezza la filter-argstring
        # e drawtext può fallire con errori fuorvianti (es. "Both text and text file provided").
        base.append(f"timecode='{tc_escaped}'")
        # Usa l'alias 'r' (rational) per il frame rate del timecode (più robusto su versioni vecchie).
        base.append(f"r={rate_str}")
        base.append("fontsize=36")
        base.append("fontcolor=white")
        base.append("box=1")
        base.append("boxcolor=0x00000099")
        base.append("x=40")
        base.append("y=40")

        return "drawtext=" + ":".join(base)

    def _escape_timecode_for_drawtext(self, timecode: str) -> str:
        # FFmpeg richiede '\:' per includere ':' nei valori. In argv (no shell) basta '\\:' in stringa python.
        return timecode.replace(":", "\\:")

    def _format_fps_for_drawtext(self, fps: float | None) -> str:
        # drawtext rate accetta un numero; se non noto usa 25.
        if not fps or fps <= 0:
            return "25"
        # Evita rappresentazioni lunghe
        if abs(fps - round(fps)) < 1e-6:
            return str(int(round(fps)))
        return f"{fps:.3f}".rstrip("0").rstrip(".")

    def _inject_drawtext_into_params(self, params: list[str], drawtext_filter: str) -> list[str]:
        """
        Se esiste già -vf/-filter:v, appende ,drawtext=... alla filterchain.
        Altrimenti aggiunge -vf drawtext=...
        """
        if not params:
            return ["-vf", drawtext_filter]

        # Cerca opzione filtro video e relativo argomento
        for key in ("-vf", "-filter:v", "-filter_complex"):
            if key in params:
                idx = params.index(key)
                if idx + 1 >= len(params):
                    # opzione senza argomento: aggiungi
                    return params + [drawtext_filter]
                current = params[idx + 1]
                if "drawtext=" in current:
                    logger.warning("Filtro drawtext già presente; skip iniezione timecode.")
                    return params
                params[idx + 1] = current + "," + drawtext_filter
                return params

        # Nessun filtro video trovato
        return params + ["-vf", drawtext_filter]

    def _get_source_timecode_and_fps(self, input_path: str) -> tuple[str, float | None]:
        """
        Estrae timecode embedded e fps dal file sorgente via ffprobe.
        - timecode: format.tags.timecode, streams[].tags.timecode, stream tmcd tags.timecode
        - fps: avg_frame_rate o r_frame_rate del primo stream video
        """
        data = self._ffprobe_show_format_streams(input_path)
        timecode = self._extract_timecode_from_ffprobe(data)
        fps = self._extract_fps_from_ffprobe(data)

        if not timecode:
            logger.warning("Timecode sorgente non trovato in %s. Fallback 00:00:00:00.", input_path)
            timecode = "00:00:00:00"
        else:
            # Normalizza drop-frame ';' → ':'
            if ";" in timecode:
                logger.warning("Timecode drop-frame rilevato (%s). Normalizzo ';' in ':'.", timecode)
                timecode = timecode.replace(";", ":")

        if not fps:
            logger.warning("FPS sorgente non determinato per %s. Uso rate=25 per drawtext.", input_path)

        return timecode, fps

    def _ffprobe_show_format_streams(self, input_path: str) -> dict:
        if not os.access(input_path, os.R_OK):
            return {}
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_streams", "-show_format", input_path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, errors="replace")
            if result.returncode != 0 or not result.stdout:
                return {}
            return json.loads(result.stdout)
        except Exception as e:
            logger.warning("ffprobe fallito su %s: %s", input_path, e)
            return {}

    def _extract_timecode_from_ffprobe(self, data: dict) -> str | None:
        if not isinstance(data, dict):
            return None

        fmt = data.get("format") or {}
        fmt_tags = (fmt.get("tags") or {}) if isinstance(fmt, dict) else {}
        tc = fmt_tags.get("timecode")
        if tc:
            return str(tc)

        streams = data.get("streams") or []
        if isinstance(streams, list):
            # stream tags
            for s in streams:
                if not isinstance(s, dict):
                    continue
                tags = s.get("tags") or {}
                if isinstance(tags, dict) and tags.get("timecode"):
                    return str(tags.get("timecode"))

            # tmcd stream (tipico MOV)
            for s in streams:
                if not isinstance(s, dict):
                    continue
                if s.get("codec_name") == "tmcd":
                    tags = s.get("tags") or {}
                    if isinstance(tags, dict) and tags.get("timecode"):
                        return str(tags.get("timecode"))

        return None

    def _extract_fps_from_ffprobe(self, data: dict) -> float | None:
        streams = data.get("streams") or []
        if not isinstance(streams, list):
            return None

        for s in streams:
            if not isinstance(s, dict):
                continue
            if s.get("codec_type") != "video":
                continue
            # prefer avg_frame_rate
            for k in ("avg_frame_rate", "r_frame_rate"):
                rate = s.get(k)
                fps = self._parse_ffprobe_rate(rate)
                if fps:
                    return fps
        return None

    def _parse_ffprobe_rate(self, rate) -> float | None:
        """
        rate può essere tipo '25/1', '30000/1001', '0/0' o None.
        """
        if not rate or not isinstance(rate, str):
            return None
        if rate == "0/0":
            return None
        try:
            frac = Fraction(rate)
            if frac <= 0:
                return None
            return float(frac)
        except Exception:
            return None
    
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

