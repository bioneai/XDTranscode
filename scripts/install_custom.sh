#!/usr/bin/env bash
# XDTranscode - Installazione personalizzata (richiede root)
set -euo pipefail

REPO_URL="https://github.com/bioneai/XDTranscode.git"
INSTALL_DIR="/opt/xdtranscode/XDTranscode"
DATA_DIR="/var/lib/xdtranscode"
SERVICE_USER="xdtranscode"
SERVICE_NAME="xdtranscode"
ADMIN_PASSWORD="adminsrd"
FLASK_PORT="7000"
WF_IN="/srv/XDCT_WF/IN"
WF_OUT="/srv/XDCT_WF/OUT"
WF_DONE="/srv/XDCT_WF/DONE"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Eseguire come root: sudo bash scripts/install_custom.sh"
  exit 1
fi

echo "=== XDTranscode - Installazione server ==="

echo "[1/12] Installazione pacchetti..."
apt-get update -qq
apt-get install -y git python3-venv python3-pip ffmpeg mediainfo

echo "[2/12] Setup repository..."
mkdir -p /opt/xdtranscode
if [[ -d "${INSTALL_DIR}/.git" ]]; then
  cd "${INSTALL_DIR}"
  git fetch origin
  git reset --hard origin/master
else
  rm -rf "${INSTALL_DIR}"
  git clone "${REPO_URL}" "${INSTALL_DIR}"
fi
cd "${INSTALL_DIR}"

echo "[3/12] Creazione utente ${SERVICE_USER}..."
if ! id "${SERVICE_USER}" &>/dev/null; then
  useradd --system --no-create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
fi

echo "[4/12] Directory dati e watchfolder..."
mkdir -p "${DATA_DIR}" "${WF_IN}" "${WF_OUT}" "${WF_DONE}"
chown "${SERVICE_USER}:${SERVICE_USER}" "${DATA_DIR}"
chown -R "${SERVICE_USER}:${SERVICE_USER}" /srv/XDCT_WF
chmod 2775 /srv/XDCT_WF "${WF_IN}" "${WF_OUT}" "${WF_DONE}"

echo "[5/12] Setup Python venv..."
python3 -m venv "${INSTALL_DIR}/.venv"
"${INSTALL_DIR}/.venv/bin/pip" install -q --upgrade pip
"${INSTALL_DIR}/.venv/bin/pip" install -q -r "${INSTALL_DIR}/requirements.txt"

echo "[6/12] Creazione .env..."
ADMIN_PASSWORD_HASH=$(echo -n "${ADMIN_PASSWORD}" | sha256sum | cut -d' ' -f1)
SECRET_KEY=$(openssl rand -hex 32)
cat > "${INSTALL_DIR}/.env" << EOF
SECRET_KEY=${SECRET_KEY}
ADMIN_PASSWORD_HASH=${ADMIN_PASSWORD_HASH}
DB_PATH=${DATA_DIR}/xdcam_transcoder.db
FLASK_HOST=0.0.0.0
FLASK_PORT=${FLASK_PORT}
FLASK_DEBUG=False
EOF
chown "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}/.env"
chmod 600 "${INSTALL_DIR}/.env"

echo "[7/12] Inizializzazione database..."
export DB_PATH="${DATA_DIR}/xdcam_transcoder.db"
"${INSTALL_DIR}/.venv/bin/python" init_db.py
"${INSTALL_DIR}/.venv/bin/python" migrate_db.py

echo "[8/12] Post-config DB (worker, watchfolder, preset)..."
"${INSTALL_DIR}/.venv/bin/python" - << 'PYEOF'
import os
import sys
sys.path.insert(0, "/opt/xdtranscode/XDTranscode")
os.chdir("/opt/xdtranscode/XDTranscode")
from dotenv import load_dotenv
load_dotenv()
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, WatchFolder, TranscodePreset, Worker

db_path = os.environ["DB_PATH"]
engine = create_engine(f"sqlite:///{db_path}", echo=False)
Session = sessionmaker(bind=engine)
session = Session()

# Preset XDCAM50 default
if not session.query(TranscodePreset).filter(TranscodePreset.name == "XDCAM50").first():
    session.add(TranscodePreset(
        name="XDCAM50",
        description="Preset XDCAM50 standard per broadcast",
        video_codec="mpeg2video",
        video_bitrate="50000k",
        audio_codec="pcm_s16le",
        audio_bitrate="1536k",
        audio_sample_rate="48000",
        audio_channels="2",
        container="mxf",
        ffmpeg_params="-profile:v 0 -level:v 2 -pix_fmt yuv422p",
    ))
    session.commit()

preset = session.query(TranscodePreset).filter(TranscodePreset.name == "XDCAM50").first()

# Clone H264_LOWRES_TC se esiste H264_LOWRES
src = session.query(TranscodePreset).filter(TranscodePreset.name == "H264_LOWRES").first()
if src and not session.query(TranscodePreset).filter(TranscodePreset.name == "H264_LOWRES_TC").first():
    session.add(TranscodePreset(
        name="H264_LOWRES_TC",
        description=src.description or "",
        video_codec=src.video_codec,
        video_bitrate=src.video_bitrate,
        audio_codec=src.audio_codec,
        audio_bitrate=src.audio_bitrate,
        audio_sample_rate=src.audio_sample_rate,
        audio_channels=src.audio_channels,
        container=src.container,
        ffmpeg_params=src.ffmpeg_params,
    ))
    session.commit()
    print("Creato preset H264_LOWRES_TC")

# Worker
if not session.query(Worker).filter(Worker.name == "worker-1").first():
    session.add(Worker(name="worker-1", active=1, max_concurrent_jobs=1, status="idle"))
    session.commit()
    print("Creato worker worker-1")

# Watchfolder
if not session.query(WatchFolder).filter(WatchFolder.name == "XDCT_WF").first():
    session.add(WatchFolder(
        name="XDCT_WF",
        path="/srv/XDCT_WF/IN",
        output_path="/srv/XDCT_WF/OUT",
        archive_path="/srv/XDCT_WF/DONE",
        watch_type="local",
        active=1,
        status="idle",
        preset_id=preset.id if preset else None,
    ))
    session.commit()
    print("Creato watchfolder XDCT_WF")

session.close()
PYEOF

chown "${SERVICE_USER}:${SERVICE_USER}" "${DATA_DIR}/xdcam_transcoder.db" 2>/dev/null || true

echo "[9/12] Configurazione systemd..."
cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=XDCAM Transcoder (XDTranscode)
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${INSTALL_DIR}/.env
Environment=PYTHONUNBUFFERED=1
ExecStart=${INSTALL_DIR}/.venv/bin/python ${INSTALL_DIR}/app.py
Restart=on-failure
RestartSec=2
TimeoutStopSec=20

[Install]
WantedBy=multi-user.target
EOF

echo "[10/12] Permessi app..."
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"

echo "[11/12] Avvio servizio..."
systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}.service"

echo "[12/12] Verifica..."
sleep 3
systemctl status "${SERVICE_NAME}.service" --no-pager || true
curl -sf "http://localhost:${FLASK_PORT}/api/public/status" | head -c 500 || echo "curl fallito"
echo ""

echo "=============================================="
echo "  XDTranscode installato"
echo "  URL: http://0.0.0.0:${FLASK_PORT}/"
echo "  Admin password: ${ADMIN_PASSWORD}"
echo "=============================================="
