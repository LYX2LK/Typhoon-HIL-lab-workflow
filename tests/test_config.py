import copy
import json
from pathlib import Path
import unittest
from typhoon_lab.config import validate_config

BASE=json.loads((Path(__file__).resolve().parents[1]/"configs"/"rlc_baseline.json").read_text(encoding="utf-8"))
class ConfigTests(unittest.TestCase):
    def test_invalid_and_unknown_inputs(self):
        cases=[]
        bad=copy.deepcopy(BASE);bad["source"]["rms_v"]=float("nan");cases.append(bad)
        bad=copy.deepcopy(BASE);bad["circuit"]["rin_ohm"]=True;cases.append(bad)
        bad=copy.deepcopy(BASE);bad["backend"]="physical_hil";cases.append(bad)
        bad=copy.deepcopy(BASE);bad["source"]["frequency"]=1000;cases.append(bad)
        for bad in cases:
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                validate_config(bad)
    def test_capture_must_support_declared_analysis(self):
        bad=copy.deepcopy(BASE);bad["capture"]["duration_s"]=.0203
        with self.assertRaises(ValueError):validate_config(bad)
        bad=copy.deepcopy(BASE);bad["capture"]["sample_rate_hz"]=1000
        with self.assertRaises(ValueError):validate_config(bad)
    def test_bounded_sweep(self):
        bad=copy.deepcopy(BASE);bad["sweep"]={"parameter":"rin_ohm","values":[1,1]}
        with self.assertRaises(ValueError):validate_config(bad,sweep=True)
        bad["sweep"]["values"]=list(range(1,14))
        with self.assertRaises(ValueError):validate_config(bad,sweep=True)

if __name__=="__main__":unittest.main()
