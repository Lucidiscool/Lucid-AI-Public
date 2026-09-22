"""Local-only browser interface for LucidAI V5. No hosted services."""
import argparse
import json
import secrets
import threading
import time
import webbrowser
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dev_chat import DeveloperChat
from local_chat import Backend, ROOT


class Stopped(RuntimeError):
    pass


class BrowserBackend(Backend):
    def __init__(self, stop):
        super().__init__()
        self.stop = stop

    def answer(self, *args, **kwargs):
        original = kwargs.pop('on_token', None)
        def token(part):
            if self.stop.is_set():
                raise Stopped('Stopped by you.')
            if original:
                original(part)
        if self.stop.is_set():
            raise Stopped('Stopped by you.')
        return super().answer(*args, on_token=token, **kwargs)


class Workspace:
    def __init__(self, root=ROOT, app=None):
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.token = secrets.token_urlsafe(32)
        self.messages = []
        self.events = []
        self.busy = False
        self.error = ''
        self.notice = ''
        self.partial = None
        self.job = 0
        self.app = app or DeveloperChat(root, BrowserBackend(self.stop), self.output)
        self.app.output = self.output
        self.app.stream = self.stream

    def event(self, text):
        with self.lock:
            self.events.append({'text': text, 'time': time.strftime('%H:%M:%S')})
            self.events = self.events[-60:]
        print(text, flush=True)

    def output(self, text):
        with self.lock:
            if text.startswith(('LucidAI V5: ', 'Experiment: ')):
                content = text.split(': ', 1)[1]
                if self.partial is not None:
                    self.messages[self.partial].update(content=content, pending=False)
                else:
                    self.messages.append({'role': 'assistant', 'content': content, 'pending': False})
                self.partial = None
            elif text.startswith(('[Web]', '[Memory]', '[Process summary]', '[Auto]')):
                self.event(text)
            else:
                self.notice = text

    def stream(self, part):
        with self.lock:
            if self.partial is None:
                self.partial = len(self.messages)
                self.messages.append({'role': 'assistant', 'content': '', 'pending': True})
            self.messages[self.partial]['content'] += part

    def snapshot(self):
        with self.lock:
            return {'token': self.token, 'messages': [dict(m) for m in self.messages], 'events': list(self.events),
                'busy': self.busy, 'error': self.error, 'notice': self.notice, 'job': self.job,
                'experiment': self.app.blank is not None, 'think': self.app.think,
                'temperature': self.app.temperature, 'max_tokens': self.app.tokens,
                'settings': self.app.store.settings(), 'memories': self.app.store.memories(),
                'chats': [{'id': i, 'title': title} for i, title in self.app.store.chats()][:40],
                'chat_id': self.app.identifier, 'seconds': round(self.app.last_seconds, 1),
                'turns': self.app.turns}

    def submit(self, text):
        if not isinstance(text, str) or not text.strip() or len(text) > 16000:
            raise ValueError('Enter a message of 1–16000 characters.')
        with self.lock:
            if self.busy:
                raise RuntimeError('A reply is already in progress.')
            if text.strip() == '/quit':
                raise ValueError('Close the browser tab to leave. Stop the terminal to shut down the website.')
            self.busy = True
            self.stop.clear()
            self.job += 1
            self.error = self.notice = ''
            self.events = []
            self.partial = None
            if not text.startswith('/') or text.startswith(('/search ', '/research ', '/teach ')):
                self.messages.append({'role': 'user', 'content': text, 'pending': False})
        thread = threading.Thread(target=self.run, args=(text,), daemon=True)
        thread.start()
        return thread

    def run(self, text):
        try:
            self.event('Preparing your reply…' if not text.startswith('/') else 'Applying command…')
            was_blank = self.app.blank is not None
            self.app.handle(text)
            with self.lock:
                if text == '/new' or text == '/reset' or text.startswith('/load ') or was_blank != (self.app.blank is not None):
                    self.messages = [] if self.app.blank else [dict(m, pending=False) for m in self.app.history]
        except Exception as error:
            with self.lock:
                self.error = str(error)
                if self.partial is not None:
                    self.messages[self.partial].update(pending=False, interrupted=True)
                self.event('Stopped.' if isinstance(error, Stopped) else 'The request could not finish.')
        finally:
            with self.lock:
                self.partial = None
                self.busy = False


def make_handler(workspace, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def valid_host(self):
            return self.headers.get('Host') in (f'127.0.0.1:{port}', f'localhost:{port}')

        def send(self, status, body, mime='application/json'):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', mime + '; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            if not self.valid_host():
                return self.send(403, {'error': 'Local host only.'})
            if self.path == '/api/health':
                return self.send(200, {'app': 'lucid-v5-web'})
            if self.path == '/api/state':
                return self.send(200, workspace.snapshot())
            if self.path == '/admin.html':
                self.send_response(302)
                self.send_header('Location', 'https://lucidiscool.github.io/Lucid-AI-Public/admin.html')
                self.end_headers()
                return
            files = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'),
                     '/style.css': ('style.css', 'text/css'), '/logo.svg': ('logo.svg', 'image/svg+xml')}
            if self.path in files:
                name, mime = files[self.path]
                return self.send(200, (ROOT / 'website' / name).read_bytes(), mime)
            self.send(404, {'error': 'Not found.'})

        def do_POST(self):
            origin = self.headers.get('Origin')
            if (not self.valid_host() or self.headers.get('X-Lucid-Token') != workspace.token
                or origin not in (None, f'http://127.0.0.1:{port}', f'http://localhost:{port}')):
                return self.send(403, {'error': 'Invalid local request.'})
            try:
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= 70000:
                    return self.send(413, {'error': 'Request too large.'})
                data = json.loads(self.rfile.read(length))
                if self.path == '/api/message':
                    workspace.submit(data.get('message'))
                elif self.path == '/api/stop':
                    workspace.stop.set()
                else:
                    return self.send(404, {'error': 'Not found.'})
                self.send(202, {'ok': True})
            except (ValueError, TypeError, AttributeError) as error:
                self.send(400, {'error': str(error)})
            except RuntimeError as error:
                self.send(409, {'error': str(error)})
    return Handler


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-open', action='store_true')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Port must be 1024–65535.')
    url = f'http://127.0.0.1:{args.port}'
    import httpx
    try:
        response = httpx.get(url + '/api/health', timeout=1, trust_env=False)
        if response.json().get('app') == 'lucid-v5-web':
            if not args.no_open:
                webbrowser.open(url)
            print('LucidAI is already open at ' + url)
            return
    except (httpx.HTTPError, ValueError):
        pass
    workspace = Workspace()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(workspace, args.port))
    print('LucidAI V5 · browser edition\n' + url + '\nKeep this terminal open. Ctrl+C stops the website.', flush=True)
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        workspace.stop.set()
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
