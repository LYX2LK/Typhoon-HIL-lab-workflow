"""Synthetic response and injected-failure tests; these do not validate Typhoon."""
from copy import deepcopy
import csv
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from typhoon_lab.config import validate_config
from typhoon_lab.analysis import analyze
from typhoon_lab.boost_analysis import COLUMNS
from typhoon_lab.adapters.boost import BoostAdapter
from typhoon_lab.runtime import execute_case
from typhoon_lab.reporting import write_report
from typhoon_lab.cli import verify_run
from typhoon_lab.utils import write_json, finalize

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT/"configs/boost_reference_step.json").read_text(encoding="utf-8"))

class BoostConfigTests(unittest.TestCase):
    def test_four_shipped_configs(self):
        for path in (ROOT/"configs").glob("boost_*.json"):
            self.assertEqual(validate_config(json.loads(path.read_text(encoding="utf-8")))["schema_version"], 2)

    def test_event_time_and_window_bounds(self):
        for at in (.50003, .01, 1.3):
            c=deepcopy(CONFIG);c["events"][0]["at_s"]=at
            with self.subTest(at=at), self.assertRaises(ValueError): validate_config(c)

    def test_unknown_target_multiple_events_and_noop(self):
        for change in ("unknown", "multiple", "noop"):
            c=deepcopy(CONFIG)
            if change=="unknown": c["events"][0]["target"]="load"
            elif change=="multiple": c["events"]*=2
            else: c["events"][0]["value"]=50
            with self.subTest(change=change), self.assertRaises(ValueError): validate_config(c)

    def test_invalid_parameters_version_backend_and_sampling(self):
        changes=[("parameters","pwm_enabled",False),("parameters","input_voltage_v",True),
            ("parameters","reference_voltage_v",101),("parameters","input_voltage_v",float("nan")),
            ("capture","sample_rate_hz",9999),("acceptance","min_samples",15000.5)]
        for group,key,value in changes:
            c=deepcopy(CONFIG);c[group][key]=value
            with self.subTest(key=key), self.assertRaises(ValueError): validate_config(c)
        for key,value in (("schema_version",1),("backend","physical_hil"),("extra",1)):
            c=deepcopy(CONFIG);c[key]=value
            with self.subTest(key=key), self.assertRaises(ValueError): validate_config(c)

    def test_boost_cannot_track_below_input(self):
        c=deepcopy(CONFIG);c["events"][0]["value"]=30
        with self.assertRaises(ValueError): validate_config(c)

    def test_boost_sweep_is_explicitly_unsupported(self):
        with self.assertRaises(ValueError): validate_config(CONFIG, sweep=True)

class BoostAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name);self.csv=self.path/"waveforms.csv";self.config=deepcopy(CONFIG)

    def fixture(self, mode="reference", observer_time=.5, observer_final=None):
        c=self.config
        if mode=="baseline": c["events"]=[]
        if mode=="disturbance": c["events"]=[{"at_s":.5,"target":"input_voltage_v","value":28}]
        event=c["events"][0] if c["events"] else None
        init=c["parameters"]["reference_voltage_v"]
        rows=[]
        for k in range(15000):
            t=k/10000
            ref=init;vin=35.;out=init
            if event:
                is_ref=event["target"]=="reference_voltage_v"
                if t>=.5:
                    out=(event["value"]+(init-event["value"])*math.exp(-(t-.5)/.1)) if is_ref else init-2*math.exp(-(t-.5)/.08)
                if t>=observer_time:
                    if is_ref: ref=event["value"] if observer_final is None else observer_final
                    else: vin=event["value"] if observer_final is None else observer_final
            rows.append([t,t,out,1+.1*math.sin(2*math.pi*17*t),ref,vin])
        self.save(rows)
        return rows

    def save(self, rows):
        with self.csv.open("w",encoding="utf-8",newline="") as f:
            writer=csv.writer(f);writer.writerow(COLUMNS);writer.writerows(rows)

    def test_known_first_order_settling_and_steady_mean(self):
        rows=self.fixture();m=analyze(self.csv,self.config)
        expected=.1*math.log(10/(60*.02))
        self.assertEqual(m["status"],"passed")
        self.assertGreaterEqual(m["response"]["settling_time_s"]+1e-10,expected)
        self.assertLessEqual(m["response"]["settling_time_s"],expected+.00010001)
        independent=sum(row[2] for row in rows[-1000:])/1000
        self.assertAlmostEqual(m["signals"]["Vout_V"]["steady_mean"],independent,places=10)
        self.assertEqual(m["response"]["overshoot_fraction_of_step"],0)
        self.assertEqual(m,analyze(self.csv,self.config))

    def test_observed_event_interval_contains_requested_time(self):
        self.fixture();m=analyze(self.csv,self.config);e=m["events"][0]
        self.assertAlmostEqual(e["observed_at_s"],.5)
        self.assertLess(e["observed_interval_s"][0],.5)
        self.assertGreaterEqual(e["observed_interval_s"][1],.5)
        self.assertAlmostEqual(e["time_resolution_s"],.0001)

    def test_capture_phase_offset_and_sum_delay_regression(self):
        rows=self.fixture()
        for row in rows: row[1]+=.5e-6
        self.save(rows)
        self.assertEqual(analyze(self.csv,self.config)["status"],"passed")
        rows=self.fixture(observer_time=.5001)
        for row in rows: row[1]+=.5e-6
        self.save(rows)
        self.assertEqual(analyze(self.csv,self.config)["status"],"error")
        schedule=BoostAdapter().describe_schedule(self.config)[0]
        self.assertAlmostEqual(schedule["model_step_trigger_at_s"]+schedule["pipeline_compensation_s"],.5)

    def test_baseline_and_disturbance(self):
        self.fixture("baseline");m=analyze(self.csv,self.config)
        self.assertEqual(m["status"],"passed");self.assertEqual(m["events"],[])
        self.fixture("disturbance");m=analyze(self.csv,self.config)
        self.assertEqual(m["status"],"passed")
        self.assertAlmostEqual(m["response"]["maximum_deviation_relative"],.04)
        expected=.08*math.log(2)
        self.assertAlmostEqual(m["response"]["settling_time_s"],expected,delta=.000101)

    def test_downward_reference_response(self):
        self.config["parameters"]["reference_voltage_v"]=60
        self.config["events"][0]["value"]=50
        self.fixture();m=analyze(self.csv,self.config)
        self.assertEqual(m["status"],"passed")
        self.assertEqual(m["response"]["overshoot_fraction_of_step"],0)

    def test_event_missing_is_execution_error(self):
        self.fixture(observer_time=2)
        m=analyze(self.csv,self.config)
        self.assertEqual(m["status"],"error")
        self.assertIsNone(m["events"][0]["observed_at_s"])
        self.assertIsNone(m["response"]["settling_time_s"])

    def test_event_wrong_time_and_level_are_errors(self):
        for time,level in ((.55,60),(.5,62)):
            self.fixture(observer_time=time,observer_final=level)
            with self.subTest(time=time,level=level): self.assertEqual(analyze(self.csv,self.config)["status"],"error")

    def test_hold_channel_unexpected_change_is_error(self):
        rows=self.fixture()
        for row in rows[6000:]: row[5]=34
        self.save(rows)
        self.assertEqual(analyze(self.csv,self.config)["status"],"error")

    def test_pre_event_not_settled_is_failed(self):
        rows=self.fixture()
        for row in rows[4000:5000]: row[2]=45
        self.save(rows)
        self.assertEqual(analyze(self.csv,self.config)["status"],"failed")

    def test_overshoot_is_fraction_of_step(self):
        rows=self.fixture();rows[7000][2]=61;self.save(rows)
        m=analyze(self.csv,self.config)
        self.assertEqual(m["status"],"failed")
        self.assertAlmostEqual(m["response"]["overshoot_fraction_of_step"],.1)

    def test_no_recovery_is_null_with_reason(self):
        rows=self.fixture()
        for row in rows[5000:]: row[2]=63
        self.save(rows);m=analyze(self.csv,self.config)
        self.assertEqual(m["status"],"failed")
        self.assertIsNone(m["response"]["settling_time_s"])
        self.assertEqual(m["response"]["settling_reason"],"not_settled_within_capture")

    def test_late_excursion_prevents_false_settling(self):
        rows=self.fixture();rows[-1][2]=63;self.save(rows)
        m=analyze(self.csv,self.config)
        self.assertIsNone(m["response"]["settling_time_s"])

    def test_missing_gap_nonfinite_and_time_misalignment_rejected(self):
        for issue in ("short","gap","nan","time"):
            rows=self.fixture()
            if issue=="short": rows=rows[:10000]
            elif issue=="gap": del rows[7000]
            elif issue=="nan": rows[7000][2]=float("nan")
            else: rows[7000][1]+=.00002
            self.save(rows);before=self.csv.read_bytes()
            with self.subTest(issue=issue), self.assertRaises(ValueError): analyze(self.csv,self.config)
            self.assertEqual(before,self.csv.read_bytes())

    def test_report_is_boost_specific_and_keeps_raw_data(self):
        self.fixture();m=analyze(self.csv,self.config);before=self.csv.read_bytes()
        write_json(self.path/"config.json",self.config);write_json(self.path/"metrics.json",m)
        write_report(self.path,{"model":"boost_closed_loop","status":m["status"]})
        text=(self.path/"report.html").read_text(encoding="utf-8")
        import re
        visible=re.sub(r'src="data:image/[^"]+"', 'src="[embedded image]"', text)
        self.assertIn("Boost",visible);self.assertNotIn("RLC",visible)
        self.assertIn("data:image/png;base64,",text);self.assertIn("事件证据",text)
        self.assertEqual(before,self.csv.read_bytes())
        self.assertTrue((self.path/"waveforms.png").exists())
        self.assertTrue((self.path/"response_detail.png").exists())

    def test_failed_performance_record_can_be_consistent(self):
        rows=self.fixture();rows[7000][2]=61;self.save(rows)
        m=analyze(self.csv,self.config)
        write_json(self.path/"config.json",self.config);write_json(self.path/"metrics.json",m)
        write_json(self.path/"capture.json",{})
        write_json(self.path/"events.json",{"schema_version":2,"planned":self.config["events"],"events":m["events"]})
        manifest={"schema_version":2,"kind":"run","model":"boost_closed_loop","backend":"virtual_hil", "status":m["status"],
            "events":m["events"],"event_schedule":BoostAdapter().describe_schedule(self.config)}
        finalize(self.path,manifest);result=verify_run(self.path,write=False)
        self.assertEqual(result["status"],"failed")
        self.assertEqual(result["experiment_status"],"failed")
        self.assertEqual(result["record_status"],"passed")
        self.assertEqual(result["record_problems"],[])

    def test_event_record_is_recomputed_even_if_hashes_are_updated(self):
        self.fixture();m=analyze(self.csv,self.config)
        write_json(self.path/"config.json",self.config);write_json(self.path/"metrics.json",m)
        write_json(self.path/"capture.json",{})
        event_record={"schema_version":2,"planned":self.config["events"],"events":m["events"]}
        write_json(self.path/"events.json",event_record)
        manifest={"schema_version":2,"kind":"run","model":"boost_closed_loop","backend":"virtual_hil", "status":m["status"],
            "events":m["events"],"event_schedule":BoostAdapter().schedule(None,self.config)}
        finalize(self.path,manifest)
        self.assertEqual(verify_run(self.path,write=False)["status"],"passed")
        event_record["events"][0]["observed_at_s"]=.4
        write_json(self.path/"events.json",event_record);finalize(self.path,manifest)
        result=verify_run(self.path,write=False)
        self.assertEqual(result["status"],"failed")
        self.assertTrue(any("event record differs" in s for s in result["problems"]))

class VerificationStatusTests(unittest.TestCase):
    def test_failed_child_has_consistent_recursive_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);child=root/"cases/one";child.mkdir(parents=True)
            write_json(child/"readings.json",[{"input":10,"measured":9,"passed":False}])
            finalize(child,{"kind":"smoke","status":"failed"})
            finalize(root,{"kind":"sweep","status":"failed","cases":[{"case_id":"one","relative_dir":"cases/one","status":"failed"}]})
            result=verify_run(root,write=False)
            self.assertEqual(result["status"],"failed")
            self.assertEqual(result["record_status"],"passed")
            self.assertEqual(result["record_problems"],[])

class BoostRuntimeFailureTests(unittest.TestCase):
    def test_failed_start_cleans_armed_capture_without_stopping_other_simulations(self):
        config=deepcopy(CONFIG);config["events"]=[]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);model=path/"model.tse";model.write_text("synthetic API fixture",encoding="utf-8")
            api=Mock();api.load.return_value=True;api.save_as.return_value=True;api.compile.return_value=True
            api.get_compiled_model_file.return_value=str(path/"model.cpd")
            hil=Mock();hil.get_model_file_path.return_value=None;hil.load_model.return_value=True
            hil.get_sources.return_value=[["Vin"]];hil.get_analog_signals.return_value=[list(BoostAdapter.signals)]
            hil.get_sim_step.return_value=.5e-6;hil.start_capture.return_value=True;hil.start_simulation.return_value=False
            hil.stop_capture.return_value=None
            with patch("typhoon_lab.runtime.api_modules",return_value=(api,hil)), patch("typhoon_lab.runtime.environment",return_value={}), \
                 patch("typhoon_lab.runtime.snapshot_code",return_value={}), patch("typhoon_lab.runtime.source_copy",return_value=(model,{})), \
                 patch.object(BoostAdapter,"prepare",return_value={}), patch.object(BoostAdapter,"initialize",return_value={}):
                result=execute_case(path,config)
            self.assertEqual(result["status"],"error")
            hil.stop_capture.assert_called_once();hil.stop_simulation.assert_not_called()
            self.assertTrue((path/"manifest.json").exists());self.assertTrue((path/"report.html").exists())
            self.assertFalse((path/"waveforms.csv").exists())

    def test_cleanup_failure_is_recorded(self):
        from typhoon_lab.runtime import cleanup
        with tempfile.TemporaryDirectory() as tmp:
            hil=Mock();hil.stop_capture.side_effect=OSError("capture cleanup denied");hil.stop_simulation.return_value=False
            issues=cleanup(hil,True,True,Path(tmp))
            self.assertEqual(len(issues),2)
            self.assertIn("capture cleanup denied",issues[0])

if __name__=="__main__": unittest.main()
