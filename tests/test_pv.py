import unittest,tempfile,json
from pathlib import Path
from copy import deepcopy
import numpy as np
from typhoon_lab.adapters.pv import PVAdapter,REFERENCE_POINTS
from typhoon_lab.pv_analysis import analyze_pv
from typhoon_lab.config import load_config
from typhoon_lab.utils import PROJECT

class PVTests(unittest.TestCase):
    def setUp(self):
        self.config=load_config(PROJECT/'configs/pv_hzwatt_51hz.json')
        self.config['capture'].update(duration_s=1,sample_rate_hz=2000)
        self.config['acceptance']['min_samples']=2000
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'waveforms.csv'
        n=2000;rel=np.arange(n)/2000
        self.data=np.column_stack([rel,rel+12,np.full(n,170.),np.full(n,250.),np.full(n,51.),np.ones(n),np.zeros(n),np.zeros(n)])
    def tearDown(self):self.temp.cleanup()
    def analyze(self):
        np.savetxt(self.path,self.data,delimiter=',',header=','.join(('t_relative_s','t_simulation_s',*PVAdapter.columns)),comments='',fmt='%.17g')
        return analyze_pv(self.path,self.config)
    def test_independent_reference_and_pass(self):
        r=self.analyze()
        self.assertEqual(r['status'],'passed');self.assertEqual(r['power']['expected_kw'],170.)
        self.assertEqual(r['capture']['sample_count'],2000)
    def test_all_four_tabulated_references(self):
        for frequency,power in REFERENCE_POINTS.items():
            self.config['parameters']['frequency_pu']=frequency
            self.data[:,2]=power*250
            self.data[:,4]=frequency*50
            self.assertEqual(self.analyze()['status'],'passed')
    def test_single_outlier_fails_all_sample_criterion(self):
        self.data[123,2]=172
        r=self.analyze();self.assertEqual(r['status'],'failed');self.assertEqual(r['power']['exceeded_sample_count'],1)
    def test_reference_error_fails_even_with_correct_power(self):
        self.data[:,3]=170
        self.assertEqual(self.analyze()['status'],'failed')
    def test_alarm_is_performance_failure(self):
        self.data[50,6]=1
        self.assertEqual(self.analyze()['status'],'failed')
    def test_wrong_frequency_is_invalid_experiment(self):
        self.data[:,4]=50
        with self.assertRaisesRegex(ValueError,'frequency'):self.analyze()
    def test_disabled_is_invalid_experiment(self):
        self.data[:,5]=0
        with self.assertRaisesRegex(ValueError,'enable'):self.analyze()
    def test_truncated_capture_rejected(self):
        self.data=self.data[:-1]
        with self.assertRaises(ValueError):self.analyze()
    def test_nan_rejected(self):
        self.data[10,2]=np.nan
        with self.assertRaises(ValueError):self.analyze()
    def test_gap_rejected(self):
        self.data[100:,0:2]+=.001
        with self.assertRaises(ValueError):self.analyze()
    def test_early_capture_rejected(self):
        self.data[:,1]-=1
        with self.assertRaisesRegex(ValueError,'settling'):self.analyze()
    def test_unsupported_frequency_rejected(self):
        self.config['parameters']['frequency_pu']=1.01
        with self.assertRaisesRegex(ValueError,'reference point'):PVAdapter().validate(self.config)
    def test_bool_and_fractional_counts_rejected(self):
        for group,key,value in [('parameters','frequency_pu',True),('acceptance','min_samples',2000.5),('capture','duration_s',float('inf'))]:
            c=deepcopy(self.config);c[group][key]=value
            with self.assertRaises(ValueError):PVAdapter().validate(c)
    def test_wrong_backend_and_sweep_rejected(self):
        c=deepcopy(self.config);c['backend']='physical_hil'
        with self.assertRaises(ValueError):PVAdapter().validate(c)
        with self.assertRaises(ValueError):PVAdapter().validate(self.config,sweep=True)
    def test_report_uses_pv_scope_and_preserves_raw(self):
        from typhoon_lab.pv_reporting import write_pv_report
        r=self.analyze();folder=self.path.parent;before=self.path.read_bytes()
        (folder/'config.json').write_text(json.dumps(self.config),encoding='utf-8')
        (folder/'metrics.json').write_text(json.dumps(r),encoding='utf-8')
        write_pv_report(folder,{'status':'passed'})
        text=(folder/'report.md').read_text(encoding='utf-8')
        self.assertIn('Generic PV plant',text)
        self.assertNotIn('RLC',text)
        self.assertEqual(before,self.path.read_bytes())
    def test_old_pv_method_is_explicitly_unsupported(self):
        from typhoon_lab.versions import record_version_problems
        self.assertIn('unsupported analysis_method_version: 1',record_version_problems(
            {'kind':'run','model':'generic_pv_plant','analysis_method_version':1}))
    def test_missing_signal_rejected(self):
        self.data=self.data[:,:-1]
        with self.assertRaises(ValueError):self.analyze()

if __name__=='__main__':unittest.main()
