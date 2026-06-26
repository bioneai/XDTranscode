#!/usr/bin/env bash
# Deploy modifiche da /home/bione/XDTranscode a installazione system /opt
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Eseguire: sudo bash scripts/deploy_to_opt.sh"
  exit 1
fi

SOURCE="/home/bione/XDTranscode"
TARGET="/opt/xdtranscode/XDTranscode"

rsync -a --exclude '.venv' --exclude '__pycache__' --exclude '.env' --exclude '*.db' --exclude 'xdcam_transcoder.log' \
  "${SOURCE}/" "${TARGET}/"

chown -R xdtranscode:xdtranscode "${TARGET}"

cd "${TARGET}"
sudo -u xdtranscode bash -c "source .env 2>/dev/null || true; export DB_PATH=/var/lib/xdtranscode/xdcam_transcoder.db; .venv/bin/python migrate_db.py && .venv/bin/python scripts/seed_presets.py"

chmod 2775 /srv/XDCT_WF/OUT /srv/XDCT_WF/IN /srv/XDCT_WF/DONE /var/lib/xdtranscode/ftp_temp 2>/dev/null || true
find /srv/XDCT_WF -type d -exec chmod 2775 {} + 2>/dev/null || true
find /srv/XDCT_WF /var/lib/xdtranscode/ftp_temp -type f -user xdtranscode -exec chmod 664 {} + 2>/dev/null || true
if id bione &>/dev/null; then
  if command -v setfacl &>/dev/null; then
    setfacl -R -m u:bione:rwx /srv/XDCT_WF /var/lib/xdtranscode/ftp_temp 2>/dev/null || true
    setfacl -R -d -m u:bione:rwx /srv/XDCT_WF /var/lib/xdtranscode/ftp_temp 2>/dev/null || true
  fi
fi

systemctl restart xdtranscode.service
sleep 2
systemctl status xdtranscode.service --no-pager
curl -sf http://localhost:7000/api/public/status | head -c 400
echo ""
