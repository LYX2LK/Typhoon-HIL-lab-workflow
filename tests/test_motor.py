"""Synthetic tracking data exercise boundaries independently of the HIL model."""
from copy import deepcopy
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from typhoon_lab.config import validate_config
from typhoon_lab.adapters.induction import InductionMotorAdapter
from typhoon_lab.motor_analysis import COLUMNS,analyze_motor

ROOT=Path(__file__).resolve().parents[1]
BASE=json.loads((ROOT/'configs/im_speed_1430.json').read_text(encoding='utf-8'))


class MotorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.csv=Path(self.tmp.name)/'waveforms.csv'
        self.config=deepcopy(BASE);self.config['capture']['duration_s']=.2
        self.config['acceptance'].update(window_start_s=.1,window_end_s=.2,min_samples=2000)
        self.rows=[[k/20000,k/20000+5e-7,1430.,2.,1430.,2.] for k in range(4000)]

    def save(self):
        with self.csv.open('w',encoding='utf-8',newline='') as f:
            w=csv.writer(f);w.writerow(COLUMNS);w.writerows(self.rows)

    def test_shipped_configs_and_sampling(self):
        for p in (ROOT/'configs').glob('im_speed_*.json'):
            c=validate_config(json.loads(p.read_text(encoding='utf-8')))
            self.assertFalse(InductionMotorAdapter.has_events)
            InductionMotorAdapter().check_sampling(20000,80000,c)
        for rate,count in ((9000,36000),(20000,40000)):
            with self.assertRaises(ValueError):InductionMotorAdapter().check_sampling(rate,count,BASE)

    def test_inclusive_one_percent_and_outside_window(self):
        for row in self.rows:row[2]=1430*1.01
        self.rows[100][2]=0.;self.save();before=self.csv.read_bytes()
        m=analyze_motor(self.csv,self.config)
        self.assertEqual(m['status'],'passed');self.assertEqual(m['speed']['exceeded_sample_count'],0)
        self.assertEqual(before,self.csv.read_bytes())

    def test_one_exceeded_sample_is_failed_and_located(self):
        self.rows[2500][2]=1500.;self.save();m=analyze_motor(self.csv,self.config)
        self.assertEqual(m['status'],'failed');self.assertEqual(m['speed']['exceeded_sample_count'],1)
        self.assertEqual(m['speed']['exceeded_times_s'],[self.rows[2500][1]])
        self.assertAlmostEqual(m['speed']['max_absolute_error_rpm'],70)

    def test_window_includes_left_endpoint_and_excludes_right_endpoint(self):
        for row in self.rows:row[1]=row[0]
        self.config['acceptance']['window_end_s']=.15
        self.rows[3000][2]=0.  # Exactly t=0.15, outside [0.1, 0.15).
        self.save();m=analyze_motor(self.csv,self.config)
        self.assertEqual(m['status'],'passed')
        self.assertEqual(m['analysis']['evaluation_sample_count'],1000)
        self.rows[2000][2]=0.  # Exactly t=0.1, inside the window.
        self.save();m=analyze_motor(self.csv,self.config)
        self.assertEqual(m['status'],'failed')
        self.assertEqual(m['speed']['exceeded_times_s'],[.1])

    def test_invalid_data_is_error_instead_of_performance_failure(self):
        original=deepcopy(self.rows)
        for issue in ('gap','truncated','nan','reference','load','time'):
            self.rows=deepcopy(original)
            if issue=='gap':del self.rows[2500]
            elif issue=='truncated':self.rows=self.rows[:2500]
            elif issue=='nan':self.rows[2500][2]=float('nan')
            elif issue=='reference':self.rows[2500][4]=850
            elif issue=='load':self.rows[2500][5]=0
            else:self.rows[2500][1]+=.001
            self.save()
            with self.subTest(issue=issue),self.assertRaises(ValueError):analyze_motor(self.csv,self.config)

    def test_config_rejects_boolean_missing_window_and_events(self):
        for field,value in (('reference_speed_rpm',True),('load_pu',2)):
            c=deepcopy(BASE);c['parameters'][field]=value
            with self.assertRaises(ValueError):validate_config(c)
        c=deepcopy(BASE);c['acceptance']['window_end_s']=5
        with self.assertRaises(ValueError):validate_config(c)
        c=deepcopy(BASE);c['events']=[{'at_s':1}]
        with self.assertRaises(ValueError):validate_config(c)

    def test_inspection_uses_normalized_property_dictionary(self):
        source=Path(self.tmp.name)/'model.tse';source.write_text('Ts = 100e-6\n',encoding='utf-8')
        api=Mock();api.get_item.side_effect=lambda name:name;api.get_model_file_path.return_value=str(source)
        api.get_property_values.side_effect=lambda name:({'gain':[4.]} if name=='Gain6' else {'gain':[60/(2*3.141592653589793)]} if name=='To rpm' else {'load_src':'Model','ext_mdl_load_type':'torque','el_trq_out':True,'mech_speed_out':True,'Jm':.015,'pms':'pms'})
        api.get_property_value.side_effect=AssertionError('raw expression API can return a list')
        values=InductionMotorAdapter().inspect_parameters(api)
        self.assertEqual(values['load_gain_nm_per_pu'],4)
        self.assertAlmostEqual(values['speed_conversion'],9.549296585513721)
        for invalid in ([],[4.,4.],[float('nan')]):
            original=api.get_property_values.side_effect
            api.get_property_values.side_effect=lambda name:({'gain':invalid} if name=='Gain6' else original(name))
            with self.subTest(gain=invalid),self.assertRaises(ValueError):
                InductionMotorAdapter().inspect_parameters(api)
            api.get_property_values.side_effect=original
