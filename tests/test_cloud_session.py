"""Exercise hosted V5 state handling without loading GPU weights locally."""
import ast
import copy
import json
from pathlib import Path
import tempfile
import time
import types
import secrets
from admin_service import AdminService
import unittest
from dev_chat import DeveloperChat
from chat_store import ChatStore


def load_session_code():
    path = Path(__file__).resolve().parents[1] / 'hosting/huggingface/app.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    keep = []
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in ('MemoryStore', 'chat'):
            keep.append(node)
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ('ALLOWED', 'ATTRS') for t in node.targets):
            keep.append(node)
    class FakeBackend:
        def start(self): pass
        def answer(self, messages, **kwargs):
            return messages + [{'role': 'assistant', 'content': 'Test answer: '+messages[-1]['content']}]
    scope = dict(copy=copy, json=json, tempfile=tempfile, time=time, Path=Path, secrets=secrets, admin=AdminService(),
                 DeveloperChat=DeveloperChat, ChatStore=ChatStore,
                 CloudBackend=FakeBackend, gr=types.SimpleNamespace(Error=ValueError))
    exec(compile(ast.Module(body=keep, type_ignores=[]), str(path), 'exec'), scope)
    return scope['chat']


class CloudSessionTests(unittest.TestCase):
    def test_admin_errors_are_exposed_as_safe_gradio_errors(self):
        path = Path(__file__).resolve().parents[1] / 'hosting/huggingface/app.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        keep = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                and n.name in ('admin_login', 'admin_action_request')]
        class DisplayError(Exception):
            pass
        scope = {'admin': AdminService(''), 'gr': types.SimpleNamespace(Error=DisplayError)}
        exec(compile(ast.Module(body=keep, type_ignores=[]), str(path), 'exec'), scope)
        with self.assertRaisesRegex(DisplayError, 'LUCID_ADMIN_PASSCODE'):
            scope['admin_login']('test')
        with self.assertRaisesRegex(DisplayError, 'expired'):
            scope['admin_action_request']('invalid', 'dashboard')

    def test_history_memory_and_isolation(self):
        chat = load_session_code()
        messages, view, saved = chat('Hi there', None)
        self.assertEqual(len(messages), 2)
        self.assertFalse(view['settings']['auto_web'])
        _, view, saved = chat('/remember My preferred color is blue.', saved)
        self.assertEqual(len(view['memories']), 1)
        _, other, _ = chat('New visitor', None)
        self.assertEqual(other['memories'], [])
        self.assertNotEqual(other['chat_id'], view['chat_id'])
        _, fresh, saved = chat('/new', saved)
        self.assertEqual(fresh['messages'], [])
        self.assertEqual(len(fresh['memories']), 1)

    def test_limits_and_no_mutation_on_failure(self):
        chat = load_session_code()
        _, _, saved = chat('Hello', None)
        before = copy.deepcopy(saved)
        for message in ['/search private data', '/system hello', '/model', '/tokens 1024', 'x'*4001]:
            with self.assertRaises(ValueError): chat(message, saved)
        self.assertEqual(saved, before)

    def test_experiment_survives_session_roundtrip(self):
        chat = load_session_code()
        _, view, saved = chat('/forget on', None)
        self.assertTrue(view['experiment'])
        _, _, saved = chat('/teach The sky is blue.', saved)
        _, view, saved = chat('/facts', saved)
        self.assertIn('blue', view['notice'])
        _, view, _ = chat('/forget off', saved)
        self.assertFalse(view['experiment'])
