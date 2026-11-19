import copy
import unittest

import numpy as np

from typhoon_lab.pmsm_calibration import healthy_reference, phase_change, sign_check
from typhoon_lab.pmsm_evidence_qualification import EVIDENCE_CANDIDATES, SCORERS, _matched_pairs, _summarize


class EvidenceQualificationTests(unittest.TestCase):
    def test_relative_phase_change_ignores_individual_probe_signs(self):
        healthy = np.exp(2j * np.pi * np.arange(3) / 3)
        fault = healthy * np.array([1.10, 0.92, 1.02]) * np.exp(1j * np.array([0.25, 0, 0]))
        reference = healthy_reference({10: healthy, 30: healthy * np.exp(0.5j)})
        reversed_signs = np.array([1, -1, -1])
        expected = phase_change(fault, reference)
        self.assertGreater(expected[1], 0)
        self.assertGreater(expected[2], 0)
        np.testing.assert_allclose(phase_change(fault * reversed_signs * np.exp(0.7j), reference), expected)
        reversed_reference = healthy_reference({10: healthy, 30: -healthy})
        np.testing.assert_allclose(phase_change(fault, reversed_reference), expected)

    def test_candidate_is_fitted_only_on_health_reference_windows(self):
        native = np.exp(2j * np.pi * np.arange(3) / 3)
        reversed_first = native * np.array([-1, 1, 1])
        signs, check = sign_check({10: reversed_first, 30: reversed_first, 60: native, 90: native})
        self.assertEqual(signs, (-1, 1, 1))
        self.assertEqual(check["check_windows_agree"], 0)
        self.assertGreater(check["check_adjusted_median"], check["check_native_median"])

    def test_historical_scores_cannot_override_development_gate(self):
        best = {"net_gain": 2, "correct_by_fault": {"interturn": 4, "intercoil": 4}}
        inadequate = {"net_gain": 2, "correct_by_fault": {"interturn": 3, "intercoil": 5}}
        folds = []
        for motor in (1000, 1500, 3000):
            folds.append({"test_motor_w": motor, "scores": {
                name: {scorer: copy.deepcopy(best if motor == 3000 else inadequate) for scorer in SCORERS}
                for name in EVIDENCE_CANDIDATES
            }})
        measured = {str(motor): {"records": []} for motor in (1000, 1500, 3000)}
        self.assertEqual(_summarize(measured, folds)["decision"], "evidence_screen_not_met")
        for fold in folds[:2]:
            for scorer in SCORERS:
                fold["scores"]["phase_reference"][scorer] = best
        self.assertEqual(_summarize(measured, folds)["passing_candidates"], ["phase_reference"])

    def test_pairs_share_the_published_bypass_setting(self):
        rows = [
            {"label": label, "severity_pct": str(level * multiplier)}
            for label, multiplier in (("interturn", 1), ("intercoil", 2))
            for level in range(7, 0, -1)
        ]
        scaled = np.arange(14).reshape(14, 1)
        pairs = _matched_pairs(rows, scaled)
        self.assertEqual(len(pairs), 7)
        self.assertEqual(next(pair["indices"] for pair in pairs if pair["bypass_ohm"] == 6), [6, 13])
        self.assertEqual(next(pair["indices"] for pair in pairs if pair["bypass_ohm"] == 0.5), [0, 7])
