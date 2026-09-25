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
from visitor_data_store import VisitorDataStore

ORIGIN = 'https://lucidiscool.github.io'
PORT = 8767
ALLOWED = {'/new', '/think', '/forget', '/facts', '/teach', '/reset', '/remember',
           '/memories', '/good', '/bad', '/correct', '/feedback', '/unrate', '/chats',
           '/load', '/history', '/save', '/temperature', '/tokens', '/settings', '/stats',
           '/auto-memory'}


class PublicWorkspace(Workspace):
    def __init__(self, *args, data_store=None, data_identity=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.data_store = data_store
        self.data_identity = data_identity

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
            if self.data_store:
                try:
                    with admin.lock:
                        self.data_store.save_activity(list(admin.activity))
                    self.data_store.sync(self.data_identity)
                except Exception:
                    self.event('[Storage] Private backup sync failed; the local copy remains on this PC.')
            self.gate.release()


class Sessions:
    def __init__(self, factory=None, data_store=None):
        self.items = {}
        self.visitors = {}
        self.lock = threading.RLock()
        self.gate = threading.Lock()
        self.created = deque()
        self.factory = factory
        self.data_store = data_store

    def create(self, visitor_id=None):
        with self.lock:
            now = time.monotonic()
            unique_items = {id(item): item for item in self.items.values()}
            for item in unique_items.values():
                if not item['workspace'].busy and now - item['seen'] > 3600:
                    for session_key, active in list(self.items.items()):
                        if active is item:
                            del self.items[session_key]
                    self.visitors.pop(item['identity'], None)
                    item['workspace'].app.backend.client.close()
                    cleanup = getattr(item['directory'], 'cleanup', None)
                    if cleanup:
                        cleanup()
            while self.created and now - self.created[0] > 60:
                self.created.popleft()
            if len(self.items) >= 12 or len(self.created) >= 12:
                raise RuntimeError('Lucid is at capacity. Please try again later.')
            visitor_id = visitor_id if isinstance(visitor_id, str) else secrets.token_hex(32)
            if self.data_store:
                directory, identity = self.data_store.directory_for(visitor_id)
                existing = self.visitors.get(identity)
                if existing and now - existing['seen'] <= 3600:
                    existing['seen'] = now
                    token = secrets.token_urlsafe(32)
                    self.items[token] = existing
                    self.created.append(now)
                    return token
            else:
                directory = tempfile.TemporaryDirectory(prefix='lucid-public-')
                identity = secrets.token_hex(32)
            stop = threading.Event()
            backend = self.factory(stop) if self.factory else BrowserBackend(stop)
            workspace_root = Path(directory.name) if hasattr(directory, 'name') else Path(directory)
            app = DeveloperChat(workspace_root, backend, lambda *_: None)
            if not (workspace_root / 'personal' / 'settings.json').exists():
                app.store.set_setting('auto_web', False)
                app.store.set_setting('auto_memory', False)
            try:
                app.identifier, app.history = app.store.load('latest')
            except (ValueError, OSError):
                pass
            app.system += ' This public session has no web access. Do not claim you can browse.'
            workspace = PublicWorkspace(app=app, data_store=self.data_store, data_identity=identity)
            workspace.stop = stop
            workspace.gate = self.gate
            workspace.visitor = identity[:12]
            workspace.messages = [dict(message, pending=False) for message in app.history]
            token = secrets.token_urlsafe(32)
            item = {'workspace': workspace, 'directory': directory, 'identity': identity,
                    'seen': now, 'requests': deque(), 'count': 0}
            self.items[token] = item
            if self.data_store:
                self.visitors[identity] = item
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
                    return self.send(200, admin.action(body.get('token'), body.get('action')))
                if self.path == '/api/session':
                    return self.send(201, {'session': sessions.create(body.get('visitor_id'))})
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
    visitor_data = VisitorDataStore()
    with admin.lock:
        admin.activity = deque(visitor_data.load_activity(), maxlen=2000)
    ThreadingHTTPServer(('127.0.0.1', PORT), make_handler(Sessions(data_store=visitor_data))).serve_forever()
