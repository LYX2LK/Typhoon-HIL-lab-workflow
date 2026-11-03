"""Independent frame vectors and bus failure handling; no device or wall waits."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from typhoon_lab.cases import read_json
from typhoon_lab.cli import main
from typhoon_lab.lin_session import exchange_schedule, run_mock_scenario, validate_scenario
from typhoon_lab.lin_transport import MockClock, MockLINMaster, LINTransportError
from typhoon_lab.utils import PROJECT, sha256


class LINSessionTests(unittest.TestCase):
    def setUp(self):
        self.scenario = read_json(PROJECT / 'configs/tle9877_lin_mock.json')

    def session(self, scenario=None, driver_type=MockLINMaster):
        scenario = deepcopy(scenario or self.scenario)
        clock = MockClock()
        driver = driver_type(scenario['steps'], clock)
        result = exchange_schedule(driver, clock, scenario)
        return result, driver, clock

    def test_reference_schedule_and_wire_values_without_wall_sleep(self):
        with patch('time.sleep', side_effect=AssertionError('mock must not wait on wall time')):
            result, driver, clock = self.session()
        self.assertEqual(result['status'], 'passed')
        exchanges = [e for e in result['journal'] if e['event'] == 'exchange']
        self.assertEqual([e['id'] for e in exchanges], [39, 38, 37, 38, 37])
        self.assertEqual(exchanges[1]['raw']['pid'], 0xA6)
        self.assertEqual(exchanges[1]['raw']['data'], [0x64, 0])
        self.assertEqual(exchanges[1]['raw']['checksum'], 0xF4)
        self.assertEqual(exchanges[2]['decoded']['signals']['Voltage']['value'], 9)
        for entry, expected in zip(exchanges, [0, .001, .011, .021, .031]):
            self.assertAlmostEqual(entry['actual_start_time_s'], expected, places=12)
        self.assertAlmostEqual(clock.monotonic(), .041, places=12)
        self.assertEqual(result['ldf_schedule']['cycle_s'], .02)
        self.assertEqual(result['clock_synchronization'], 'not_established')
        self.assertEqual(driver.calls[-1]['operation'], 'close')
        self.assertFalse(driver.is_open)

    def test_timeout_retains_attempt_and_does_not_retry_or_send_implicit_stop(self):
        self.scenario['steps'][2]['outcome'] = 'timeout'
        result, driver, _ = self.session()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['error']['code'], 'LINTimeout')
        self.assertEqual([c['operation'] for c in driver.calls],
                         ['open', 'wake_up', 'request', 'publish', 'request', 'close'])
        failed = [e for e in result['journal'] if e.get('status') == 'failed']
        self.assertEqual(failed[0]['id'], 37)
        self.assertNotIn('raw', failed[0])
        self.assertAlmostEqual(failed[0]['completed_time_s'] - failed[0]['actual_start_time_s'], .008)

    def test_bad_checksum_pid_and_length_preserve_received_bytes(self):
        for replacement, message in [({'checksum': 0}, 'checksum'), ({'pid': 0xA5}, 'parity'),
                                     ({'data': '64 64 5A 50 0A 00 00'}, 'exactly')]:
            with self.subTest(replacement=replacement):
                scenario = deepcopy(self.scenario)
                scenario['steps'][2].update(replacement)
                result, driver, _ = self.session(scenario)
                self.assertEqual(result['status'], 'failed')
                self.assertIn(message, result['error']['message'])
                entry = [e for e in result['journal'] if e.get('status') == 'failed'][0]
                self.assertIn('raw', entry)
                self.assertNotIn('decoded', entry)
                self.assertEqual(driver.calls[-1]['operation'], 'close')

    def test_script_detects_wrong_transmit_bytes_independently(self):
        self.scenario['steps'][1]['expected_data'] = '63 00'
        result, driver, _ = self.session()
        self.assertEqual(result['status'], 'failed')
        self.assertIn('independent expected vector', result['error']['message'])
        self.assertEqual(sum(c['operation'] == 'request' for c in driver.calls), 1)

    def test_disconnect_open_failure_and_close_failure_are_recorded(self):
        self.scenario['steps'][0]['outcome'] = 'transport_error'
        result, driver, _ = self.session()
        self.assertEqual(result['error']['code'], 'LINTransportError')
        self.assertFalse(driver.is_open)

        class BrokenOpen(MockLINMaster):
            def open(self, **kwargs):
                raise LINTransportError('partial open failed')

        result, driver, _ = self.session(driver_type=BrokenOpen)
        self.assertEqual(result['error']['message'], 'partial open failed')
        self.assertEqual(driver.calls, [{'operation': 'close'}])

        class BrokenClose(MockLINMaster):
            def close(self):
                super().close()
                raise LINTransportError('close failed')

        result, _, _ = self.session(driver_type=BrokenClose)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['journal'][-1]['event'], 'close_error')

    def test_misbehaving_driver_timeout_stops_before_next_frame(self):
        class Overrun(MockLINMaster):
            def request(self, *args, **kwargs):
                frame = super().request(*args, **kwargs)
                if args[0] == 37:
                    self.clock.advance(.008)
                return frame

        result, driver, _ = self.session(driver_type=Overrun)
        self.assertEqual(result['status'], 'failed')
        self.assertIn('timeout', result['error']['message'])
        self.assertEqual(sum(c['operation'] == 'publish' for c in driver.calls), 1)

    def test_optional_version_and_wake_up_can_be_omitted(self):
        self.scenario.update(read_version=False, wake_up=False, cycles=1)
        self.scenario['steps'] = self.scenario['steps'][1:3]
        result, driver, clock = self.session()
        self.assertEqual(result['status'], 'passed')
        self.assertEqual([c['operation'] for c in driver.calls], ['open', 'publish', 'request', 'close'])
        self.assertAlmostEqual(clock.monotonic(), .02, places=12)

    def test_late_schedule_wake_up_does_not_start_a_late_frame(self):
        class LateClock(MockClock):
            def sleep_until(self, deadline_s):
                super().sleep_until(deadline_s)
                if deadline_s > 0:
                    self.advance(.001)

        self.scenario['read_version'] = False
        self.scenario['steps'] = self.scenario['steps'][1:]
        clock = LateClock()
        driver = MockLINMaster(self.scenario['steps'], clock)
        result = exchange_schedule(driver, clock, self.scenario)
        self.assertEqual(result['status'], 'failed')
        self.assertIn('frame not started', result['error']['message'])
        self.assertEqual([c['operation'] for c in driver.calls], ['open', 'wake_up', 'publish', 'close'])

    def test_driver_receive_error_is_preserved_even_when_bytes_decode(self):
        class BadStatus(MockLINMaster):
            def request(self, *args, **kwargs):
                return replace(super().request(*args, **kwargs), driver_status='framing_error')

        result, driver, _ = self.session(driver_type=BadStatus)
        self.assertEqual(result['status'], 'failed')
        entry = [e for e in result['journal'] if e.get('status') == 'failed'][0]
        self.assertEqual(entry['raw']['driver_status'], 'framing_error')
        self.assertNotIn('decoded', entry)
        self.assertEqual(driver.calls[-1]['operation'], 'close')

    def test_invalid_scenario_is_rejected_before_creating_a_package(self):
        for key, value in [('cycles', True), ('cycles', 101), ('response_timeout_s', .01),
                           ('scope', 'physical_hil'), ('wake_up', 1)]:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as folder:
                scenario = deepcopy(self.scenario)
                scenario[key] = value
                source = Path(folder) / 'bad.json'
                source.write_text(json.dumps(scenario), encoding='utf-8')
                output = Path(folder) / 'result'
                with self.assertRaises(ValueError):
                    run_mock_scenario(source, output)
                self.assertFalse(output.exists())
        self.scenario['steps'][0]['delay_s'] = -1
        with self.assertRaises(ValueError):
            validate_scenario(self.scenario)

    def test_package_raw_log_hashes_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'session'
            result = run_mock_scenario(PROJECT / 'configs/tle9877_lin_mock.json', output)
            self.assertEqual(result['status'], 'passed')
            self.assertFalse(result['sent_to_hardware'])
            self.assertEqual(result['physical_validation_status'], 'not_evaluated')
            for name, digest in result['input_and_log_sha256'].items():
                self.assertEqual(sha256(output / name), digest)
            log = [json.loads(line) for line in (output / 'bus.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual(log[-1]['event'], 'closed')
            before = sha256(output / 'bus.jsonl')
            with self.assertRaises(FileExistsError):
                run_mock_scenario(PROJECT / 'configs/tle9877_lin_mock.json', output)
            self.assertEqual(sha256(output / 'bus.jsonl'), before)

    def test_cli_normal_and_failed_bus_sessions_keep_experiment_status_null(self):
        with tempfile.TemporaryDirectory() as folder:
            for name, outcome, expected in [('normal', 'ok', 0), ('timeout', 'timeout', 1)]:
                scenario = deepcopy(self.scenario)
                scenario['steps'][0]['outcome'] = outcome
                source = Path(folder) / (name + '.json')
                source.write_text(json.dumps(scenario), encoding='utf-8')
                out = io.StringIO()
                with redirect_stdout(out), redirect_stderr(io.StringIO()):
                    code = main(['lin-mock', '--scenario', str(source), '--output-dir', str(Path(folder) / name), '--json'])
                response = json.loads(out.getvalue())
                self.assertEqual(code, expected)
                self.assertEqual(response['command'], 'lin-mock')
                self.assertIsNone(response['experiment_status'])
                self.assertIsNone(response['record_status'])
                self.assertFalse(response['result']['sent_to_hardware'])
                self.assertIn('bus.jsonl', response['artifacts'])


if __name__ == '__main__':
    unittest.main()
