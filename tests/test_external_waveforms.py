"""External intake invariants: numerical meaning, provenance, and CLI status."""
from copy import deepcopy
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from typhoon_lab.cli import main
from typhoon_lab.external_waveforms import analyze_dataset, validate_intake, features
from typhoon_lab.external_records import analyze_external, verify_external
from typhoon_lab.utils import write_json, sha256


def fixture(name="stranger.csv", method="dip", time_unit="ms", value_unit="mV"):
    def known(value):
        return {"value": value, "status": "confirmed", "source": "synthetic test definition"}
    analysis = {"method": method, "window": None}
    if method in {"dip", "rise"}:
        analysis["baseline_fraction"] = .2
    if method == "dip":
        analysis["drop_fraction"] = .05
    if method == "rise":
        analysis.update(low_fraction=.1, high_fraction=.9)
    return {"schema_version": 1, "dataset_id": "unfamiliar", "purpose": "offline description",
            "records": [{"id": "signal", "csv": name,
                         "format": {"encoding": "utf-8-sig", "header": False, "time_column": 0, "value_column": 1},
                         "metadata": {"time_unit": known(time_unit), "value_unit": known(value_unit)},
                         "analysis": analysis}]}


class ExternalWaveformTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.source = self.base / "source"
        self.source.mkdir()
        self.data = fixture()
        self.path = self.base / "intake.json"
        self.csv = self.source / "stranger.csv"
        self.csv.write_text("0,5000\n1,5000\n2,4000\n3,4000\n4,5000\n5,5000\n", encoding="utf-8")

    def make_record(self, name="record"):
        write_json(self.path, self.data)
        out = self.base / name
        result = analyze_external(self.path, self.source, out)
        return out, result

    def invoke(self, args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([*args, "--json"])
        return code, json.loads(stdout.getvalue())

    def test_unfamiliar_name_unit_conversion_and_exact_dip(self):
        profile, _ = analyze_dataset(self.source, validate_intake(self.data))
        rec = profile["records"][0]
        self.assertEqual(rec["units"], {"time": "s", "value": "V"})
        self.assertAlmostEqual(rec["dt_median_s"], .001)
        self.assertEqual(rec["feature"]["baseline"], 5)
        self.assertEqual(rec["feature"]["max_drop"], 1)
        self.assertEqual(rec["feature"]["longest_segment"]["sample_count"], 2)
        self.assertAlmostEqual(rec["feature"]["longest_segment"]["sample_support_duration_s"], .002)

    def test_header_and_reversed_columns_with_current_units(self):
        self.csv.write_text("current,time\n100,0\n200,1\n300,2\n", encoding="utf-8")
        rec = self.data["records"][0]
        rec["format"].update(header=True, time_column=1, value_column=0)
        rec["metadata"]["value_unit"]["value"] = "mA"
        rec["analysis"] = {"method": "summary"}
        profile, _ = analyze_dataset(self.source, validate_intake(self.data))
        self.assertAlmostEqual(profile["records"][0]["mean"], .2)
        self.assertEqual(profile["records"][0]["units"]["value"], "A")

    def test_corrupt_csv_is_recorded_without_repair(self):
        cases = [("0,1,2\n1,2,3\n2,3,4\n", "two columns"),
                 ("0,1\n1,nan\n2,3\n", "nonfinite"),
                 ("0,1\n0,2\n2,3\n", "strictly increasing"),
                 ("0,1\n2,2\n1,3\n", "strictly increasing"),
                 ("0,1\n1,2\n3,3\n", "nonuniform"),
                 ("0,1\n\n2,3\n", "two columns"),
                 ("0,1\n1,2\n", "three samples")]
        for text, reason in cases:
            with self.subTest(reason=reason, text=text):
                self.csv.write_text(text, encoding="utf-8")
                before = sha256(self.csv)
                profile, _ = analyze_dataset(self.source, self.data)
                self.assertEqual(profile["data_quality_status"], "failed")
                self.assertIn(reason, profile["records"][0]["error"])
                self.assertEqual(sha256(self.csv), before)

    def test_unknown_units_allow_structure_but_no_physical_features(self):
        self.data["records"][0]["metadata"]["value_unit"] = {"value": None, "status": "unconfirmed", "source": ""}
        out, result = self.make_record()
        self.assertEqual(result["status"], "failed")
        profile = json.loads((out / "profile.json").read_text(encoding="utf-8"))
        self.assertEqual(profile["data_quality_status"], "passed")
        self.assertEqual(profile["records"][0]["feature"]["status"], "not_evaluated")
        self.assertNotIn("mean", profile["records"][0])
        self.assertEqual(verify_external(out)["record_status"], "passed")

    def test_window_and_inapplicable_rise(self):
        rec = self.data["records"][0]
        rec["analysis"] = {"method": "rise", "baseline_fraction": .2, "low_fraction": .1, "high_fraction": .9}
        profile, _ = analyze_dataset(self.source, self.data)
        self.assertEqual(profile["records"][0]["feature"]["status"], "not_applicable")
        rec["analysis"] = {"method": "summary", "window": [99, 100]}
        profile, _ = analyze_dataset(self.source, self.data)
        self.assertEqual(profile["records"][0]["feature"]["status"], "not_applicable")

    def test_resolved_rise_and_single_sample_edge(self):
        analysis = {"method": "rise", "baseline_fraction": .1, "low_fraction": .1, "high_fraction": .9}
        t = np.arange(11, dtype=float)
        result = features(t, np.arange(11, dtype=float), analysis)
        self.assertEqual(result["first_crossing_interval_s"], 8)
        self.assertEqual(result["max_drawdown"], 0)
        y = np.array([0] * 5 + [10] * 6)
        self.assertEqual(features(t, y, analysis)["status"], "not_applicable")

    def test_intake_rejects_wrong_format_method_parameters_and_paths(self):
        modifications = [
            lambda r: r.update(csv="../outside.csv"),
            lambda r: r.update(csv="C:/outside.csv"),
            lambda r: r["format"].update(value_column=2),
            lambda r: r["analysis"].update(method="CAN"),
            lambda r: r["analysis"].update(drop_fraction=2),
            lambda r: r["analysis"].update(window=[2, 1]),
            lambda r: r["metadata"]["time_unit"].update(value="minutes"),
            lambda r: r["metadata"]["time_unit"].update(source=""),
        ]
        for change in modifications:
            data = deepcopy(self.data)
            change(data["records"][0])
            with self.assertRaises(ValueError):
                validate_intake(data)
        data = deepcopy(self.data)
        data["records"].append(deepcopy(data["records"][0]))
        with self.assertRaises(ValueError):
            validate_intake(data)

    def test_missing_input_and_output_overlap_do_not_write(self):
        write_json(self.path, self.data)
        self.csv.rename(self.csv.with_suffix(".bak"))
        with self.assertRaisesRegex(ValueError, "missing input"):
            analyze_external(self.path, self.source, self.base / "missing")
        self.assertFalse((self.base / "missing").exists())
        with self.assertRaisesRegex(ValueError, "non-nested"):
            analyze_external(self.path, self.source, self.source / "output")

    def test_portable_readonly_verification_without_original_sources(self):
        before = sha256(self.csv)
        out, result = self.make_record()
        self.assertIsNone(result["record_status"])
        self.assertEqual(sha256(self.csv), before)
        self.source.rename(self.base / "moved-source")
        moved = self.base / "中文 搬迁"
        shutil.copytree(out, moved)
        hashes_before = {p.relative_to(moved): sha256(p) for p in moved.rglob("*") if p.is_file()}
        check = verify_external(moved)
        self.assertEqual(check["record_status"], "passed", check)
        self.assertEqual(check["performance_status"], "not_evaluated")
        self.assertEqual(hashes_before, {p.relative_to(moved): sha256(p) for p in moved.rglob("*") if p.is_file()})
        self.assertFalse((moved / "verification.json").exists())
        self.assertEqual(verify_external(moved, write=True)["status"], "passed")
        self.assertTrue((moved / "verification.json").is_file())
        self.assertEqual(verify_external(moved)["status"], "passed")

    def test_existing_output_and_original_bytes_preserved(self):
        out, _ = self.make_record()
        original = {p.relative_to(out): sha256(p) for p in out.rglob("*") if p.is_file()}
        with self.assertRaisesRegex(ValueError, "must be new"):
            analyze_external(self.path, self.source, out)
        self.assertEqual(original, {p.relative_to(out): sha256(p) for p in out.rglob("*") if p.is_file()})

    def test_corrupt_input_has_valid_failure_record(self):
        self.csv.write_text("0,1\n0,2\n2,3\n", encoding="utf-8")
        out, result = self.make_record()
        self.assertEqual(result["data_quality_status"], "failed")
        check = verify_external(out)
        self.assertEqual(check["record_status"], "passed", check)
        self.assertEqual(check["data_quality_status"], "failed")

    def test_changed_input_code_and_missing_required_hash_detected(self):
        out, _ = self.make_record()
        for rel in ("inputs/signal/csv.csv", "code_snapshot/external_waveforms.py", "report.md"):
            with self.subTest(rel=rel):
                p = out / rel
                original = p.read_bytes()
                p.write_bytes(original + b"\nchanged")
                self.assertEqual(verify_external(out)["record_status"], "failed")
                p.write_bytes(original)
        manifest_path = out / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        del manifest["artifacts"]["report.md"]
        write_json(manifest_path, manifest)
        self.assertIn("required artifact not hashed: report.md", verify_external(out)["problems"])

    def test_recomputation_detects_wrong_metric_even_after_rehash(self):
        out, _ = self.make_record()
        profile_path = out / "profile.json"
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        profile["records"][0]["feature"]["max_drop"] = 2
        write_json(profile_path, profile)
        manifest_path = out / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["artifacts"]["profile.json"] = sha256(profile_path)
        write_json(manifest_path, manifest)
        check = verify_external(out)
        self.assertTrue(any("feature.max_drop" in p for p in check["problems"]), check)

    def test_unknown_version_skips_recomputation(self):
        out, _ = self.make_record()
        path = out / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["analysis_method_version"] = 999
        write_json(path, manifest)
        with patch("typhoon_lab.external_records.analyze_dataset", side_effect=AssertionError("must not recompute")):
            check = verify_external(out)
        self.assertEqual(check["record_status"], "failed")
        self.assertTrue(any("unsupported" in p for p in check["problems"]))

    def test_cli_json_status_no_simulator_and_explicit_write(self):
        write_json(self.path, self.data)
        out = self.base / "cli-result"
        with patch("typhoon_lab.runtime.api_modules", side_effect=AssertionError("no simulator")):
            code, value = self.invoke(["analyze-waveforms", "--intake", str(self.path),
                                       "--input-dir", str(self.source), "--output-dir", str(out)])
            self.assertEqual(code, 0, value)
            self.assertIsNone(value["record_status"])
            self.assertIsNone(value["experiment_status"])
            self.assertEqual(value["result"]["performance_status"], "not_evaluated")
            code, value = self.invoke(["verify-waveforms", "--run-dir", str(out)])
            self.assertEqual(code, 0, value)
            self.assertEqual(value["record_status"], "passed")
            self.assertIsNone(value["experiment_status"])
            self.assertFalse((out / "verification.json").exists())
            code, value = self.invoke(["verify-waveforms", "--run-dir", str(out), "--write"])
            self.assertEqual(code, 0, value)
            self.assertTrue((out / "verification.json").exists())

    def test_cli_invalid_arguments_and_generic_verify(self):
        code, value = self.invoke(["analyze-waveforms"])
        self.assertEqual(code, 2)
        self.assertEqual(value["error"]["stage"], "arguments")
        out, _ = self.make_record()
        code, value = self.invoke(["verify", "--run-dir", str(out)])
        self.assertEqual(code, 0, value)
        self.assertEqual(value["record_status"], "passed")
        self.assertIsNone(value["experiment_status"])


if __name__ == "__main__":
    unittest.main()
