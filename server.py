#!/usr/bin/env python3
import json
import ssl
import urllib.request
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent / 'web'
CONFIG = ROOT / 'data' / 'config.json'

KARASJOK_LAT = 69.4719
KARASJOK_LON = 25.5112
MET_URL = f"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={KARASJOK_LAT}&lon={KARASJOK_LON}"
MET_USER_AGENT = "SapmiDalSignage/1.0 (+https://github.com/DaikoSapmi/sapmi-dal-signage-rpi; contact: rune@fjellheim.tv)"

def fetch_weather():
    req = urllib.request.Request(MET_URL, headers={'User-Agent': MET_USER_AGENT, 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=15, context=ssl.create_default_context()) as resp:
        raw = resp.read().decode('utf-8', errors='replace')
    data = json.loads(raw)

    ts = data.get('properties', {}).get('timeseries', [])
    if not ts:
        raise RuntimeError('No timeseries from MET API')

    first = ts[0]
    details = first.get('data', {}).get('instant', {}).get('details', {})
    temp = details.get('air_temperature')

    summary = first.get('data', {}).get('next_1_hours', {}).get('summary', {})
    if not summary:
        summary = first.get('data', {}).get('next_6_hours', {}).get('summary', {})
    symbol = summary.get('symbol_code', '')

    return {
        'location': 'Kárášjohka',
        'temperature_c': temp,
        'symbol_code': symbol,
        'updated_at': datetime.now(timezone.utc).isoformat(),
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith('/api/config'):
            if CONFIG.exists():
                try:
                    return self._json(json.loads(CONFIG.read_text(encoding='utf-8')))
                except Exception:
                    return self._json({'sources': []})
            return self._json({'sources': []})

        if self.path.startswith('/api/weather'):
            try:
                return self._json(fetch_weather())
            except Exception as e:
                return self._json({'error': str(e)}, 502)

        return super().do_GET()

    def do_POST(self):
        if self.path.startswith('/api/config'):
            length = int(self.headers.get('Content-Length', '0'))
            raw = self.rfile.read(length) if length else b'{}'
            try:
                data = json.loads(raw.decode('utf-8'))
            except Exception:
                return self._json({'ok': False, 'error': 'invalid json'}, 400)
            CONFIG.parent.mkdir(parents=True, exist_ok=True)
            CONFIG.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            return self._json({'ok': True})
        return self._json({'ok': False, 'error': 'not found'}, 404)

if __name__ == '__main__':
    httpd = ThreadingHTTPServer(('0.0.0.0', 8788), Handler)
    print('Serving on :8788')
    httpd.serve_forever()
