import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

import numpy as np

from typhoon_lab.kaist_pmsm import ARCHIVES, LABELS, OBSERVATIONS, _current_features, _vibration_features, inspect_archives
from typhoon_lab.pmsm_diagnosis_comparison import freeze_comparison, holdout_cases, run_comparison, verify_comparison
from typhoon_lab.pmsm_evidence_policy import (
    classify_answer, make_calibration, request_for, rule_session, session, tune_stop,
)
from typhoon_lab.utils import sha256, write_json


class MeasuredComparisonTests(unittest.TestCase):
    def setUp(self):
        self.recordings = [
            {"motor_w": motor, "label": label, "severity_pct": "2.30", "observations": {
                bundle: {key: 0.1 + i * (0.6 + 0.1 * j) for j, key in enumerate(features)}
                for bundle, features in OBSERVATIONS.items()
            }}
            for motor in (1000, 1500) for i, label in enumerate(LABELS)
        ]
        self.calibration = make_calibration(self.recordings)
        self.case = {"task_id": "K01", "observations": self.recordings[1]["observations"]}
        self.answer = {
            "decision": "undetermined", "action": "Q1", "evidence_ids": ["I0"],
            "reason": "Check normalized sequence amplitude.",
            "prediction": {"feature": "sequence_minor_major", "higher": "interturn", "lower": "healthy"},
        }

    def test_archive_inventory_handles_publisher_vibration_alias_and_keeps_source_digest(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            receipt = []
            for motor, name in ARCHIVES.items():
                archive = root / name
                with ZipFile(archive, "w") as bundle:
                    for sensor in ("current", "vibration"):
                        for label in ("interturn", "intercoil"):
                            native = "coil" if sensor == "vibration" and label == "intercoil" else label
                            bundle.writestr(f"{sensor}/{motor}W_0_00_{sensor}_{native}.tdms", b"alias")
                    bundle.writestr(f"current/{motor}W_1.01_current_intercoil.tdms", b"fault")
                    bundle.writestr(f"vibration/{motor}W_1_01_vibration_coil.tdms", b"waveform")
                receipt.append({"filename": name,
                                "content_details": {"size": archive.stat().st_size, "sha256_hash": sha256(archive)}})
            (root / "repository-files.json").write_text(json.dumps(receipt), encoding="utf-8")
            result = inspect_archives(root)
            group, fault = result["motors"]["3000"]["conditions"]
            self.assertEqual(group["label"], "healthy")
            self.assertEqual([len(group[sensor]) for sensor in ("current", "vibration")], [2, 2])
            self.assertEqual(fault["severity_pct"], "1.01")
            self.assertEqual([len(fault[sensor]) for sensor in ("current", "vibration")], [1, 1])
            with (root / ARCHIVES[3000]).open("ab") as dst:
                dst.write(b"changed")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                inspect_archives(root)

    def test_observations_distinguish_harmonics_orders_and_sequence(self):
        current_time = np.arange(200_000) / 100_000
        phases = np.arange(3).reshape(-1, 1) * (2 * np.pi / 3)
        waveform = np.sin(2 * np.pi * 200 * current_time - phases)
        waveform += 0.15 * np.sin(2 * np.pi * 1000 * current_time - phases)
        result = _current_features(waveform)
        self.assertAlmostEqual(result["electrical_fundamental_hz"], 200)
        self.assertAlmostEqual(result["current_h5_ratio"], 0.15, places=5)
        self.assertLess(result["sequence_minor_major"], 1e-6)
        vibration_time = np.arange(51_200) / 25_600
        measured = _vibration_features(np.sin(2 * np.pi * 150 * vibration_time))
        self.assertGreater(measured["vibration_3x_share"], 0.999)
        self.assertLess(measured["vibration_1x_share"], 1e-8)

    def test_invalid_repeated_and_excess_queries_consume_only_the_available_budget(self):
        outcome = session(self.case, self.calibration, lambda *_: (self.answer, None))
        self.assertEqual([entry["status"] for entry in outcome["trace"]],
                         ["query", "repeated_query", "budget_exhausted"])
        self.assertEqual(outcome["queries"], 2)
        self.assertEqual(outcome["valid_queries"], 1)
        self.assertEqual(outcome["invalid_actions"], 2)

    def test_hidden_cases_do_not_expose_truth_or_measurements(self):
        cases = holdout_cases(self.recordings)
        self.assertEqual(len(cases), len(self.recordings) + len(LABELS))
        hidden = [case for case in cases if case["masked"]]
        self.assertEqual({case["label"] for case in hidden}, set(LABELS))
        request = request_for(hidden[0], self.calibration, [], 2)
        self.assertNotIn("truth", request)
        self.assertNotIn("label", request)
        self.assertNotIn("recording_id", request)
        self.assertNotIn("severity_pct", request)
        self.assertIsNone(request["initial"])
        self.assertEqual(request["available_queries"], {})
        stop, _ = tune_stop(self.recordings, (1000, 1500))
        for method in ("fixed", "adaptive"):
            outcome = rule_session(hidden[0], self.calibration, stop, method)
            self.assertEqual(outcome["decision"], "undetermined")
            self.assertEqual(outcome["queries"], 0)

    def test_finishing_with_an_unobserved_citation_is_rejected(self):
        request = request_for(self.case, self.calibration, [], 2)
        unsupported = {"decision": "intercoil", "action": "finish", "reason": "", "prediction": None,
                       "evidence_ids": ["Q3"]}
        self.assertEqual(classify_answer(unsupported, request), "invalid_evidence")

    def test_frozen_comparison_replays_identical_scores_and_rejects_modified_results(self):
        def readings(_source, _inventory, motors, _workdir):
            baseline = self.recordings[:len(LABELS)]
            rows = [
                {**row, "motor_w": motor, "severity_pct": str(level),
                 "sensors": {"current": {"members": [{"sha256": f"{motor}-{row['label']}-{level}"}]}}}
                for motor in motors for row in baseline for level in (1, 2)
            ]
            return {"recordings": rows, "excluded": []}

        def fake_transport(folder, _service, system, request):
            answer = {"action": "finish", "decision": "undetermined", "reason": "Fixture",
                      "prediction": None, "evidence_ids": []}
            usage = {"prompt_tokens": 10, "completion_tokens": 6}
            response_id = str(folder)
            write_json(folder / "input.json", request)
            write_json(folder / "http_request.json", {
                "model": "test-service", "temperature": 0, "max_tokens": 1500,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(request)},
                ],
            })
            write_json(folder / "http_response.json", {
                "id": response_id, "model": "test-service", "usage": usage,
                "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(answer)}}],
            })
            write_json(folder / "model_call.json", {
                "status": "completed", "input_sha256": sha256(folder / "input.json"),
                "response_id": response_id, "returned_model": "test-service", "elapsed_s": 0.1, "usage": usage,
            })
            write_json(folder / "answer.json", answer)
            return answer

        module = "typhoon_lab.pmsm_diagnosis_comparison"
        with TemporaryDirectory() as folder:
            work = Path(folder)
            service = work / "service.json"
            write_json(service, {"model": "test-service", "max_tokens": 1500})
            result_dir = work / "run"
            with (patch(f"{module}.inspect_archives", return_value={"doi": "test"}),
                  patch(f"{module}.read_recordings", side_effect=readings) as reader,
                  patch(f"{module}.load_service"), patch(f"{module}.call_json", side_effect=fake_transport)):
                self.assertEqual(freeze_comparison(result_dir, work, service)["workflow_status"], "frozen")
                self.assertEqual(reader.call_args.args[2], (1000, 1500))
                self.assertEqual(run_comparison(result_dir, work, service)["workflow_status"], "completed")
                self.assertEqual(reader.call_args.args[2], (3000,))
                verified = verify_comparison(result_dir)
                self.assertEqual(verified["record_status"], "passed", verified)
                self.assertEqual(verified["sessions_replayed"], 45)
                self.assertFalse((result_dir / "verification.json").exists())
                (result_dir / "results.json").write_text("[]", encoding="utf-8")
                self.assertEqual(verify_comparison(result_dir)["record_status"], "failed")
