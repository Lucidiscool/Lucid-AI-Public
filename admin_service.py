"""Server-only admin authentication, temporary activity, and host selection."""
import copy
import hashlib
import hmac
import os
import secrets
import threading
import time
from collections import Counter, deque


class AdminService:
    def __init__(self, passcode=None):
        password = os.environ.get('LUCID_ADMIN_PASSCODE', '') if passcode is None else passcode
        self.salt = secrets.token_bytes(16)
        self.digest = self.hash(password) if 4 <= len(password) <= 512 else None
        self.login_window = 3600 if len(password) < 12 else 60
        self.lock = threading.RLock()
        self.attempts = deque()
        self.tokens = {}
        self.activity = deque(maxlen=2000)
        self.started = time.time()
        self.host = {'provider': 'local'}

    def hash(self, password):
        return hashlib.scrypt(password.encode(), salt=self.salt, n=16384, r=8, p=1)

    def login(self, password):
        with self.lock:
            now = time.monotonic()
            while self.attempts and self.attempts[0] < now - self.login_window:
                self.attempts.popleft()
            if len(self.attempts) >= 5:
                raise ValueError('Too many login attempts. Try again later.')
            self.attempts.append(now)
            if not self.digest:
                raise ValueError('Admin is disabled. Set LUCID_ADMIN_PASSCODE to at least 4 characters on the server.')
            if not isinstance(password, str) or len(password) > 512 or not hmac.compare_digest(self.hash(password), self.digest):
                raise ValueError('Invalid passcode.')
            self.tokens = {t: expiry for t, expiry in self.tokens.items() if expiry > now}
            if len(self.tokens) >= 20:
                self.tokens.pop(next(iter(self.tokens)))
            token = secrets.token_urlsafe(32)
            self.tokens[token] = now + 1800
            return {'token': token, 'expires_in': 1800}

    def authorize(self, token):
        with self.lock:
            if not isinstance(token, str) or self.tokens.get(token, 0) <= time.monotonic():
                raise PermissionError('Admin session expired. Sign in again.')

    def config(self):
        with self.lock:
            return copy.deepcopy(self.host)

    def record(self, visitor, message, messages, error='', visitor_id=None):
        # Bounded RAM only. Never retain session credentials or owner workspace data.
        with self.lock:
            answer = messages[-1].get('content', '') if messages and messages[-1].get('role') == 'assistant' else ''
            self.activity.append({'visitor': visitor, 'visitor_id': visitor_id, 'time': time.time(),
                'feature': message.split()[0] if message.startswith('/') else 'chat',
                'message': message[:4000], 'answer': answer[:8000], 'failed': bool(error)})
            self.prune()

    def prune(self):
        while self.activity and self.activity[0]['time'] < time.time() - 86400:
            self.activity.popleft()

    def action(self, token, action):
        with self.lock:
            self.authorize(token)
            if action == 'logout':
                self.tokens.pop(token, None)
                return {'ok': True}
            if action != 'dashboard':
                raise ValueError('Unknown admin action.')
            self.prune()
            rows = list(self.activity)
            return {'hosting': self.config(), 'started': self.started,
                'requests': len(rows), 'visitors': len({r['visitor'] for r in rows}),
                'failures': sum(r['failed'] for r in rows),
                'features': dict(Counter(r['feature'] for r in rows).most_common()),
                'activity': copy.deepcopy(rows[-200:][::-1])}


admin = AdminService()
