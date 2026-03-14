# Sápmi dál Signage — Raspberry Pi (Plug & Play)

Automatisk infoskjerm for Raspberry Pi med:
- webserver (`:8788`)
- oppdatering av nyhetsdata hvert 5. minutt
- Chromium kiosk-autostart ved oppstart

## 1) Klon repo på Raspberry Pi

```bash
git clone https://github.com/DaikoSapmi/sapmi-dal-signage-rpi.git
cd sapmi-dal-signage-rpi
```

## 2) Installer (én kommando)

```bash
chmod +x pi/*.sh start.sh refresh-loop.sh scripts/update_data.py
./pi/install.sh
```

Installer-scriptet:
- installerer `chromium` (eller `chromium-browser`) og `python3`
- oppretter og aktiverer systemd-tjenester:
  - `sapmi-signage-web.service`
  - `sapmi-signage-updater.service`
  - `sapmi-signage-kiosk.service` (starter Chromium i kiosk på `DISPLAY=:0`)
- rydder gammel LXDE-autostart-blokk for å unngå dobbelt browser

## 3) Reboot

```bash
sudo reboot
```

Etter reboot skal skjermen starte automatisk i kiosk-modus på:
`http://127.0.0.1:8788`

---

## Endre kanaler raskt i terminal (nano)

Rediger kanalene her:

```bash
nano web/data/channels.conf
```

Innstilling + format:

```text
@display_count=5
@weather_name=Kárášjohka
@weather_lat=69.4719
@weather_lon=25.5112
Navn|RSS/Atom-URL|maxItems|enabled
```

Eksempel:

```text
@display_count=5
NRK Sápmi|https://www.nrk.no/sapmi/oddasat.rss|6|1
```

- `@display_count`: hvor mange nyheter som vises i rotasjon
- `@weather_name`: visningsnavn for sted i vær-linjen
- `@weather_lat` / `@weather_lon`: koordinater for værdata (MET/yr)
- `maxItems`: hvor mange artikler hentes fra kanalen per oppdatering
- `enabled`: `1` = på, `0` = av

Lagre filen og vent opptil 5 min (eller kjør `./refresh-loop.sh` lokalt) for at endringer skal slå inn.

## Nyttige kommandoer

Status:
```bash
./pi/status.sh
```

Se logger:
```bash
journalctl -u sapmi-signage-web.service -f
journalctl -u sapmi-signage-updater.service -f
```

Avinstallere tjenester:
```bash
./pi/uninstall.sh
```

---

## Lokal test uten systemd

```bash
./refresh-loop.sh   # terminal 1
./start.sh          # terminal 2
```

Åpne: `http://127.0.0.1:8788`
