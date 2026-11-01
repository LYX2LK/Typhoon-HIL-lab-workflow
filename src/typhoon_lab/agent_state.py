"""Shared append-only conversation state and turn-option selection."""
import json
import secrets
from .boost_ai import read
from .boost_agent_tools import digest
from .utils import write_json, now


class PersistentSession:
    def persist(self, event, details):
        with self.guard:
            self.state['revision'] += 1
            write_json(self.root / 'session.json', self.state)
            journal = self.root / 'events.jsonl'
            previous = '0' * 64
            if journal.exists():
                lines = journal.read_text(encoding='utf-8').splitlines()
                if lines:
                    previous = json.loads(lines[-1])['sha256']
            value = {'at': now(), 'revision': self.state['revision'], 'event': event, 'details': details,
                     'state_sha256': digest(self.state), 'previous_sha256': previous}
            value['sha256'] = digest(value)
            with journal.open('a', encoding='utf-8') as handle:
                handle.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n')

    def add(self, role, text='', **values):
        with self.guard:
            message = {'id': secrets.token_hex(8), 'role': role, 'text': text, 'at': now(), **values}
            self.state['messages'].append(message)
            self.persist('message', {'id': message['id'], 'role': role})
            return message['id']

    def tool_status(self, title, status='running', details=None, message_id=None):
        with self.guard:
            if message_id is None:
                return self.add('tool', title, status=status, details=details)
            message = next(x for x in self.state['messages'] if x['id'] == message_id)
            message.update(status=status, details=details)
            self.persist('tool_update', {'id': message_id, 'status': status})

    def _option(self, turn_id, option_id):
        if turn_id != self.state['active_turn']:
            raise ValueError('这组建议已有后续对话，请使用最新选项')
        turn = next(x for x in self.state['turns'] if x['id'] == turn_id)
        question = read(self.root / turn['path'] / 'answer.json').get('question')
        option = next((x for x in question['options'] if x['id'] == option_id), None) if question else None
        if option is None:
            raise ValueError('选项不属于本轮模型回答')
        return turn, option
