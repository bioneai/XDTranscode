#!/usr/bin/env python3
"""
Script di utilità per verificare i permessi di file e directory
"""

import os
import sys

def check_file_permissions(file_path):
    """Verifica permessi di un file"""
    print(f"\nVerifica file: {file_path}")
    print("-" * 60)
    
    if not os.path.exists(file_path):
        print("❌ File non trovato")
        return False
    
    print(f"✅ File esistente")
    
    # Verifica permessi
    readable = os.access(file_path, os.R_OK)
    writable = os.access(file_path, os.W_OK)
    executable = os.access(file_path, os.X_OK)
    
    print(f"Lettura: {'✅' if readable else '❌'}")
    print(f"Scrittura: {'✅' if writable else '❌'}")
    print(f"Esecuzione: {'✅' if executable else '❌'}")
    
    # Stat info
    stat_info = os.stat(file_path)
    print(f"\nProprietario: UID {stat_info.st_uid}, GID {stat_info.st_gid}")
    print(f"Permessi: {oct(stat_info.st_mode)[-3:]}")
    
    return readable

def check_directory_permissions(dir_path):
    """Verifica permessi di una directory"""
    print(f"\nVerifica directory: {dir_path}")
    print("-" * 60)
    
    if not os.path.exists(dir_path):
        print("❌ Directory non trovata")
        print(f"Tentativo creazione...")
        try:
            os.makedirs(dir_path, exist_ok=True)
            print("✅ Directory creata")
        except Exception as e:
            print(f"❌ Errore creazione: {str(e)}")
            return False
    else:
        print(f"✅ Directory esistente")
    
    # Verifica permessi
    readable = os.access(dir_path, os.R_OK)
    writable = os.access(dir_path, os.W_OK)
    executable = os.access(dir_path, os.X_OK)
    
    print(f"Lettura: {'✅' if readable else '❌'}")
    print(f"Scrittura: {'✅' if writable else '❌'}")
    print(f"Esecuzione: {'✅' if executable else '❌'}")
    
    # Stat info
    stat_info = os.stat(dir_path)
    print(f"\nProprietario: UID {stat_info.st_uid}, GID {stat_info.st_gid}")
    print(f"Permessi: {oct(stat_info.st_mode)[-3:]}")
    
    return writable

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Uso: python check_permissions.py <file_or_directory>")
        print("\nEsempi:")
        print("  python check_permissions.py /path/to/file.mp4")
        print("  python check_permissions.py /path/to/directory")
        sys.exit(1)
    
    path = sys.argv[1]
    
    if os.path.isfile(path):
        result = check_file_permissions(path)
    elif os.path.isdir(path):
        result = check_directory_permissions(path)
    else:
        print(f"❌ Path non valido: {path}")
        sys.exit(1)
    
    if result:
        print("\n✅ Permessi OK")
    else:
        print("\n❌ Permessi insufficienti")
        print("\nSuggerimenti:")
        print("  - Verifica che il file/directory appartenga all'utente corretto")
        print("  - Controlla i permessi con: ls -la")
        print("  - Se necessario, modifica i permessi con: chmod o chown")
        sys.exit(1)

