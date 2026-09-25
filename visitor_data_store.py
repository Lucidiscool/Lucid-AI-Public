"""Persistent visitor workspaces backed by a private GitHub repository."""
import hashlib
import json
import os
import re
import subprocess
import tempfile
import threading
from pathlib import Path


REPOSITORY = 'Lucidiscool/Lucid-AI-Visitor-Data'


class VisitorDataStore:
    def __init__(self, root=None, repository=REPOSITORY):
        self.repository = repository
        if os.environ.get('LOCALAPPDATA'):
            local = Path(os.environ['LOCALAPPDATA'])
        elif os.name == 'nt':
            local = Path.home() / 'AppData' / 'Local'
        else:
            local = Path(os.environ.get('XDG_DATA_HOME') or (Path.home() / '.local' / 'share'))
        self.root = Path(root or os.environ.get('LUCID_VISITOR_DATA_DIR') or local / 'LucidAI' / 'VisitorData')
        self.lock = threading.RLock()
        self.ensure_repository()

    def run(self, args, *, cwd=None, timeout=120):
        environment = dict(os.environ, GIT_TERMINAL_PROMPT='0')
        return subprocess.run(args, cwd=cwd, env=environment, check=True,
                              capture_output=True, text=True, timeout=timeout)

    def ensure_repository(self):
        self.root.parent.mkdir(parents=True, exist_ok=True)
        if not (self.root / '.git').is_dir():
            if self.root.exists() and any(self.root.iterdir()):
                raise RuntimeError('The visitor data folder exists but is not the private repository checkout.')
            if self.root.exists():
                self.root.rmdir()
            self.run(['gh', 'repo', 'clone', self.repository, str(self.root)])
        details = self.run(['gh', 'repo', 'view', self.repository, '--json', 'isPrivate'])
        if not json.loads(details.stdout).get('isPrivate'):
            raise RuntimeError('Visitor data repository must be private.')
        remote = self.run(['git', 'remote', 'get-url', 'origin'], cwd=self.root).stdout.strip().lower()
        if 'lucidiscool/lucid-ai-visitor-data' not in remote:
            raise RuntimeError('The visitor data checkout points to an unexpected GitHub repository.')
        status = self.run(['git', 'status', '--porcelain'], cwd=self.root).stdout
        if status.strip():
            self.run(['git', 'add', '--all'], cwd=self.root)
            self.run(['git', '-c', 'user.name=Lucid AI', '-c', 'user.email=lucid-ai@users.noreply.github.com',
                      'commit', '-m', 'Recover locally saved visitor data'], cwd=self.root)
        self.run(['git', 'pull', '--rebase', '--autostash'], cwd=self.root)
        self.run(['git', 'push', 'origin', 'HEAD'], cwd=self.root)
        (self.root / 'visitors').mkdir(exist_ok=True)

    @staticmethod
    def digest(visitor_id):
        if not isinstance(visitor_id, str) or not re.fullmatch(r'[a-f0-9]{64}', visitor_id):
            raise ValueError('Invalid visitor key.')
        return hashlib.sha256(visitor_id.encode('ascii')).hexdigest()

    def directory_for(self, visitor_id):
        digest = self.digest(visitor_id)
        path = self.root / 'visitors' / digest[:2] / digest
        path.mkdir(parents=True, exist_ok=True)
        return path, digest

    @staticmethod
    def write_json(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def load_activity(self):
        path = self.root / 'activity.json'
        if not path.exists():
            return []
        try:
            rows = json.loads(path.read_text(encoding='utf-8'))
            return rows[-2000:] if isinstance(rows, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def save_activity(self, rows):
        with self.lock:
            self.write_json(self.root / 'activity.json', rows[-2000:])

    def sync(self, digest):
        if not re.fullmatch(r'[a-f0-9]{64}', digest):
            raise ValueError('Invalid visitor record key.')
        with self.lock:
            self.run(['git', 'add', '--all', '--', f'visitors/{digest[:2]}/{digest}', 'activity.json'], cwd=self.root)
            changed = subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=self.root,
                                     env=dict(os.environ, GIT_TERMINAL_PROMPT='0'), check=False)
            if changed.returncode == 0:
                return
            if changed.returncode != 1:
                raise RuntimeError('Could not inspect private visitor data changes.')
            self.run(['git', '-c', 'user.name=Lucid AI', '-c', 'user.email=lucid-ai@users.noreply.github.com',
                      'commit', '-m', f'Update visitor {digest[:12]}'], cwd=self.root)
            try:
                self.run(['git', 'push', 'origin', 'HEAD'], cwd=self.root)
            except subprocess.CalledProcessError:
                self.run(['git', 'pull', '--rebase', '--autostash'], cwd=self.root)
                self.run(['git', 'push', 'origin', 'HEAD'], cwd=self.root)
