"""Preview boundaries, command timing, complete windows and absolute stop errors."""
from copy import deepcopy
import json
import math
from pathlib import Path
import tempfile
import unittest
import numpy as np

from typhoon_lab.adapters import get_adapter, describe_capabilities
from typhoon_lab.config import load_config, validate_config
from typhoon_lab.pmsm_preview import PMSMPreviewAdapter, analyze_preview, PERIOD
from typhoon_lab.utils import PROJECT


class PMSMPreviewTests(unittest.TestCase):
    def setUp(self):
        self.c=load_config(PROJECT/'configs/pmsm_software_preview.json')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'waveforms.csv'

    def data(self,missing_event=False,stop_error=0,truncate=False):
        t=np.arange(80000)/100000
        ref=np.full(len(t),1800.0)
        ref[t>=.20005]=2400
        if not missing_event: ref[t>=.5501]=0
        load=np.full(len(t),.01);load[t>=.35005]=.03
        speed=ref.copy();speed[t>=.651]+=stop_error
        current=np.sin(2*np.pi*100*t)
        y=np.column_stack([t,t,speed*math.pi/30,current,-current,np.zeros(len(t)),load,ref*math.pi/30,load])
        if truncate: y=y[:72000]
        np.savetxt(self.path,y,delimiter=',',header=','.join(('t_relative_s','t_simulation_s',*PMSMPreviewAdapter.columns)),comments='',fmt='%.17g')

    def test_explicit_software_scope_and_model_capabilities(self):
        cap=describe_capabilities(get_adapter(self.c['model']))
        self.assertTrue(cap['run'])
        self.assertEqual(len(cap['signal_details']),7)
        self.assertFalse(self.c['assumptions']['sample_parameter_confirmation'])
        bad=deepcopy(self.c);bad['scope']='sample_validated'
        with self.assertRaises(ValueError): validate_config(bad)
        bad=deepcopy(self.c);bad['assumptions']['sample_parameter_confirmation']=True
        with self.assertRaises(ValueError): validate_config(bad)

    def test_invalid_parameter_and_event_conditions(self):
        changes=[('parameters','lq_h',self.c['parameters']['ld_h']),('parameters','pole_pairs',5.1),
                 ('capture','duration_s',.56),('capture','sample_rate_hz',200000)]
        for group,key,value in changes:
            bad=deepcopy(self.c);bad[group][key]=value
            with self.assertRaises(ValueError): validate_config(bad)
        for time in (.20101,.19):
            bad=deepcopy(self.c);bad['events'][1]['at_s']=time
            with self.assertRaises(ValueError): validate_config(bad)

    def test_independent_known_waveforms_pass_and_preserve_event_times(self):
        self.data();result=analyze_preview(self.path,self.c)
        self.assertEqual(result['status'],'passed')
        self.assertAlmostEqual(result['events'][0]['observed_at_s'],.20005)
        self.assertAlmostEqual(result['events'][2]['observed_at_s'],.5501)
        self.assertEqual(len(result['windows']),4)
        self.assertEqual(result['sample_performance_status'],'not_evaluated')

    def test_stop_error_fails_without_dividing_by_zero(self):
        self.data(stop_error=60);result=analyze_preview(self.path,self.c)
        self.assertEqual(result['status'],'failed')
        self.assertFalse(result['windows'][-1]['passed'])
        self.assertAlmostEqual(result['windows'][-1]['max_speed_error_rpm'],60)

    def test_missing_stop_event_and_truncated_capture_do_not_pass(self):
        self.data(missing_event=True);result=analyze_preview(self.path,self.c)
        self.assertFalse(result['checks']['events_applied'])
        self.assertFalse(result['checks']['reference_speed_rpm_command_levels'])
        self.data(truncate=True)
        with self.assertRaisesRegex(ValueError,'incomplete'): analyze_preview(self.path,self.c)

    def test_grouped_events_allow_overlap_and_empty_control_only_explicitly(self):
        c=deepcopy(self.c)
        c['events']=[{'at_s':.3,'target':'reference_speed_rpm','value':2400},
                     {'at_s':.305,'target':'load_torque_nm','value':.03}]
        with self.assertRaises(ValueError): validate_config(c)
        c['acceptance']['window_policy']='event_group'
        self.assertEqual(len(validate_config(c)['events']),2)
        c['events'][1]['at_s']=.3
        self.assertEqual(len(validate_config(c)['events']),2)
        c['events'][1]['target']='reference_speed_rpm'
        with self.assertRaises(ValueError): validate_config(c)
        c['events']=[]
        self.assertEqual(validate_config(c)['events'],[])
        del c['acceptance']['window_policy']
        with self.assertRaises(ValueError): validate_config(c)

    def test_group_analysis_preserves_transient_but_tests_final_window(self):
        c=deepcopy(self.c);c['acceptance']['window_policy']='event_group'
        c['events']=[{'at_s':.3,'target':'reference_speed_rpm','value':2400},
                     {'at_s':.305,'target':'load_torque_nm','value':.03}]
        c=validate_config(c)
        t=np.arange(80000)/100000;ref=np.where(t>=.30005,2400.,1800.)
        load=np.where(t>=.30505,.03,.01);speed=ref.copy()
        speed[(t>=.3)&(t<.37)]-=100
        def save():
            y=np.column_stack([t,t,speed*math.pi/30,np.zeros((len(t),3)),load,ref*math.pi/30,load])
            np.savetxt(self.path,y,delimiter=',',header=','.join(('t_relative_s','t_simulation_s',*PMSMPreviewAdapter.columns)),comments='')
        save();r=analyze_preview(self.path,c)
        self.assertEqual(r['status'],'passed');self.assertEqual(len(r['windows']),2)
        speed[t>=.42]-=60;save();r=analyze_preview(self.path,c)
        self.assertEqual(r['status'],'failed')
        self.assertFalse(r['checks']['settled_speed_tracking'])

    def test_group_policy_rejects_bad_policy_order_and_short_final_window(self):
        for policy in ('invalid',None,False):
            c=deepcopy(self.c);c['acceptance']['window_policy']=policy
            with self.assertRaises(ValueError): validate_config(c)
        c=deepcopy(self.c);c['acceptance']['window_policy']='event_group'
        c['events'][1]['at_s']=.19
        with self.assertRaises(ValueError): validate_config(c)
        c=deepcopy(self.c);c['acceptance']['window_policy']='event_group';c['events'][-1]['at_s']=.75
        with self.assertRaises(ValueError): validate_config(c)


if __name__=='__main__': unittest.main()
