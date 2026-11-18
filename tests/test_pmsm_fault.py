"""A verified injection and a failed speed requirement are separate facts."""
from copy import deepcopy
import math
from pathlib import Path
import tempfile
import unittest
import numpy as np

from typhoon_lab.config import load_config, validate_config
from typhoon_lab.adapters import describe_capabilities
from typhoon_lab.pmsm_fault import PMSMFeedbackAdapter
from typhoon_lab.utils import PROJECT


class FeedbackFaultTests(unittest.TestCase):
    def test_kind_time_and_magnitude_boundaries(self):
        capability = describe_capabilities(PMSMFeedbackAdapter())
        self.assertEqual(capability['configuration_fields']['fault']['kind']['enum'], ['speed_feedback_bias'])
        self.assertEqual(len(capability['capture_signals']), 9)
        base = load_config(PROJECT / 'configs/pmsm_feedback/bias150.json')
        for key, value in [('bias_rpm', True), ('bias_rpm', 500), ('at_s', .40001), ('kind', 'arbitrary_code')]:
            c = deepcopy(base); c['fault'][key] = value
            with self.assertRaises(ValueError): validate_config(c)

    def make_data(self, path, config, disconnect=False):
        t = np.arange(80000) / 100000
        reference = np.where(t >= .20005, 2400., 1800.)
        bias = np.where(t >= .40005, config['fault']['bias_rpm'], 0.)
        true = reference - bias
        used = true if disconnect else true + bias
        zeros = np.zeros(len(t)); load = np.full(len(t), .01)
        columns = (t, t, true * math.pi / 30, zeros, zeros, zeros, load, reference * math.pi / 30, load,
                   used * math.pi / 30, bias * math.pi / 30)
        np.savetxt(path, np.column_stack(columns), delimiter=',',
                   header=','.join(('t_relative_s', 't_simulation_s', *PMSMFeedbackAdapter.columns)), comments='')

    def test_normal_passes_and_biased_true_speed_fails_while_injection_is_verified(self):
        adapter = PMSMFeedbackAdapter()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'waveforms.csv'
            for name, expected in [('normal', 'passed'), ('bias150', 'failed')]:
                c = load_config(PROJECT / f'configs/pmsm_feedback/{name}.json')
                self.make_data(path, c)
                result = adapter.analyze(path, c)
                self.assertEqual(result['status'], expected)
                self.assertTrue(result['fault_observation']['injection_verified'])
                if name == 'bias150':
                    self.assertAlmostEqual(result['fault_observation']['true_tracking_mean_error_rpm'], -150)
                    self.assertAlmostEqual(result['fault_observation']['used_feedback_mean_error_rpm'], 0)

    def test_recording_a_bias_without_its_feedback_effect_does_not_verify(self):
        c = load_config(PROJECT / 'configs/pmsm_feedback/bias150.json')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'waveforms.csv'
            self.make_data(path, c, disconnect=True)
            result = PMSMFeedbackAdapter().analyze(path, c)
            self.assertFalse(result['fault_observation']['injection_verified'])


if __name__ == '__main__': unittest.main()
