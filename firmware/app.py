"""BRICQ foundation: no GPIO imports, servo initialization, or motion endpoints."""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer


class StatusHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/health':
            self.send_error(404)
            return
        body = json.dumps({
            'name': 'BRICQ', 'version': os.environ.get('BRICQ_VERSION', 'unknown'),
            'healthy': True, 'armed': False, 'mode': 'status-only',
        }).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    print('BRICQ status service ready; hardware control is disabled.', flush=True)
    HTTPServer(('127.0.0.1', 8765), StatusHandler).serve_forever()
