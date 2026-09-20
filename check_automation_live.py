"""Live checks without writing test facts into personal memory."""
import sys
from local_chat import Backend, SYSTEM
from chat_automation import decide
sys.stdout.reconfigure(encoding='utf-8')
backend = Backend()
original_answer = backend.answer
def inspect_answer(*args, **kwargs):
    response = original_answer(*args, **kwargs)
    print('Model decision:', response[-1]['content'], flush=True)
    return response
backend.answer = inspect_answer
try:
    backend.start()
    for prompt in ['My name is Elliott and I prefer short answers.', 'What are the latest Python releases?', 'Explain what a Python function is.']:
        result = decide(backend, prompt, {'auto_memory': True, 'auto_web': True})
        print(prompt, result, flush=True)
        if 'My name' in prompt:
            assert result['memories'] and not result['search']
        elif 'latest' in prompt:
            assert result['search']
        else:
            assert not result['search']
            assert not result['memories']
    answer = backend.answer([{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': 'Explain what a Python function is.'}], max_tokens=180, temperature=0, display=False)[-1]['content']
    print('Concise answer:', answer, flush=True)
    assert len(answer.split()) < 100
finally:
    backend.client.close()
