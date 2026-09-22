"""Bounded public gateway for Lucid V5; never serves the owner's workspace."""
import json
import secrets
import tempfile
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dev_chat import DeveloperChat
from admin_service import admin
from website_server import Workspace, BrowserBackend

ORIGIN = 'https://lucidiscool.github.io'
PORT = 8767
ALLOWED = {'/new', '/think', '/forget', '/facts', '/teach', '/reset', '/remember',
           '/memories', '/good', '/bad', '/correct', '/feedback', '/unrate', '/chats',
           '/load', '/history', '/save', '/temperature', '/tokens', '/settings', '/stats',
           '/auto-memory'}


class PublicWorkspace(Workspace):
    def event(self, text):
        # Do not log visitors' memory or conversation contents.
        with self.lock:
            self.events.append({'text': text, 'time': time.strftime('%H:%M:%S')})
            self.events = self.events[-30:]

    def run(self, text):
        try:
            super().run(text)
            with self.lock:
                if self.error and self.error != 'Stopped by you.':
                    self.error = 'Lucid could not finish this reply. Try a shorter message or a new conversation.'
        finally:
            admin.record(self.visitor, text, self.snapshot()['messages'], self.error)
            self.gate.release()


class Sessions:
    def __init__(self, factory=None):
        self.items = {}
        self.lock = threading.RLock()
        self.gate = threading.Lock()
        self.created = deque()
        self.factory = factory

    def create(self):
        with self.lock:
            now = time.monotonic()
            for key, item in list(self.items.items()):
                if not item['workspace'].busy and now - item['seen'] > 3600:
                    item['workspace'].app.backend.client.close()
                    item['directory'].cleanup()
                    del self.items[key]
            while self.created and now - self.created[0] > 60:
                self.created.popleft()
            if len(self.items) >= 12 or len(self.created) >= 12:
                raise RuntimeError('Lucid is at capacity. Please try again later.')
            directory = tempfile.TemporaryDirectory(prefix='lucid-public-')
            stop = threading.Event()
            backend = self.factory(stop) if self.factory else BrowserBackend(stop)
            app = DeveloperChat(Path(directory.name), backend, lambda *_: None)
            app.store.set_setting('auto_web', False)
            app.store.set_setting('auto_memory', False)
            app.system += ' This public session has no web access. Do not claim you can browse.'
            workspace = PublicWorkspace(app=app)
            workspace.stop = stop
            workspace.gate = self.gate
            workspace.visitor = secrets.token_hex(8)
            token = secrets.token_urlsafe(32)
            self.items[token] = {'workspace': workspace, 'directory': directory,
                                 'seen': now, 'requests': deque(), 'count': 0}
            self.created.append(now)
            return token

    def get(self, token):
        with self.lock:
            item = self.items.get(token)
            if not item or time.monotonic() - item['seen'] > 3600:
                return None
            item['seen'] = time.monotonic()
            return item

    def submit(self, item, message):
        if not isinstance(message, str) or not 1 <= len(message.strip()) <= 4000:
            raise ValueError('Enter a message of 1–4000 characters.')
        message = message.strip()
        command = message.split()[0]
        if command.startswith('/') and command not in ALLOWED:
            raise ValueError('That command is available only in the local app.')
        if command == '/tokens':
            try:
                value = int(message.split(maxsplit=1)[1])
                if not 32 <= value <= 1024:
                    raise ValueError()
            except (ValueError, IndexError):
                raise ValueError('The public reply limit is 32–1024 tokens.')
        with self.lock:
            now = time.monotonic()
            times = item['requests']
            while times and now - times[0] > 60:
                times.popleft()
            if len(times) >= 10 or item['count'] >= 100:
                raise RuntimeError('Session request limit reached. Please try again later.')
            if not self.gate.acquire(blocking=False):
                raise RuntimeError('Lucid is answering another message. Please try again shortly.')
            try:
                worker = item['workspace'].submit(message)
                times.append(now)
                item['count'] += 1
                return worker
            except Exception:
                self.gate.release()
                raise


def make_handler(sessions):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *_):
            pass

        def allowed(self):
            return (self.headers.get('Host') == f'127.0.0.1:{PORT}'
                    and self.headers.get('Origin') == ORIGIN)

        def send(self, status, body):
            raw = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            if self.headers.get('Origin') == ORIGIN:
                self.send_header('Access-Control-Allow-Origin', ORIGIN)
                self.send_header('Vary', 'Origin')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Lucid-Session, X-Lucid-Token')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_OPTIONS(self):
            self.send(200 if self.allowed() else 403, {})

        def do_GET(self):
            if not self.allowed():
                return self.send(403, {'error': 'Invalid origin or host.'})
            if self.path == '/api/health':
                return self.send(200, {'app': 'lucid-v5-public'})
            item = sessions.get(self.headers.get('X-Lucid-Session', ''))
            if not item:
                return self.send(401, {'error': 'Session expired. Reload the page to reconnect.'})
            if self.path == '/api/state':
                return self.send(200, item['workspace'].snapshot())
            self.send(404, {'error': 'Not found.'})

        def do_POST(self):
            if not self.allowed():
                return self.send(403, {'error': 'Invalid origin or host.'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 20000:
                    return self.send(413, {'error': 'Request too large.'})
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError('Expected a JSON object.')
                if self.path == '/api/admin/login':
                    return self.send(200, admin.login(body.get('password')))
                if self.path == '/api/admin/action':
                    return self.send(200, admin.action(body.get('token'), body.get('action'), body.get('url', '')))
                if self.path == '/api/session':
                    return self.send(201, {'session': sessions.create()})
                item = sessions.get(self.headers.get('X-Lucid-Session', ''))
                if not item:
                    return self.send(401, {'error': 'Session expired. Reload the page to reconnect.'})
                workspace = item['workspace']
                if not secrets.compare_digest(self.headers.get('X-Lucid-Token', ''), workspace.token):
                    return self.send(403, {'error': 'Invalid request token.'})
                if self.path == '/api/message':
                    sessions.submit(item, body.get('message'))
                elif self.path == '/api/stop':
                    workspace.stop.set()
                else:
                    return self.send(404, {'error': 'Not found.'})
                self.send(202, {'ok': True})
            except PermissionError as error:
                self.send(401, {'error': str(error)})
            except (ValueError, TypeError) as error:
                if self.path.startswith('/api/admin/'):
                    return self.send(400, {'error': str(error)})
                self.send(400, {'error': 'Invalid message or command. Messages: up to 4000 characters; reply tokens: 32–1024. Web research and model configuration are local-only.'})
            except RuntimeError as error:
                self.send(429, {'error': str(error)})
            except Exception:
                self.send(503, {'error': 'Lucid is temporarily unavailable.'})
    return Handler


if __name__ == '__main__':
    print('Lucid V5 public gateway on 127.0.0.1:8767', flush=True)
    ThreadingHTTPServer(('127.0.0.1', PORT), make_handler(Sessions())).serve_forever()
