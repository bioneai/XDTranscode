#!/usr/bin/env bash
# Completa installazione system-wide (richiede: sudo bash scripts/finish_as_root.sh)
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Eseguire come root: sudo bash scripts/finish_as_root.sh"
  exit 1
fi

SOURCE="/home/bione/XDTranscode"
INSTALL_DIR="/opt/xdtranscode/XDTranscode"
DATA_DIR="/var/lib/xdtranscode"
SERVICE_USER="xdtranscode"
SERVICE_NAME="xdtranscode"
WF_BASE="/srv/XDCT_WF"

echo "=== Migrazione XDTranscode a installazione system ==="

apt-get update -qq
apt-get install -y python3-venv python3-pip ffmpeg mediainfo

if ! id "${SERVICE_USER}" &>/dev/null; then
  useradd --system --no-create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
fi

mkdir -p /opt/xdtranscode "${DATA_DIR}" "${WF_BASE}/IN" "${WF_BASE}/OUT" "${WF_BASE}/DONE"

if [[ -d "${INSTALL_DIR}" ]]; then
  rm -rf "${INSTALL_DIR}.bak"
  mv "${INSTALL_DIR}" "${INSTALL_DIR}.bak"
fi

rsync -a --exclude '.venv' --exclude '__pycache__' "${SOURCE}/" "${INSTALL_DIR}/"

python3 -m venv "${INSTALL_DIR}/.venv"
"${INSTALL_DIR}/.venv/bin/pip" install -q --upgrade pip
"${INSTALL_DIR}/.venv/bin/pip" install -q -r "${INSTALL_DIR}/requirements.txt"

ADMIN_HASH=$(grep ADMIN_PASSWORD_HASH "${SOURCE}/.env" | cut -d= -f2)
SECRET_KEY=$(grep SECRET_KEY "${SOURCE}/.env" | cut -d= -f2)
cat > "${INSTALL_DIR}/.env" << EOF
SECRET_KEY=${SECRET_KEY}
ADMIN_PASSWORD_HASH=${ADMIN_HASH}
DB_PATH=${DATA_DIR}/xdcam_transcoder.db
FLASK_HOST=0.0.0.0
FLASK_PORT=7000
FLASK_DEBUG=False
EOF
chmod 600 "${INSTALL_DIR}/.env"

if [[ -f /home/bione/.local/share/xdtranscode/xdcam_transcoder.db ]]; then
  cp /home/bione/.local/share/xdtranscode/xdcam_transcoder.db "${DATA_DIR}/xdcam_transcoder.db"
else
  export DB_PATH="${DATA_DIR}/xdcam_transcoder.db"
  cd "${INSTALL_DIR}"
  "${INSTALL_DIR}/.venv/bin/python" init_db.py
  "${INSTALL_DIR}/.venv/bin/python" migrate_db.py
fi

# Aggiorna path watchfolder a /srv
"${INSTALL_DIR}/.venv/bin/python" - << 'PYEOF'
import os
os.environ["DB_PATH"] = "/var/lib/xdtranscode/xdcam_transcoder.db"
import sys
sys.path.insert(0, "/opt/xdtranscode/XDTranscode")
from dotenv import load_dotenv
load_dotenv("/opt/xdtranscode/XDTranscode/.env")
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import WatchFolder, Worker, TranscodePreset

engine = create_engine("sqlite:////var/lib/xdtranscode/xdcam_transcoder.db")
Session = sessionmaker(bind=engine)
s = Session()
wf = s.query(WatchFolder).filter(WatchFolder.name == "XDCT_WF").first()
if wf:
    wf.path = "/srv/XDCT_WF/IN"
    wf.output_path = "/srv/XDCT_WF/OUT"
    wf.archive_path = "/srv/XDCT_WF/DONE"
    s.commit()
if not s.query(Worker).filter(Worker.name == "worker-1").first():
    s.add(Worker(name="worker-1", active=1, max_concurrent_jobs=1))
    s.commit()
s.close()
PYEOF

chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}" "${DATA_DIR}" "${WF_BASE}"
chmod 2775 "${WF_BASE}" "${WF_BASE}/IN" "${WF_BASE}/OUT" "${WF_BASE}/DONE"

apt-get install -y acl 2>/dev/null || true
if id bione &>/dev/null; then
  usermod -aG "${SERVICE_USER}" bione 2>/dev/null || true
  if command -v setfacl &>/dev/null; then
    setfacl -R -m u:bione:rwx "${WF_BASE}" "${DATA_DIR}/ftp_temp" 2>/dev/null || true
    setfacl -R -d -m u:bione:rwx "${WF_BASE}" "${DATA_DIR}/ftp_temp" 2>/dev/null || true
  fi
fi

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

systemctl stop xdtranscode-user 2>/dev/null || true
systemctl disable xdtranscode-user 2>/dev/null || true
pkill -f "bione/XDTranscode/app.py" 2>/dev/null || true

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}.service"
sleep 2
systemctl status "${SERVICE_NAME}.service" --no-pager
curl -sf http://localhost:7000/api/public/status | head -c 300
echo ""
echo "Installazione system completata su /opt/xdtranscode"
