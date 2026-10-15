"""Injected failures verify the record contract without calling Typhoon."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from typhoon_lab.runtime import execute_smoke,cleanup
from typhoon_lab.cli import verify_run
from typhoon_lab.utils import write_json,sha256

class RecordTests(unittest.TestCase):
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

if __name__=="__main__":unittest.main()
