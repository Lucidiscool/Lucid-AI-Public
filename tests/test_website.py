import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock
from http.server import ThreadingHTTPServer
import httpx
from dev_chat import DeveloperChat
from website_server import Workspace, make_handler, BrowserBackend, Stopped


class WebsiteTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.app = DeveloperChat(Path(folder.name), Mock(), lambda x: None)
        self.workspace = Workspace(app=self.app)

    def run_command(self, command):
        thread = self.workspace.submit(command)
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.workspace.error, '')

    def test_experiment_messages_disappear_on_exit(self):
        self.run_command('/forget on')
        self.run_command('You are a human')
        self.run_command('Are you a human?')
        self.assertIn('Yes', self.workspace.messages[-1]['content'])
        self.run_command('/forget off')
        self.assertEqual(self.workspace.messages, [])
        self.assertEqual(self.app.history, [])

    def test_stream_is_replaced_by_final_answer(self):
        self.workspace.stream('Hello')
        self.workspace.stream(' there')
        self.workspace.output('LucidAI V5: Hello there!')
        self.assertEqual(len(self.workspace.messages), 1)
        self.assertEqual(self.workspace.messages[0]['content'], 'Hello there!')
        self.assertFalse(self.workspace.messages[0]['pending'])

    def test_busy_rejects_concurrent_requests(self):
        self.workspace.busy = True
        with self.assertRaises(RuntimeError):
            self.workspace.submit('Hello')

    def test_http_rejects_missing_token_foreign_origin_and_host(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.workspace, 0))
        port = server.server_address[1]
        server.RequestHandlerClass = make_handler(self.workspace, port)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}', trust_env=False) as client:
                response = client.get('/api/state')
                self.assertEqual(response.status_code, 200)
                token = response.json()['token']
                self.assertEqual(client.post('/api/message', json={'message': '/think'}).status_code, 403)
                self.assertEqual(client.post('/api/message', headers={'X-Lucid-Token': token, 'Origin': 'https://evil.example'}, json={'message': '/think'}).status_code, 403)
                self.assertEqual(client.get('/api/state', headers={'Host': 'evil.example'}).status_code, 403)
                self.assertEqual(client.post('/api/message', headers={'X-Lucid-Token': token}, json={'message': '/think'}).status_code, 202)
                self.assertEqual(client.get('/../local_model.json').status_code, 404)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_cancelled_backend_does_not_start_generation(self):
        stop = threading.Event()
        stop.set()
        backend = BrowserBackend.__new__(BrowserBackend)
        backend.stop = stop
        with self.assertRaises(Stopped):
            backend.answer([])
