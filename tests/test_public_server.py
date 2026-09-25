import json
import hashlib
import threading
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from admin_service import AdminService
from http.server import ThreadingHTTPServer
import httpx
from public_server import Sessions, make_handler, ORIGIN, PORT


class FakeBackend:
    def __init__(self, stop):
        self.client = httpx.Client()
    def start(self): pass
    def answer(self, messages, **kwargs):
        text = 'Hello from the isolated test model.'
        if kwargs.get('on_token'): kwargs['on_token'](text)
        return messages + [{'role': 'assistant', 'content': text}]


class FakeVisitorDataStore:
    def __init__(self, root):
        self.root = Path(root)
        self.synced = []

    def directory_for(self, visitor_id):
        digest = hashlib.sha256(visitor_id.encode()).hexdigest()
        path = self.root / digest
        path.mkdir(parents=True, exist_ok=True)
        return path, digest

    def save_activity(self, rows):
        pass

    def sync(self, identity):
        self.synced.append(identity)


class PublicTests(unittest.TestCase):
    def setUp(self):
        self.sessions = Sessions(FakeBackend)
    def tearDown(self):
        for item in self.sessions.items.values():
            item['workspace'].app.backend.client.close()
            item['directory'].cleanup()

    def test_isolation_and_commands(self):
        first = self.sessions.get(self.sessions.create())
        second = self.sessions.get(self.sessions.create())
        self.sessions.submit(first, '/remember My test preference is blue.').join(5)
        self.assertEqual(len(first['workspace'].app.store.memories()), 1)
        self.assertEqual(second['workspace'].app.store.memories(), [])
        self.assertFalse(first['workspace'].app.store.settings()['auto_web'])
        for text in ['/search http://127.0.0.1', '/auto-web on', '/model', '/system', '/tokens 4096']:
            with self.assertRaises(ValueError): self.sessions.submit(first, text)
        self.sessions.submit(first, 'Hello').join(5)
        self.assertIn('isolated test model', first['workspace'].snapshot()['messages'][-1]['content'])
        self.assertEqual(second['workspace'].snapshot()['messages'], [])

    def test_capacity_and_busy(self):
        item = self.sessions.get(self.sessions.create())
        self.sessions.gate.acquire()
        try:
            with self.assertRaises(RuntimeError): self.sessions.submit(item, 'Hello')
        finally: self.sessions.gate.release()
        for _ in range(11): self.sessions.create()
        with self.assertRaises(RuntimeError): self.sessions.create()

    def test_visitor_settings_memories_and_chats_survive_new_session(self):
        with tempfile.TemporaryDirectory() as root:
            data_store = FakeVisitorDataStore(root)
            visitor_id = 'a' * 64
            first = Sessions(FakeBackend, data_store)
            first_item = first.get(first.create(visitor_id))
            app = first_item['workspace'].app
            app.store.set_setting('auto_memory', True)
            app.store.remember('Likes clear examples.')
            app.handle('/temperature 0.4')
            app.handle('/tokens 320')
            app.handle('/think on')
            first.submit(first_item, 'Hello').join(5)
            self.assertFalse(first_item['workspace'].busy)

            second = Sessions(FakeBackend, data_store)
            second_item = second.get(second.create(visitor_id))
            restored = second_item['workspace']
            self.assertEqual(restored.app.history[-1]['content'], 'Hello from the isolated test model.')
            self.assertEqual(restored.messages[-1]['content'], 'Hello from the isolated test model.')
            self.assertEqual(restored.app.store.memories()[0]['text'], 'Likes clear examples.')
            self.assertTrue(restored.app.store.settings()['auto_memory'])
            self.assertEqual(restored.app.temperature, 0.4)
            self.assertEqual(restored.app.tokens, 320)
            self.assertTrue(restored.app.think)
            self.assertEqual(len(data_store.synced), 1)
            for item in (first_item, second_item):
                item['workspace'].app.backend.client.close()

    def test_admin_http_requires_separate_credential(self):
        service = AdminService('3553')
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.sessions))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with patch('public_server.admin', service), httpx.Client(base_url=f'http://127.0.0.1:{server.server_port}', trust_env=False) as client:
                headers = {'Host': f'127.0.0.1:{PORT}', 'Origin': ORIGIN}
                self.assertEqual(client.post('/api/admin/login', json={'password': '3553'}).status_code, 403)
                preflight = client.options('/api/admin/login', headers={**headers,
                    'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'content-type'})
                self.assertEqual(preflight.status_code, 200)
                self.assertEqual(preflight.headers.get('Access-Control-Allow-Origin'), ORIGIN)
                visitor = self.sessions.create()
                self.assertEqual(client.post('/api/admin/action', headers=headers, json={'token': visitor, 'action': 'dashboard'}).status_code, 401)
                response = client.post('/api/admin/login', headers=headers, json={'password': '3553'})
                self.assertEqual(response.status_code, 200)
                token = response.json()['token']
                self.assertEqual(client.post('/api/admin/action', headers=headers, json={'token': token, 'action': 'dashboard'}).status_code, 200)
                client.post('/api/admin/action', headers=headers, json={'token': token, 'action': 'logout'})
                self.assertEqual(client.post('/api/admin/action', headers=headers, json={'token': token, 'action': 'dashboard'}).status_code, 401)
        finally:
            server.shutdown()
            server.server_close()

    def test_http_boundaries(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.sessions))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{server.server_port}', trust_env=False) as client:
                headers = {'Host': f'127.0.0.1:{PORT}', 'Origin': ORIGIN}
                self.assertEqual(client.post('/api/session', json={}).status_code, 403)
                self.assertEqual(client.get('/api/state', headers=headers).status_code, 401)
                response = client.post('/api/session', json={}, headers=headers)
                self.assertEqual(response.status_code, 201)
                headers['X-Lucid-Session'] = response.json()['session']
                state = client.get('/api/state', headers=headers).json()
                self.assertEqual(client.post('/api/message', json={'message': 'Hi'}, headers=headers).status_code, 403)
                headers['X-Lucid-Token'] = state['token']
                self.assertEqual(client.post('/api/message', json={'message': '/model'}, headers=headers).status_code, 400)
                self.assertEqual(client.get('/personal/memories.json', headers=headers).status_code, 404)
                self.assertEqual(client.get('/api/state', headers={**headers, 'X-Lucid-Session': 'bad'}).status_code, 401)
        finally:
            server.shutdown()
            server.server_close()
