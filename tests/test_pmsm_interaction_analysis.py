"""Independent recovery edge cases, including re-entry and finite-horizon censoring."""
import importlib.util
from pathlib import Path
import unittest
import numpy as np

spec=importlib.util.spec_from_file_location('interaction_analysis',Path(__file__).resolve().parents[1]/'scripts/analyze_pmsm_interaction.py')
analysis=importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


class RecoveryTests(unittest.TestCase):
    def test_known_step_recovery_uses_last_exit_not_first_entry(self):
        t=np.arange(1001)/1000
        e=np.zeros(len(t));e[(t>=.2)&(t<.25)]=100
        e[(t>=.3)&(t<.31)]=-80
        result=analysis.recovery(t,e,.2)
        self.assertAlmostEqual(result['recovery_s'],.11)
        self.assertAlmostEqual(result['recovery_interval_s'][0],.109)

    def test_unrecovered_and_short_tail_are_censored(self):
        t=np.arange(1001)/1000;e=np.full(len(t),60.)
        self.assertTrue(analysis.recovery(t,e,.2)['recovery_censored'])
        e[t>=.99]=0
        self.assertIsNone(analysis.recovery(t,e,.2)['recovery_s'])

    def test_band_boundary_and_immediate_recovery(self):
        t=np.arange(1001)/1000;e=np.full(len(t),50.)
        self.assertEqual(analysis.recovery(t,e,.2)['recovery_s'],0.)
        with self.assertRaises(ValueError): analysis.recovery(t,e,1.1)


if __name__=='__main__': unittest.main()
