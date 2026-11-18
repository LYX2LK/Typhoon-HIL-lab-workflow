from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
import numpy as np

from typhoon_lab.config import load_config, validate_config
from typhoon_lab.pmsm_current_fault import PMSMCurrentFeedbackAdapter
from typhoon_lab.utils import PROJECT


class CurrentFaultTests(unittest.TestCase):
    def test_rejects_invalid_faults(self):
        base = load_config(PROJECT/'configs/pmsm_current_feedback/bias3.json')
        for key, value in [('bias_a', True), ('bias_a', float('nan')), ('bias_a', 6),
                           ('at_s', .40001), ('kind', 'phase_short')]:
            c = deepcopy(base); c['fault'][key] = value
            with self.assertRaises(ValueError):
                validate_config(c)

    def test_disconnected_bias_cannot_pass_and_both_signs_are_observed(self):
        adapter = PMSMCurrentFeedbackAdapter()
        t = np.arange(80000)/100000
        ref = np.where(t >= .20005, 2400, 1800)*np.pi/30
        load = np.full(len(t), .01); zero = np.zeros(len(t)); raw = np.full(len(t), 2.)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'waveforms.csv'
            for name in ('normal', 'bias3', 'bias_minus3'):
                c = load_config(PROJECT/f'configs/pmsm_current_feedback/{name}.json')
                bias = np.where(t >= .40005, c['fault']['bias_a'], 0.)
                for connected in (True, False):
                    used = raw + bias if connected else raw
                    a = np.column_stack((t,t,ref,zero,zero,zero,load,ref,load,raw,used,bias))
                    np.savetxt(path,a,delimiter=',',header=','.join(('t_relative_s','t_simulation_s',*adapter.columns)),comments='')
                    result = adapter.analyze(path,c)
                    self.assertEqual(result['fault_observation']['injection_verified'], connected or name=='normal')
