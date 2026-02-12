#!/usr/bin/env python3
"""
Clona un preset esistente in un nuovo preset, copiando tutti i campi.

Uso:
  source .venv/bin/activate
  python scripts/clone_preset.py --src H264_LOWRES --dst H264_LOWRES_TC

Legge DB_PATH da .env (default: xdcam_transcoder.db).
"""

import argparse
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Permette l'esecuzione da /scripts mantenendo import dal project root
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from models import TranscodePreset  # noqa: E402


def clone_preset(src_name: str, dst_name: str) -> int:
    load_dotenv()
    db_path = os.getenv("DB_PATH", "xdcam_transcoder.db")
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    SessionLocal = sessionmaker(bind=engine)

    session = SessionLocal()
    try:
        src = session.query(TranscodePreset).filter(TranscodePreset.name == src_name).first()
        if not src:
            raise SystemExit(f"Preset sorgente non trovato: {src_name}")

        existing = session.query(TranscodePreset).filter(TranscodePreset.name == dst_name).first()
        if existing:
            print(f"Preset già presente: {dst_name} (id={existing.id})")
            return 0

        dst = TranscodePreset(
            name=dst_name,
            description=(src.description or ""),
            video_codec=src.video_codec,
            video_bitrate=src.video_bitrate,
            audio_codec=src.audio_codec,
            audio_bitrate=src.audio_bitrate,
            audio_sample_rate=src.audio_sample_rate,
            audio_channels=src.audio_channels,
            container=src.container,
            ffmpeg_params=src.ffmpeg_params,
        )
        session.add(dst)
        session.commit()
        print(f"Creato preset: {dst.name} (id={dst.id}) da {src.name} (id={src.id})")
        return 0
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", required=True, help="Nome preset sorgente (es. H264_LOWRES)")
    parser.add_argument("--dst", required=True, help="Nome nuovo preset (es. H264_LOWRES_TC)")
    args = parser.parse_args()
    return clone_preset(args.src, args.dst)


if __name__ == "__main__":
    raise SystemExit(main())

