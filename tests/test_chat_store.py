import tempfile
import unittest
from chat_store import ChatStore


class StoreTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = ChatStore(temporary.name)

    def test_memory_survives_reopen_and_forget(self):
        self.store.remember('My bicycle is orange.')
        reopened = ChatStore(self.store.root)
        self.assertIn('orange', reopened.system('Base'))
        reopened.forget(reopened.memories()[0]['id'])
        self.assertNotIn('orange', self.store.system('Base'))

    def test_resume_preserves_full_conversation(self):
        messages = [{'role': 'user', 'content': 'Hello'}, {'role': 'assistant', 'content': 'Hi'}]
        identifier = 'chat-' + 'a' * 32
        self.store.save(identifier, messages)
        self.assertEqual(ChatStore(self.store.root).load('latest'), (identifier, messages))
        self.assertEqual(self.store.chats(), [(identifier, 'Hello')])

    def test_path_escape_and_invalid_conversation_rejected(self):
        with self.assertRaises(ValueError):
            self.store.load('../memories')
        identifier = 'chat-' + 'b' * 32
        self.store.write(identifier + '.json', [{'role': 'system', 'content': 'bad'}])
        with self.assertRaises(ValueError):
            self.store.load(identifier)

    def test_duplicate_and_limits(self):
        self.store.remember('Hello')
        self.store.remember('hello')
        self.assertEqual(len(self.store.memories()), 1)
        with self.assertRaises(ValueError):
            self.store.remember('x' * 501)
        with self.assertRaises(ValueError):
            self.store.forget('missing')
        self.assertEqual(len(self.store.memories()), 1)
