from flask import Flask, render_template, jsonify, request, session, redirect, url_for, send_file
from flask_cors import CORS
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from models import Base, WatchFolder, TranscodePreset, Worker, TranscodeJob, FileStatus
from dotenv import load_dotenv
import os
import threading
from datetime import datetime
import hashlib
import logging

# Configura logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('xdcam_transcoder.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('XDCAMTranscoder')

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-this')
CORS(app)

# Database setup
DB_PATH = os.getenv('DB_PATH', 'xdcam_transcoder.db')
engine = create_engine(f'sqlite:///{DB_PATH}', echo=False)
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)

# Session factory function
def get_db_session():
    return SessionLocal()

# Import workers after DB setup
from watchfolder_manager import WatchFolderManager
from transcoder_worker import TranscoderWorker

# Global managers
watchfolder_manager = WatchFolderManager(get_db_session)
transcoder_worker = TranscoderWorker(get_db_session)

# Admin password (in production use proper auth)
ADMIN_PASSWORD_HASH = os.getenv('ADMIN_PASSWORD_HASH', 
    hashlib.sha256('admin'.encode()).hexdigest())

@app.route('/')
def public_dashboard():
    """Pagina pubblica con status watchfolder e transcodifica"""
    return render_template('public_dashboard.html')

@app.route('/admin')
def admin_login():
    """Pagina login admin"""
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))
    return render_template('admin_login.html')

@app.route('/admin/login', methods=['POST'])
def admin_authenticate():
    """Autenticazione admin"""
    data = request.json
    password = data.get('password', '')
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    
    if password_hash == ADMIN_PASSWORD_HASH:
        session['admin_logged_in'] = True
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Password errata'}), 401

@app.route('/admin/logout', methods=['POST'])
def admin_logout():
    """Logout admin"""
    session.pop('admin_logged_in', None)
    return jsonify({'success': True})

@app.route('/admin/dashboard')
def admin_dashboard():
    """Dashboard amministrazione"""
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    return render_template('admin_dashboard.html')

# API Pubbliche
@app.route('/api/public/status')
def public_status():
    """Status generale per pagina pubblica"""
    db_session = get_db_session()
    try:
        watchfolders = db_session.query(WatchFolder).filter(WatchFolder.active == True).all()
        jobs = db_session.query(TranscodeJob).order_by(TranscodeJob.created_at.desc()).limit(50).all()
        workers = db_session.query(Worker).filter(Worker.active == True).all()
        
        result = {
            'watchfolders': [{
                'id': wf.id,
                'name': wf.name,
                'path': wf.path,
                'status': wf.status,
                'active': wf.active,
                'total_files': len([j for j in jobs if j.watchfolder_id == wf.id]),
                'pending': len([j for j in jobs if j.watchfolder_id == wf.id and j.status == FileStatus.PENDING]),
                'processing': len([j for j in jobs if j.watchfolder_id == wf.id and j.status == FileStatus.PROCESSING]),
                'completed': len([j for j in jobs if j.watchfolder_id == wf.id and j.status == FileStatus.COMPLETED]),
                'failed': len([j for j in jobs if j.watchfolder_id == wf.id and j.status == FileStatus.FAILED])
            } for wf in watchfolders],
            'recent_jobs': [{
                'id': job.id,
                'filename': job.input_filename,
                'watchfolder': job.watchfolder.name if job.watchfolder else 'N/A',
                'status': job.status.value,
                'progress': job.progress,
                'created_at': job.created_at.isoformat(),
                'started_at': job.started_at.isoformat() if job.started_at else None,
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                'error_message': job.error_message,
                'input_size': job.input_size,
                'output_size': job.output_size,
                'input_duration': job.input_duration,
                'output_duration': job.output_duration
            } for job in jobs],
            'workers': [{
                'id': w.id,
                'name': w.name,
                'active': w.active,
                'current_job_id': w.current_job_id,
                'status': w.status
            } for w in workers]
        }
        return jsonify(result)
    finally:
        db_session.close()

@app.route('/api/public/jobs/<int:job_id>')
def public_job_details(job_id):
    """Dettagli job per pagina pubblica"""
    db_session = get_db_session()
    try:
        job = db_session.query(TranscodeJob).filter(TranscodeJob.id == job_id).first()
        if not job:
            return jsonify({'error': 'Job non trovato'}), 404
        
        return jsonify({
            'id': job.id,
            'filename': job.input_filename,
            'watchfolder': job.watchfolder.name if job.watchfolder else 'N/A',
            'status': job.status.value,
            'progress': job.progress,
            'created_at': job.created_at.isoformat(),
            'started_at': job.started_at.isoformat() if job.started_at else None,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            'error_message': job.error_message,
            'input_path': job.input_path,
            'output_path': job.output_path,
            'input_size': job.input_size,
            'output_size': job.output_size,
            'input_duration': job.input_duration,
            'output_duration': job.output_duration,
            'preset': job.preset.name if job.preset else 'N/A'
        })
    finally:
        db_session.close()

# API Admin
@app.route('/api/admin/watchfolders', methods=['GET'])
def admin_get_watchfolders():
    """Lista watchfolder"""
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Non autorizzato'}), 401
    
    db_session = get_db_session()
    try:
        watchfolders = db_session.query(WatchFolder).all()
        return jsonify([{
            'id': wf.id,
            'name': wf.name,
            'path': wf.path,
            'output_path': wf.output_path,
            'archive_path': wf.archive_path,
            'watch_type': wf.watch_type or 'local',
            'ftp_host': wf.ftp_host,
            'ftp_port': wf.ftp_port,
            'ftp_username': wf.ftp_username,
            'ftp_password': wf.ftp_password if wf.ftp_password else None,  # Non mostrare password
            'ftp_remote_path': wf.ftp_remote_path,
            'ftp_local_temp': wf.ftp_local_temp,
            'active': wf.active,
            'status': wf.status,
            'preset_id': wf.preset_id,
            'created_at': wf.created_at.isoformat()
        } for wf in watchfolders])
    finally:
        db_session.close()

@app.route('/api/admin/watchfolders', methods=['POST'])
def admin_create_watchfolder():
    """Crea watchfolder"""
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Non autorizzato'}), 401
    
    data = request.json
    db_session = get_db_session()
    try:
        watchfolder = WatchFolder(
            name=data['name'],
            path=data.get('path', ''),
            output_path=data.get('output_path', ''),
            archive_path=data.get('archive_path', ''),
            watch_type=data.get('watch_type', 'local'),
            ftp_host=data.get('ftp_host'),
            ftp_port=data.get('ftp_port', 21),
            ftp_username=data.get('ftp_username'),
            ftp_password=data.get('ftp_password'),
            ftp_remote_path=data.get('ftp_remote_path', '/'),
            ftp_local_temp=data.get('ftp_local_temp', '/tmp/xdcam_ftp'),
            active=data.get('active', True),
            preset_id=data.get('preset_id'),
            status='idle'
        )
        db_session.add(watchfolder)
        db_session.commit()
        
        # Avvia monitoraggio se attivo
        if watchfolder.active:
            watchfolder_manager.start_watchfolder(watchfolder.id)
        
        return jsonify({'id': watchfolder.id, 'success': True})
    except Exception as e:
        db_session.rollback()
        return jsonify({'error': str(e)}), 400
    finally:
        db_session.close()

@app.route('/api/admin/watchfolders/<int:watchfolder_id>', methods=['PUT'])
def admin_update_watchfolder(watchfolder_id):
    """Aggiorna watchfolder"""
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Non autorizzato'}), 401
    
    data = request.json
    db_session = get_db_session()
    try:
        watchfolder = db_session.query(WatchFolder).filter(WatchFolder.id == watchfolder_id).first()
        if not watchfolder:
            return jsonify({'error': 'Watchfolder non trovato'}), 404
        
        watchfolder.name = data.get('name', watchfolder.name)
        watchfolder.path = data.get('path', watchfolder.path)
        watchfolder.output_path = data.get('output_path', watchfolder.output_path)
        watchfolder.archive_path = data.get('archive_path', watchfolder.archive_path)
        watchfolder.watch_type = data.get('watch_type', watchfolder.watch_type or 'local')
        watchfolder.ftp_host = data.get('ftp_host', watchfolder.ftp_host)
        watchfolder.ftp_port = data.get('ftp_port', watchfolder.ftp_port or 21)
        watchfolder.ftp_username = data.get('ftp_username', watchfolder.ftp_username)
        if 'ftp_password' in data and data['ftp_password']:  # Aggiorna solo se fornita
            watchfolder.ftp_password = data['ftp_password']
        watchfolder.ftp_remote_path = data.get('ftp_remote_path', watchfolder.ftp_remote_path)
        watchfolder.ftp_local_temp = data.get('ftp_local_temp', watchfolder.ftp_local_temp)
        watchfolder.preset_id = data.get('preset_id', watchfolder.preset_id)
        
        old_active = watchfolder.active
        watchfolder.active = data.get('active', watchfolder.active)
        
        db_session.commit()
        
        # Gestisci start/stop monitoraggio
        if watchfolder.active and not old_active:
            watchfolder_manager.start_watchfolder(watchfolder.id)
        elif not watchfolder.active and old_active:
            watchfolder_manager.stop_watchfolder(watchfolder.id)
        
        return jsonify({'success': True})
    except Exception as e:
        db_session.rollback()
        return jsonify({'error': str(e)}), 400
    finally:
        db_session.close()

@app.route('/api/admin/watchfolders/<int:watchfolder_id>', methods=['DELETE'])
def admin_delete_watchfolder(watchfolder_id):
    """Elimina watchfolder"""
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Non autorizzato'}), 401
    
    db_session = get_db_session()
    try:
        watchfolder = db_session.query(WatchFolder).filter(WatchFolder.id == watchfolder_id).first()
        if not watchfolder:
            return jsonify({'error': 'Watchfolder non trovato'}), 404
        
        watchfolder_manager.stop_watchfolder(watchfolder_id)
        db_session.delete(watchfolder)
        db_session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db_session.rollback()
        return jsonify({'error': str(e)}), 400
    finally:
        db_session.close()

@app.route('/api/admin/presets', methods=['GET'])
def admin_get_presets():
    """Lista preset"""
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Non autorizzato'}), 401
    
    db_session = get_db_session()
    try:
        presets = db_session.query(TranscodePreset).all()
        return jsonify([{
            'id': p.id,
            'name': p.name,
            'description': p.description,
            'video_codec': p.video_codec,
            'video_bitrate': p.video_bitrate,
            'audio_codec': p.audio_codec,
            'audio_bitrate': p.audio_bitrate,
            'audio_sample_rate': p.audio_sample_rate,
            'audio_channels': p.audio_channels,
            'container': p.container,
            'ffmpeg_params': p.ffmpeg_params
        } for p in presets])
    finally:
        db_session.close()

@app.route('/api/admin/presets', methods=['POST'])
def admin_create_preset():
    """Crea preset"""
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Non autorizzato'}), 401
    
    data = request.json
    db_session = get_db_session()
    try:
        preset = TranscodePreset(
            name=data['name'],
            description=data.get('description', ''),
            video_codec=data.get('video_codec', 'mpeg2video'),
            video_bitrate=data.get('video_bitrate', '50000k'),
            audio_codec=data.get('audio_codec', 'pcm_s16le'),
            audio_bitrate=data.get('audio_bitrate', '1536k'),
            audio_sample_rate=data.get('audio_sample_rate', '48000'),
            audio_channels=data.get('audio_channels', '2'),
            container=data.get('container', 'mxf'),
            ffmpeg_params=data.get('ffmpeg_params', '')
        )
        db_session.add(preset)
        db_session.commit()
        return jsonify({'id': preset.id, 'success': True})
    except Exception as e:
        db_session.rollback()
        return jsonify({'error': str(e)}), 400
    finally:
        db_session.close()

@app.route('/api/admin/presets/<int:preset_id>', methods=['PUT'])
def admin_update_preset(preset_id):
    """Aggiorna preset"""
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Non autorizzato'}), 401
    
    data = request.json
    db_session = get_db_session()
    try:
        preset = db_session.query(TranscodePreset).filter(TranscodePreset.id == preset_id).first()
        if not preset:
            return jsonify({'error': 'Preset non trovato'}), 404
        
        for key in ['name', 'description', 'video_codec', 'video_bitrate', 
                   'audio_codec', 'audio_bitrate', 'audio_sample_rate', 
                   'audio_channels', 'container', 'ffmpeg_params']:
            if key in data:
                setattr(preset, key, data[key])
        
        db_session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db_session.rollback()
        return jsonify({'error': str(e)}), 400
    finally:
        db_session.close()

@app.route('/api/admin/presets/<int:preset_id>', methods=['DELETE'])
def admin_delete_preset(preset_id):
    """Elimina preset"""
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Non autorizzato'}), 401
    
    db_session = get_db_session()
    try:
        preset = db_session.query(TranscodePreset).filter(TranscodePreset.id == preset_id).first()
        if not preset:
            return jsonify({'error': 'Preset non trovato'}), 404
        
        db_session.delete(preset)
        db_session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db_session.rollback()
        return jsonify({'error': str(e)}), 400
    finally:
        db_session.close()

@app.route('/api/admin/workers', methods=['GET'])
def admin_get_workers():
    """Lista worker"""
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Non autorizzato'}), 401
    
    db_session = get_db_session()
    try:
        workers = db_session.query(Worker).all()
        return jsonify([{
            'id': w.id,
            'name': w.name,
            'active': w.active,
            'status': w.status,
            'current_job_id': w.current_job_id,
            'max_concurrent_jobs': w.max_concurrent_jobs
        } for w in workers])
    finally:
        db_session.close()

@app.route('/api/admin/workers', methods=['POST'])
def admin_create_worker():
    """Crea worker"""
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Non autorizzato'}), 401
    
    data = request.json
    db_session = get_db_session()
    try:
        worker = Worker(
            name=data['name'],
            active=data.get('active', True),
            max_concurrent_jobs=data.get('max_concurrent_jobs', 1)
        )
        db_session.add(worker)
        db_session.commit()
        
        if worker.active:
            transcoder_worker.start_worker(worker.id)
        
        return jsonify({'id': worker.id, 'success': True})
    except Exception as e:
        db_session.rollback()
        return jsonify({'error': str(e)}), 400
    finally:
        db_session.close()

@app.route('/api/admin/workers/<int:worker_id>', methods=['PUT'])
def admin_update_worker(worker_id):
    """Aggiorna worker"""
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Non autorizzato'}), 401
    
    data = request.json
    db_session = get_db_session()
    try:
        worker = db_session.query(Worker).filter(Worker.id == worker_id).first()
        if not worker:
            return jsonify({'error': 'Worker non trovato'}), 404
        
        old_active = worker.active
        worker.name = data.get('name', worker.name)
        worker.active = data.get('active', worker.active)
        worker.max_concurrent_jobs = data.get('max_concurrent_jobs', worker.max_concurrent_jobs)
        
        db_session.commit()
        
        if worker.active and not old_active:
            transcoder_worker.start_worker(worker.id)
        elif not worker.active and old_active:
            transcoder_worker.stop_worker(worker.id)
        
        return jsonify({'success': True})
    except Exception as e:
        db_session.rollback()
        return jsonify({'error': str(e)}), 400
    finally:
        db_session.close()

@app.route('/api/admin/jobs', methods=['GET'])
def admin_get_jobs():
    """Lista job"""
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Non autorizzato'}), 401
    
    db_session = get_db_session()
    try:
        jobs = db_session.query(TranscodeJob).order_by(TranscodeJob.created_at.desc()).limit(100).all()
        return jsonify([{
            'id': job.id,
            'input_filename': job.input_filename,
            'watchfolder_id': job.watchfolder_id,
            'preset_id': job.preset_id,
            'status': job.status.value,
            'progress': job.progress,
            'created_at': job.created_at.isoformat(),
            'started_at': job.started_at.isoformat() if job.started_at else None,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            'error_message': job.error_message
        } for job in jobs])
    finally:
        db_session.close()

@app.route('/api/admin/logs')
def admin_get_logs():
    """Restituisce ultime righe del log"""
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Non autorizzato'}), 401
    
    log_file = 'xdcam_transcoder.log'
    lines = request.args.get('lines', 100, type=int)
    
    try:
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                all_lines = f.readlines()
                # Prendi ultime N righe
                recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
                return jsonify({
                    'logs': recent_lines,
                    'total_lines': len(all_lines)
                })
        else:
            return jsonify({'logs': [], 'total_lines': 0, 'message': 'File log non trovato'})
    except Exception as e:
        logger.error(f"Errore lettura log: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/logs/download')
def admin_download_logs():
    """Scarica il file di log completo"""
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Non autorizzato'}), 401
    
    log_file = 'xdcam_transcoder.log'
    if os.path.exists(log_file):
        return send_file(log_file, as_attachment=True, download_name='xdcam_transcoder.log')
    else:
        return jsonify({'error': 'File log non trovato'}), 404

def init_default_preset():
    """Inizializza preset XDCAM50 di default"""
    db_session = get_db_session()
    try:
        existing = db_session.query(TranscodePreset).filter(TranscodePreset.name == 'XDCAM50').first()
        if not existing:
            preset = TranscodePreset(
                name='XDCAM50',
                description='Preset XDCAM50 standard per broadcast',
                video_codec='mpeg2video',
                video_bitrate='50000k',
                audio_codec='pcm_s16le',
                audio_bitrate='1536k',
                audio_sample_rate='48000',
                audio_channels='2',
                container='mxf',
                ffmpeg_params='-profile:v 0 -level:v 2 -pix_fmt yuv422p'
            )
            db_session.add(preset)
            db_session.commit()
    finally:
        db_session.close()

if __name__ == '__main__':
    # Esegui migrazione database se necessario
    try:
        from migrate_db import migrate_database
        migrate_database()
    except Exception as e:
        print(f"Nota: Migrazione database non eseguita: {e}")
    
    init_default_preset()
    
    # Avvia watchfolder attivi all'avvio
    db_session = get_db_session()
    try:
        active_watchfolders = db_session.query(WatchFolder).filter(WatchFolder.active == True).all()
        for wf in active_watchfolders:
            watchfolder_manager.start_watchfolder(wf.id)
        
        active_workers = db_session.query(Worker).filter(Worker.active == True).all()
        for w in active_workers:
            transcoder_worker.start_worker(w.id)
    finally:
        db_session.close()
    
    app.run(
        host=os.getenv('FLASK_HOST', '0.0.0.0'),
        port=int(os.getenv('FLASK_PORT', 5000)),
        debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true',
        threaded=True
    )

