#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="xdtranscode"
SRC_SERVICE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/xdtranscode.service"
DST_SERVICE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "Installazione unit systemd: ${DST_SERVICE}"
sudo cp -f "${SRC_SERVICE}" "${DST_SERVICE}"
sudo systemctl daemon-reload
sudo systemctl enable --now "${SERVICE_NAME}.service"
sudo systemctl status --no-pager "${SERVICE_NAME}.service"
