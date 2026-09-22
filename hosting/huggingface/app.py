"""Lucid V5 app logic with a Transformers adapter for Hugging Face ZeroGPU."""
import copy
import json
import tempfile
import time
import secrets
from admin_service import admin
from pathlib import Path

import spaces
import torch
import gradio as gr
from transformers import AutoTokenizer, AutoModelForCausalLM
from dev_chat import DeveloperChat
from chat_store import ChatStore

MODEL = 'Qwen/Qwen3-4B-Instruct-2507'
REVISION = 'cdbee75f17c01a7cc42f958dc650907174af0554'
tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=REVISION)
model = AutoModelForCausalLM.from_pretrained(
    MODEL, revision=REVISION, torch_dtype=torch.bfloat16,
    low_cpu_mem_usage=True, attn_implementation='sdpa').to('cuda')


@spaces.GPU(duration=45)
def generate(messages, max_tokens, temperature):
    messages = list(messages)
    while True:
        inputs = tokenizer.apply_chat_template(messages, add_generation_prompt=True,
                    tokenize=True, return_dict=True, return_tensors='pt').to('cuda')
        if inputs['input_ids'].shape[1] + max_tokens <= 8192:
            break
        if len(messages) <= 2:
            raise ValueError('Message is too long. Please shorten it.')
        del messages[1:3]
    options = {'max_new_tokens': min(max_tokens, 512), 'do_sample': temperature > 0,
               'pad_token_id': tokenizer.eos_token_id}
    if temperature > 0:
        options.update(temperature=temperature, top_p=0.9)
    with torch.inference_mode():
        result = model.generate(**inputs, **options)
    answer = tokenizer.decode(result[0, inputs['input_ids'].shape[1]:], skip_special_tokens=True)
    if not answer.strip():
        raise RuntimeError('The model returned an empty answer. Please try again.')
    return answer


class CloudBackend:
    def start(self):
        pass

    def answer(self, messages, max_tokens=512, temperature=0.6, display=False, on_token=None):
        answer = generate(messages, max_tokens, temperature)
        if on_token:
            on_token(answer)
        return messages + [{'role': 'assistant', 'content': answer}]


class MemoryStore(ChatStore):
    """Reuse V5 memory/feedback logic without writing visitor content to disk."""
    def __init__(self, files):
        self.files = files

    def read(self, name, default):
        return copy.deepcopy(self.files.get(name, default))

    def write(self, name, value):
        self.files[name] = copy.deepcopy(value)

    def chats(self):
        result = []
        for name in reversed(list(self.files)):
            if name.startswith('chat-') and name.endswith('.json'):
                identifier, messages = self.load(name[:-5])
                result.append((identifier, messages[0]['content'][:70] if messages else '(empty)'))
        return result


ALLOWED = {'/new', '/think', '/forget', '/facts', '/teach', '/reset', '/remember', '/memories',
           '/good', '/bad', '/correct', '/feedback', '/unrate', '/chats', '/load', '/history',
           '/save', '/temperature', '/tokens', '/settings', '/stats', '/auto-memory', '/help'}
ATTRS = ['history', 'identifier', 'blank', 'think', 'temperature', 'tokens', 'turns', 'last_seconds']


def chat(message, session):
    if not isinstance(message, str) or not 1 <= len(message.strip()) <= 4000:
        raise gr.Error('Enter a message of 1–4000 characters.')
    session = copy.deepcopy(session or {})
    visitor = session.get('visitor') or secrets.token_hex(8)
    if session.get('requests', 0) >= 100:
        raise gr.Error('Session limit reached. Reload to start a new session.')
    message = message.strip()
    command = message.split()[0]
    if command.startswith('/') and command not in ALLOWED:
        raise gr.Error('That command is available only in the local app.')
    if command == '/tokens':
        try:
            if not 32 <= int(message.split(maxsplit=1)[1]) <= 512:
                raise ValueError()
        except (ValueError, IndexError):
            raise gr.Error('Free hosting supports 32–512 reply tokens.')
    if len(json.dumps(session.get('files', {}))) > 500000:
        raise gr.Error('Session storage is full. Reload to start a new session.')
    messages = session.get('messages', [])
    events, notices = [], []
    def output(text):
        if text.startswith(('LucidAI V5: ', 'Experiment: ')):
            messages.append({'role': 'assistant', 'content': text.split(': ', 1)[1]})
        elif text.startswith(('[Web]', '[Memory]', '[Process summary]', '[Auto]')):
            events.append({'text': text, 'time': time.strftime('%H:%M:%S')})
        else:
            notices.append(text)
    with tempfile.TemporaryDirectory(prefix='lucid-init-') as directory:
        app = DeveloperChat(Path(directory), CloudBackend(), output)
        app.store = MemoryStore(session.get('files', {}))
        if not session:
            app.store.set_setting('auto_memory', False)
        app.store.set_setting('auto_web', False)
        app.tokens = 384
        app.system += ' This hosted session has no web access. Do not claim to browse.'
        for key in ATTRS:
            if key in session:
                setattr(app, key, session[key])
        was_blank = app.blank is not None
        before = copy.deepcopy(messages)
        if not message.startswith('/') or message.startswith('/teach '):
            messages.append({'role': 'user', 'content': message})
        try:
            app.handle(message)
        except Exception as error:
            admin.record(visitor, message, [], 'failed')
            # Gradio shows quota/queue failures without leaking host filesystem paths.
            raise gr.Error('Lucid could not finish this request. '+str(error)[:350]) from None
        if message in ('/new', '/reset') or message.startswith('/load ') or was_blank != (app.blank is not None):
            messages = [] if app.blank else copy.deepcopy(app.history)
        snapshot = {'messages': messages, 'events': events[-30:], 'busy': False, 'error': '',
                    'notice': '\n'.join(notices)[-4000:], 'experiment': app.blank is not None,
                    'think': app.think, 'temperature': app.temperature, 'max_tokens': app.tokens,
                    'settings': app.store.settings(), 'memories': app.store.memories(),
                    'chats': [{'id': i, 'title': title} for i, title in app.store.chats()],
                    'chat_id': app.identifier, 'seconds': app.last_seconds, 'turns': app.turns}
        saved = {key: copy.deepcopy(getattr(app, key)) for key in ATTRS}
        saved.update(files=app.store.files, messages=messages, requests=session.get('requests', 0)+1)
        saved['visitor'] = visitor
        admin.record(saved['visitor'], message, messages)
    return messages, snapshot, saved


def admin_login(password):
    try:
        return admin.login(password)
    except (ValueError, PermissionError) as error:
        raise gr.Error(str(error)) from None


def admin_action_request(token, action, url=''):
    try:
        return admin.action(token, action, url)
    except (ValueError, PermissionError) as error:
        raise gr.Error(str(error)) from None


with gr.Blocks() as demo:
    gr.Markdown('# Lucid AI V5\nYour V5 app, running on free Hugging Face GPUs. '
                'Same Qwen3-4B-Instruct-2507 model in BF16 rather than the local Q4 GGUF. '
                'No owner computer required. Free GPU quotas and queues apply. '
                'The site owner can review messages, replies, and feature usage for up to 24 hours (at most 2,000 requests). Do not share sensitive information. '
                'Web research is available only in the local app.')
    conversation = gr.Chatbot(label='Lucid V5', height=420)
    prompt = gr.Textbox(label='Message Lucid', placeholder='What is on your mind?', max_lines=6)
    send = gr.Button('Send', variant='primary')
    session = gr.State(value=None, time_to_live=3600)
    snapshot = gr.JSON(visible=False)
    inputs, outputs = [prompt, session], [conversation, snapshot, session]
    send.click(chat, inputs, outputs, api_name='chat', concurrency_limit=1)
    prompt.submit(chat, inputs, outputs, api_name=False, concurrency_limit=1)
    # All private reads and mutations authenticate inside the server function.
    admin_password = gr.Textbox(type='password', visible=False)
    admin_token = gr.Textbox(visible=False)
    admin_action = gr.Textbox(visible=False)
    admin_url = gr.Textbox(visible=False)
    admin_result = gr.JSON(visible=False)
    gr.Button(visible=False).click(admin_login, [admin_password], admin_result, api_name='admin_login', queue=False)
    gr.Button(visible=False).click(admin_action_request, [admin_token, admin_action, admin_url], admin_result, api_name='admin_action', queue=False)
    gr.Button(visible=False).click(admin.config, [], admin_result, api_name='hosting_config', queue=False)
demo.queue(max_size=20).launch()
