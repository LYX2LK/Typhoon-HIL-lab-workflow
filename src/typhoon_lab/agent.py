"""Case-bound conversational Agent, shared persistence, tools and approval workflow."""
from copy import deepcopy
import json
import re
from pathlib import Path
import secrets
import shutil
import threading
from .boost_agent import AgentSession as BoostSession, MAX_RUNS
from .boost_ai import read
from .boost_agent_tools import digest
from .agent_service import api_call
from .agent_cases import BOOST, WAVEFORMS, BRIDGE, case_spec, prepare_waveforms, evidence_for, build_config
from .agent_contract import prompt, numeric_refs, read_tool, report_tool, tool_output, validate_controls
from .agent_render import message_html, export_session, prepare_assets, markdown
from .agent_comparison import comparison, completed_pairs
from .records import verify_run
from .utils import PROJECT, new_run, now, write_json, sha256, runtime_lock, finalize


def analysis_runs(runs, context):
    """Bind a focused turn to the selected records without dropping session data."""
    focus = context.get('focus_run_ids', [])
    if not isinstance(focus, list) or any(not isinstance(rid, str) for rid in focus) or len(set(focus)) != len(focus) or any(rid not in runs for rid in focus):
        raise ValueError('所选波形记录不存在、重复或不可复核')
    if not focus and context.get('intent') in ('inspect_waveform', 'compare_waveforms'):
        raise ValueError('请指定要查看或比较的波形记录')
    if context.get('intent') == 'compare_waveforms' and len(focus) < 2:
        raise ValueError('比较需要至少两条波形记录')
    return {rid: runs[rid] for rid in focus} if focus else runs


class AgentSession(BoostSession):
    def __init__(self, session_dir=None, service_path=None, default_case=BOOST):
        self.guard = threading.RLock()
        self.worker = None
        self.service = Path(service_path or PROJECT / 'configs/ai_service_agent.json')
        self.default_case = case_spec(default_case)['id']
        if session_dir is not None:
            self.root = Path(session_dir).resolve()
            if not self.root.is_relative_to(PROJECT / 'results'):
                raise ValueError('会话必须位于项目results内')
            self.state = read(self.root / 'session.json')
            if self.state.get('kind') != 'agent_session' or self.state.get('schema_version') != 2:
                raise ValueError('不支持该Agent会话版本')
            if self.state.get('busy'):
                raise ValueError('该会话仍在运行，保留现场，不能自动恢复')
            if verify_session(self.root)['record_status'] != 'passed':
                raise ValueError('会话复核失败，不能恢复')
        else:
            self.root = new_run('agent')
            self.state = {'schema_version': 2, 'kind': 'agent_session', 'created_at': now(), 'case_id': None,
                          'busy': False, 'status': 'ready', 'message': '选择案例后发送问题，或开始案例分析。',
                          'messages': [], 'runs': {}, 'turns': [], 'active_turn': None, 'pending': None, 'revision': 0}
            self.persist('session_created', {})

    def snapshot(self):
        with self.guard:
            state = {**deepcopy(self.state), 'session_dir': str(self.root), 'default_case_id': self.default_case}
        for message in state['messages']:
            if message['role'] == 'assistant':
                message['html'] = message_html(self.root, message)
            elif message['role'] == 'draft':
                message['html'] = markdown(message['text'])
        return state

    def export(self):
        with self.guard:
            export_session(self.root, self.state)

    def launch(self, operation, data):
        with self.guard:
            if self.state['busy']:
                raise ValueError('Agent正在处理当前任务，请等待')
            supplied = data.get('case_id')
            if self.state['case_id'] and supplied is not None and supplied != self.state['case_id']:
                raise ValueError('首条消息后案例已锁定，请新建对话选择其他案例')
            if operation == 'start' or (operation == 'say' and not self.state['messages']):
                if self.state['messages'] or self.state['runs'] or self.state['case_id']:
                    raise ValueError('本会话已开始，请继续追问或新建对话')
                spec = case_spec(supplied or self.default_case)
                text = data.get('text') or spec['default_question']
                if not isinstance(text, str) or not text.strip() or len(text) > 4000:
                    raise ValueError('请输入1到4000字的问题')
                self.state['case_id'] = spec['id']
                (self.root / 'task.md').write_text('# ' + spec['title'] + '\n\n' + spec['description'] + '\n\n' + spec['scope'] + '\n', encoding='utf-8')
                write_json(self.root / 'case.json', spec)
                self.state['case_sha256'] = sha256(self.root / 'case.json')
                self.persist('case_bound', {'case_id': spec['id']})
                self.add('user', text)
                job = ('initial', text, None)
            elif self.state['case_id'] == BOOST:
                return super().launch(operation, data)
            elif operation == 'retry':
                if self.state['status'] != 'error':
                    raise ValueError('当前没有失败的分析，请使用最新建议或继续追问')
                latest = self.state['turns'][-1] if self.state['turns'] else None
                if latest and latest['status'] == 'error':
                    if data.get('turn_id') is not None and data['turn_id'] != latest['id']:
                        raise ValueError('该错误已有后续分析，请重试最新失败的问题')
                    path = self.root / latest['path']
                    inp = read(path / 'input.json')
                    if inp['case_id'] != self.state['case_id'] or sha256(path / 'input.json') != read(path / 'manifest.json')['request_sha256']:
                        raise ValueError('原问题记录已变化，不能重试')
                    text, context = inp['user_request'], deepcopy(inp['context'])
                else:
                    text = next(x['text'] for x in reversed(self.state['messages']) if x['role'] == 'user')
                    context = {}
                self.add('user', '重新分析：' + text)
                job = ('analysis', text, context)
            elif operation == 'say':
                text = data.get('text')
                if not isinstance(text, str) or not text.strip() or len(text) > 4000:
                    raise ValueError('请输入1到4000字的追问')
                self.add('user', text)
                job = ('analysis', text, None)
            elif operation == 'choose':
                turn, option = self._option(data.get('turn_id'), data.get('option_id'))
                if option['tool'] == 'run_experiment':
                    return self.prepare_plan(turn, option)
                text = option['arguments'].get('message', '请查看所选波形。')
                context = {'intent': 'conclude' if option['tool'] == 'conclude' else option['tool'],
                           'focus_run_ids': option['arguments'].get('run_ids', list(read(self.root / turn['path'] / 'manifest.json')['run_refs']))}
                if option['tool'] in ('inspect_waveform', 'compare_waveforms'):
                    text = option['label'] + '：' + ', '.join(context['focus_run_ids']) + '。请提供' + ('局部波形。' if option['tool'] == 'inspect_waveform' else '比较图与数值分析。')
                self.add('user', text if option['tool'] in ('inspect_waveform', 'compare_waveforms') else option['label'] + '：' + text)
                job = ('analysis', text, context)
            elif operation == 'confirm':
                job = self.confirm_plan(data)
            else:
                raise ValueError('请先选择案例并开始分析')
            self.state.update(busy=True, status='running', pending=None, active_turn=None, message='Agent正在处理任务')
            self.persist('job_started', {'operation': job[0], 'case_id': self.state['case_id']})
            self.worker = threading.Thread(target=self.work, args=job, daemon=True)
            self.worker.start()
            return {'accepted': True}

    def prepare_plan(self, turn, option):
        if self.state['case_id'] != BRIDGE or len(self.state['runs']) >= MAX_RUNS:
            raise ValueError('当前案例未开放更多实验')
        config, anchor, diff = build_config(BRIDGE, option['arguments'], self.state['runs'], self.root)
        plan_id = secrets.token_hex(8)
        path = self.root / 'plans' / plan_id
        path.mkdir(parents=True)
        write_json(path / 'config.json', config)
        ref = option['arguments']['reference_run']
        plan = {'schema_version': 2, 'case_id': BRIDGE, 'id': plan_id, 'created_at': now(), 'turn_id': turn['id'], 'option': option,
                'answer_sha256': sha256(self.root / turn['path'] / 'answer.json'), 'reference_run': ref,
                'reference_manifest_sha256': sha256(self.root / self.state['runs'][ref]['path'] / 'manifest.json'),
                'config_sha256': sha256(path / 'config.json'), 'anchor_s': anchor, 'differences': diff,
                'confirmation_token': secrets.token_hex(16)}
        write_json(path / 'plan.json', plan)
        self.state['pending'] = plan
        self.persist('option_prepared', {'plan_id': plan_id})
        return {'accepted': True, 'pending': plan}

    def confirm_plan(self, data):
        pending = self.state['pending']
        if not pending or pending['case_id'] != self.state['case_id'] or data.get('approved') is not True or data.get('plan_id') != pending['id']:
            raise ValueError('请先选择当前建议并确认计划')
        if not secrets.compare_digest(str(data.get('token', '')), pending['confirmation_token']):
            raise ValueError('确认标识不匹配')
        operator = data.get('operator')
        if not isinstance(operator, str) or not operator.strip() or len(operator) > 120:
            raise ValueError('请填写实际确认操作者')
        turn, option = self._option(pending['turn_id'], pending['option']['id'])
        path = self.root / 'plans' / pending['id']
        config, anchor, _ = build_config(BRIDGE, option['arguments'], self.state['runs'], self.root)
        ref = self.root / self.state['runs'][pending['reference_run']]['path']
        if read(path / 'plan.json') != pending or pending['option'] != option or read(path / 'config.json') != config or sha256(path / 'config.json') != pending['config_sha256'] or sha256(ref / 'manifest.json') != pending['reference_manifest_sha256'] or sha256(self.root / turn['path'] / 'answer.json') != pending['answer_sha256']:
            raise ValueError('待确认计划或来源记录已变化，请重新选择')
        if verify_run(ref, write=False)['record_status'] != 'passed':
            raise ValueError('来源记录复核失败')
        confirmation = {'at': now(), 'operator': operator, 'plan_sha256': sha256(path / 'plan.json'), 'config_sha256': pending['config_sha256']}
        with (path / 'confirmation.json').open('x', encoding='utf-8') as handle:
            json.dump(confirmation, handle, ensure_ascii=False, indent=2)
        self.add('user', '确认执行“' + option['label'] + '”。', confirmation=confirmation)
        return ('experiment', '请比较新运行与已有记录，更新分析。', {'plan': pending, 'config': config, 'anchor': anchor})

    def run_bridge(self, config, plan=None):
        from .runtime import execute_case
        ui = self.tool_status('Typhoon Virtual HIL：编译、运行并采集整流桥波形')
        with runtime_lock():
            rid = f"R{len(self.state['runs']) + 1:03d}"
            path = self.root / 'runs' / rid
            path.mkdir(parents=True)
            manifest = execute_case(path, config)
        checked = verify_run(path, write=False)
        entry = {'id': rid, 'path': path.relative_to(self.root).as_posix(), 'source_kind': 'virtual_hil',
                 'manifest_sha256': sha256(path / 'manifest.json'), 'record_status': checked['record_status'],
                 'experiment_status': manifest['status'], 'plan_id': plan['id'] if plan else None}
        self.state['runs'][rid] = entry
        self.persist('experiment_finished', entry)
        if plan:
            write_json(self.root / 'plans' / plan['id'] / 'execution.json', entry)
        self.tool_status('', message_id=ui, status='completed' if manifest['status'] != 'error' and checked['record_status'] == 'passed' else 'error', details=entry)
        if manifest['status'] == 'error' or checked['record_status'] != 'passed':
            raise RuntimeError('整流桥执行或记录异常，原始证据已保存')
        return rid

    def work(self, operation, text, context):
        if self.state['case_id'] == BOOST:
            return super().work(operation, text, context)
        try:
            if operation == 'initial':
                if self.state['case_id'] == WAVEFORMS:
                    ui = self.tool_status('导入四组原始波形、固定规则识别并复核')
                    entries = prepare_waveforms(self.root)
                    for entry in entries.values():
                        if verify_run(self.root / entry['path'], write=False)['record_status'] != 'passed':
                            raise ValueError('导入波形复核失败')
                    self.state['runs'].update(entries)
                    self.persist('waveforms_imported', {'records': list(entries)})
                    self.tool_status('', message_id=ui, status='completed')
                else:
                    from .rectifier_fault import configuration, prepare_model
                    prepare_model()
                    for fault in ('none', 'A_upper_open'):
                        self.run_bridge(configuration(fault))
            elif operation == 'experiment':
                self.run_bridge(context['config'], context['plan'])
            self.respond_case(text, context or {})
            self.state.update(status='waiting', message='分析已完成，可选择建议或继续追问。')
        except Exception as exc:
            for message in self.state['messages']:
                if message['role'] == 'tool' and message.get('status') == 'running':
                    message['status'] = 'error'
            latest = self.state['turns'][-1] if self.state['turns'] else None
            self.add('error', str(exc), turn_id=latest['id'] if latest and latest['status'] == 'error' else None)
            self.state.update(status='error', message='本轮中止，原始数据与调用记录已保存，可重新分析。')
        finally:
            with self.guard:
                self.state['busy'] = False
                self.persist('job_finished', {'status': self.state['status']})
            self.export()

    def respond_case(self, text, context):
        case_id = self.state['case_id']
        context = deepcopy(context)
        runs = {rid: entry for rid, entry in self.state['runs'].items() if entry['record_status'] == 'passed' and entry['experiment_status'] != 'error'}
        version = 3 if case_id == WAVEFORMS else 2
        if case_id == WAVEFORMS and not context.get('intent') and re.search('比较|对比|叠加', text):
            ids = list(dict.fromkeys(re.findall(r'(?<![a-z0-9_])tu[1-4](?![a-z0-9_])', text.lower())))
            context.update(intent='compare_waveforms', focus_run_ids=ids or list(runs))
        runs = analysis_runs(runs, context)
        evidence = {rid: evidence_for(case_id, entry, self.root) for rid, entry in runs.items()}
        if not evidence:
            raise ValueError('没有可复核的已有证据；查看数据准备错误记录')
        compared = comparison(evidence) if case_id == WAVEFORMS and context.get('intent') == 'compare_waveforms' else None
        completed = completed_pairs(self.root, self.state['turns'], evidence) if version >= 3 else set()
        if compared:
            completed.update(pair['id'] for pair in compared['pairs'])
        tid = f"T{len(self.state['turns']) + 1:03d}"
        path = self.root / 'turns' / tid
        path.mkdir(parents=True)
        remaining = MAX_RUNS - len(runs) if case_id == BRIDGE else 0
        inp = {'schema_version': 2, 'case_id': case_id, 'user_request': text, 'context': context,
               'history': [{'role': x['role'], 'text': x.get('text') or x.get('answer', {}).get('narrative', '')}
                           for x in self.state['messages'] if x['role'] in ('user', 'assistant')][-12:],
               'evidence_sha256': digest(evidence), 'numeric_refs': numeric_refs(evidence, compared), 'remaining_experiments': remaining}
        if version >= 3:
            inp.update(comparison_sha256=digest(compared) if compared else None, completed_comparison_pairs=sorted(completed))
        write_json(path / 'input.json', inp)
        write_json(path / 'evidence.json', evidence)
        if compared:
            write_json(path / 'comparison.json', compared)
        request_hash = sha256(path / 'input.json')
        manifest = {'kind': 'agent_turn', 'case_id': case_id, 'configuration_schema_version': 2, 'analysis_method_version': 1,
                    'status': 'error', 'started_at': now(), 'request_sha256': request_hash, 'run_refs': deepcopy(runs),
                    'output_contract': f'case_report_v{version}'}
        if version >= 3:
            manifest['evidence_tools_version'] = 2
        turn = {'id': tid, 'path': path.relative_to(self.root).as_posix(), 'status': 'running'}
        self.state['turns'].append(turn)
        self.persist('agent_turn_started', {'id': tid})
        messages = [{'role': 'system', 'content': prompt(case_id, compared, sorted(completed))}, {'role': 'user', 'content': json.dumps(inp, ensure_ascii=False)}]
        calls = []
        narrative = None
        index = 0
        try:
            write_json(path / 'tool_calls.json', calls)
            snapshot = path / 'code_snapshot'
            snapshot.mkdir()
            for source in [*(PROJECT / 'src/typhoon_lab').glob('agent*.py'), PROJECT / 'src/typhoon_lab/rectifier_fault.py', PROJECT / 'src/typhoon_lab/agent_page.html']:
                shutil.copy2(source, snapshot / source.name)
            names = ['read_evidence', 'compare_runs'] if (compared is not None or version < 3 and len(evidence) > 1) else ['read_evidence']
            for name in names:
                index += 1
                definition = read_tool(name, evidence)
                ui = self.tool_status('读取波形证据' if name == 'read_evidence' else '比较已有记录')
                response, finish = api_call(path, index, {'messages': messages, 'tools': [definition], 'tool_choice': {'type': 'function', 'function': {'name': name}}}, self.service)
                tool_calls = response.get('tool_calls') or []
                if finish != 'tool_calls' or len(tool_calls) != 1 or tool_calls[0]['function']['name'] != name:
                    raise ValueError('模型未按只读工具协议提交')
                call = tool_calls[0]
                arguments = json.loads(call['function']['arguments'])
                output = tool_output(name, arguments, case_id, evidence, 2 if version >= 3 else 1)
                if set(arguments.get('run_ids', [])) != set(evidence):
                    raise ValueError('本轮需读取和比较所选记录：' + ', '.join(evidence))
                calls.append({'call_id': call['id'], 'name': name, 'arguments': arguments, 'output': output})
                write_json(path / 'tool_calls.json', calls)
                messages += [{'role': 'assistant', 'content': response.get('content'), 'tool_calls': tool_calls},
                             {'role': 'tool', 'tool_call_id': call['id'], 'content': json.dumps(output, ensure_ascii=False)}]
                self.tool_status('', message_id=ui, status='completed')
            write_json(path / 'tool_calls.json', calls)
            index += 1
            ui = self.tool_status('根据真实证据生成分析正文')
            response, finish = api_call(path, index, {'messages': messages + [{'role': 'user', 'content': '现在仅输出分析正文 Markdown，先给主要发现，再给证据解释和下一步。'}], 'tool_choice': 'none'}, self.service)
            narrative = response.get('content')
            if finish != 'stop' or response.get('tool_calls') or not isinstance(narrative, str) or not narrative.strip():
                raise ValueError('模型分析正文未完整生成')
            (path / 'narrative.md').write_text(narrative, encoding='utf-8')
            manifest['narrative_call_index'] = index
            self.tool_status('', message_id=ui, status='completed')
            messages += [{'role': 'assistant', 'content': narrative}, {'role': 'user', 'content': json.dumps({'stage': 'report_controls', 'narrative_sha256': sha256(path / 'narrative.md'), 'instruction': '调用present_report，逐条分类、复制数值引用，选择图表并提出下一步。'}, ensure_ascii=False)}]
            index += 1
            definition = report_tool(case_id, request_hash, evidence, remaining, context.get('intent') == 'conclude', version, compared, sorted(completed))
            ui = self.tool_status('校验分类、数值引用与案例操作')
            response, finish = api_call(path, index, {'messages': messages, 'tools': [definition], 'tool_choice': {'type': 'function', 'function': {'name': 'present_report'}}}, self.service)
            controls_calls = response.get('tool_calls') or []
            if finish != 'tool_calls' or len(controls_calls) != 1 or controls_calls[0]['function']['name'] != 'present_report':
                raise ValueError('模型未按报告工具协议提交')
            controls = validate_controls(json.loads(controls_calls[0]['function']['arguments']), case_id, request_hash, evidence, remaining, context.get('intent') == 'conclude', version, compared, sorted(completed))
            write_json(path / 'wire_answer.json', controls)
            answer = {'case_id': case_id, 'request_sha256': request_hash, 'narrative': narrative, 'controls': controls, 'question': controls['question']}
            write_json(path / 'answer.json', answer)
            assets = prepare_assets(path, controls, case_id, evidence, runs, self.root)
            write_json(path / 'render_assets.json', assets)
            self.tool_status('', message_id=ui, status='completed')
            manifest.update(status='passed', final_call_index=index, report_call_id=controls_calls[0]['id'])
            turn.update(status='passed', request_sha256=request_hash)
            self.add('assistant', answer=answer, turn_id=tid)
            self.state['active_turn'] = tid if controls['question'] else None
        except Exception as exc:
            if narrative:
                self.add('draft', narrative, turn_id=tid)
            manifest['error'] = {'type': type(exc).__name__, 'message': str(exc)}
            turn['status'] = 'error'
            write_json(path / 'format_error.json', {'category': 'case_report', 'type': type(exc).__name__, 'message': str(exc)})
            raise
        finally:
            finalize(path, manifest)
            self.persist('agent_turn_finished', {'id': tid, 'status': turn['status']})


def open_session(session_dir=None, **kwargs):
    if session_dir is not None and read(Path(session_dir) / 'session.json').get('kind') == 'boost_agent_session':
        return BoostSession(session_dir, kwargs.get('service_path'))
    return AgentSession(session_dir, **kwargs)


def verify_session(root, write=False):
    root = Path(root).resolve()
    state = read(root / 'session.json')
    if state.get('kind') == 'boost_agent_session' or state.get('case_id') == BOOST:
        from .boost_agent import verify_session as boost_verify
        return boost_verify(root, write)
    problems = []
    try:
        if state.get('kind') != 'agent_session' or type(state.get('schema_version')) is not int or state['schema_version'] != 2:
            raise ValueError('unsupported session version')
        case_id = state['case_id']
        if case_id is not None:
            case_spec(case_id)
            if read(root / 'case.json').get('id') != case_id or (state.get('case_sha256') and sha256(root / 'case.json') != state['case_sha256']):
                raise ValueError('case catalog binding differs')
        elif state['messages'] or state['runs'] or state['turns']:
            raise ValueError('unbound session contains work')
        previous = '0' * 64
        last = None
        for line in (root / 'events.jsonl').read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            signature = row.pop('sha256')
            if row['previous_sha256'] != previous or digest(row) != signature:
                raise ValueError('event journal differs')
            previous, last = signature, row
        if last is None or last['state_sha256'] != digest(state):
            raise ValueError('session differs from journal')
        def safe(rel):
            path = (root / rel).resolve()
            if not path.is_relative_to(root):
                raise ValueError('path leaves agent session')
            return path
        evidence = {}
        verified = set()
        for rid, entry in state['runs'].items():
            path = safe(entry['path'])
            if sha256(path / 'manifest.json') != entry['manifest_sha256']:
                raise ValueError('source manifest changed')
            if path not in verified:
                if verify_run(path, write=False)['record_status'] != 'passed':
                    raise ValueError('source verification failed')
                verified.add(path)
            if entry['record_status'] == 'passed' and entry['experiment_status'] != 'error':
                evidence[rid] = evidence_for(case_id, entry, root)
        for turn_index, turn in enumerate(state['turns']):
            path = safe(turn['path'])
            manifest = read(path / 'manifest.json')
            if manifest.get('kind') != 'agent_turn' or manifest.get('case_id') != case_id or manifest.get('record_format_version') != 1 or manifest.get('analysis_method_version') != 1 or manifest.get('output_contract') not in ('case_report_v1', 'case_report_v2', 'case_report_v3'):
                raise ValueError('turn case or version differs')
            if any(x not in manifest.get('artifacts', {}) for x in ('input.json', 'evidence.json')):
                raise ValueError('required turn artifacts missing')
            for rel, expected in manifest['artifacts'].items():
                artifact = (path / rel).resolve()
                if not artifact.is_relative_to(path) or not artifact.is_file() or sha256(artifact) != expected:
                    raise ValueError('turn artifact changed: ' + rel)
            ev = {rid: evidence[rid] for rid in manifest['run_refs']}
            inp = read(path / 'input.json')
            version = int(manifest['output_contract'].rsplit('v', 1)[1])
            compared = None
            completed = set()
            if version >= 3:
                if case_id != WAVEFORMS or manifest.get('evidence_tools_version') != 2:
                    raise ValueError('unsupported comparison protocol')
                compared = comparison(ev) if inp['context'].get('intent') == 'compare_waveforms' else None
                completed = completed_pairs(root, state['turns'][:turn_index], ev)
                if compared:
                    completed.update(pair['id'] for pair in compared['pairs'])
                    if 'comparison.json' not in manifest['artifacts'] or read(path / 'comparison.json') != compared:
                        raise ValueError('recomputed paired comparison differs')
                if inp.get('comparison_sha256') != (digest(compared) if compared else None) or inp.get('completed_comparison_pairs') != sorted(completed):
                    raise ValueError('comparison progress or binding differs')
            if inp['case_id'] != case_id or read(path / 'evidence.json') != ev or inp['evidence_sha256'] != digest(ev) or inp['numeric_refs'] != numeric_refs(ev, compared) or sha256(path / 'input.json') != manifest['request_sha256']:
                raise ValueError('recomputed turn evidence differs')
            for rid, entry in manifest['run_refs'].items():
                if entry != state['runs'][rid]:
                    raise ValueError('turn source reference differs')
            if manifest['status'] == 'passed':
                ni, fi = manifest['narrative_call_index'], manifest['final_call_index']
                required = ['answer.json', 'wire_answer.json', 'narrative.md', 'tool_calls.json', 'render_assets.json',
                            f'call-{ni:02d}.response.json', f'call-{fi:02d}.response.json', f'call-{fi:02d}.request.json']
                if any(x not in manifest['artifacts'] for x in required):
                    raise ValueError('completed turn missing required artifacts')
                narrative = (path / 'narrative.md').read_text(encoding='utf-8')
                nr = read(path / f'call-{ni:02d}.response.json')['choices'][0]
                if nr['finish_reason'] != 'stop' or nr['message'].get('content') != narrative or nr['message'].get('tool_calls'):
                    raise ValueError('narrative differs from actual response')
                conclude = inp['context'].get('intent') == 'conclude'
                controls = validate_controls(read(path / 'wire_answer.json'), case_id, manifest['request_sha256'], ev, inp['remaining_experiments'], conclude, version, compared, sorted(completed))
                actual = read(path / f'call-{fi:02d}.response.json')['choices'][0]
                tc = actual['message'].get('tool_calls') or []
                if actual['finish_reason'] != 'tool_calls' or len(tc) != 1 or tc[0]['id'] != manifest['report_call_id'] or tc[0]['function']['name'] != 'present_report' or json.loads(tc[0]['function']['arguments']) != controls:
                    raise ValueError('controls differ from actual response')
                request = read(path / f'call-{fi:02d}.request.json')
                if request.get('tools') != [report_tool(case_id, manifest['request_sha256'], ev, inp['remaining_experiments'], conclude, version, compared, sorted(completed))] or request.get('tool_choice') != {'type': 'function', 'function': {'name': 'present_report'}}:
                    raise ValueError('strict report schema differs')
                binding = json.loads(request['messages'][-1]['content'])
                if binding.get('narrative_sha256') != sha256(path / 'narrative.md') or request['messages'][-2].get('content') != narrative:
                    raise ValueError('controls are not bound to narrative')
                expected_answer = {'case_id': case_id, 'request_sha256': manifest['request_sha256'], 'narrative': narrative, 'controls': controls, 'question': controls['question']}
                if read(path / 'answer.json') != expected_answer:
                    raise ValueError('answer differs')
                received = {}
                for response_path in path.glob('call-*.response.json'):
                    for call in read(response_path)['choices'][0]['message'].get('tool_calls') or []:
                        received[call['id']] = call['function']
                tools = read(path / 'tool_calls.json')
                required_tools = {'read_evidence', 'compare_runs'} if (compared is not None or version < 3 and len(ev) > 1) else {'read_evidence'}
                if {x['name'] for x in tools} != required_tools:
                    raise ValueError('required evidence tools missing')
                for call in tools:
                    function = received.get(call['call_id'])
                    if function is None or function['name'] != call['name'] or json.loads(function['arguments']) != call['arguments'] or call['output'] != tool_output(call['name'], call['arguments'], case_id, ev, 2 if version >= 3 else 1):
                        raise ValueError('tool invocation or recomputed output differs')
        for path in (root / 'plans').glob('*/plan.json'):
            plan = read(path)
            if plan.get('case_id') != case_id or case_id != BRIDGE:
                raise ValueError('plan case differs')
            turn = next(x for x in state['turns'] if x['id'] == plan['turn_id'])
            answer_path = safe(turn['path']) / 'answer.json'
            option = next(x for x in read(answer_path)['question']['options'] if x['id'] == plan['option']['id'])
            config, _, _ = build_config(case_id, option['arguments'], state['runs'], root)
            if option != plan['option'] or sha256(answer_path) != plan['answer_sha256'] or read(path.parent / 'config.json') != config or sha256(path.parent / 'config.json') != plan['config_sha256'] or sha256(safe(state['runs'][plan['reference_run']]['path']) / 'manifest.json') != plan['reference_manifest_sha256']:
                raise ValueError('plan binding differs')
            if (path.parent / 'confirmation.json').exists():
                confirmation = read(path.parent / 'confirmation.json')
                if confirmation['plan_sha256'] != sha256(path) or confirmation['config_sha256'] != plan['config_sha256']:
                    raise ValueError('confirmation changed')
                if (path.parent / 'execution.json').exists():
                    execution = read(path.parent / 'execution.json')
                    if state['runs'].get(execution['id']) != execution or sha256(safe(execution['path']) / 'config.json') != confirmation['config_sha256']:
                        raise ValueError('execution differs from confirmation')
                elif not state['busy']:
                    problems.append('confirmed experiment has no execution record')
        for message in state['messages']:
            if message['role'] == 'assistant' and message['answer'] != read(safe('turns/' + message['turn_id']) / 'answer.json'):
                raise ValueError('displayed answer differs from saved model answer')
        if (root / 'export_manifest.json').exists():
            export = read(root / 'export_manifest.json')
            if export['report_sha256'] != sha256(root / 'report.html') or export.get('case_id') != case_id:
                raise ValueError('export differs')
    except Exception as exc:
        problems.append(type(exc).__name__ + ': ' + str(exc))
    result = {'checked_at': now(), 'status': 'failed' if problems else 'passed', 'record_status': 'failed' if problems else 'passed',
              'experiment_status': None, 'case_id': state.get('case_id'), 'problems': problems, 'run_count': len(state.get('runs', {})),
              'model_turn_count': len(state.get('turns', [])), 'run_dir': str(root)}
    if write:
        write_json(root / 'verification.json', result)
    return result
