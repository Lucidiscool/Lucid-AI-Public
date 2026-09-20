"""Ephemeral English fact sandbox. Never calls the pretrained model."""
import re


class BlankExperiment:
    def __init__(self):
        self.facts = {}

    @staticmethod
    def subject(text):
        text = re.sub(r'^(?:a|an|the)\s+', '', text.strip().lower())
        return {'you': 'assistant', 'i': 'user', 'me': 'user'}.get(text, text)

    @staticmethod
    def value(text):
        return re.sub(r'^(?:a|an|the)\s+', '', text.strip().lower().rstrip('.!?'))

    def reply(self, message):
        text = message.strip().rstrip('.!')
        if text.lower() in ('hi', 'hello', 'hey'):
            return 'Hello.'
        question = re.fullmatch(r'(?:are|is|am)\s+(.+?)\??', text, re.I)
        if question:
            body = question[1].lower().rstrip('?')
            subjects = {'you': 'assistant', 'i': 'user', **{s: s for s in self.facts},
                        **{'the ' + s: s for s in self.facts}}
            for phrase in sorted(subjects, key=len, reverse=True):
                if body.startswith(phrase + ' '):
                    value = self.value(body[len(phrase):])
                    if value in self.facts.get(subjects[phrase], []):
                        return 'Yes, according to what you taught me in this experiment.'
            return "I don't know."
        question = re.fullmatch(r'(?:what|who)(?:\s+\w+)?\s+(?:are|is|am)\s+(.+?)\??', text, re.I)
        if question:
            known = self.facts.get(self.subject(question[1].rstrip('?')), [])
            return '; '.join(known) if known else "I don't know."
        # Declarative statements are the only source of facts.
        text = re.sub(r'^yes[, ]+\s*', '', text, flags=re.I)
        statement = re.fullmatch(r'(.+?)\s+(?:is|are|am)\s+([^?]+)', text, re.I)
        if statement and not re.match(r'^(?:what|who|why|how|when|where)\b', text, re.I):
            subject, value = self.subject(statement[1]), self.value(statement[2])
            if len(subject) > 100 or len(value) > 500 or len(self.facts) >= 100:
                return 'That is too much for this small experiment.'
            values = self.facts.setdefault(subject, [])
            if value not in values:
                values.append(value)
            return 'Learned for this experiment: ' + subject + ' is ' + value + '.'
        return "I don't know. Teach me with a statement such as 'the sky is blue'."
