#!/usr/bin/env bash
set -euo pipefail

sudo systemctl disable --now sapmi-signage-web.service sapmi-signage-updater.service sapmi-signage-kiosk.service || true
sudo rm -f /etc/systemd/system/sapmi-signage-web.service
sudo rm -f /etc/systemd/system/sapmi-signage-updater.service
sudo rm -f /etc/systemd/system/sapmi-signage-kiosk.service
sudo systemctl daemon-reload

echo "✅ Services fjernet."
echo "Merk: Eventuelle gamle autostart-linjer i ~/.config/lxsession/LXDE-pi/autostart kan fjernes manuelt ved behov."
