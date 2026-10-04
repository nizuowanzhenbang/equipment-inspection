"""Disposable local HTTP procurement peer; never contact a configured live system."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Event, Thread
from types import SimpleNamespace

from app.config import settings


@contextmanager
def procurement_server(monkeypatch, *, status=200, hold=False, malformed=False):
    peer = SimpleNamespace(status=status, malformed=malformed, entered=Event(), release=Event(), requests=[])
    if not hold:
        peer.release.set()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            peer.requests.append({'path': self.path, 'payload': payload,
                                  'token': self.headers.get('X-Integration-Token')})
            peer.entered.set()
            if not peer.release.wait(timeout=10):
                self.send_error(504)
                return
            body = b'not json' if peer.malformed else json.dumps({'code': 200, 'data': {'order_no': 'LOCAL-PO-1'}}).encode()
            self.send_response(peer.status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
    monkeypatch.setattr(settings, 'PROCUREMENT_SYSTEM_URL', f'http://127.0.0.1:{server.server_port}')
    monkeypatch.setattr(settings, 'PROCUREMENT_INTEGRATION_TOKEN', 'isolated-local-procurement-token')
    thread.start()
    try:
        yield peer
    finally:
        peer.release.set()
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
