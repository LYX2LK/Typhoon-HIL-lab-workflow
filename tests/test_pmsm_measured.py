from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from scipy.io import savemat

from typhoon_lab.diagnostic_tools import ObservationTools
from typhoon_lab.pmsm_measured import (MAPPING, UNITS, condition, native_arrays,
    prepare_measured, query_measured, verify_measured)
from typhoon_lab.records import verify_run


class MeasuredTests(unittest.TestCase):
    def native(self, path, speed_offset=0):
        t = np.arange(10001)/10000; speed = 100+10*t+speed_offset
        d = {v['native']: np.ones(len(t)) for v in MAPPING.values()}
        d.update(Time=t, Speed_rpm=speed, Speed_requred_rpm=speed,
                 Speed_rad_el=speed*np.pi/30*10, Speed_requred_rad_el=speed*np.pi/30*10)
        savemat(path,d)

    def test_time_and_electrical_units_cannot_be_confused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'x.mat';self.native(path)
            d=native_arrays(path)
            tool=ObservationTools(d,UNITS,units=UNITS)
            result=tool.execute('difference',{'left':'measured_speed_rpm','right':'measured_electrical_speed','window_s':[0,.5]})
            self.assertEqual(result['status'],'invalid_query')
            self.assertEqual(condition(d,[0,.5])['phase'],'accelerating')
            self.assertEqual(tool.execute('availability',{'channels':['model_speed_rpm']})['available']['model_speed_rpm'],False)

    def test_stage_distinguishes_initial_hold_steps_and_post_step_hold(self):
        t=np.arange(20001)/10000
        d={'time_s':t,'reference_speed_rpm':np.where(t>=.6,110.,100.)}
        self.assertEqual(condition(d,[0,.5])['stage'],'no_prior_observed_change')
        self.assertEqual(condition(d,[.5,1.])['reference_change_count'],1)
        self.assertEqual(condition(d,[.5,1.])['stage'],'changing_up')
        after=condition(d,[1.,1.5])
        self.assertEqual(after['stage'],'post_change_hold')
        self.assertAlmostEqual(after['time_since_previous_change_s'],.4)

    def test_source_projection_reference_and_tamper_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);src=root/'raw';src.mkdir()
            self.native(src/'spd10-5000rpm_flt0z_25NM.mat')
            self.native(src/'spd10-5000rpm_flt1zu_25NM.mat')
            self.native(src/'spd10-5000rpm_flt1zu_30NM.mat')
            with patch('typhoon_lab.runtime.snapshot_code'):
                result=prepare_measured(root/'out',src)
            self.assertEqual(result['record_status'],'passed')
            self.assertEqual(verify_run(root/'out',write=False)['record_status'],'passed')
            import json
            public=json.loads((root/'out/dataset.json').read_text(encoding='utf-8'))
            args={'channels':['i1_q','i2_q'],'window_s':[0,.5]}
            for case_id,case in public['cases'].items():
                result=query_measured(root/'out',case_id,'normal_reference',args)
                expected='unavailable' if case_id in public['normal_reference_ids'] or case['load_setpoint_nm']==30 else 'ok'
                self.assertEqual(result['status'],expected)
                if expected=='ok': self.assertEqual(result['distinct_reference_recordings'],1)
            (root/'out/observations'/f'{case_id}.npz').write_bytes(b'changed')
            self.assertEqual(verify_measured(root/'out')['record_status'],'failed')
