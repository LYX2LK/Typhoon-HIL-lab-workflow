"""Independent equations and synthetic records; actual Virtual HIL is separate."""
from copy import deepcopy
import csv
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from typhoon_lab.adapters.rectifier import RectifierAdapter
from typhoon_lab.config import validate_config
from typhoon_lab.rectifier_analysis import COLUMNS,analyze_rectifier,expected_rectifier
from typhoon_lab.rectifier_comparison import compare_metrics,recompute_comparison
from typhoon_lab.reporting import write_report
from typhoon_lab.cli import verify_run
from typhoon_lab.utils import write_json,finalize,sha256

ROOT=Path(__file__).resolve().parents[1]
CONFIG=json.loads((ROOT/"configs/rectifier_baseline.json").read_text(encoding="utf-8"))

class RectifierConfigTests(unittest.TestCase):
    def test_all_shipped_configs_share_steady_schema(self):
        for p in (ROOT/"configs").glob("rectifier_*.json"):
            c=validate_config(json.loads(p.read_text(encoding="utf-8")))
            self.assertEqual(c["schema_version"],1)
            self.assertFalse(RectifierAdapter.has_events)

    def test_invalid_values_unknown_fields_and_unsettled_window(self):
        for group,key,value in (("source","rms_v",True),("circuit","load_ohm",0),("capture","duration_s",.203),("capture","settle_s",.5),("acceptance","relative_ripple_error",.06),("acceptance","min_samples",2000.5)):
            c=deepcopy(CONFIG);c[group][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):validate_config(c)
        for key,value in (("schema_version",2),("events",[]),("backend","physical_hil")):
            c=deepcopy(CONFIG);c[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):validate_config(c)
        with self.assertRaises(ValueError):validate_config(CONFIG,sweep=True)

    def test_sampling_quantization_preserves_integer_cycles(self):
        adapter=RectifierAdapter();adapter.check_sampling(20000,4000,CONFIG)
        for rate,count in ((20001,4000),(20000,3998),(9000,1800)):
            with self.subTest(rate=rate,count=count),self.assertRaises(ValueError):adapter.check_sampling(rate,count,CONFIG)

class IndependentBridgeTests(unittest.TestCase):
    def test_step_convergence_and_positive_periodic_solution(self):
        for name in ("baseline","heavy_load"):
            c=json.loads((ROOT/f"configs/rectifier_{name}.json").read_text(encoding="utf-8"))
            coarse=expected_rectifier(c,2000);fine=expected_rectifier(c,4000)
            for key in ("mean_v","rms_v","ripple_pp_v"):
                self.assertLess(abs(coarse[key]-fine[key])/fine[key],.001)
            self.assertGreater(fine["rms_v"],fine["mean_v"])
            self.assertGreater(fine["ripple_pp_v"],0)
            self.assertLess(fine["periodic_max_change_per_input_peak"],1e-5)

    def test_linear_scaling_and_heavier_load_physics(self):
        base=expected_rectifier(CONFIG)
        low=deepcopy(CONFIG);low["source"]["rms_v"]*=.8
        lowref=expected_rectifier(low)
        for key in ("mean_v","rms_v","ripple_pp_v","mean_load_a"):
            self.assertAlmostEqual(lowref[key]/base[key],.8,places=12)
        heavy=deepcopy(CONFIG);heavy["circuit"]["load_ohm"]/=2
        h=expected_rectifier(heavy)
        self.assertLess(h["mean_v"],base["mean_v"])
        self.assertGreater(h["ripple_pp_v"],base["ripple_pp_v"])
        self.assertGreater(h["mean_load_a"],base["mean_load_a"])

class RectifierAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name);self.csv=self.path/"waveforms.csv"
        self.config=validate_config(CONFIG)
        # Analytic sinusoid isolates metrics from the separately tested circuit solver.
        self.reference={"mean_v":300.,"rms_v":math.sqrt(300**2+10**2/2),"ripple_pp_v":20.,"mean_load_a":3.}
        self.patcher=patch("typhoon_lab.rectifier_analysis.expected_rectifier",return_value=self.reference)
        self.patcher.start();self.addCleanup(self.patcher.stop)

    def fixture(self):
        rows=[]
        for k in range(4000):
            t=k/20000;v=300+10*math.cos(2*math.pi*100*t)
            rows.append([t,1.5+t,v,v/100,-.001*10*2*math.pi*100*math.sin(2*math.pi*100*t)])
        self.save(rows);return rows

    def save(self,rows):
        with self.csv.open("w",encoding="utf-8",newline="") as handle:
            writer=csv.writer(handle);writer.writerow(COLUMNS);writer.writerows(rows)

    def test_analytic_mean_rms_ripple_frequency_and_cycle_stability(self):
        self.fixture();before=self.csv.read_bytes();m=analyze_rectifier(self.csv,self.config)
        self.assertEqual(m["status"],"passed")
        self.assertAlmostEqual(m["signals"]["Vdc_V"]["mean"],300)
        self.assertAlmostEqual(m["signals"]["Vdc_V"]["rms"],self.reference["rms_v"])
        self.assertAlmostEqual(m["signals"]["Vdc_V"]["ripple_pp"],20)
        self.assertAlmostEqual(m["periodicity"]["dominant_ripple_hz"],100)
        self.assertEqual(len(m["periodicity"]["per_input_cycle"]),10)
        self.assertEqual(before,self.csv.read_bytes())

    def test_load_capacitor_cycle_and_reference_failures_remain_failed(self):
        for issue in ("load","capacitor","cycle","reference"):
            rows=self.fixture()
            if issue=="load":
                for row in rows:row[3]*=1.02
            elif issue=="capacitor":
                for row in rows:row[4]+=.1
            elif issue=="cycle":
                for row in rows[-400:]:row[2]+=3;row[3]=row[2]/100
            else:
                for row in rows:row[2]*=1.1;row[3]=row[2]/100
            self.save(rows)
            with self.subTest(issue=issue):self.assertEqual(analyze_rectifier(self.csv,self.config)["status"],"failed")

    def test_short_gap_nonfinite_and_time_misalignment_rejected(self):
        for issue in ("short","gap","nan","time"):
            rows=self.fixture()
            if issue=="short":rows=rows[:1000]
            elif issue=="gap":del rows[1000]
            elif issue=="nan":rows[1000][2]=float("nan")
            else:rows[1000][1]+=.001
            self.save(rows);before=self.csv.read_bytes()
            with self.subTest(issue=issue),self.assertRaises(ValueError):analyze_rectifier(self.csv,self.config)
            self.assertEqual(before,self.csv.read_bytes())

    def record(self):
        self.fixture();m=analyze_rectifier(self.csv,self.config)
        write_json(self.path/"config.json",self.config);write_json(self.path/"metrics.json",m);write_json(self.path/"capture.json",{})
        manifest={"schema_version":1,"model":"single_phase_rectifier","kind":"run","backend":"virtual_hil","status":m["status"]}
        finalize(self.path,manifest);return m,manifest

    def test_steady_schema_does_not_create_boost_event_requirements(self):
        _,_=self.record()
        self.assertEqual(verify_run(self.path,write=False)["status"],"passed")
        self.assertFalse((self.path/"events.json").exists())

    def test_reference_and_periodicity_are_recomputed_after_hash_update(self):
        m,manifest=self.record();m["periodicity"]["expected_ripple_hz"]=90
        write_json(self.path/"metrics.json",m);finalize(self.path,manifest)
        result=verify_run(self.path,write=False)
        self.assertEqual(result["record_status"],"failed")
        self.assertTrue(any("periodicity" in p for p in result["record_problems"]))

    def test_report_preserves_raw_data_and_is_model_specific(self):
        m,manifest=self.record();before=self.csv.read_bytes();write_report(self.path,manifest)
        text=(self.path/"report.md").read_text(encoding="utf-8")
        self.assertIn("单相桥",text);self.assertNotIn("RLC",text);self.assertIn("独立参考",text)
        self.assertTrue((self.path/"waveforms.png").is_file());self.assertEqual(before,self.csv.read_bytes())

class RectifierComparisonTests(unittest.TestCase):
    def fixtures(self):
        result={}
        for role in ("baseline","low_input","heavy_load"):
            c=validate_config(json.loads((ROOT/f"configs/rectifier_{role}.json").read_text(encoding="utf-8")))
            ref=expected_rectifier(c)
            result[role]={"config":c,"metrics":{"status":"passed","signals":{"Vdc_V":{"mean":ref["mean_v"],"ripple_pp":ref["ripple_pp_v"]},"Iload_A":{"mean":ref["mean_load_a"]}},"capture":{"cycles":10},"periodicity":{"dominant_ripple_hz":100}}}
        return result

    def test_reference_trends_pass_and_missing_trend_fails(self):
        records=self.fixtures();self.assertEqual(compare_metrics(records)["status"],"passed")
        records["heavy_load"]["metrics"]["signals"]["Vdc_V"]["ripple_pp"]=records["baseline"]["metrics"]["signals"]["Vdc_V"]["ripple_pp"]
        self.assertEqual(compare_metrics(records)["status"],"failed")

    def test_multiple_simultaneous_changes_are_rejected(self):
        records=self.fixtures();records["low_input"]["config"]["circuit"]["load_ohm"]=50
        with self.assertRaises(ValueError):compare_metrics(records)

    def test_replay_detects_changed_source_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/"source";source.mkdir();(source/"manifest.json").write_text("original",encoding="utf-8")
            inputs={role:{"path":"source","sha256":{"manifest.json":sha256(source/"manifest.json")}} for role in ("baseline","low_input","heavy_load")}
            write_json(root/"inputs.json",inputs)
            (source/"manifest.json").write_text("changed",encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"source changed"):recompute_comparison(root)

if __name__=="__main__":unittest.main()
