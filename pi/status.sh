#!/usr/bin/env bash
set -euo pipefail
sudo systemctl --no-pager --full status sapmi-signage-web.service || true
echo
sudo systemctl --no-pager --full status sapmi-signage-updater.service || true
