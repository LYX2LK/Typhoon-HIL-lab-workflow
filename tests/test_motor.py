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
        for p in (ROOT/'configs').glob('im_speed_[0-9]*.json'):
            c=validate_config(json.loads(p.read_text(encoding='utf-8')))
            self.assertTrue(InductionMotorAdapter.has_events)
            self.assertFalse(InductionMotorAdapter().record_events(c))
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


class MotorStepTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.csv=Path(self.tmp.name)/'waveforms.csv'
        self.config=json.loads((ROOT/'configs/im_speed_step_1430_to_850.json').read_text(encoding='utf-8'))
        self.config['events'][0]['at_s']=.1
        self.config['capture'].update(duration_s=.5,sample_rate_hz=10000)
        self.config['acceptance'].update(window_start_s=.3,window_end_s=.5,
                                         min_samples=3000,pre_event_window_s=.05,
                                         post_event_delay_s=.2)
        self.config=validate_config(self.config)
        self.rows=[]
        for k in range(5000):
            t=k/10000+5e-7
            applied=850. if t>=.1001005 else 1430.
            speed=1430. if t<.1001005 else (850. if t>=.25 else 1000.)
            self.rows.append([k/10000,t,speed,2.,applied,2.])

    def save(self):
        with self.csv.open('w',encoding='utf-8',newline='') as f:
            w=csv.writer(f);w.writerow(COLUMNS);w.writerows(self.rows)

    def test_valid_step_and_one_percent_boundary(self):
        self.rows[4000][2]=850*1.01
        self.save();before=self.csv.read_bytes()
        m=analyze_motor(self.csv,self.config)
        self.assertEqual(m['status'],'passed')
        self.assertEqual(m['events'][0]['status'],'passed')
        self.assertEqual(m['speed']['post_event_exceeded_sample_count'],0)
        self.assertEqual(m['events'][0]['observed_interval_s'],[self.rows[1000][1],self.rows[1001][1]])
        self.assertEqual(before,self.csv.read_bytes())
        self.assertTrue(InductionMotorAdapter().record_events(self.config))

    def test_event_missing_mistimed_and_wrong_level_are_error(self):
        for issue in ('missing','late','wrong_level'):
            rows=deepcopy(self.rows)
            for i,row in enumerate(rows):
                if issue=='missing':row[4]=1430.
                elif issue=='late':row[4]=850. if i>=1200 else 1430.
                elif issue=='wrong_level' and i>=1001:row[4]=840.
            self.rows=rows;self.save()
            with self.subTest(issue=issue):
                m=analyze_motor(self.csv,self.config)
                self.assertEqual(m['status'],'error')
                self.assertEqual(m['events'][0]['status'],'error')

    def test_valid_event_with_performance_failure(self):
        self.rows[4000][2]=900.
        self.save();m=analyze_motor(self.csv,self.config)
        self.assertEqual(m['status'],'failed')
        self.assertEqual(m['events'][0]['status'],'passed')
        self.assertEqual(m['speed']['post_event_exceeded_sample_count'],1)

    def test_pre_event_not_settled_is_failed(self):
        self.rows[750][2]=1400.
        self.save();m=analyze_motor(self.csv,self.config)
        self.assertEqual(m['status'],'failed')
        self.assertFalse(next(x for x in m['checks'] if x['name']=='pre_event_tracking')['passed'])

    def test_post_event_never_settles_is_failed(self):
        for row in self.rows[1001:]:
            row[2]=900.
        self.save();m=analyze_motor(self.csv,self.config)
        self.assertEqual(m['status'],'failed')
        self.assertIsNone(m['speed']['settling_time_s'])
        self.assertFalse(next(x for x in m['checks'] if x['name']=='settling_time')['passed'])

    def test_incomplete_sampling_and_bad_config(self):
        self.rows=self.rows[:4500];self.save()
        with self.assertRaises(ValueError):analyze_motor(self.csv,self.config)
        for mutation in ('unaligned','same_speed','missing_window'):
            c=deepcopy(self.config)
            if mutation=='unaligned':c['events'][0]['at_s']=.10005
            elif mutation=='same_speed':c['events'][0]['value']=1430
            else:del c['acceptance']['post_event_delay_s']
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):validate_config(c)
