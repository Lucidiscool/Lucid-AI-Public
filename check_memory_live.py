"""Opt-in live memory check, isolated from real personal data."""
import tempfile
from chat_store import ChatStore
from local_chat import Backend, SYSTEM

with tempfile.TemporaryDirectory() as directory:
    store = ChatStore(directory)
    store.remember('My project codename is Amber Finch.')
    store = ChatStore(directory)
    backend = Backend()
    try:
        backend.start()
        answer = backend.answer([{'role': 'system', 'content': store.system(SYSTEM)},
            {'role': 'user', 'content': 'What is my project codename?'}],
            max_tokens=80, temperature=0, display=False)[-1]['content']
        print('Recall:', answer)
        assert 'amber finch' in answer.lower()
        store.forget('all')
        assert 'Amber Finch' not in store.system(SYSTEM)
        print('PASS: persisted memory recalled; forgotten fact removed from fresh context.')
    finally:
        backend.client.close()
