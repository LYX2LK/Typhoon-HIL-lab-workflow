import unittest
from pathlib import Path

from typhoon_lab.adapters import get_adapter
from typhoon_lab.config import load_config, validate_config


class FeedbackComparisonTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.config = load_config(root / 'configs/pmsm_feedback/normal.json')
        self.config.update(model='pmsm_feedback_comparison',
                           fault=dict(kind='feedback_comparison', at_s=.4, bias_rpm=0, bias_a=0))

    def test_all_conditions_share_the_same_physical_measurements(self):
        for speed, current in ((0, 0), (150, 0), (0, 3)):
            self.config['fault'].update(bias_rpm=speed, bias_a=current)
            config = validate_config(self.config)
            adapter = get_adapter(config['model'])
            self.assertEqual(len(adapter.columns), len(set(adapter.signals)))
            self.assertTrue({'SpeedFeedback_rad_s', 'MechanicalSpeed_rad_s',
                             'IqRaw_A', 'IqFeedback_A'} <= set(adapter.columns))

    def test_simultaneous_injections_and_off_grid_onsets_are_rejected(self):
        for speed, current, onset in ((150, 3, .4), (0, 0, .400023)):
            self.config['fault'].update(bias_rpm=speed, bias_a=current, at_s=onset)
            with self.assertRaises(ValueError):
                validate_config(self.config)
