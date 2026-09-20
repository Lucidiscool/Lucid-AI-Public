import json
import threading
import unittest
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
