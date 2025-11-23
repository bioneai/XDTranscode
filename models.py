from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum, Float, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

Base = declarative_base()

class FileStatus(enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class WatchFolder(Base):
    __tablename__ = 'watchfolders'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    path = Column(String(512), nullable=False)
    output_path = Column(String(512))
    archive_path = Column(String(512))  # Cartella per archiviare file originali dopo transcodifica
    watch_type = Column(String(20), default='local')  # 'local' o 'ftp'
    ftp_host = Column(String(255))  # Host FTP
    ftp_port = Column(Integer, default=21)  # Porta FTP
    ftp_username = Column(String(255))  # Username FTP
    ftp_password = Column(String(255))  # Password FTP (in produzione usare encryption)
    ftp_remote_path = Column(String(512))  # Path remoto sul server FTP
    ftp_local_temp = Column(String(512))  # Directory locale temporanea per download
    active = Column(Integer, default=1)  # 1 = active, 0 = inactive
    status = Column(String(50), default='idle')  # idle, monitoring, error
    preset_id = Column(Integer, ForeignKey('presets.id'))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    preset = relationship("TranscodePreset", back_populates="watchfolders")
    jobs = relationship("TranscodeJob", back_populates="watchfolder")

class TranscodePreset(Base):
    __tablename__ = 'presets'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    video_codec = Column(String(50), default='mpeg2video')
    video_bitrate = Column(String(50), default='50000k')
    audio_codec = Column(String(50), default='pcm_s16le')
    audio_bitrate = Column(String(50), default='1536k')
    audio_sample_rate = Column(String(50), default='48000')
    audio_channels = Column(String(10), default='2')
    container = Column(String(20), default='mxf')
    ffmpeg_params = Column(Text)  # Parametri aggiuntivi FFmpeg
    created_at = Column(DateTime, default=datetime.utcnow)
    
    watchfolders = relationship("WatchFolder", back_populates="preset")
    jobs = relationship("TranscodeJob", back_populates="preset")

class Worker(Base):
    __tablename__ = 'workers'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    active = Column(Integer, default=1)
    status = Column(String(50), default='idle')  # idle, running, error
    current_job_id = Column(Integer, ForeignKey('jobs.id'), nullable=True)
    max_concurrent_jobs = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    current_job = relationship("TranscodeJob", foreign_keys=[current_job_id])

class TranscodeJob(Base):
    __tablename__ = 'jobs'
    
    id = Column(Integer, primary_key=True)
    watchfolder_id = Column(Integer, ForeignKey('watchfolders.id'))
    preset_id = Column(Integer, ForeignKey('presets.id'))
    worker_id = Column(Integer, ForeignKey('workers.id'), nullable=True)
    
    input_filename = Column(String(512), nullable=False)
    input_path = Column(String(512), nullable=False)
    output_path = Column(String(512))
    
    status = Column(Enum(FileStatus), default=FileStatus.PENDING)
    progress = Column(Integer, default=0)  # 0-100
    
    input_size = Column(Integer)  # bytes
    output_size = Column(Integer)  # bytes
    input_duration = Column(Float)  # seconds
    output_duration = Column(Float)  # seconds
    
    error_message = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    
    watchfolder = relationship("WatchFolder", back_populates="jobs")
    preset = relationship("TranscodePreset", back_populates="jobs")
    worker = relationship("Worker", foreign_keys=[worker_id])

