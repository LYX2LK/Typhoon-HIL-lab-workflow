"""Known numerical examples and field-data provenance/clock failure boundaries."""
from copy import deepcopy
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import math
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from typhoon_lab.cli import main
from typhoon_lab.field_intake import validate_intake, read_source
from typhoon_lab.field_analysis import analyze_data
from typhoon_lab.field_records import analyze_field, verify_field
from typhoon_lab.field_reporting import figure_specs
from typhoon_lab.tle9877 import parse_sample_ldf, decode_frame_from_ldf
from typhoon_lab.utils import PROJECT, sha256, write_json


def known(value):
    return {'value': value, 'status': 'confirmed', 'source': 'independent synthetic definition'}


def source(sid='capture', file='capture.csv'):
    return {'id': sid, 'file': file, 'format': 'waveform_csv', 'source_kind': 'synthetic',
        'provenance': known('hand-calculated fixture'), 'device': 'fixture',
        'time': {'field': 'ms', 'unit': known('ms'), 'clock_domain': sid}, 'alignment': None,
        'signals': [{'id': 'speed', 'column': 'rpm', 'role': 'model_speed', 'unit': known('rpm')},
                    {'id': 'current', 'column': 'mA', 'role': 'current', 'unit': known('mA')}],
        'detail_window_s': [.5, 1.]}


def fixture():
    common = {'confirmed': True, 'basis': 'fixture limits, not sample requirements', 'max_gap_s': .11, 'min_samples': 3}
    return {'schema_version': 1, 'dataset_id': 'known-example', 'purpose': 'independent offline checks',
        'sources': [source()], 'events': [{'id': 'stop', 'label': 'explicit stop request', 'source_id': 'capture',
                                        'time_s': .5, 'confirmed': True, 'basis': 'fixture stop instruction'}],
        'criteria': [dict(common, id='track', type='speed_tracking', signal='capture.speed', window_s=[.1, .4], target_rpm=1000, max_error_rpm=2),
                     dict(common, id='current', type='max_current', signal='capture.current', window_s=[.1, .4], limit_a=1.2),
                     dict(common, id='stop', type='stop', signal='capture.speed', window_s=[.5, 1], event_id='stop',
                          threshold_rpm=5, deadline_s=.3, hold_s=.2, max_time_uncertainty_s=.01)]}


class FieldAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ldf = parse_sample_ldf(PROJECT / 'data/tle9877/LIN.ldf')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.input = self.root / 'input'; self.input.mkdir()
        self.data = fixture()
        self.path = self.root / 'intake.json'
        speeds = [1000, 1000, 1002, 1000, 1000, 1000, 100, 5, 0, 0, 0]
        currents = [500, 500, -1200, 600, 500, 500, 400, 300, 200, 100, 0]
        self.csv = self.input / 'capture.csv'
        self.csv.write_text('ms,rpm,mA\n' + ''.join(f'{i*100},{w},{a}\n' for i, (w, a) in enumerate(zip(speeds, currents))), encoding='utf-8')

    def analyze(self):
        return analyze_data(self.input, validate_intake(self.data), self.ldf)

    def package(self, name='result'):
        write_json(self.path, self.data)
        out = self.root / name
        result = analyze_field(self.path, self.input, out)
        return out, result

    def invoke(self, args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(args)
        return code, json.loads(stdout.getvalue()), stderr.getvalue()

    def test_exact_units_thresholds_and_hold(self):
        metrics, streams = self.analyze()
        self.assertEqual(metrics['criteria_status'], 'passed')
        self.assertEqual(metrics['performance_status'], 'not_evaluated')
        self.assertEqual(metrics['checks'][0]['metrics']['maximum_speed_error_rpm'], 2)
        self.assertEqual(metrics['checks'][1]['metrics']['maximum_absolute_current_a'], 1.2)
        stop = metrics['checks'][2]['metrics']
        self.assertAlmostEqual(stop['first_below_sample_s'], .7)
        self.assertAlmostEqual(stop['hold_verified_until_s'], .9)
        self.assertEqual(streams['capture']['signals']['current']['values_raw'][2], -1200)
        self.assertEqual(streams['capture']['signals']['current']['values'][2], -1.2)

    def test_failures_stay_failed(self):
        self.data['criteria'][0]['max_error_rpm'] = 1.9
        self.data['criteria'][1]['limit_a'] = 1.19
        self.data['criteria'][2]['threshold_rpm'] = 0
        self.data['criteria'][2]['deadline_s'] = .1
        metrics, _ = self.analyze()
        self.assertEqual([c['status'] for c in metrics['checks']], ['failed'] * 3)
        self.assertEqual(metrics['status'], 'failed')

    def test_configured_physical_evaluation_has_limited_scope(self):
        self.data['sources'][0]['source_kind'] = 'physical'
        metrics, _ = self.analyze()
        self.assertEqual(metrics['performance_status'], 'passed')
        self.data['sources'][0]['provenance']['status'] = 'unconfirmed'
        self.assertEqual(self.analyze()[0]['performance_status'], 'not_evaluated')

    def test_unknown_units_criteria_and_missing_roles_never_pass(self):
        for change in ('unit', 'time', 'basis', 'threshold', 'role', 'window', 'no_checks'):
            data = deepcopy(self.data)
            if change == 'unit': self.data['sources'][0]['signals'][0]['unit']['status'] = 'unconfirmed'
            if change == 'time': self.data['sources'][0]['time']['unit']['status'] = 'unconfirmed'
            if change == 'basis': self.data['criteria'][0]['basis'] = ''
            if change == 'threshold': self.data['criteria'][0]['max_error_rpm'] = None
            if change == 'role': self.data['sources'][0]['signals'][0]['role'] = 'requested_speed'
            if change == 'window': self.data['criteria'][0]['window_s'] = [.1, 3]
            if change == 'no_checks': self.data['criteria'] = []
            with self.subTest(change=change):
                metrics, _ = self.analyze()
                if metrics['checks']:
                    self.assertEqual(metrics['checks'][0]['status'], 'not_evaluated')
                self.assertNotEqual(metrics['criteria_status'], 'passed')
            self.data = data

    def test_feedback_voltage_cannot_be_used_as_current(self):
        s = self.data['sources'][0]['signals'][1]
        s.update(role='feedback_voltage', unit=known('mV'))
        metrics, streams = self.analyze()
        self.assertEqual(streams['capture']['signals']['current']['unit'], 'V')
        self.assertEqual(metrics['checks'][1]['status'], 'not_evaluated')

    def test_nonuniform_samples_are_accepted_without_interpolation(self):
        self.csv.write_text(self.csv.read_text(encoding='utf-8').replace('200,', '210,'), encoding='utf-8')
        metrics, streams = self.analyze()
        self.assertEqual(metrics['data_quality_status'], 'passed')
        self.assertEqual(len(streams['capture']['time_s']), 11)
        self.assertEqual(streams['capture']['time_s'][2], .21)

    def test_missing_bad_duplicate_and_reverse_samples_retained(self):
        original = self.csv.read_text(encoding='utf-8')
        for a, b, expected in [('200,1002,-1200', '200,,NaN', 'missing_or_invalid_value'),
                               ('200,', '100,', 'time_not_monotonic'),
                               ('200,', '50,', 'time_not_monotonic')]:
            with self.subTest(replacement=b):
                self.csv.write_text(original.replace(a, b), encoding='utf-8')
                metrics, streams = self.analyze()
                self.assertEqual(len(streams['capture']['time_raw']), 11)
                self.assertEqual(metrics['data_quality_status'], 'failed')
                self.assertIn(expected, {i['code'] for i in streams['capture']['issues']})
                self.assertNotIn('passed', [c['status'] for c in metrics['checks']])

    def test_gap_and_short_hold_are_not_false_passes(self):
        self.data['criteria'][0]['max_gap_s'] = .05
        self.assertEqual(self.analyze()[0]['checks'][0]['status'], 'not_evaluated')
        self.data = fixture()
        self.data['criteria'][2]['window_s'] = [.5, .9]
        self.assertEqual(self.analyze()[0]['checks'][2]['status'], 'not_evaluated')
        self.data = fixture()
        self.data['criteria'][2]['hold_s'] = .21
        self.assertEqual(self.analyze()[0]['checks'][2]['status'], 'not_evaluated')

    def test_threshold_dip_without_complete_hold_fails(self):
        text = self.csv.read_text(encoding='utf-8').replace('900,0,', '900,10,')
        self.csv.write_text(text, encoding='utf-8')
        self.assertEqual(self.analyze()[0]['checks'][2]['status'], 'failed')

    def test_gap_crossing_window_boundary_is_not_ignored(self):
        self.csv.write_text(self.csv.read_text(encoding='utf-8').replace('100,1000,500\n',''),encoding='utf-8')
        self.assertEqual(self.analyze()[0]['checks'][0]['status'],'not_evaluated')

    def test_clock_mapping_validity_uncertainty_and_unsynchronized(self):
        event_source = source('controller', 'event.csv')
        (self.input/'event.csv').write_text('ms,rpm,mA\n5000,0,0\n6000,0,0\n', encoding='utf-8')
        self.data['sources'].append(event_source)
        self.data['events'][0].update(source_id='controller', time_s=5.25)
        self.assertEqual(self.analyze()[0]['checks'][2]['status'], 'not_evaluated')
        event_source['alignment'] = {'group': 'common', 'scale': 2, 'offset_s': -10, 'uncertainty_s': .001,
                                    'valid_range_s': [5, 6], 'basis': 'known fixture anchors'}
        self.data['sources'][0]['alignment'] = {'group': 'common', 'scale': 1, 'offset_s': 0, 'uncertainty_s': .001,
                                              'valid_range_s': [0, 1], 'basis': 'shared fixture clock'}
        metrics, streams = self.analyze()
        self.assertEqual(metrics['checks'][2]['status'], 'passed')
        self.assertAlmostEqual(metrics['checks'][2]['metrics']['event_time_in_signal_clock_s'], .5)
        self.assertTrue(any(s['axis'] == 'aligned' for s in figure_specs(self.data, streams)))
        event_source['alignment']['uncertainty_s'] = .02
        self.assertIn('uncertainty', self.analyze()[0]['checks'][2]['reason'])
        event_source['alignment']['valid_range_s'] = [5.5, 6]
        self.assertIn('common clock', self.analyze()[0]['checks'][2]['reason'])

    def test_sampling_interval_straddling_deadline_is_unrated(self):
        self.data['criteria'][2]['deadline_s'] = .15
        metrics, _ = self.analyze()
        self.assertEqual(metrics['checks'][2]['status'], 'not_evaluated')
        self.assertIn('straddles', metrics['checks'][2]['reason'])

    def test_declared_clock_rate_is_used_for_stop_durations(self):
        self.data['sources'][0]['alignment']={'group':'common','scale':2,'offset_s':0,'uncertainty_s':0,
                                              'valid_range_s':[0,1],'basis':'known clock rate'}
        self.data['criteria'][2]['deadline_s']=.15
        checked=self.analyze()[0]['checks'][2]
        self.assertEqual(checked['status'],'failed')
        self.assertEqual(checked['metrics']['duration_scale'],2)

    def test_missing_column_and_overflow_are_reported(self):
        self.csv.write_text('ms,other\n0,1\n100,2\n',encoding='utf-8')
        metrics,streams=self.analyze()
        self.assertEqual(metrics['data_quality_status'],'failed')
        self.assertIn('missing columns',streams['capture']['issues'][0]['message'])
        self.csv.write_text('ms,rpm,mA\n0,1e308,1\n100,1e308,2\n',encoding='utf-8')
        self.data['sources'][0]['signals'][0].update(scale=1e308,conversion_basis='explicit overflow test')
        metrics,streams=self.analyze()
        self.assertEqual(streams['capture']['signals']['speed']['values'],[None,None])
        self.assertEqual(metrics['data_quality_status'],'failed')

    def test_missing_source_does_not_hide_other_data(self):
        self.data['sources'].append(source('missing', 'absent.csv'))
        metrics, streams = self.analyze()
        self.assertEqual(metrics['data_quality_status'], 'failed')
        self.assertEqual(metrics['checks'][0]['status'], 'passed')
        self.assertEqual(len(streams['capture']['time_s']), 11)
        self.assertEqual(streams['missing']['signals'], {})

    def test_rad_s_unit_conversion(self):
        signal = self.data['sources'][0]['signals'][0]
        signal['unit'] = known('rad/s')
        text = self.csv.read_text(encoding='utf-8').replace(',1000,', ',104.71975511965977,')
        self.csv.write_text(text, encoding='utf-8')
        self.assertAlmostEqual(self.analyze()[1]['capture']['signals']['speed']['values'][0], 1000)

    def test_lin_frames_use_independent_known_vectors(self):
        lin = source('lin', 'lin.csv')
        lin.update(format='lin_csv', columns={k: k for k in ('direction','identifier','identifier_kind','data','checksum','driver_status')})
        lin.pop('signals'); lin['time'].update(field='ms')
        (self.input/'lin.csv').write_text('ms,direction,identifier,identifier_kind,data,checksum,driver_status\n'
            '0,tx,0xA6,pid,64 00,0xF4,ok\n0,rx,0x25,pid,64 64 5A 50 0A 00 00 00,0x5D,ok\n'
            '20,rx,0x25,id,FF FF FF FF FF FF FF FF,0,ok\n30,rx,0x10,id,00,0,ok\n'
            '40,tx,0x26,id,64 00,,ok\n', encoding='utf-8')
        self.data['sources'].append(lin)
        metrics, streams = self.analyze()
        values = streams['lin']['signals']
        self.assertEqual(values['ControlSetspeed']['values'][0], 2240)
        self.assertEqual(values['ActualSpeed']['values'][1], 2240)
        self.assertEqual(values['Current']['values'][1], 2)
        self.assertEqual(values['ControlSetspeed']['values'][-1], None)
        self.assertEqual([f['status'] for f in streams['lin']['frames']], ['passed','passed','failed','unsupported','unverified'])
        self.assertEqual(streams['lin']['frames'][0]['meaning'], 'local_tx_record')
        self.assertEqual(metrics['data_quality_status'], 'failed')

    def test_jsonl_ignores_cached_decoding_and_retains_timeout(self):
        lin = source('lin', 'bus.jsonl'); lin.update(format='lin_jsonl')
        lin.pop('signals'); lin['time'].update(field='session_time_s', unit=known('s'))
        rows = [{'event':'opened','session_time_s':0}, {'event':'exchange','operation':'publish','session_time_s':0,
            'raw':{'pid':166,'data':[100,0],'checksum':244,'driver_status':'ok'}, 'decoded':{'fake':100000}},
            {'event':'exchange','operation':'request','session_time_s':.01,'error':{'code':'timeout'}}]
        (self.input/'bus.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
        stream = read_source(self.input/'bus.jsonl',lin,self.ldf)
        self.assertEqual(stream['signals']['ControlSetspeed']['values'], [2240, None])
        self.assertEqual(len(stream['journal']), 3)
        self.assertEqual(stream['frames'][1]['status'], 'failed')

    def test_jsonl_clock_conflict_and_failed_exchange_are_not_reinterpreted(self):
        lin=source('lin','bus.jsonl');lin.update(format='lin_jsonl');lin.pop('signals')
        lin['time'].update(field='raw.device_time_s',unit=known('s'),clock_domain='expected_device')
        row={'event':'exchange','operation':'request','status':'passed',
             'raw':{'pid':166,'data':[100,0],'checksum':244,'driver_status':'ok','device_time_s':0,'clock_domain':'different_device'}}
        path=self.input/'bus.jsonl';path.write_text(json.dumps(row)+'\n',encoding='utf-8')
        stream=read_source(path,lin,self.ldf)
        self.assertEqual(stream['time_s'],[None])
        self.assertEqual(stream['data_quality_status'],'failed')
        row['raw']['clock_domain']='expected_device';row['status']='failed'
        path.write_text(json.dumps(row)+'\n',encoding='utf-8')
        stream=read_source(path,lin,self.ldf)
        self.assertEqual(stream['frames'][0]['status'],'failed')
        self.assertEqual(stream['signals'],{})

    def test_schema_rejects_unsafe_paths_and_implicit_transforms(self):
        for change in ('path','unknown','scale','alignment','duplicate','negative'):
            data = deepcopy(self.data)
            if change == 'path': data['sources'][0]['file'] = '../bad.csv'
            if change == 'unknown': data['sources'][0]['guess'] = True
            if change == 'scale': data['sources'][0]['signals'][0]['scale'] = 2
            if change == 'alignment': data['sources'][0]['alignment'] = {'offset_s':0}
            if change == 'duplicate': data['sources'].append(deepcopy(data['sources'][0]))
            if change == 'negative': data['criteria'][0]['max_gap_s'] = -1
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_intake(data)

    def test_portable_package_and_read_only_verification(self):
        before = sha256(self.csv)
        out, result = self.package()
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(sha256(self.csv), before)
        shutil.rmtree(self.input)
        moved = self.root/'moved'; shutil.move(str(out),moved)
        hashes = {p.relative_to(moved).as_posix(): sha256(p) for p in moved.rglob('*') if p.is_file()}
        with patch('typhoon_lab.tle9877.load_profile',side_effect=AssertionError('must use packaged LDF')):
            checked = verify_field(moved)
        self.assertEqual(checked['record_status'], 'passed', checked['problems'])
        self.assertFalse((moved/'verification.json').exists())
        self.assertEqual(hashes,{p.relative_to(moved).as_posix():sha256(p) for p in moved.rglob('*') if p.is_file()})

    def test_failed_criteria_package_can_verify_and_cli_reports_statuses(self):
        self.data['criteria'][0]['max_error_rpm'] = 1
        write_json(self.path,self.data)
        out=self.root/'failed'
        code, response, _ = self.invoke(['--json','analyze-field-data','--intake',str(self.path),'--input-dir',str(self.input),'--output-dir',str(out)])
        self.assertEqual(code,1)
        self.assertEqual(response['result']['criteria_status'],'failed')
        self.assertIsNone(response['experiment_status'])
        self.assertIsNone(response['record_status'])
        code, response, _ = self.invoke(['verify-field-data','--run-dir',str(out),'--json'])
        self.assertEqual(code,0)
        self.assertEqual(response['record_status'],'passed')
        self.assertEqual(response['result']['criteria_status'],'failed')
        self.assertIsNone(response['experiment_status'])
        code, response, _ = self.invoke(['--json','verify','--run-dir',str(out)])
        self.assertEqual(code,0)
        self.assertIsNone(response['experiment_status'])
        verify_field(out,write=True)
        self.assertTrue((out/'verification.json').is_file())

    def test_changed_files_and_unknown_version_are_detected(self):
        out,_ = self.package()
        for rel in ('inputs/capture.csv','normalized.json','code_snapshot/field_analysis.py','report.html','inputs/LIN.ldf'):
            path=out/rel; original=path.read_bytes();path.write_bytes(original+b' ')
            with self.subTest(file=rel):
                self.assertEqual(verify_field(out)['record_status'],'failed')
            path.write_bytes(original)
        manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
        manifest['analysis_method_version']=999;write_json(out/'manifest.json',manifest)
        with patch('typhoon_lab.field_records.analyze_data',side_effect=AssertionError('must not recompute')):
            checked=verify_field(out)
        self.assertEqual(checked['record_status'],'failed')
        self.assertTrue(any('recomputation skipped' in s for s in checked['problems']))

    def test_missing_source_package_is_portable_and_consistent(self):
        self.data['sources'].append(source('missing','absent.csv'))
        out,_=self.package()
        moved=self.root/'moved';shutil.move(str(out),moved)
        checked=verify_field(moved)
        self.assertEqual(checked['record_status'],'passed',checked['problems'])
        self.assertEqual(checked['data_quality_status'],'failed')

    def test_output_refuses_overwrite_nested_directories_and_bad_args(self):
        write_json(self.path,self.data)
        with self.assertRaises(ValueError): analyze_field(self.path,self.input,self.input/'nested')
        out,_=self.package()
        with self.assertRaises(ValueError): analyze_field(self.path,self.input,out)
        code,response,_=self.invoke(['--json','analyze-field-data','--intake',str(self.path)])
        self.assertEqual(code,2)
        self.assertIsNone(response['experiment_status'])
