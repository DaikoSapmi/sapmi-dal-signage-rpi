#!/usr/bin/env bash
set -euo pipefail

sudo systemctl disable --now sapmi-signage-web.service sapmi-signage-updater.service || true
sudo rm -f /etc/systemd/system/sapmi-signage-web.service
sudo rm -f /etc/systemd/system/sapmi-signage-updater.service
sudo systemctl daemon-reload

echo "✅ Services fjernet."
echo "Merk: Chromium autostart-linjen ligger i ~/.config/lxsession/LXDE-pi/autostart og kan fjernes manuelt ved behov."
