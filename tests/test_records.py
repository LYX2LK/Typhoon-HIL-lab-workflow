"""Injected failures verify the record contract without calling Typhoon."""
from pathlib import Path
import json
import math
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from typhoon_lab.analysis import expected_rlc_rms
from typhoon_lab.runtime import execute_smoke,cleanup
from typhoon_lab.cli import verify_run
from typhoon_lab.utils import write_json,sha256
from typhoon_lab.versions import ANALYSIS_METHOD_VERSIONS, record_version_problems

class RecordTests(unittest.TestCase):
    def test_practice_recomputes_extra_measurement_after_hash_refresh(self):
        from typhoon_lab.model_practice import recompute_practice
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            config={"source":{"rms_v":10.,"frequency_hz":1000.,"phase_deg":0.},
                    "circuit":{"rin_ohm":8.,"branch_r_ohm":.1,"l_h":1e-5,"c_f":5e-4},
                    "acceptance":{"max_relative_rms_error":.03,"minimum_samples":256}}
            write_json(path/"config.json",config)
            expected=expected_rlc_rms(config)
            t=np.arange(400)/20000
            current=np.sqrt(2)*expected["I_A"]*np.sin(2*math.pi*1000*t)
            voltage=np.sqrt(2)*expected["Va1_V"]*np.sin(2*math.pi*1000*t)
            drop=8*current
            np.savetxt(path/"waveforms.csv",np.column_stack([t,t+.05,current,voltage,drop]),
                       delimiter=',',header='t_relative_s,t_simulation_s,I_A,Va1_V,V_Rin_V',comments='')
            metrics=recompute_practice(path);write_json(path/"metrics.json",metrics)
            (path/"source_model.tse").write_bytes(b"self-built source")
            (path/"model.tse").write_bytes(b"changed model")
            manifest={"kind":"modeling_practice","status":"passed",
                      "source_sha256":sha256(path/"source_model.tse"),
                      "parameter_change":{"Rin_ohm_before":5.,"Rin_ohm_after":8.},
                      "discovered_signals":["I","Va1","V_Rin"]}
            from typhoon_lab.utils import finalize
            finalize(path,manifest)
            self.assertEqual(verify_run(path,write=False)["record_status"],"passed")
            changed=np.loadtxt(path/"waveforms.csv",delimiter=',',skiprows=1)
            changed[:,4]*=.7
            np.savetxt(path/"waveforms.csv",changed,delimiter=',',
                       header='t_relative_s,t_simulation_s,I_A,Va1_V,V_Rin_V',comments='')
            manifest["artifacts"]["waveforms.csv"]=sha256(path/"waveforms.csv")
            write_json(path/"manifest.json",manifest)
            result=verify_run(path,write=False)
            self.assertEqual(result["record_status"],"failed")
            self.assertTrue(any("practice metrics" in problem for problem in result["record_problems"]))

    def test_api_import_failure_preserves_error_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            with patch("typhoon_lab.runtime.api_modules",side_effect=ImportError("injected import failure")):
                result=execute_smoke(path)
            saved=json.loads((path/"manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"],"error")
            self.assertEqual(saved["status"],"error")
            self.assertIn("injected import failure",saved["error"])
            self.assertTrue((path/"run.log").is_file())

    def test_false_capture_cleanup_is_recorded_but_none_is_compatible(self):
        class Hil:
            def __init__(self,result):self.result=result
            def stop_capture(self):return self.result
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(cleanup(Hil(None),False,True,Path(tmp)),[])
            self.assertEqual(cleanup(Hil(False),False,True,Path(tmp)),["stop_capture returned False"])

    def test_modified_record_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            readings=path/"readings.json"
            write_json(readings,[{"input":10,"measured":10,"passed":True}])
            snapshot=path/"code_snapshot"/"example.py"
            snapshot.parent.mkdir()
            snapshot.write_text("# explicit unit test fixture\n",encoding="utf-8")
            write_json(path/"manifest.json",{"kind":"smoke","status":"passed",
                "artifacts":{"readings.json":sha256(readings),"code_snapshot/example.py":sha256(snapshot)},
                "code_sha256":{"example.py":sha256(snapshot)}})
            self.assertEqual(verify_run(path,write=False)["status"],"passed")
            snapshot.write_text("# altered fixture\n",encoding="utf-8")
            result=verify_run(path,write=False)
            self.assertEqual(result["status"],"failed")
            self.assertTrue(any("snapshot" in p for p in result["problems"]))

    def test_legacy_record_and_unsupported_format_are_distinguished(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            readings=path/"readings.json"
            write_json(readings,[{"input":10,"measured":10,"passed":True}])
            manifest={"kind":"smoke","schema_version":1,"status":"passed",
                      "artifacts":{"readings.json":sha256(readings)}}
            write_json(path/"manifest.json",manifest)
            self.assertEqual(verify_run(path,write=False)["record_status"],"passed")
            manifest["record_format_version"]=999
            write_json(path/"manifest.json",manifest)
            result=verify_run(path,write=False)
            self.assertEqual(result["record_status"],"failed")
            self.assertTrue(any("unsupported record_format_version" in p for p in result["record_problems"]))

    def test_analysis_method_revision_is_scoped_to_model(self):
        with patch.dict(ANALYSIS_METHOD_VERSIONS,{("run","boost_closed_loop"):2}):
            self.assertEqual(record_version_problems({"kind":"run","model":"rlc_filter",
                                                      "analysis_method_version":1}),[])
            problems=record_version_problems({"kind":"run","model":"boost_closed_loop",
                                              "analysis_method_version":1})
            self.assertTrue(any("unsupported analysis_method_version" in p for p in problems))

if __name__=="__main__":unittest.main()
