# XDCAM Transcoder

Applicazione web professionale per la gestione di watchfolder multipli e transcodifica video in formato XDCAM50.

## Caratteristiche

- **Gestione Multi-Watchfolder**: Monitora più cartelle simultaneamente
- **Transcodifica XDCAM50**: Conversione automatica in formato broadcast standard
- **Backend Amministrazione**: Interfaccia completa per gestione watchfolder, preset e worker
- **Dashboard Pubblica**: Monitoraggio in tempo reale dello status e avanzamento transcodifica
- **Design Broadcast Moderno**: Interfaccia professionale, responsive e curata
- **Worker System**: Elaborazione asincrona con gestione worker multipli
- **Preset Personalizzabili**: Configurazione flessibile dei parametri di transcodifica

## Requisiti

- Python 3.8+
- FFmpeg installato e disponibile nel PATH
- FFprobe (incluso con FFmpeg)

## Installazione

1. Clona o scarica il progetto
2. Installa le dipendenze:
```bash
pip install -r requirements.txt
```

3. Configura le variabili d'ambiente (opzionale, crea un file `.env`):
```
SECRET_KEY=your-secret-key-here
ADMIN_PASSWORD_HASH=sha256-hash-of-your-password
DB_PATH=xdcam_transcoder.db
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
FLASK_DEBUG=False
```

Per generare l'hash della password admin:
```python
import hashlib
hashlib.sha256('your-password'.encode()).hexdigest()
```

## Avvio

```bash
python app.py
```

L'applicazione sarà disponibile su:
- Dashboard pubblica: http://localhost:5000/
- Admin panel: http://localhost:5000/admin

## Utilizzo

### Dashboard Pubblica
La dashboard pubblica mostra:
- Status di tutti i watchfolder attivi
- Lista dei job di transcodifica recenti con progresso
- Status dei worker attivi
- Dettagli completi di ogni job

### Admin Panel
L'admin panel permette di:

1. **Gestire Watchfolder**:
   - Creare nuovi watchfolder
   - Configurare path di input e output
   - Associare preset di transcodifica
   - Attivare/disattivare monitoraggio

2. **Gestire Preset**:
   - Creare preset personalizzati
   - Configurare codec video/audio
   - Impostare bitrate e parametri FFmpeg
   - Preset XDCAM50 preconfigurato incluso

3. **Gestire Worker**:
   - Creare worker per elaborazione
   - Configurare job concorrenti
   - Monitorare status worker

4. **Monitorare Jobs**:
   - Visualizzare tutti i job
   - Verificare progresso e errori
   - Analizzare performance

## Formati Supportati

Input: MP4, MOV, AVI, MXF, MKV, MTS, M2TS
Output: MXF (XDCAM50)

## Preset XDCAM50 Default

- Video Codec: MPEG-2
- Video Bitrate: 50 Mbps
- Audio Codec: PCM 16-bit
- Audio Sample Rate: 48 kHz
- Audio Channels: 2 (stereo)
- Container: MXF

## Struttura Progetto

```
xdcam_transcoder/
├── app.py                 # Applicazione Flask principale
├── models.py              # Modelli database SQLAlchemy
├── watchfolder_manager.py # Gestione watchfolder
├── transcoder_worker.py   # Worker transcodifica
├── requirements.txt       # Dipendenze Python
├── templates/            # Template HTML
│   ├── public_dashboard.html
│   ├── admin_dashboard.html
│   └── admin_login.html
└── static/               # File statici
    ├── css/
    │   ├── style.css
    │   └── admin.css
    └── js/
        ├── public_dashboard.js
        └── admin_dashboard.js
```

## Note

- Assicurati che FFmpeg sia installato e accessibile dal sistema
- I watchfolder devono avere permessi di lettura appropriati
- Le directory di output devono avere permessi di scrittura
- La password admin di default è "admin" (cambiala in produzione)
- Il database SQLite viene creato automaticamente al primo avvio

## Risoluzione Problemi

### Errore "Permission denied"

Se ricevi errori di permessi durante la transcodifica:

1. **Verifica permessi file input:**
   ```bash
   python check_permissions.py /path/to/input/file.mp4
   ```

2. **Verifica permessi directory output:**
   ```bash
   python check_permissions.py /path/to/output/directory
   ```

3. **Correggi permessi se necessario:**
   ```bash
   # Per file/directory di proprietà dell'utente corrente
   chmod 644 /path/to/file.mp4
   chmod 755 /path/to/output/directory
   
   # Se il file appartiene a un altro utente
   sudo chown $USER:$USER /path/to/file.mp4
   ```

4. **Verifica che l'utente che esegue l'app abbia accesso:**
   ```bash
   ls -la /path/to/file.mp4
   ls -la /path/to/output/directory
   ```

### Altri Errori Comuni

- **File non trovato**: Verifica che il percorso del watchfolder sia corretto
- **Directory output non scrivibile**: Crea la directory e imposta i permessi appropriati
- **FFmpeg non trovato**: Assicurati che FFmpeg sia nel PATH o specifica il percorso completo

## Licenza

Progetto sviluppato per uso broadcast professionale.

