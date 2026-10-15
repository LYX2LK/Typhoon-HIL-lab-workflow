"""Synthetic-fixture unit tests; they never run Typhoon or verify hardware."""
from __future__ import annotations
import copy
import csv
import json
import math
from pathlib import Path
import tempfile
import unittest
from typhoon_lab.analysis import COLUMNS, analyze, expected_rlc_rms
from typhoon_lab.reporting import write_report, write_sweep_report

BASE_CONFIG = {
    'schema_version': 1, 'model': 'rlc_filter', 'backend': 'virtual_hil',
    'source': {'rms_v': 10, 'frequency_hz': 1000, 'phase_deg': 17},
    'circuit': {'rin_ohm': 5, 'branch_r_ohm': .1, 'l_h': 1e-5, 'c_f': .0005},
    'capture': {'settle_s': .05, 'duration_s': .02, 'sample_rate_hz': 20000, 'wall_timeout_s': 60},
    'acceptance': {'relative_rms_error': .03, 'min_samples': 256},
}


def independent_phasors(config):
    """Use parallel admittance, independently of analysis's product formula."""
    source, circuit = config['source'], config['circuit']
    w = 2 * math.pi * source['frequency_hz']
    admittance = 1 / complex(0, w * circuit['l_h'])
    admittance += 1 / complex(circuit['branch_r_ohm'], -1 / (w * circuit['c_f']))
    z_parallel = 1 / admittance
    current = source['rms_v'] / (circuit['rin_ohm'] + z_parallel)
    return current, current * z_parallel


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='analysis-test-', dir=Path(__file__).parent)
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.config = copy.deepcopy(BASE_CONFIG)
        self.csv = self.folder / 'waveforms.csv'

    def fixture(self, config=None, count=400, current_multiplier=1.0):
        config = config or self.config
        current, voltage = independent_phasors(config)
        frequency = config['source']['frequency_hz']
        source_phase = math.radians(config['source'].get('phase_deg', 0))
        rows = []
        for index in range(count):
            t = index / 20000
            phase = 2 * math.pi * frequency * t + source_phase
            def sample(phasor):
                return math.sqrt(2) * (phasor.real * math.cos(phase) - phasor.imag * math.sin(phase))
            rows.append([t, .06 + t, sample(current) * current_multiplier, sample(voltage)])
        self.write_rows(rows)
        return rows

    def write_rows(self, rows, columns=COLUMNS):
        with self.csv.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow(columns)
            writer.writerows(rows)

    def test_phasor_reference_for_scan_values(self):
        for rin in (1, 5, 10):
            with self.subTest(rin=rin):
                config = copy.deepcopy(self.config)
                config['circuit']['rin_ohm'] = rin
                reference = expected_rlc_rms(config)
                current, voltage = independent_phasors(config)
                self.assertAlmostEqual(reference['I_A'], abs(current), places=12)
                self.assertAlmostEqual(reference['Va1_V'], abs(voltage), places=12)

    def test_exact_sinusoid_and_capture_metadata(self):
        self.fixture()
        metrics = analyze(self.csv, self.config)
        current, voltage = independent_phasors(self.config)
        self.assertEqual(metrics['status'], 'passed')
        self.assertAlmostEqual(metrics['signals']['I_A']['rms'], abs(current), places=12)
        self.assertAlmostEqual(metrics['signals']['Va1_V']['rms'], abs(voltage), places=12)
        self.assertEqual(metrics['sample_count'], 400)
        self.assertAlmostEqual(metrics['sample_rate_hz'], 20000, places=7)
        self.assertAlmostEqual(metrics['capture']['span_s'], .01995)
        self.assertAlmostEqual(metrics['capture']['duration_s'], .02)
        self.assertAlmostEqual(metrics['capture']['cycles'], 20)
        self.assertEqual(metrics, analyze(self.csv, self.config))
        self.assertEqual(metrics['source_csv'], 'waveforms.csv')
        json.dumps(metrics, allow_nan=False)

    def test_wrong_current_is_failed_without_dropping_data(self):
        self.fixture(current_multiplier=1.1)
        original = self.csv.read_bytes()
        metrics = analyze(self.csv, self.config)
        self.assertEqual(metrics['status'], 'failed')
        self.assertFalse(metrics['signals']['I_A']['passed'])
        self.assertTrue(metrics['signals']['Va1_V']['passed'])
        self.assertAlmostEqual(metrics['signals']['I_A']['relative_rms_error'], .1)
        self.assertEqual(self.csv.read_bytes(), original)

    def test_insufficient_samples_rejected(self):
        self.fixture(count=200)
        with self.assertRaisesRegex(ValueError, 'Insufficient samples'):
            analyze(self.csv, self.config)

    def test_missing_and_duplicate_columns_rejected(self):
        rows = self.fixture()
        self.write_rows([row[:3] for row in rows], COLUMNS[:3])
        with self.assertRaisesRegex(ValueError, 'columns'):
            analyze(self.csv, self.config)
        self.write_rows(rows, ('t_relative_s', 't_simulation_s', 'I_A', 'I_A'))
        with self.assertRaisesRegex(ValueError, 'columns'):
            analyze(self.csv, self.config)

    def test_nonfinite_and_nonnumeric_samples_rejected(self):
        for invalid in ('nan', 'inf', '-inf', 'not-a-number', ''):
            with self.subTest(value=invalid):
                rows = self.fixture()
                rows[20][2] = invalid
                self.write_rows(rows)
                with self.assertRaises(ValueError):
                    analyze(self.csv, self.config)

    def test_repeated_and_reversed_time_rejected(self):
        for position in (0, 1):
            with self.subTest(column=position):
                rows = self.fixture()
                rows[20][position] = rows[19][position]
                self.write_rows(rows)
                with self.assertRaisesRegex(ValueError, 'strictly increasing'):
                    analyze(self.csv, self.config)

    def test_missing_time_sample_rejected_without_filling(self):
        rows = self.fixture()
        del rows[200]
        self.write_rows(rows)
        with self.assertRaisesRegex(ValueError, 'not uniformly spaced'):
            analyze(self.csv, self.config)

    def test_disagreement_between_time_coordinates_rejected(self):
        rows = self.fixture()
        rows[200][1] += .00001
        self.write_rows(rows)
        with self.assertRaisesRegex(ValueError, 'share a time grid'):
            analyze(self.csv, self.config)

    def test_capture_checks_fail_on_inconsistent_request(self):
        self.fixture()
        for key, value, check_name in (
            ('sample_rate_hz', 10000, 'sample_rate'),
            ('duration_s', .03, 'capture_duration'),
            ('settle_s', .07, 'settled_before_capture'),
        ):
            with self.subTest(key=key):
                config = copy.deepcopy(self.config)
                config['capture'][key] = value
                result = analyze(self.csv, config)
                self.assertEqual(result['status'], 'failed')
                selected = next(check for check in result['checks'] if check['name'] == check_name)
                self.assertFalse(selected['passed'])

    def test_undersampling_is_failed_even_with_aliased_sinusoid(self):
        self.config['source']['frequency_hz'] = 11000
        self.fixture()
        metrics = analyze(self.csv, self.config)
        self.assertEqual(metrics['status'], 'failed')
        check = next(item for item in metrics['checks'] if item['name'] == 'sampling_above_nyquist')
        self.assertFalse(check['passed'])

    def test_zero_source_and_negative_component_rejected(self):
        for group, key, value in (('source', 'rms_v', 0), ('circuit', 'l_h', -1), ('circuit', 'c_f', float('nan'))):
            with self.subTest(key=key):
                config = copy.deepcopy(self.config)
                config[group][key] = value
                with self.assertRaises(ValueError):
                    expected_rlc_rms(config)


class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='report-test-', dir=Path(__file__).parent)
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)

    def populate(self, folder, rin=5):
        folder.mkdir(parents=True, exist_ok=True)
        config = copy.deepcopy(BASE_CONFIG)
        config['circuit']['rin_ohm'] = rin
        current, voltage = independent_phasors(config)
        with (folder / 'waveforms.csv').open('w', encoding='utf-8', newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow(COLUMNS)
            for index in range(400):
                t = index / 20000
                phase = 2 * math.pi * 1000 * t
                writer.writerow([t, .06 + t, math.sqrt(2) * (current.real * math.cos(phase) - current.imag * math.sin(phase)), math.sqrt(2) * (voltage.real * math.cos(phase) - voltage.imag * math.sin(phase))])
        metrics = analyze(folder / 'waveforms.csv', config)
        for name, value in (('config.json', config), ('metrics.json', metrics), ('capture.json', {'trigger_timestamp_utc_time_ns': None, 'simulation_step_s': 5e-7, 'decimation': 100})):
            (folder / name).write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        return metrics

    def test_single_report_preserves_raw_and_is_offline(self):
        self.populate(self.folder)
        raw_before = (self.folder / 'waveforms.csv').read_bytes()
        config_before = (self.folder / 'config.json').read_bytes()
        manifest = {'status': 'passed', 'environment': {'thcc_version': '2026.3', 'python': '3.11.4', 'typhoon_hil_api': '1.32.1', 'typhoontest': '1.35.6'}, 'model_origin': {'original_path': 'official-example', 'sha256': 'abc123'}, 'artifacts': {'model.tse': 'def456'}}
        outputs = write_report(self.folder, manifest)
        self.assertEqual({path.name for path in outputs}, {'waveforms.png', 'report.html', 'report.md'})
        self.assertTrue(all(path.is_file() for path in outputs))
        document = (self.folder / 'report.html').read_text(encoding='utf-8')
        self.assertIn('data:image/png;base64,', document)
        self.assertNotIn('<script', document)
        self.assertNotIn('src="http', document)
        self.assertIn('Virtual HIL', document)
        self.assertIn('非实时', document)
        self.assertIn('capture.json', document)
        self.assertIn('abc123', document)
        self.assertIn('def456', document)
        self.assertIn('1.32.1', document)
        self.assertIn('TyphoonTest', document)
        markdown = (self.folder / 'report.md').read_text(encoding='utf-8')
        self.assertIn('```json', markdown)
        self.assertEqual(raw_before, (self.folder / 'waveforms.csv').read_bytes())
        self.assertEqual(config_before, (self.folder / 'config.json').read_bytes())

    def test_execution_error_without_waveform_keeps_reason_and_no_fabrication(self):
        detail = 'compile failed <script>alert(1)</script>'
        outputs = write_report(self.folder, {'status': 'error', 'error': detail})
        self.assertEqual({path.name for path in outputs}, {'report.html', 'report.md'})
        self.assertFalse((self.folder / 'waveforms.csv').exists())
        self.assertFalse((self.folder / 'waveforms.png').exists())
        document = (self.folder / 'report.html').read_text(encoding='utf-8')
        self.assertIn('执行异常 (error)', document)
        self.assertIn('未计算', document)
        self.assertIn('&lt;script&gt;', document)
        self.assertNotIn('<script>', document)

    def test_missing_evidence_and_empty_sweep_cannot_pass(self):
        write_report(self.folder, {'status': 'passed'})
        self.assertIn('执行异常 (error)', (self.folder / 'report.html').read_text(encoding='utf-8'))
        write_sweep_report(self.folder, {'status': 'passed', 'cases': []})
        self.assertIn('执行异常 (error)', (self.folder / 'report.html').read_text(encoding='utf-8'))

    def test_sweep_uses_relative_dir_and_each_config_rin(self):
        for index, rin in enumerate((1, 10)):
            self.populate(self.folder / 'cases' / f'case-{index}', rin)
        cases = [{'case_id': 'low', 'relative_dir': 'cases/case-0', 'status': 'passed'}, {'case_id': 'high', 'relative_dir': 'cases/case-1', 'status': 'passed'}]
        outputs = write_sweep_report(self.folder, {'status': 'passed', 'cases': cases})
        self.assertEqual({path.name for path in outputs}, {'comparison.csv', 'comparison.png', 'report.html', 'report.md'})
        with (self.folder / 'comparison.csv').open('r', encoding='utf-8', newline='') as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual([float(row['rin_ohm']) for row in rows], [1, 10])
        self.assertGreater(float(rows[0]['I_rms_A']), float(rows[1]['I_rms_A']))
        document = (self.folder / 'report.html').read_text(encoding='utf-8')
        self.assertIn('cases/case-0/manifest.json', document)
        self.assertIn('实际工况配置', document)

    def test_sweep_missing_case_is_not_filled_with_zero(self):
        (self.folder / 'cases' / 'missing').mkdir(parents=True)
        write_sweep_report(self.folder, {'status': 'error', 'cases': [{'case_id': 'missing', 'relative_dir': 'cases/missing', 'status': 'error'}]})
        with (self.folder / 'comparison.csv').open('r', encoding='utf-8', newline='') as handle:
            row = next(csv.DictReader(handle))
        self.assertEqual(row['I_rms_A'], '')
        self.assertEqual(row['rin_ohm'], '')
        self.assertEqual(row['status'], 'error')
        self.assertFalse((self.folder / 'comparison.png').exists())

    def test_sweep_rejects_escape_from_run_directory(self):
        with self.assertRaisesRegex(ValueError, 'inside the run directory'):
            write_sweep_report(self.folder, {'cases': [{'relative_dir': '../outside'}]})


if __name__ == '__main__':
    unittest.main()
