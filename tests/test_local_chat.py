import unittest
import httpx
from local_chat import Backend


class LocalChatTests(unittest.TestCase):
    def backend(self, handler):
        backend = Backend.__new__(Backend)
        backend.config = {'context': 100, 'alias': 'lucid-local'}
        backend.client = httpx.Client(base_url='http://test', transport=httpx.MockTransport(handler))
        self.addCleanup(backend.client.close)
        return backend

    def test_removes_oldest_pair_without_mutating_input(self):
        import json
        def handler(request):
            body = json.loads(request.content)
            if request.url.path == '/apply-template':
                return httpx.Response(200, json={'prompt': str(len(body['messages']))})
            return httpx.Response(200, json={'tokens': [0] * (80 if body['content'] == '4' else 10)})
        backend = self.backend(handler)
        messages = [{'role': role, 'content': str(i)} for i, role in enumerate(['system', 'user', 'assistant', 'user'])]
        self.assertEqual(backend.fit(messages, 20), [messages[0], messages[3]])
        self.assertEqual(len(messages), 4)

    def test_oversized_message_rejected(self):
        backend = self.backend(lambda request: httpx.Response(200, json={'prompt': 'x', 'tokens': [0]*100}))
        with self.assertRaises(ValueError):
            backend.fit([{'role': 'system'}, {'role': 'user'}], 20)

    def test_wrong_model_rejected(self):
        backend = self.backend(lambda request: httpx.Response(200, json={'data': [{'id': 'other'}]}))
        with self.assertRaises(RuntimeError):
            backend.ready()

    def test_failed_stream_does_not_change_history(self):
        backend = self.backend(lambda request: httpx.Response(500))
        backend.fit = lambda messages, max_tokens: list(messages)
        history = [{'role': 'user', 'content': 'hello'}]
        with self.assertRaises(httpx.HTTPStatusError):
            backend.answer(history, display=False)
        self.assertEqual(len(history), 1)
