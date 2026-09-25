"""Local Qwen chat via the bundled llama.cpp Vulkan server."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import sys
from datetime import datetime
import uuid
from chat_store import ChatStore

import httpx

ROOT = Path(__file__).resolve().parent
SYSTEM = ('You are LucidAI, a helpful local assistant powered by Qwen3-4B-Instruct-2507. '
          'Lead with the answer. Default to 1–3 short sentences or at most 3 useful bullets. '
          'For summaries, give the main conclusion and only essential details. No preambles, repetition or closing offers. '
          'Give more detail when the user asks or the task requires it. '
          'The app can search automatically or through /search and /research. Without supplied sources, do not claim you browsed. '
          'Do not invent facts about the user or claim to have performed actions.')


class Backend:
    def __init__(self):
        self.config = json.loads((ROOT / 'local_model.json').read_text())
        self.client = httpx.Client(base_url=f"http://127.0.0.1:{self.config['port']}", timeout=180, trust_env=False)

    def ready(self):
        try:
            response = self.client.get('/health', timeout=2)
        except (httpx.ConnectError, httpx.TimeoutException):
            return False
        if response.status_code == 503:
            return False
        response.raise_for_status()
        models = self.client.get('/v1/models').json()['data']
        if not any(m['id'] == self.config['alias'] for m in models):
            raise RuntimeError('Port is occupied by a different model server.')
        return True

    def server_command(self):
        c = self.config
        return [c['server'], '-m', c['model'], '--device', c.get('device', 'Vulkan0'),
                '-ngl', str(c['gpu_layers']), '-c', str(c['context']), '-np', '1',
                '--host', '127.0.0.1', '--port', str(c['port']), '--alias', c['alias'],
                '--no-webui', '--cors-origins', f"http://127.0.0.1:{c['port']}",
                '--cache-ram', str(c.get('cache_ram', 256)), '-lv', '4']

    def start(self):
        if self.ready():
            return
        c = self.config
        log = ROOT / 'runs/local-server.log'
        log.parent.mkdir(exist_ok=True)
        print('Loading the local Qwen model. Server log:', log, flush=True)
        with log.open('ab') as output:
            process = subprocess.Popen(self.server_command(), cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        for _ in range(120):
            if process.poll() is not None:
                raise RuntimeError(f'Model server stopped. Read {log}')
            if self.ready():
                return
            time.sleep(1)
        raise RuntimeError(f'Model loading timed out. Read {log}')

    def fit(self, messages, max_tokens):
        messages = list(messages)
        while True:
            response = self.client.post('/apply-template', json={'messages': messages})
            response.raise_for_status()
            tokens = self.client.post('/tokenize', json={'content': response.json()['prompt'],
                'add_special': False, 'parse_special': True})
            tokens.raise_for_status()
            if len(tokens.json()['tokens']) + max_tokens + 32 <= self.config['context']:
                return messages
            if len(messages) <= 2:
                raise ValueError('Message is too long for the local context. Shorten it or use /new.')
            del messages[1:3]

    def answer(self, messages, max_tokens=768, temperature=0.6, display=True, on_token=None):
        messages = self.fit(messages, max_tokens)
        answer = ''
        with self.client.stream('POST', '/v1/chat/completions', json={
            'model': self.config['alias'], 'messages': messages, 'max_tokens': max_tokens,
            'temperature': temperature, 'top_p': 0.9, 'stream': True}) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line.startswith('data: '):
                    continue
                data = line[6:]
                if data == '[DONE]':
                    break
                packet = json.loads(data)
                if 'error' in packet:
                    raise RuntimeError(str(packet['error']))
                for choice in packet.get('choices', []):
                    part = choice.get('delta', {}).get('content') or ''
                    answer += part
                    if on_token:
                        on_token(part)
                    if display:
                        print(part, end='', flush=True)
        if not answer.strip():
            raise RuntimeError('The model returned an empty response.')
        return messages + [{'role': 'assistant', 'content': answer}]


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prompt')
    parser.add_argument('--resume', nargs='?', const='latest', help='Resume latest chat or a chat ID')
    parser.add_argument('--max-new-tokens', type=int, default=768)
    args = parser.parse_args()
    if not 1 <= args.max_new_tokens <= 4096:
        parser.error('--max-new-tokens must be between 1 and 4096')
    backend = Backend()
    try:
        backend.start()
        store = ChatStore(ROOT / 'personal')
        identifier, history = store.load(args.resume) if args.resume else ('chat-' + uuid.uuid4().hex, [])
        print('LucidAI | local RX 6600 | Conversations save automatically.\n/help lists commands; /quit exits.\n')
        print('Automatic memory and web settings:', store.settings(), '\n')
        if args.resume:
            for message in history[-4:]:
                print(message['role'].capitalize() + ': ' + message['content'])
        while True:
            try:
                prompt = args.prompt if args.prompt is not None else input('You: ').strip()
                if prompt == '/quit':
                    break
                if prompt == '/new':
                    identifier, history = 'chat-' + uuid.uuid4().hex, []
                    print('Started a new conversation.')
                elif prompt == '/help':
                    print('/auto-memory on|off | /auto-web on|off (persistent settings)')
                    print('/search TOPIC (quick web search) | /research TOPIC (multiple searches and source comparison)')
                    print('/good [reason] | /bad [reason] | /correct PREFERRED ANSWER\n/feedback | /unrate (remove rating on latest answer)')
                    print('/remember TEXT | /memories | /forget ID | /forget all\n/chats | /load ID | /load latest | /new | /save | /quit\nForgetting removes saved memory; old conversations still contain their original text.')
                elif prompt.split(' ', 1)[0] in ('/auto-memory', '/auto-web'):
                    command, _, value = prompt.partition(' ')
                    if value not in ('on', 'off'):
                        raise ValueError('Use on or off.')
                    store.set_setting(command[1:].replace('-', '_'), value == 'on')
                    print(command[1:] + ': ' + value)
                elif prompt.split(' ', 1)[0] in ('/search', '/research'):
                    from web_research import Research
                    command, _, topic = prompt.partition(' ')
                    research = Research(backend, ROOT / 'personal' / 'research', progress=lambda text: print(text, flush=True))
                    report = research.run(topic, deep=command == '/research')
                    print('\nLucidAI: ' + report + '\n')
                    history += [{'role': 'user', 'content': prompt}, {'role': 'assistant', 'content': report}]
                    store.save(identifier, history)
                elif prompt.split(' ', 1)[0] in ('/good', '/bad', '/correct'):
                    command, _, note = prompt.partition(' ')
                    store.rate(identifier, history, command[1:], note)
                    print('Feedback saved for the latest answer. Relevant feedback can guide future replies; model weights are unchanged.')
                elif prompt == '/unrate':
                    store.unrate(identifier, history)
                    print('Removed feedback for the latest answer.')
                elif prompt == '/feedback':
                    items = store.feedback()
                    print(f'{len(items)} rated answers. Model weights are unchanged.')
                    for item in items[-10:]:
                        print(f"{item['id']} [{item['rating']}] {item['note'] or '(no explanation)'}")
                elif prompt.startswith('/remember '):
                    print(store.remember(prompt[len('/remember '):]))
                elif prompt == '/memories':
                    print('\n'.join(f"{m['id']}: {m['text']}" for m in store.memories()) or 'No saved memories.')
                elif prompt.startswith('/forget '):
                    store.forget(prompt[len('/forget '):].strip())
                    print('Saved memory removed. Use /new to clear the current conversation context too.')
                elif prompt == '/chats':
                    print('\n'.join(f'{i}: {title}' for i, title in store.chats()) or 'No saved conversations.')
                elif prompt.startswith('/load '):
                    identifier, history = store.load(prompt[len('/load '):].strip())
                    print('Loaded:', identifier)
                    for message in history[-4:]:
                        print(message['role'].capitalize() + ': ' + message['content'])
                elif prompt == '/save':
                    store.save(identifier, history)
                    print('Saved:', identifier)
                elif prompt.startswith('/'):
                    print('Unknown command. Type /help.')
                elif not prompt:
                    if args.prompt is not None:
                        break
                    continue
                else:
                    from chat_automation import decide
                    print('[Auto] Checking whether memory or web would help...', flush=True)
                    try:
                        decision = decide(backend, prompt, store.settings())
                    except (httpx.HTTPError, ValueError, RuntimeError):
                        print('[Auto] Could not decide; continuing without automatic actions.')
                        decision = {'search': '', 'memories': []}
                    for item in decision['memories']:
                        notice = store.auto_remember(item['key'], item['text'])
                        if notice:
                            print('[Memory] ' + notice, flush=True)
                    user = {'role': 'user', 'content': prompt}
                    if decision['search']:
                        from web_research import Research
                        print('[Auto] Web information may help. Query: ' + decision['search'], flush=True)
                        report = Research(backend, ROOT / 'personal' / 'research', progress=lambda text: print(text, flush=True)).run(decision['search'])
                        answer = {'role': 'assistant', 'content': report}
                        print('\nLucidAI: ' + report)
                    else:
                        print('LucidAI: ', end='', flush=True)
                        answer = backend.answer([{'role': 'system', 'content': store.system(SYSTEM) + store.feedback_context(prompt)}] + history + [user], args.max_new_tokens)[-1]
                    history = history + [user, answer]
                    store.save(identifier, history)
                    print('\n')
            except (httpx.HTTPError, ValueError, RuntimeError, OSError) as error:
                print('\nChat error:', error)
                if args.prompt is not None:
                    raise SystemExit(1)
            if args.prompt is not None:
                break
    finally:
        backend.client.close()


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print('\nChat closed.')
