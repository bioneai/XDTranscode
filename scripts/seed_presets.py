#!/usr/bin/env python3
"""
Seed preset broadcast predefiniti (idempotente).
Uso: python scripts/seed_presets.py
"""

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import TranscodePreset

AUDIO_DEFAULTS = {
    "audio_codec": "pcm_s16le",
    "audio_bitrate": "1536k",
    "audio_sample_rate": "48000",
    "audio_channels": "2",
}

BROADCAST_PRESETS = [
    {
        "name": "DNXHD_120",
        "description": "Avid DNxHD 120 Mbps (broadcast)",
        "video_codec": "dnxhd",
        "video_bitrate": "120M",
        "container": "mov",
        "ffmpeg_params": "-pix_fmt yuv422p",
    },
    {
        "name": "DNXHD_145",
        "description": "Avid DNxHD 145 Mbps (broadcast)",
        "video_codec": "dnxhd",
        "video_bitrate": "145M",
        "container": "mov",
        "ffmpeg_params": "-pix_fmt yuv422p",
    },
    {
        "name": "DNXHD_220",
        "description": "Avid DNxHD 220 Mbps (broadcast)",
        "video_codec": "dnxhd",
        "video_bitrate": "220M",
        "container": "mov",
        "ffmpeg_params": "-pix_fmt yuv422p",
    },
    {
        "name": "H264_HQ",
        "description": "H.264 HQ per delivery web/archivio",
        "video_codec": "libx264",
        "video_bitrate": "15000k",
        "container": "mp4",
        "ffmpeg_params": "-preset medium -pix_fmt yuv420p -profile:v high",
    },
    {
        "name": "H264_BROADCAST",
        "description": "H.264 4:2:2 broadcast",
        "video_codec": "libx264",
        "video_bitrate": "50000k",
        "container": "mxf",
        "ffmpeg_params": "-preset slow -pix_fmt yuv422p -profile:v high422",
    },
    {
        "name": "H265_HQ",
        "description": "H.265/HEVC HQ per delivery",
        "video_codec": "libx265",
        "video_bitrate": "12000k",
        "container": "mp4",
        "ffmpeg_params": "-preset medium -pix_fmt yuv420p -tag:v hvc1",
    },
    {
        "name": "H265_BROADCAST",
        "description": "H.265/HEVC 4:2:2 broadcast",
        "video_codec": "libx265",
        "video_bitrate": "25000k",
        "container": "mp4",
        "ffmpeg_params": "-preset slow -pix_fmt yuv422p -tag:v hvc1",
    },
    {
        "name": "H266_HQ",
        "description": "H.266/VVC HQ (richiede libvvenc)",
        "video_codec": "libvvenc",
        "video_bitrate": "8000k",
        "container": "mp4",
        "ffmpeg_params": "-preset faster -pix_fmt yuv420p",
        "requires_encoder": "libvvenc",
    },
    {
        "name": "PRORES_PROXY",
        "description": "Apple ProRes 422 Proxy",
        "video_codec": "prores_ks",
        "video_bitrate": "0",
        "container": "mov",
        "ffmpeg_params": "-profile:v 0 -pix_fmt yuv422p10le",
    },
    {
        "name": "PRORES_LT",
        "description": "Apple ProRes 422 LT",
        "video_codec": "prores_ks",
        "video_bitrate": "0",
        "container": "mov",
        "ffmpeg_params": "-profile:v 1 -pix_fmt yuv422p10le",
    },
    {
        "name": "PRORES_422",
        "description": "Apple ProRes 422",
        "video_codec": "prores_ks",
        "video_bitrate": "0",
        "container": "mov",
        "ffmpeg_params": "-profile:v 2 -pix_fmt yuv422p10le",
    },
    {
        "name": "PRORES_HQ",
        "description": "Apple ProRes 422 HQ",
        "video_codec": "prores_ks",
        "video_bitrate": "0",
        "container": "mov",
        "ffmpeg_params": "-profile:v 3 -pix_fmt yuv422p10le",
    },
    {
        "name": "PRORES_4444",
        "description": "Apple ProRes 4444",
        "video_codec": "prores_ks",
        "video_bitrate": "0",
        "container": "mov",
        "ffmpeg_params": "-profile:v 4 -pix_fmt yuva444p10le",
    },
]


def get_available_encoders():
    """Ritorna set di encoder video disponibili in ffmpeg."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-encoders"],
            capture_output=True,
            text=True,
            timeout=15,
            errors="replace",
        )
        output = (result.stdout or "") + (result.stderr or "")
        encoders = set()
        for line in output.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0].startswith("V"):
                encoders.add(parts[1])
        return encoders
    except Exception:
        return set()


def seed_broadcast_presets(db_session, available_encoders=None, verbose=True):
    """
    Inserisce preset broadcast se non esistono.
    Ritorna dict con conteggi created, skipped, skipped_encoder.
    """
    if available_encoders is None:
        available_encoders = get_available_encoders()

    stats = {"created": [], "skipped": [], "skipped_encoder": []}

    for spec in BROADCAST_PRESETS:
        name = spec["name"]
        required = spec.get("requires_encoder")
        if required and required not in available_encoders:
            stats["skipped_encoder"].append(name)
            if verbose:
                print(f"  SKIP (encoder mancante {required}): {name}")
            continue

        existing = db_session.query(TranscodePreset).filter(TranscodePreset.name == name).first()
        if existing:
            stats["skipped"].append(name)
            if verbose:
                print(f"  SKIP (esistente): {name}")
            continue

        preset = TranscodePreset(
            name=name,
            description=spec["description"],
            video_codec=spec["video_codec"],
            video_bitrate=spec["video_bitrate"],
            container=spec["container"],
            ffmpeg_params=spec["ffmpeg_params"],
            **AUDIO_DEFAULTS,
        )
        db_session.add(preset)
        stats["created"].append(name)
        if verbose:
            print(f"  CREATO: {name}")

    if stats["created"]:
        db_session.commit()

    return stats


def main():
    load_dotenv(PROJECT_ROOT / ".env")
    db_path = os.getenv("DB_PATH", "xdcam_transcoder.db")
    print(f"Seed preset broadcast → {db_path}")
    print("-" * 50)

    encoders = get_available_encoders()
    print(f"Encoder rilevati: {', '.join(sorted(e for e in encoders if e in {'dnxhd','libx264','libx265','libvvenc','prores_ks'})) or 'nessuno rilevante'}")

    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        stats = seed_broadcast_presets(session, encoders, verbose=True)
    finally:
        session.close()

    print("-" * 50)
    print(f"Creati: {len(stats['created'])} | Esistenti: {len(stats['skipped'])} | Encoder mancante: {len(stats['skipped_encoder'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
