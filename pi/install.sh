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

# Debian/Raspberry Pi OS kan bruke ulikt pakkenavn for Chromium
CHROMIUM_PKG=""
for pkg in chromium chromium-browser; do
  if apt-cache show "$pkg" >/dev/null 2>&1; then
    CHROMIUM_PKG="$pkg"
    break
  fi
done

if [[ -z "$CHROMIUM_PKG" ]]; then
  echo "Fant ingen Chromium-pakke (prøvde: chromium, chromium-browser)."
  echo "Installer manuelt og kjør install.sh på nytt."
  exit 1
fi

sudo apt-get install -y --no-install-recommends "$CHROMIUM_PKG" python3

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

CHROMIUM_BIN=""
if command -v chromium >/dev/null 2>&1; then
  CHROMIUM_BIN="/usr/bin/chromium"
elif command -v chromium-browser >/dev/null 2>&1; then
  CHROMIUM_BIN="/usr/bin/chromium-browser"
else
  echo "Fant ikke chromium-binær i PATH etter installasjon."
  exit 1
fi

# Kiosk som systemd-tjeneste (fungerer uten tastatur/mus og uten LXDE-autostart)
sudo tee /etc/systemd/system/sapmi-signage-kiosk.service >/dev/null <<EOF
[Unit]
Description=Sápmi dál Signage kiosk browser
After=graphical.target sapmi-signage-web.service
Wants=graphical.target

[Service]
Type=simple
User=$USER_NAME
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/$USER_NAME/.Xauthority
ExecStartPre=/bin/sleep 10
ExecStart=$CHROMIUM_BIN --kiosk --incognito --noerrdialogs --disable-infobars --disable-session-crashed-bubble http://127.0.0.1:8788
Restart=always
RestartSec=5

[Install]
WantedBy=graphical.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now sapmi-signage-web.service
sudo systemctl enable --now sapmi-signage-updater.service
sudo systemctl enable --now sapmi-signage-kiosk.service

# Rydd legacy LXDE-autostart, så vi unngår dobbelt Chromium-instans
mkdir -p "/home/$USER_NAME/.config/lxsession/LXDE-pi"
AUTOSTART_FILE="/home/$USER_NAME/.config/lxsession/LXDE-pi/autostart"
touch "$AUTOSTART_FILE"
sed -i.bak '/# sapmi-signage-kiosk/,+4d' "$AUTOSTART_FILE" || true
sed -i.bak '/# sapmi-signage-kiosk-begin/,/# sapmi-signage-kiosk-end/d' "$AUTOSTART_FILE" || true

echo "✅ Ferdig. Reboot anbefales: sudo reboot"
echo "Status:"
echo "  systemctl status sapmi-signage-web.service"
echo "  systemctl status sapmi-signage-updater.service"
echo "  systemctl status sapmi-signage-kiosk.service"
