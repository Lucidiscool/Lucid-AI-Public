import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from blank_experiment import BlankExperiment
from dev_chat import DeveloperChat


class DeveloperTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.output = []
        self.backend = Mock()
        self.app = DeveloperChat(Path(folder.name), self.backend, self.output.append)

    def test_unknown_then_taught_identity(self):
        blank = BlankExperiment()
        self.assertEqual(blank.reply('Are you a human?'), "I don't know.")
        blank.reply('Yes you are a human')
        self.assertIn('Yes', blank.reply('Are you a human?'))
        self.assertIn('Yes', blank.reply('are you human'))
        blank.reply('The blue sky is beautiful')
        self.assertIn('Yes', blank.reply('is the blue sky beautiful?'))
        self.assertIn("don't know", blank.reply('What is 2 + 2?'))

    def test_experiment_never_touches_normal_state_or_model(self):
        self.app.store.remember('My name is RealUser')
        self.app.history = [{'role': 'user', 'content': 'normal'}, {'role': 'assistant', 'content': 'normal answer'}]
        before = (self.app.store.root / 'memories.json').read_bytes()
        for command in ['/forget on', 'you are a human', '/remember I am fictional', '/search news', '/save', '/forget off']:
            self.app.handle(command)
        self.assertEqual(len(self.app.history), 2)
        self.assertEqual((self.app.store.root / 'memories.json').read_bytes(), before)
        self.assertFalse(list(self.app.store.root.glob('chat-*.json')))
        self.backend.answer.assert_not_called()
        self.backend.start.assert_not_called()
        self.app.handle('/forget on')
        self.assertEqual(self.app.blank.facts, {})

    def test_think_is_toggle_and_process_summary(self):
        self.app.handle('/think')
        self.app.handle('/forget on')
        self.app.handle('What is gravity?')
        self.assertTrue(any('[Process summary]' in line for line in self.output))
        self.app.handle('/think')
        self.assertFalse(self.app.think)

    def test_explicit_forget_id_remains_memory_delete(self):
        self.app.store.remember('A remembered fact')
        identifier = self.app.store.memories()[0]['id']
        self.app.handle('/forget ' + identifier)
        self.assertIsNone(self.app.blank)
        self.assertEqual(self.app.store.memories(), [])

    def test_settings_validate_and_apply(self):
        self.app.handle('/temperature 0.2')
        self.app.handle('/tokens 128')
        self.app.handle('/auto-memory off')
        self.app.handle('/auto-web off')
        self.backend.answer.return_value = [{'role': 'assistant', 'content': 'A concise reply.'}]
        self.app.handle('Hello')
        self.assertEqual(self.backend.answer.call_args.kwargs['temperature'], 0.2)
        self.assertEqual(self.backend.answer.call_args.kwargs['max_tokens'], 128)
        with self.assertRaises(ValueError):
            self.app.handle('/temperature 3')
        with self.assertRaises(ValueError):
            self.app.handle('/tokens 99999')
