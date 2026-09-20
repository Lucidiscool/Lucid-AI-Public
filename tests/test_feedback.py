import tempfile
import unittest
from chat_store import ChatStore


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = ChatStore(folder.name)
        self.chat = 'chat-' + 'a'*32
        self.history = [{'role': 'user', 'content': 'Explain Python functions'},
                        {'role': 'assistant', 'content': 'An incorrect answer'}]

    def test_correction_survives_restart_and_is_retrieved(self):
        self.store.rate(self.chat, self.history, 'correct', 'Functions are reusable blocks of code.')
        reopened = ChatStore(self.store.root)
        context = reopened.feedback_context('Explain Python functions simply')
        self.assertIn('reusable blocks', context)
        self.assertNotIn('An incorrect answer', context)
        self.assertEqual(reopened.feedback_context('Describe ocean wildlife'), '')

    def test_rerating_replaces_and_unrating_removes(self):
        self.store.rate(self.chat, self.history, 'good')
        self.store.rate(self.chat, self.history, 'bad', 'Too vague')
        self.assertEqual(len(self.store.feedback()), 1)
        self.assertIn('Too vague', self.store.feedback_context('Explain Python functions'))
        self.assertNotIn('An incorrect answer', self.store.feedback_context('Explain Python functions'))
        self.store.unrate(self.chat, self.history)
        self.assertEqual(self.store.feedback_context('Explain Python functions'), '')

    def test_empty_history_and_empty_correction_rejected(self):
        with self.assertRaises(ValueError):
            self.store.rate(self.chat, [], 'good')
        with self.assertRaises(ValueError):
            self.store.rate(self.chat, self.history, 'correct')
        self.assertEqual(self.store.feedback(), [])

    def test_positive_example_is_available(self):
        self.store.rate(self.chat, self.history, 'good', 'Clear explanation')
        self.assertIn('approved_answer', self.store.feedback_context('Explain Python functions'))
