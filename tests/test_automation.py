import json
import tempfile
import unittest
from unittest.mock import Mock
from chat_automation import decide
from chat_store import ChatStore


class AutomationTests(unittest.TestCase):
    def decision(self, prompt, data):
        backend = Mock()
        backend.answer.return_value = [{'content': json.dumps(data)}]
        return decide(backend, prompt, {'auto_memory': True, 'auto_web': True})

    def test_unstated_memory_rejected(self):
        result = self.decision('Hello', {'memories': [{'key': 'name', 'text': 'My name is Jane'}]})
        self.assertEqual(result['memories'], [])
        result = self.decision('Explain Python functions', {'memories': [{'key': 'preference', 'text': 'Explain Python functions'}]})
        self.assertEqual(result['memories'], [])

    def test_secrets_and_opt_out(self):
        result = self.decision('My password is abcdef', {'search': 'abcdef', 'memories': [{'key': 'tools', 'text': 'My password is abcdef'}]})
        self.assertEqual(result, {'search': '', 'memories': []})
        self.assertEqual(self.decision('Do not browse for current news', {'search': 'news'})['search'], '')

    def test_off_skips_model(self):
        backend = Mock()
        decide(backend, 'Hello', {'auto_memory': False, 'auto_web': False})
        backend.answer.assert_not_called()

    def test_malformed_output_does_not_act(self):
        backend = Mock()
        backend.answer.return_value = [{'content': 'not json'}]
        self.assertEqual(decide(backend, 'Hello', {'auto_memory': True, 'auto_web': True}), {'search': '', 'memories': []})

    def test_name_update_forget_and_persistent_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ChatStore(folder)
            store.auto_remember('name', 'My name is Pat')
            store.auto_remember('name', 'My name is Alex')
            self.assertEqual(len(store.memories()), 1)
            store.forget('all')
            self.assertIsNone(store.auto_remember('name', 'My name is Alex'))
            self.assertNotIn('Alex', (store.root / 'forgotten.json').read_text())
            store.set_setting('auto_web', False)
            self.assertFalse(ChatStore(folder).settings()['auto_web'])
