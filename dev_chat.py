"""LucidAI V5 developer console with isolated experimental state."""
import argparse
import json
import sys
import time
import uuid
from local_chat import Backend, ROOT, SYSTEM
from chat_store import ChatStore
from chat_automation import decide
from blank_experiment import BlankExperiment

HELP = '''LucidAI V5 developer commands
  /help                       Show this command list
  /think [on|off]              Toggle readable action/decision summaries
  /forget [on|off]             Toggle a blank, temporary fact experiment
  /facts                      Show facts learned in the experiment
  /teach STATEMENT            Teach a fact in the experiment
  /reset                      Clear experimental facts
  /search TOPIC               Force web search (normal mode)
  /research TOPIC             Multi-source research (normal mode)
  /auto-memory on|off          Enable/disable automatic memory
  /auto-web on|off             Enable/disable automatic search
  /remember TEXT              Save normal long-term memory
  /memories                   List normal saved memories
  /forget ID | /forget all     Delete normal saved memory (not a mode toggle)
  /good [NOTE] | /bad [NOTE]   Rate the latest normal reply
  /correct ANSWER             Save a preferred answer
  /feedback | /unrate          Review/remove feedback
  /new                        New normal chat, or reset experiment
  /chats | /load ID            List/resume normal saved chats
  /load latest                Resume latest normal chat
  /history | /save             View/save normal conversation
  /temperature 0..2            Sampling temperature for normal replies
  /tokens 32..4096             Maximum reply length
  /system [TEXT|reset]         Show/change/reset your normal system prompt
  /settings | /model | /stats Show configuration and session timings
  /quit                       Exit
Blank mode is a fictional fact sandbox, not erased model weights. It uses
simple English patterns, no Qwen, no web, and no normal memory. Leaving it
discards its facts. /think shows concise process summaries, not hidden thoughts.
'''


class DeveloperChat:
    def __init__(self, root=ROOT, backend=None, output=print):
        self.root = root
        self.store = ChatStore(root / 'personal')
        self.backend = backend
        self.output = output
        self.history = []
        self.identifier = 'chat-' + uuid.uuid4().hex
        self.blank = None
        saved = self.store.read('runtime-settings.json', {})
        self.think = saved.get('think') is True
        self.temperature = saved.get('temperature', 0.6)
        self.tokens = saved.get('tokens', 768)
        self.system = saved.get('system', SYSTEM)
        if type(self.temperature) not in (int, float) or not 0 <= self.temperature <= 2:
            self.temperature = 0.6
        if type(self.tokens) is not int or not 32 <= self.tokens <= 4096:
            self.tokens = 768
        if not isinstance(self.system, str) or len(self.system) > 4000:
            self.system = SYSTEM
        self.turns = 0
        self.last_seconds = 0
        self.stream = None

    def trace(self, text):
        if self.think:
            self.output('[Process summary] ' + text)

    def save_runtime_settings(self):
        self.store.write('runtime-settings.json', {'think': self.think,
            'temperature': self.temperature, 'tokens': self.tokens, 'system': self.system})

    def engine(self):
        if self.backend is None:
            self.backend = Backend()
        self.backend.start()
        return self.backend

    @staticmethod
    def toggle(current, argument):
        if argument not in ('', 'on', 'off'):
            raise ValueError('Use on or off, or leave it blank to toggle.')
        return not current if not argument else argument == 'on'

    def handle(self, prompt):
        prompt = prompt.strip()
        command, _, argument = prompt.partition(' ')
        argument = argument.strip()
        if not prompt:
            return True
        if command == '/quit':
            self.blank = None
            return False
        if command == '/help':
            self.output(HELP)
            return True
        if command == '/think':
            self.think = self.toggle(self.think, argument)
            self.save_runtime_settings()
            self.output('Readable process summaries: ' + ('on' if self.think else 'off'))
            return True
        if command == '/forget' and argument in ('', 'on', 'off'):
            enabled = self.toggle(self.blank is not None, argument)
            if enabled and self.blank is None:
                self.blank = BlankExperiment()
                self.output('EXPERIMENT ON: temporary fictional facts only. Normal chat is paused. No pretrained model or internet is used.')
            elif not enabled:
                self.blank = None
                self.output('EXPERIMENT OFF: temporary facts discarded. Normal chat and memory restored.')
            return True
        if self.blank is not None:
            if command in ('/reset', '/new'):
                self.blank = BlankExperiment()
                self.output('Experimental facts cleared.')
            elif command == '/facts':
                self.output(json.dumps(self.blank.facts, indent=2) if self.blank.facts else 'No experimental facts.')
            elif command.startswith('/') and command != '/teach':
                self.output('This command is unavailable in the experiment. Use /forget off to return to normal chat.')
            else:
                self.trace('Matching the English question against only facts taught in this experiment; no model call or saved memory.')
                self.output('Experiment: ' + self.blank.reply(argument if command == '/teach' else prompt))
            return True
        if command in ('/facts', '/teach', '/reset'):
            raise ValueError('Use /forget on to enter the experimental mode first.')
        if command == '/settings':
            self.output(json.dumps(dict(self.store.settings(), think=self.think, temperature=self.temperature, max_tokens=self.tokens), indent=2))
        elif command == '/model':
            self.output((self.root / 'local_model.json').read_text())
        elif command == '/stats':
            self.output(f'Normal replies this session: {self.turns}; latest reply: {self.last_seconds:.2f}s; saved turns: {len(self.history)//2}')
        elif command == '/temperature':
            value = float(argument)
            if not 0 <= value <= 2:
                raise ValueError('Temperature must be 0–2.')
            self.temperature = value
            self.save_runtime_settings()
            self.output(f'Temperature: {value}')
        elif command == '/tokens':
            value = int(argument)
            if not 32 <= value <= 4096:
                raise ValueError('Tokens must be 32–4096.')
            self.tokens = value
            self.save_runtime_settings()
            self.output(f'Maximum new tokens: {value}')
        elif command == '/system':
            if argument:
                if len(argument) > 4000:
                    raise ValueError('System prompt limit is 4000 characters.')
                self.system = SYSTEM if argument == 'reset' else argument
                self.save_runtime_settings()
            self.output(self.system)
        elif command in ('/auto-memory', '/auto-web'):
            if argument not in ('on', 'off'):
                raise ValueError('Use on or off.')
            self.store.set_setting(command[1:].replace('-', '_'), argument == 'on')
            self.output(command[1:] + ': ' + argument)
        elif command == '/remember':
            self.output(self.store.remember(argument))
        elif command == '/memories':
            self.output('\n'.join(f"{m['id']}: {m['text']}" for m in self.store.memories()) or 'No saved memories.')
        elif command == '/forget':
            self.store.forget(argument)
            self.output('Saved memory removed. Old transcripts are unchanged.')
        elif command == '/new':
            self.identifier, self.history = 'chat-' + uuid.uuid4().hex, []
            self.store.activate(self.identifier)
            self.output('New normal chat.')
        elif command == '/chats':
            self.output('\n'.join(f'{i}: {title}' for i, title in self.store.chats()) or 'No saved chats.')
        elif command == '/load':
            self.identifier, self.history = self.store.load(argument)
            self.store.activate(self.identifier)
            self.output('Loaded: ' + self.identifier)
        elif command == '/history':
            for message in self.history:
                self.output(message['role'] + ': ' + message['content'])
        elif command == '/save':
            self.store.save(self.identifier, self.history)
            self.output('Saved: ' + self.identifier)
        elif command in ('/good', '/bad', '/correct'):
            self.store.rate(self.identifier, self.history, command[1:], argument)
            self.output('Feedback saved; model weights unchanged.')
        elif command == '/unrate':
            self.store.unrate(self.identifier, self.history)
            self.output('Latest rating removed.')
        elif command == '/feedback':
            self.output(json.dumps(self.store.feedback()[-10:], indent=2))
        elif command in ('/search', '/research') or not command.startswith('/'):
            engine = self.engine()
            started = time.monotonic()
            forced = command in ('/search', '/research')
            decision = {'search': '', 'memories': []}
            if not forced:
                self.trace('Locally checking this message for useful lasting facts and need for fresh web information.')
                try:
                    decision = decide(engine, prompt, self.store.settings())
                except (ValueError, RuntimeError, OSError) as error:
                    self.output('[Auto] Decision unavailable; answering without automatic actions.')
                for item in decision['memories']:
                    notice = self.store.auto_remember(item['key'], item['text'])
                    if notice:
                        self.output('[Memory] ' + notice)
            query = argument if forced else decision['search']
            if query or forced:
                from web_research import Research
                self.trace('Using web sources because search was requested or current information may help. Query: ' + query)
                answer = Research(engine, self.root / 'personal/research', self.output).run(query, deep=command == '/research')
            else:
                self.trace(f'Answering locally with {len(self.history)//2} conversation turns and {len(self.store.memories())} saved facts; temperature {self.temperature}, token limit {self.tokens}.')
                options = {'max_tokens': self.tokens, 'temperature': self.temperature, 'display': False}
                if self.stream:
                    options['on_token'] = self.stream
                response = engine.answer([{'role': 'system', 'content': self.store.system(self.system) + self.store.feedback_context(prompt)}] + self.history + [{'role': 'user', 'content': prompt}], **options)
                answer = response[-1]['content']
            self.history += [{'role': 'user', 'content': prompt}, {'role': 'assistant', 'content': answer}]
            self.store.save(self.identifier, self.history)
            self.last_seconds = time.monotonic() - started
            self.turns += 1
            self.output('LucidAI V5: ' + answer)
            self.trace(f'Finished in {self.last_seconds:.2f} seconds. Conversation saved locally; model weights unchanged.')
        else:
            self.output('Unknown command. Type /help to see all commands.')
        return True


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prompt')
    parser.add_argument('--resume', nargs='?', const='latest')
    parser.add_argument('--forget', action='store_true', help='Start the isolated blank experiment')
    args = parser.parse_args()
    app = DeveloperChat()
    print('LucidAI V5 — Developer Edition\nType /help to see all commands.\n')
    try:
        if args.resume:
            app.handle('/load ' + args.resume)
        if args.forget:
            app.handle('/forget on')
        while True:
            try:
                prompt = args.prompt if args.prompt is not None else input('Experiment> ' if app.blank else 'You> ')
                if not app.handle(prompt) or args.prompt is not None:
                    break
            except Exception as error:
                print('Error:', error)
                if args.prompt is not None:
                    return 1
    except (EOFError, KeyboardInterrupt):
        print('\nClosed; experimental facts discarded.')
    finally:
        app.blank = None
        if app.backend is not None:
            app.backend.client.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
