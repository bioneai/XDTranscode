#!/usr/bin/env python3
"""
Script per inizializzare il database
"""

from sqlalchemy import create_engine
from models import Base
import os
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv('DB_PATH', 'xdcam_transcoder.db')
engine = create_engine(f'sqlite:///{DB_PATH}', echo=True)

if __name__ == '__main__':
    print(f"Creazione database: {DB_PATH}")
    Base.metadata.create_all(engine)
    print("Database creato con successo!")

