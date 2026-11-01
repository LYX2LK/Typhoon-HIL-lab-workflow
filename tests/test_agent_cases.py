"""Behavioral coverage for case isolation, raw evidence, approvals and saved provenance."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from typhoon_lab import agent
from typhoon_lab.agent_cases import BOOST, WAVEFORMS, BRIDGE, catalog, prepare_waveforms, evidence_for, build_config
from typhoon_lab.agent_contract import numeric_refs, validate_controls, report_tool
from typhoon_lab.agent_comparison import comparison, comparison_scopes, pair_id
from typhoon_lab.rectifier_fault import configuration, BridgeAdapter, ideal_reference, analyze_bridge, COLUMNS
from typhoon_lab.utils import PROJECT, write_json, sha256, finalize
from typhoon_lab.boost_ai import read


class CaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory(dir=PROJECT / 'results', prefix='agent-test-fixture-')
        cls.entries = prepare_waveforms(Path(cls.fixture.name))

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=PROJECT / 'results', prefix='agent-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        with patch.object(agent, 'new_run', return_value=self.root):
            self.session = agent.AgentSession()

    def populate(self):
        shutil.copytree(Path(self.fixture.name) / 'data', self.root / 'data')
        self.session.state.update(case_id=WAVEFORMS, runs=deepcopy(self.entries))
        write_json(self.root / 'case.json', next(x for x in catalog() if x['id'] == WAVEFORMS))
        self.session.add('user', '导入并分析示例波形')
        self.session.persist('fixture', {})
        self.session.export()
        return {rid: evidence_for(WAVEFORMS, entry, self.root) for rid, entry in self.entries.items()}

    def controls(self, evidence, request_hash='hash'):
        refs = numeric_refs(evidence)
        return {'request_sha256': request_hash, 'diagnoses': [
            {'run_id': rid, 'classification': e['classification'],
             'facts': [{'ref': key, 'value': refs[key]}]} for rid, e in evidence.items()
            for key in [next(x for x in refs if x.startswith(rid + '.'))]],
            'views': [{'type': 'metrics', 'title': '复算指标', 'run_ids': list(evidence), 'view': 'full'},
                      {'type': 'analysis', 'title': '解释', 'run_ids': list(evidence), 'view': 'full'}],
            'question': {'title': '接下来查看什么？', 'options': [
                {'id': 'compare', 'label': '比较跌落波形', 'description': '查看 tu1 与 tu2 的量化差异。', 'recommended': True,
                 'tool': 'compare_waveforms' if len(evidence) > 1 else 'inspect_waveform', 'arguments': {'run_ids': list(evidence)[:2]}},
                {'id': 'inspect', 'label': '查看异常局部', 'description': '查看所选记录的原始局部波形。', 'recommended': False,
                 'tool': 'inspect_waveform', 'arguments': {'run_ids': [rid for rid, e in evidence.items() if e['classification'] == 'abnormal'] or list(evidence)[:1]}},
                {'id': 'discuss', 'label': '继续讨论', 'description': '讨论测点确认需要哪些信息。', 'recommended': False,
                 'tool': 'discuss', 'arguments': {'message': '需要补充哪些测点信息？'}},
                {'id': 'conclude', 'label': '总结所选记录', 'description': '整理当前记录的发现与限制。', 'recommended': False,
                 'tool': 'conclude', 'arguments': {'message': '请总结当前所选记录。'}}]}}

    def fake_api(self, path, index, payload, service):
        write_json(path / f'call-{index:02d}.request.json', payload)
        evidence = read(path / 'evidence.json')
        context = read(path / 'input.json')['context']
        compared = read(path / 'comparison.json') if (path / 'comparison.json').exists() else None
        if payload.get('tool_choice') == 'none':
            message, finish = {'content': '## 观察\n\n本轮查看 ' + '、'.join(evidence) + '。具体原因需要确认测点。'}, 'stop'
        else:
            name = payload['tool_choice']['function']['name']
            args = self.controls(evidence, sha256(path / 'input.json')) if name == 'present_report' else {'run_ids': list(evidence)}
            if name == 'present_report' and 'comparison_facts' in payload['tools'][0]['function']['parameters']['properties']:
                args = self.modern_controls(evidence, sha256(path / 'input.json'), compared,
                                            read(path / 'input.json')['completed_comparison_pairs'])
            if name == 'present_report' and context.get('intent') == 'inspect_waveform':
                args['views'].insert(0, {'type': 'waveform', 'title': '所选局部波形', 'run_ids': list(evidence), 'view': 'detail'})
            if name == 'present_report' and context.get('intent') == 'conclude':
                args['question'] = None
            message, finish = {'content': None, 'tool_calls': [{'id': 'call-' + str(index), 'type': 'function',
                                      'function': {'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}}]}, 'tool_calls'
        write_json(path / f'call-{index:02d}.response.json', {'choices': [{'message': message, 'finish_reason': finish}]})
        return message, finish

    def modern_controls(self, evidence, request_hash, compared=None, completed=()):
        args = self.controls(evidence, request_hash)
        args['comparison_facts'] = []
        scopes = comparison_scopes(evidence, completed)
        args['question']['options'] = [o for o in args['question']['options']
                                      if o['tool'] != 'compare_waveforms' or sorted(o['arguments']['run_ids']) in scopes]
        if compared:
            refs = numeric_refs(evidence, compared)
            args['comparison_facts'] = [{'ref': key, 'value': refs[key]} for key in refs if key.endswith('max_deviation_V.delta')]
            args['views'] = [{'type': 'waveform', 'title': '/'.join(p['run_ids']), 'run_ids': p['run_ids'], 'view': 'detail'}
                             for p in compared['pairs']] + [
                {'type': 'comparison', 'title': '配对指标差异', 'run_ids': list(evidence), 'view': 'full'},
                {'type': 'analysis', 'title': '比较解释', 'run_ids': list(evidence), 'view': 'full'}]
        return args

    def test_catalog_has_exactly_three_case_choices(self):
        self.assertEqual([x['id'] for x in catalog()], [BOOST, WAVEFORMS, BRIDGE])
        self.assertEqual(self.session.snapshot()['case_id'], None)
        self.assertEqual(agent.verify_session(self.root)['record_status'], 'passed')

    def test_first_message_starts_and_binds_selected_case_without_extra_start_click(self):
        with patch.object(self.session, 'work') as work:
            self.session.launch('say', {'case_id': WAVEFORMS, 'text': '先比较异常位置'})
            self.session.worker.join()
        self.assertEqual(self.session.state['case_id'], WAVEFORMS)
        self.assertEqual(self.session.state['messages'][0]['text'], '先比较异常位置')
        work.assert_called_once_with('initial', '先比较异常位置', None)
        self.session.state['busy'] = False
        with self.assertRaises(ValueError):
            self.session.launch('start', {'case_id': BRIDGE})
        with self.assertRaises(ValueError):
            self.session.launch('say', {'case_id': BRIDGE, 'text': '更换案例'})

    def test_invalid_initial_case_or_text_does_not_bind_session(self):
        for data in ({'case_id': 'shell'}, {'case_id': WAVEFORMS, 'text': 7}, {'case_id': WAVEFORMS, 'text': ' ' * 5}):
            with self.assertRaises(ValueError):
                self.session.launch('start', data)
            self.assertIsNone(self.session.state['case_id'])

    def test_raw_grid_counts_classification_and_reference_label_separation(self):
        evidence = self.populate()
        self.assertEqual([x['classification'] for x in evidence.values()], ['normal', 'abnormal', 'normal', 'abnormal'])
        self.assertEqual([x['sample_count'] for x in evidence.values()], [99999, 100000, 20000, 10000])
        for rid, item in evidence.items():
            self.assertAlmostEqual(item['metrics']['dt_s'], 5e-9, places=17)
            self.assertNotIn('expected', json.dumps(item))
        self.assertEqual(agent.verify_session(self.root)['record_status'], 'passed')

    def test_control_rejects_false_classification_fabricated_number_or_cross_record_ref(self):
        evidence = self.populate()
        good = self.controls(evidence)
        for mutate in (lambda x: x['diagnoses'][0].update(classification='abnormal'),
                       lambda x: x['diagnoses'][0]['facts'][0].update(value=9e9),
                       lambda x: x['diagnoses'][0]['facts'][0].update(ref='tu2.metrics.raw_min'),
                       lambda x: x['views'][0].update(run_ids=['R001']),
                       lambda x: x['question']['options'][0].update(tool='run_experiment')):
            bad = deepcopy(good)
            mutate(bad)
            with self.assertRaises(ValueError):
                validate_controls(bad, WAVEFORMS, 'hash', evidence, 0)
        validate_controls(good, WAVEFORMS, 'hash', evidence, 0)

    def test_waveforms_have_no_experiment_capability(self):
        evidence = self.populate()
        schema = json.dumps(report_tool(WAVEFORMS, 'hash', evidence, 0))
        self.assertNotIn('run_experiment', schema)
        with self.assertRaises(ValueError):
            build_config(WAVEFORMS, {'operation': 'baseline', 'reference_run': 'tu1'}, self.entries, self.root)

    def test_saved_model_turn_recomputes_and_exports_inline_report(self):
        self.populate()
        with patch.object(agent, 'api_call', side_effect=self.fake_api):
            self.session.launch('say', {'text': '请分析全部波形'})
            self.session.worker.join(30)
        self.assertFalse(self.session.state['busy'])
        self.assertEqual(self.session.state['turns'][-1]['status'], 'passed')
        self.assertEqual(agent.verify_session(self.root)['problems'], [])
        self.assertIn('示例波形', (self.root / 'report.html').read_text(encoding='utf-8'))
        resumed = agent.open_session(self.root)
        self.assertEqual(resumed.state['case_id'], WAVEFORMS)
        self.assertIn('html', next(x for x in resumed.snapshot()['messages'] if x['role'] == 'assistant'))

    def test_changed_raw_file_fails_reverification(self):
        self.populate()
        path = self.root / self.entries['tu1']['path'] / 'source/inputs/tu1/csv.csv'
        path.write_bytes(path.read_bytes() + b'\n')
        self.assertEqual(agent.verify_session(self.root)['record_status'], 'failed')

    def test_model_failure_preserves_data_and_retry_does_not_import_again(self):
        self.populate()
        before = {rid: evidence_for(WAVEFORMS, entry, self.root)['source_csv_sha256'] for rid, entry in self.entries.items()}
        with patch.object(agent, 'api_call', side_effect=RuntimeError('injected API failure')):
            self.session.launch('say', {'text': '分析'})
            self.session.worker.join(30)
        self.assertEqual(self.session.state['status'], 'error')
        with patch.object(agent, 'api_call', side_effect=self.fake_api), patch.object(agent, 'prepare_waveforms') as prepare:
            self.session.launch('retry', {})
            self.session.worker.join(30)
            prepare.assert_not_called()
        self.assertEqual(self.session.state['status'], 'waiting')
        self.assertEqual(before, {rid: evidence_for(WAVEFORMS, entry, self.root)['source_csv_sha256'] for rid, entry in self.entries.items()})
        self.assertEqual(agent.verify_session(self.root)['problems'], [])

    def test_selected_pair_and_local_followup_use_only_selected_evidence(self):
        self.populate()
        with patch.object(agent, 'api_call', side_effect=self.fake_api):
            self.session.launch('say', {'text': '分析全部波形'})
            self.session.worker.join(30)
            for option_id, expected in [('compare', ['tu1', 'tu2']), ('inspect', ['tu2'])]:
                turn_id = self.session.state['active_turn']
                self.session.launch('choose', {'turn_id': turn_id, 'option_id': option_id})
                self.session.worker.join(30)
                turn = self.session.state['turns'][-1]
                self.assertEqual(turn['status'], 'passed', self.session.state['messages'][-1])
                path = self.root / turn['path']
                self.assertEqual(list(read(path / 'evidence.json')), expected)
                self.assertEqual(list(read(path / 'manifest.json')['run_refs']), expected)
                tools = read(path / 'tool_calls.json')
                self.assertEqual([call['name'] for call in tools], ['read_evidence', 'compare_runs'] if len(expected) > 1 else ['read_evidence'])
                self.assertTrue(all(call['arguments']['run_ids'] == expected for call in tools))
            self.assertTrue(list(path.glob('waveform-*.png')))
            self.assertEqual(list(self.session.state['runs']), ['tu1', 'tu2', 'tu3', 'tu4'])
            self.assertEqual(agent.verify_session(self.root)['problems'], [])

    def test_local_abnormal_pair_retries_original_request_after_reopening(self):
        self.populate()
        with patch.object(agent, 'api_call', side_effect=self.fake_api):
            self.session.launch('say', {'text': '分析全部波形'})
            self.session.worker.join(30)
        # Historical failed turns saved all four records even for a focused request.
        with patch.object(agent, 'api_call', side_effect=RuntimeError('injected focused API failure')), patch.object(agent, 'analysis_runs', side_effect=lambda runs, context: runs):
            self.session.launch('choose', {'turn_id': self.session.state['active_turn'], 'option_id': 'inspect'})
            self.session.worker.join(30)
        failed = self.session.state['turns'][-1]
        original = read(self.root / failed['path'] / 'input.json')
        self.assertEqual(list(read(self.root / failed['path'] / 'evidence.json')), ['tu1', 'tu2', 'tu3', 'tu4'])
        self.assertEqual(original['context']['focus_run_ids'], ['tu2', 'tu4'])
        resumed = agent.open_session(self.root)
        with patch.object(agent, 'api_call', side_effect=self.fake_api), patch.object(agent, 'prepare_waveforms') as prepare, patch.object(resumed, 'run_bridge') as run:
            resumed.launch('retry', {'turn_id': failed['id']})
            resumed.worker.join(30)
            prepare.assert_not_called()
            run.assert_not_called()
        turn = resumed.state['turns'][-1]
        retried = read(self.root / turn['path'] / 'input.json')
        self.assertEqual(turn['status'], 'passed', resumed.state['messages'][-1])
        self.assertEqual(retried['user_request'], original['user_request'])
        self.assertEqual(retried['context'], original['context'])
        self.assertEqual(list(read(self.root / turn['path'] / 'evidence.json')), ['tu2', 'tu4'])
        self.assertIn('data:image/png;base64,', (self.root / 'report.html').read_text(encoding='utf-8'))
        self.assertEqual(agent.verify_session(self.root)['problems'], [])
        with self.assertRaises(ValueError):
            resumed.launch('retry', {'turn_id': failed['id']})

    def test_focused_discussion_and_conclusion_keep_previous_selection(self):
        self.populate()
        with patch.object(agent, 'api_call', side_effect=self.fake_api):
            self.session.launch('say', {'text': '分析全部波形'})
            self.session.worker.join(30)
            for option_id in ['inspect', 'discuss', 'conclude']:
                self.session.launch('choose', {'turn_id': self.session.state['active_turn'], 'option_id': option_id})
                self.session.worker.join(30)
                turn = self.session.state['turns'][-1]
                self.assertEqual(turn['status'], 'passed', self.session.state['messages'][-1])
                self.assertEqual(list(read(self.root / turn['path'] / 'evidence.json')), ['tu2', 'tu4'])
        self.assertIsNone(self.session.state['messages'][-1]['answer']['question'])
        self.assertEqual(agent.verify_session(self.root)['problems'], [])

    def test_focus_rejects_missing_duplicate_or_cross_case_records(self):
        runs = {rid: {} for rid in ['tu1', 'tu2', 'tu3', 'tu4']}
        for focus in ([], ['R001'], ['tu2', 'tu2'], ['tu2', 7], 'tu2'):
            with self.subTest(focus=focus), self.assertRaises(ValueError):
                agent.analysis_runs(runs, {'intent': 'inspect_waveform', 'focus_run_ids': focus})
        with self.assertRaises(ValueError):
            agent.analysis_runs(runs, {'intent': 'compare_waveforms', 'focus_run_ids': ['tu2']})

    def test_model_cannot_read_outside_focused_selection(self):
        self.populate()
        def wrong_api(path, index, payload, service):
            message, finish = self.fake_api(path, index, payload, service)
            if index == 1:
                message['tool_calls'][0]['function']['arguments'] = json.dumps({'run_ids': ['tu1', 'tu2', 'tu3', 'tu4']})
                write_json(path / f'call-{index:02d}.response.json', {'choices': [{'message': message, 'finish_reason': finish}]})
            return message, finish
        with patch.object(agent, 'api_call', side_effect=wrong_api):
            self.session.work('analysis', '查看 tu2 和 tu4', {'intent': 'inspect_waveform', 'focus_run_ids': ['tu2', 'tu4']})
        self.assertEqual(self.session.state['status'], 'error')
        self.assertEqual(agent.verify_session(self.root)['problems'], [])

    def test_pair_comparison_calculates_real_deltas_ratios_and_zero_denominators(self):
        evidence = self.populate()
        result = comparison(evidence)
        self.assertEqual([p['run_ids'] for p in result['pairs']], [['tu1', 'tu2'], ['tu3', 'tu4']])
        for pair in result['pairs']:
            a, b = [evidence[rid]['metrics']['max_deviation'] for rid in pair['run_ids']]
            self.assertAlmostEqual(pair['metrics']['max_deviation_V']['delta'], b - a)
            self.assertAlmostEqual(pair['metrics']['max_deviation_V']['ratio'], b / a)
            self.assertIsNone(pair['metrics']['event_support_us']['ratio'])
            self.assertEqual(pair['metrics']['event_count']['delta'], 1)
        self.assertAlmostEqual(result['pairs'][0]['metrics']['max_deviation_V']['delta'], .58507653)
        self.assertAlmostEqual(result['pairs'][1]['metrics']['max_deviation_V']['delta'], 1.3176021)
        evidence['tu1']['metrics']['max_deviation'] = 0
        self.assertIsNone(comparison(evidence)['pairs'][0]['metrics']['max_deviation_V']['ratio'])
        json.dumps(comparison(evidence), allow_nan=False)

    def test_comparison_contract_requires_separate_pair_plots_checked_differences_and_progress(self):
        evidence = self.populate()
        compared = comparison(evidence)
        completed = [p['id'] for p in compared['pairs']]
        controls = self.modern_controls(evidence, 'hash', compared, completed)
        validate_controls(controls, WAVEFORMS, 'hash', evidence, 0, version=3, comparison_data=compared, completed=completed)
        for mutate in (lambda x: x['comparison_facts'][0].update(value=123),
                       lambda x: x['views'][0].update(run_ids=list(evidence), view='full'),
                       lambda x: x['views'].pop(2),
                       lambda x: x['comparison_facts'].pop(),
                       lambda x: x['question']['options'][0].update(tool='compare_waveforms', arguments={'run_ids': list(evidence)})):
            bad = deepcopy(controls)
            mutate(bad)
            with self.assertRaises(ValueError):
                validate_controls(bad, WAVEFORMS, 'hash', evidence, 0, version=3, comparison_data=compared, completed=completed)
        schema = json.dumps(report_tool(WAVEFORMS, 'hash', evidence, 0, version=3, comparison_data=compared, completed=completed))
        self.assertNotIn('compare_waveforms', schema)

    def test_overview_then_pair_comparison_has_new_artifacts_and_no_repeated_suggestion(self):
        self.populate()
        with patch.object(agent, 'api_call', side_effect=self.fake_api):
            self.session.launch('say', {'text': '请概览全部波形'})
            self.session.worker.join(30)
            first = self.root / self.session.state['turns'][-1]['path']
            self.assertEqual([c['name'] for c in read(first / 'tool_calls.json')], ['read_evidence'])
            self.session.launch('say', {'text': '请配对比较 tu1/tu2 与 tu3/tu4'})
            self.session.worker.join(30)
            turn = self.session.state['turns'][-1]
            self.assertEqual(turn['status'], 'passed', self.session.state['messages'][-1])
            path = self.root / turn['path']
            self.assertTrue((path / 'comparison.json').exists())
            self.assertEqual(len(list(path.glob('waveform-*.png'))), 2)
            self.assertNotIn('compare_waveforms', [o['tool'] for o in read(path / 'answer.json')['question']['options']])
            self.session.launch('say', {'text': '这些差异能说明什么？'})
            self.session.worker.join(30)
            path = self.root / self.session.state['turns'][-1]['path']
            self.assertEqual(read(path / 'input.json')['completed_comparison_pairs'], ['tu1__tu2', 'tu3__tu4'])
            self.assertNotIn('compare_waveforms', [o['tool'] for o in read(path / 'answer.json')['question']['options']])
        report = (self.root / 'report.html').read_text(encoding='utf-8')
        self.assertIn('配对指标差异', report)
        self.assertIn('百分点', report)
        self.assertIn('不定义（分母为0）', report)
        self.assertEqual(agent.verify_session(self.root)['problems'], [])
        resumed = agent.open_session(self.root)
        self.assertEqual(resumed.state['active_turn'], self.session.state['active_turn'])

    def test_mixed_family_comparison_keeps_denominators_separate(self):
        evidence = self.populate()
        result = comparison({rid: evidence[rid] for rid in ['tu2', 'tu4']})
        pair = result['pairs'][0]
        self.assertEqual(pair['family'], 'mixed')
        self.assertNotIn('deviation_percent', pair['metrics'])
        self.assertIn('不同形态规则', pair['limits'])

    def test_typed_comparison_keeps_ids_adjacent_to_chinese_text(self):
        self.populate()
        with patch.object(agent, 'api_call', side_effect=self.fake_api):
            self.session.launch('say', {'text': '请比较tu1和tu2的差异'})
            self.session.worker.join(30)
        turn = self.session.state['turns'][-1]
        self.assertEqual(turn['status'], 'passed', self.session.state['messages'][-1])
        self.assertEqual(list(read(self.root / turn['path'] / 'evidence.json')), ['tu1', 'tu2'])
        self.assertEqual(agent.verify_session(self.root)['problems'], [])

    def test_changed_comparison_artifact_fails_reverification(self):
        self.populate()
        with patch.object(agent, 'api_call', side_effect=self.fake_api):
            self.session.launch('say', {'text': '配对比较 tu1/tu2 和 tu3/tu4'})
            self.session.worker.join(30)
        path = self.root / self.session.state['turns'][-1]['path'] / 'comparison.json'
        value = read(path)
        value['pairs'][0]['metrics']['max_deviation_V']['delta'] += 1
        write_json(path, value)
        self.assertEqual(agent.verify_session(self.root)['record_status'], 'failed')

    def test_explicit_stage_conclusion_has_no_followup_question(self):
        evidence = self.populate()
        controls = self.controls(evidence)
        with self.assertRaises(ValueError):
            validate_controls(controls, WAVEFORMS, 'hash', evidence, 0, conclude=True)
        controls['question'] = None
        validate_controls(controls, WAVEFORMS, 'hash', evidence, 0, conclude=True)

    def test_analysis_position_is_model_controlled_and_legacy_layout_still_verifies(self):
        evidence = self.populate()
        controls = self.controls(evidence)
        self.assertEqual(controls['views'][-1]['type'], 'analysis')
        legacy = deepcopy(controls)
        legacy['views'].pop()
        validate_controls(legacy, WAVEFORMS, 'hash', evidence, 0, version=1)
        with self.assertRaises(ValueError):
            validate_controls(legacy, WAVEFORMS, 'hash', evidence, 0, version=2)


class ConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=PROJECT / 'results', prefix='agent-confirm-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        with patch.object(agent, 'new_run', return_value=self.root):
            self.session = agent.AgentSession()
        path = self.root / 'runs/R001'
        path.mkdir(parents=True)
        t = np.arange(6000) / 20000
        v = np.sqrt(2) * 230 * np.sin(2 * np.pi * 50 * t + np.deg2rad([0, -120, 120])[:, None])
        dc, load, currents = ideal_reference(v, 100)
        np.savetxt(path / 'waveforms.csv', np.column_stack([t, t, v.T, currents.T, dc, load]), delimiter=',',
                   header=','.join(('t_relative_s', 't_simulation_s', *COLUMNS)), comments='')
        write_json(path / 'config.json', configuration())
        write_json(path / 'metrics.json', analyze_bridge(path / 'waveforms.csv', configuration()))
        finalize(path, {'kind': 'run', 'schema_version': 1, 'model': 'three_phase_rectifier_fault',
                        'backend': 'virtual_hil', 'configuration_schema_version': 1, 'status': 'passed'})
        self.entry = {'id': 'R001', 'path': 'runs/R001', 'source_kind': 'virtual_hil', 'record_status': 'passed',
                      'experiment_status': 'passed', 'manifest_sha256': sha256(path / 'manifest.json'), 'plan_id': None}
        self.turn = {'id': 'T001', 'path': 'turns/T001', 'status': 'passed'}
        self.option = {'id': 'fault', 'label': '执行故障对照', 'description': '验证导通缺失。', 'recommended': True,
                       'tool': 'run_experiment', 'arguments': {'operation': 'fault', 'reference_run': 'R001'}}
        write_json(self.root / 'turns/T001/answer.json', {'question': {'options': [self.option]}})
        self.session.state.update(case_id=BRIDGE, runs={'R001': self.entry}, turns=[self.turn], active_turn='T001')
        self.session.add('user', '运行整流桥对照')
        self.session.prepare_plan(self.turn, self.option)

    def approval(self):
        p = self.session.state['pending']
        return {'plan_id': p['id'], 'token': p['confirmation_token'], 'approved': True, 'operator': 'unit-test operator'}

    def test_approval_binds_exact_source_config_and_actual_operator(self):
        data = self.approval()
        operation, _, context = self.session.confirm_plan(data)
        self.assertEqual(operation, 'experiment')
        self.assertEqual(context['config'], configuration('A_upper_open'))
        saved = read(self.root / 'plans' / data['plan_id'] / 'confirmation.json')
        self.assertEqual(saved['operator'], 'unit-test operator')
        self.assertEqual(saved['config_sha256'], sha256(self.root / 'plans' / data['plan_id'] / 'config.json'))

    def test_stale_question_rejects_confirmation(self):
        data = self.approval()
        self.session.state['active_turn'] = None
        with self.assertRaises(ValueError):
            self.session.confirm_plan(data)

    def test_config_or_source_tampering_rejects_confirmation(self):
        data = self.approval()
        config_path = self.root / 'plans' / data['plan_id'] / 'config.json'
        original = config_path.read_bytes()
        config = read(config_path)
        config['circuit']['load_ohm'] = 200
        write_json(config_path, config)
        with self.assertRaises(ValueError):
            self.session.confirm_plan(data)
        config_path.write_bytes(original)
        with (self.root / 'runs/R001/waveforms.csv').open('a', encoding='utf-8') as handle:
            handle.write('\n')
        with self.assertRaises(ValueError):
            self.session.confirm_plan(data)

    def test_duplicate_confirmation_does_not_launch_second_execution(self):
        data = self.approval()
        with patch.object(self.session, 'work') as work:
            self.session.launch('confirm', data)
            self.session.worker.join()
            with self.assertRaises(ValueError):
                self.session.launch('confirm', data)
            self.assertEqual(work.call_count, 1)


class BridgeTests(unittest.TestCase):
    def test_fixed_conditions_and_unsupported_fault_rejected(self):
        adapter = BridgeAdapter()
        for fault in ('none', 'A_upper_open'):
            self.assertEqual(adapter.validate(configuration(fault)), configuration(fault))
        for key, value in [('fault', 'B_upper_open'), ('schema_version', True), ('backend', 'physical_hil')]:
            config = configuration()
            config[key] = value
            with self.assertRaises(ValueError):
                adapter.validate(config)

    def test_reference_known_peak_mean_and_fault_direction(self):
        t = np.arange(6000) / 20000
        v = np.sqrt(2) * 230 * np.sin(2 * np.pi * 50 * t + np.deg2rad([0, -120, 120])[:, None])
        dc, load, phase = ideal_reference(v, 100)
        self.assertAlmostEqual(float(dc.mean()), 3 * np.sqrt(6) * 230 / np.pi, delta=.02)
        self.assertTrue(np.allclose(phase.sum(axis=0), 0))
        dc_fault, _, phase_fault = ideal_reference(v, 100, 'A_upper_open')
        self.assertLess(float(dc_fault.mean()), float(dc.mean()))
        self.assertEqual(float(phase_fault[0].max()), 0)
        self.assertLess(float(phase_fault[0].min()), -4)

    def test_metrics_from_independent_analytic_csv(self):
        with tempfile.TemporaryDirectory() as temp:
            t = np.arange(6000) / 20000
            v = np.sqrt(2) * 230 * np.sin(2 * np.pi * 50 * t + np.deg2rad([0, -120, 120])[:, None])
            for fault in ('none', 'A_upper_open'):
                dc, load, currents = ideal_reference(v, 100, fault)
                path = Path(temp) / (fault + '.csv')
                np.savetxt(path, np.column_stack([t, t, v.T, currents.T, dc, load]), delimiter=',',
                           header=','.join(('t_relative_s', 't_simulation_s', *COLUMNS)), comments='')
                metrics = analyze_bridge(path, configuration(fault))
                self.assertEqual(metrics['status'], 'passed')
                self.assertEqual(metrics['analysis_samples'], 4000)
                self.assertEqual(metrics['missing_conduction_directions'], [] if fault == 'none' else ['A_positive'])


if __name__ == '__main__':
    unittest.main()
