#!/usr/bin/env bash
# XDTranscode - Installazione server completo
# Eseguire con: sudo bash scripts/install_new_server.sh

set -euo pipefail

REPO_URL="https://github.com/bioneai/XDTranscode.git"
INSTALL_DIR="/opt/xdtranscode/XDTranscode"
DATA_DIR="/var/lib/xdtranscode"
SERVICE_USER="xdtranscode"
SERVICE_NAME="xdtranscode"

echo "=== XDTranscode - Installazione server ==="

# 1. Installa pacchetti di sistema
echo "[1/10] Installazione pacchetti..."
apt-get update -qq
apt-get install -y git python3-venv python3-pip ffmpeg mediainfo

# 2. Crea directory e clone/update repo
echo "[2/10] Setup repository..."
mkdir -p /opt/xdtranscode
if [[ -d "${INSTALL_DIR}/.git" ]]; then
    echo "  Repository esistente, aggiornamento..."
    cd "${INSTALL_DIR}"
    git fetch origin
    git reset --hard origin/master
else
    echo "  Clone repository..."
    rm -rf "${INSTALL_DIR}"
    git clone "${REPO_URL}" "${INSTALL_DIR}"
fi
cd "${INSTALL_DIR}"

# 3. Crea utente di servizio
echo "[3/10] Creazione utente ${SERVICE_USER}..."
if ! id "${SERVICE_USER}" &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
fi

# 4. Crea directory dati
echo "[4/10] Creazione directory dati..."
mkdir -p "${DATA_DIR}"
chown "${SERVICE_USER}:${SERVICE_USER}" "${DATA_DIR}"

# 5. Crea venv e installa dipendenze
echo "[5/10] Setup Python venv..."
python3 -m venv "${INSTALL_DIR}/.venv"
"${INSTALL_DIR}/.venv/bin/pip" install -q --upgrade pip
"${INSTALL_DIR}/.venv/bin/pip" install -q -r "${INSTALL_DIR}/requirements.txt"

# 6. Genera credenziali e crea .env
echo "[6/10] Creazione .env..."
ADMIN_PASSWORD=$(openssl rand -base64 16)
ADMIN_PASSWORD_HASH=$(echo -n "${ADMIN_PASSWORD}" | sha256sum | cut -d' ' -f1)
SECRET_KEY=$(openssl rand -hex 32)

cat > "${INSTALL_DIR}/.env" << EOF
SECRET_KEY=${SECRET_KEY}
ADMIN_PASSWORD_HASH=${ADMIN_PASSWORD_HASH}
DB_PATH=${DATA_DIR}/xdcam_transcoder.db
FLASK_HOST=0.0.0.0
FLASK_PORT=7000
FLASK_DEBUG=False
EOF

chown "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}/.env"
chmod 600 "${INSTALL_DIR}/.env"

# 7. Inizializza database
echo "[7/10] Inizializzazione database..."
cd "${INSTALL_DIR}"
export DB_PATH="${DATA_DIR}/xdcam_transcoder.db"
"${INSTALL_DIR}/.venv/bin/python" init_db.py
"${INSTALL_DIR}/.venv/bin/python" migrate_db.py
chown "${SERVICE_USER}:${SERVICE_USER}" "${DATA_DIR}/xdcam_transcoder.db" 2>/dev/null || true

# 8. Crea unit systemd
echo "[8/10] Configurazione systemd..."
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

# 9. Permessi directory app
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"

# 10. Abilita e avvia servizio
echo "[9/10] Avvio servizio..."
systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}.service"

echo "[10/10] Verifica..."
sleep 2
systemctl status "${SERVICE_NAME}.service" --no-pager || true

echo ""
echo "=============================================="
echo "  XDTranscode installato con successo!"
echo "=============================================="
echo ""
echo "  URL: http://0.0.0.0:7000/"
echo "  Admin password: ${ADMIN_PASSWORD}"
echo ""
echo "  CONSERVA LA PASSWORD - non verrà mostrata di nuovo."
echo "=============================================="
