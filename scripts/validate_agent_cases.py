"""Resumable real API/Virtual HIL acceptance. Approvals explicitly identify automation."""
import argparse
import json
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from typhoon_lab.agent import AgentSession, open_session, verify_session
from typhoon_lab.agent_cases import BOOST, WAVEFORMS, BRIDGE
from typhoon_lab.boost_ai import read
from typhoon_lab.utils import PROJECT, write_json

INDEX = PROJECT / 'results/agent-tasks/20261101-three-cases/acceptance.json'


def wait(session):
    started = time.monotonic()
    last = -20
    while session.state['busy']:
        elapsed = time.monotonic() - started
        if elapsed - last >= 15:
            print(session.state['case_id'], int(elapsed), session.state['messages'][-1].get('text', ''), flush=True)
            last = elapsed
        time.sleep(.5)
    # Worker exports after releasing busy; join before recording final verification.
    if session.worker:
        session.worker.join(30)
    if session.state['status'] == 'error':
        raise RuntimeError(session.state['messages'][-1].get('text', 'Agent error'))


def accept(case_id):
    index = read(INDEX) if INDEX.exists() else {'schema_version': 1, 'cases': {}}
    entry = index['cases'].get(case_id)
    session = open_session(entry['session_dir']) if entry else AgentSession(default_case=case_id)
    if entry is None:
        entry = {'session_dir': str(session.root), 'initial': False, 'followup': False, 'control': False}
        index['cases'][case_id] = entry
        write_json(INDEX, index)
    print('SESSION', session.root, flush=True)
    if not entry['initial']:
        if session.state['runs']:
            session.launch('retry', {})
        else:
            session.launch('start', {'case_id': case_id})
        wait(session)
        entry['initial'] = True
        write_json(INDEX, index)
    if not entry['followup']:
        text = '请先展示对照波形，再列出最关键的量化证据，最后说明当前结果能支持到什么程度，以及下一步怎样验证。'
        session.launch('say', {'text': text})
        wait(session)
        entry['followup'] = True
        write_json(INDEX, index)
    if case_id != WAVEFORMS and not entry['control']:
        turn = next(x for x in reversed(session.state['turns']) if x['status'] == 'passed')
        options = read(session.root / turn['path'] / 'answer.json')['question']['options']
        candidates = [x for x in options if x['tool'] == 'run_experiment']
        if not candidates:
            session.launch('say', {'text': '请提出一个当前工具支持、可经确认执行的对照实验选项。'})
            wait(session)
            turn = next(x for x in reversed(session.state['turns']) if x['status'] == 'passed')
            candidates = [x for x in read(session.root / turn['path'] / 'answer.json')['question']['options'] if x['tool'] == 'run_experiment']
        if not candidates:
            raise RuntimeError('model did not offer a supported experiment')
        choice = next((x for x in candidates if x['arguments']['operation'] in ('delay_event', 'baseline')), candidates[0])
        session.launch('choose', {'turn_id': turn['id'], 'option_id': choice['id']})
        pending = session.state['pending']
        session.launch('confirm', {'plan_id': pending['id'], 'token': pending['confirmation_token'], 'approved': True,
                                  'operator': 'Codex 自动化验收（用户实施与验收授权）'})
        wait(session)
        entry['control'] = True
        write_json(INDEX, index)
    session.export()
    result = verify_session(session.root, write=True)
    entry.update(verification=result, report=str(session.root / 'report.html'), completed=result['record_status'] == 'passed')
    write_json(INDEX, index)
    print(json.dumps(entry, ensure_ascii=False), flush=True)
    if not entry['completed']:
        raise RuntimeError('final verification failed')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--case', choices=[BOOST, WAVEFORMS, BRIDGE], required=True)
    accept(p.parse_args().case)
