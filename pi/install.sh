#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/sapmi-dal-signage-rpi}"
USER_NAME="${SUDO_USER:-$USER}"

if [[ ! -d "$APP_DIR" ]]; then
  echo "Fant ikke APP_DIR: $APP_DIR"
  echo "Tips: APP_DIR=/path/to/repo ./pi/install.sh"
  exit 1
fi

cd "$APP_DIR"
chmod +x start.sh refresh-loop.sh scripts/update_data.py

sudo apt-get update
sudo apt-get install -y --no-install-recommends chromium-browser python3

mkdir -p "$APP_DIR/.runtime"

sudo tee /etc/systemd/system/sapmi-signage-web.service >/dev/null <<EOF
[Unit]
Description=Sápmi dál Signage web server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/env bash $APP_DIR/start.sh
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/sapmi-signage-updater.service >/dev/null <<EOF
[Unit]
Description=Sápmi dál Signage data updater
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/env bash $APP_DIR/refresh-loop.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now sapmi-signage-web.service
sudo systemctl enable --now sapmi-signage-updater.service

mkdir -p "/home/$USER_NAME/.config/lxsession/LXDE-pi"
AUTOSTART_FILE="/home/$USER_NAME/.config/lxsession/LXDE-pi/autostart"
touch "$AUTOSTART_FILE"

if ! grep -q "sapmi-signage-kiosk" "$AUTOSTART_FILE" 2>/dev/null; then
  cat >> "$AUTOSTART_FILE" <<'EOF'

# sapmi-signage-kiosk
@xset s off
@xset -dpms
@xset s noblank
@chromium-browser --kiosk --incognito --noerrdialogs --disable-infobars --disable-session-crashed-bubble http://127.0.0.1:8788
EOF
fi

echo "✅ Ferdig. Reboot anbefales: sudo reboot"
echo "Status:"
echo "  systemctl status sapmi-signage-web.service"
echo "  systemctl status sapmi-signage-updater.service"
