#!/usr/bin/env python3
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent / 'web'
CONFIG = ROOT / 'data' / 'config.json'

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
