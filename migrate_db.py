#!/usr/bin/env python3
"""
Script di migrazione per aggiungere le nuove colonne FTP al database esistente
"""

import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv('DB_PATH', 'xdcam_transcoder.db')

def migrate_database():
    """Aggiunge le colonne mancanti al database"""
    
    if not os.path.exists(DB_PATH):
        print(f"Database {DB_PATH} non trovato. Verrà creato automaticamente al prossimo avvio.")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Verifica colonne esistenti
        cursor.execute("PRAGMA table_info(watchfolders)")
        columns = [row[1] for row in cursor.fetchall()]
        
        print(f"Colonne esistenti: {columns}")
        
        # Aggiungi colonne mancanti
        migrations = []
        
        if 'watch_type' not in columns:
            migrations.append("ALTER TABLE watchfolders ADD COLUMN watch_type VARCHAR(20) DEFAULT 'local'")
        
        if 'ftp_host' not in columns:
            migrations.append("ALTER TABLE watchfolders ADD COLUMN ftp_host VARCHAR(255)")
        
        if 'ftp_port' not in columns:
            migrations.append("ALTER TABLE watchfolders ADD COLUMN ftp_port INTEGER DEFAULT 21")
        
        if 'ftp_username' not in columns:
            migrations.append("ALTER TABLE watchfolders ADD COLUMN ftp_username VARCHAR(255)")
        
        if 'ftp_password' not in columns:
            migrations.append("ALTER TABLE watchfolders ADD COLUMN ftp_password VARCHAR(255)")
        
        if 'ftp_remote_path' not in columns:
            migrations.append("ALTER TABLE watchfolders ADD COLUMN ftp_remote_path VARCHAR(512)")
        
        if 'ftp_local_temp' not in columns:
            migrations.append("ALTER TABLE watchfolders ADD COLUMN ftp_local_temp VARCHAR(512)")
        
        # Esegui migrazioni
        for migration in migrations:
            print(f"Eseguendo: {migration}")
            cursor.execute(migration)
        
        conn.commit()
        
        if migrations:
            print(f"\n✅ Migrazione completata! Aggiunte {len(migrations)} colonne.")
        else:
            print("\n✅ Database già aggiornato. Nessuna migrazione necessaria.")
        
    except sqlite3.Error as e:
        print(f"❌ Errore durante la migrazione: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    print(f"Migrazione database: {DB_PATH}")
    print("-" * 60)
    migrate_database()

