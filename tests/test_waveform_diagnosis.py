"""Recognition must depend on sampled evidence, with invalid/ambiguous cases preserved."""
from copy import deepcopy
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from typhoon_lab.cli import main
from typhoon_lab.external_records import analyze_external
from typhoon_lab.external_waveforms import analyze_dataset
from typhoon_lab.utils import PROJECT, sha256, write_json
from typhoon_lab.waveform_diagnosis import (classify, diagnose, run_diagnosis, attach_explanation,
                                           validate_explanation, validate_rules, verify_diagnosis)


class DiagnosisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.raw = self.base / "raw"
        self.raw.mkdir()
        self.rules = json.loads((PROJECT / "configs/tu_diagnosis_rules.json").read_text(encoding="utf-8"))
        self.rules["minimum_duration_s"] = 2e-8
        self.rules_path = self.base / "rules.json"
        write_json(self.rules_path, self.rules)
        meta = lambda v: {"value": v, "status": "confirmed", "source": "synthetic definition"}
        self.rec = {"id": "anonymous", "csv": "unfamiliar.csv",
                    "format": {"encoding": "utf-8-sig", "header": False, "time_column": 0, "value_column": 1},
                    "metadata": {"time_unit": meta("s"), "value_unit": meta("V")},
                    "analysis": {"method": "dip", "window": None, "baseline_fraction": .1, "drop_fraction": .05}}
        self.intake = {"schema_version": 1, "dataset_id": "synthetic", "purpose": "test", "records": [self.rec]}
        self.t = np.arange(101) * 1e-8

    def prediction(self, y):
        np.savetxt(self.raw / self.rec["csv"], np.column_stack([self.t, y]), delimiter=",")
        profile, arrays = analyze_dataset(self.raw, self.intake)
        r = profile["records"][0]
        return classify(r, arrays.get(r["id"]), self.rules)

    def source(self):
        y = np.full(101, 5.)
        y[40:60] = 4.
        self.prediction(y)
        write_json(self.base / "intake.json", self.intake)
        analyze_external(self.base / "intake.json", self.raw, self.base / "source")
        return self.base / "source"

    def test_plateau_dip_location_and_duration(self):
        y = np.full(101, 5.)
        y[40:60] = 4.
        r = self.prediction(y)
        self.assertEqual(r["classification"], "abnormal")
        self.assertEqual(len(r["events"]), 1)
        e = r["events"][0]
        self.assertEqual(e["sample_count"], 20)
        self.assertAlmostEqual(e["first_sample_s"], 4e-7)
        self.assertAlmostEqual(e["last_sample_s"], 5.9e-7)
        self.assertAlmostEqual(e["sample_support_duration_s"], 2e-7)
        self.assertEqual(r["evidence"]["max_deviation"], 1)

    def test_short_spike_and_exact_amplitude_boundary_not_reported(self):
        y = np.full(101, 5.)
        y[50] = 3.
        self.assertEqual(self.prediction(y)["classification"], "normal")
        y[40:60] = 4.75
        y[50] = 4.75
        self.assertEqual(self.prediction(y)["classification"], "normal")
        y[40:42] = 4.
        self.assertEqual(self.prediction(y)["events"][0]["sample_count"], 2)

    def test_normal_and_abnormal_rising_shape(self):
        self.rec["analysis"] = {"method": "rise", "window": None, "baseline_fraction": .1,
                                "low_fraction": .1, "high_fraction": .9}
        y = np.linspace(0, 5, 101)
        self.assertEqual(self.prediction(y)["classification"], "normal")
        y[45:55] -= 1.5
        r = self.prediction(y)
        self.assertEqual(r["classification"], "abnormal")
        self.assertAlmostEqual(r["evidence"]["max_deviation"], 1.45)
        self.assertGreater(len(r["events"]), 0)

    def test_no_label_or_file_name_leakage(self):
        source = self.source()
        a = diagnose(source, self.rules)
        changed = deepcopy(self.rules)
        changed["label_context"]["expected_labels"] = {"anonymous": "normal"}
        b = diagnose(source, changed)
        self.assertEqual(a["records"], b["records"])
        intake = json.loads((source / "intake.json").read_text(encoding="utf-8"))
        old = source / intake["records"][0]["csv"]
        old.rename(source / "renamed.csv")
        intake["records"][0].update(id="other_id", csv="renamed.csv")
        write_json(source / "intake.json", intake)
        c = diagnose(source, changed)
        c["records"][0]["id"] = a["records"][0]["id"]
        self.assertEqual(a["records"], c["records"])

    def test_missing_units_coarse_sampling_and_unsupported_method_inconclusive(self):
        self.rec["metadata"]["value_unit"]["status"] = "unconfirmed"
        self.assertEqual(self.prediction(np.full(101, 5.))["classification"], "inconclusive")
        self.rec["metadata"]["value_unit"]["status"] = "confirmed"
        self.t *= 100
        self.assertEqual(self.prediction(np.full(101, 5.))["classification"], "inconclusive")
        self.rec["analysis"] = {"method": "summary", "window": None}
        self.assertEqual(self.prediction(np.full(101, 5.))["classification"], "inconclusive")

    def test_invalid_data_not_classified_normal(self):
        self.t[50] = self.t[49]
        self.assertEqual(self.prediction(np.full(101, 5.))["classification"], "inconclusive")

    def test_rule_validation_rejects_nonfinite_or_invalid_thresholds(self):
        for key, value in [("minimum_duration_s", 0), ("dip_fraction", True),
                           ("rise_drawdown_fraction", float("nan")), ("dip_fraction", 1)]:
            r = deepcopy(self.rules)
            r[key] = value
            with self.assertRaises(ValueError):
                validate_rules(r)

    def test_bundle_response_import_portability_tamper_and_cli(self):
        source = self.source()
        out = self.base / "diagnosis"
        run_diagnosis(source, self.rules_path, out)
        self.assertEqual(verify_diagnosis(out)["record_status"], "passed")
        req = json.loads((out / "llm_request.json").read_text(encoding="utf-8"))
        answer = {"schema_version": 1, "request_sha256": sha256(out / "llm_request.json"),
                  "provider": "synthetic", "model": "test fixture", "transport": "test", "context": "unit test",
                  "records": [{"id": "anonymous", "classification": "abnormal", "cause_status": "undetermined",
                               "summary": "Synthetic example explanation.", "evidence_keys": ["max_deviation", "events"]}]}
        for field, value in [("classification", "normal"), ("cause_status", "confirmed"),
                             ("evidence_keys", ["invented"])]:
            bad = deepcopy(answer)
            bad["records"][0][field] = value
            with self.assertRaises(ValueError):
                validate_explanation(bad, req, answer["request_sha256"])
        bad = deepcopy(answer)
        bad["request_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            validate_explanation(bad, req, answer["request_sha256"])
        write_json(self.base / "response.json", answer)
        final = self.base / "explained"
        attach_explanation(out, self.base / "response.json", final)
        moved = self.base / "moved"
        final.rename(moved)
        self.assertEqual(verify_diagnosis(moved)["record_status"], "passed")
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
            code = main(["verify-diagnosis", "--run-dir", str(moved), "--json"])
        envelope = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertIsNone(envelope["experiment_status"])
        self.assertEqual(envelope["record_status"], "passed")
        (moved / "source/inputs/anonymous/csv.csv").write_text("changed", encoding="utf-8")
        self.assertEqual(verify_diagnosis(moved)["record_status"], "failed")
        with self.assertRaises(ValueError):
            run_diagnosis(source, self.rules_path, source / "nested")

