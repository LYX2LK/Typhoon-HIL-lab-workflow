"""Boundary selection and censored-result handling must not turn failures into zero."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import tempfile
import json

spec=importlib.util.spec_from_file_location('boundary_analysis',Path(__file__).resolve().parents[1]/'scripts/analyze_pmsm_boundary.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class BoundaryTests(unittest.TestCase):
    def row(self,rec=.08,name='a'):
        return {'order':'simultaneous','recovery_s':rec,'observed_horizon_s':.5,
                'settled_max_error_rpm':60.,'iae_rpm_s':10.,'condition':name,
                'recovery_margin_ms':None if rec is None else (.1-rec)*1000}

    def test_verdict_preserves_deadline_and_censoring(self):
        self.assertEqual(module.recovery_verdict(self.row(.1)),'passed')
        self.assertEqual(module.recovery_verdict(self.row(.10001)),'failed')
        self.assertEqual(module.recovery_verdict(self.row(None)),'failed')
        r=self.row(None);r['observed_horizon_s']=.08
        self.assertEqual(module.recovery_verdict(r),'not_evaluable')
        r['order']='baseline';self.assertEqual(module.recovery_verdict(r),'not_applicable')

    def test_frozen_ranking_prioritizes_censoring_then_low_margin(self):
        rows=[self.row(.08,'pass'),self.row(.15,'fail'),self.row(None,'censored')]
        self.assertEqual([r['condition'] for r in sorted(rows,key=module.severity)],['censored','fail','pass'])

    def test_censored_tie_uses_final_error_and_finite_tie_iae(self):
        a=self.row(None,'a');b=self.row(None,'b');b['settled_max_error_rpm']=100
        self.assertIs(min([a,b],key=module.severity),b)
        a=self.row(.08,'a');b=self.row(.08,'b');b['iae_rpm_s']=12
        self.assertIs(min([a,b],key=module.severity),b)

    def test_order_description_uses_target_and_times(self):
        c={'parameters':{'reference_speed_rpm':1800,'load_torque_nm':.01},
           'events':[{'target':'load_torque_nm','value':.1,'at_s':.3},
                     {'target':'reference_speed_rpm','value':3000,'at_s':.315}]}
        d=module.describe(c)
        self.assertEqual(d['order'],'load_then_speed');self.assertEqual(d['signed_load_delay_ms'],-15)
        self.assertEqual(d['speed_rpm'],3000);self.assertEqual(d['load_nm'],.1)
        c['events']=[];self.assertEqual(module.describe(c)['order'],'baseline')

    def test_incomplete_coarse_grid_cannot_choose_dense_stage(self):
        with patch.object(module,'collect',return_value=([],{},[],[])):
            with self.assertRaisesRegex(ValueError,'incomplete'):
                module.select_dense([],Path('unused'))

    def test_partial_batch_keeps_error_and_skip_ledger_and_verifies_completed_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);batch=root/'batch';batch.mkdir();(batch/'ok').mkdir();(batch/'bad').mkdir()
            m={'case_id':'pmsm_boundary_coarse','experiment_status':'error','case_snapshot':'inputs/case.json',
               'runs':[{'relative_dir':'ok','experiment_status':'passed'},
                       {'config':'bad.json','relative_dir':'bad','experiment_status':'error'},
                       {'relative_dir':None,'experiment_status':'skipped'}]}
            (batch/'manifest.json').write_text(json.dumps(m),encoding='utf-8')
            with patch.object(module,'ROOT',root),patch.object(module,'verify_run',side_effect=[{'record_status':'failed','record_problems':['bad.json: run has no metrics.json for recomputation']},{'record_status':'passed'}]) as verify,patch.object(module,'load_one',return_value={'condition':'ok'}):
                rows,sources,audits,checks=module.collect([batch],include_prior=False)
                self.assertEqual(rows,[{'condition':'ok'}]);self.assertEqual(verify.call_count,2)
                self.assertEqual(len([c for c in checks if 'not_evaluable_run' in c]),2)
            with patch.object(module,'ROOT',root),patch.object(module,'verify_run',return_value={'record_status':'failed','record_problems':['artifact changed: config.json']}):
                with self.assertRaisesRegex(ValueError,'beyond documented'):
                    module.collect([batch],include_prior=False)

    def test_isolated_ledger_requires_completion_and_preserves_phase(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'ledger.json'
            ledger={'kind':'isolated_runs','completed':False,'phase':'pmsm_boundary_dense',
                    'runs':[{'run_dir':'run1','condition':'case_a','experiment_status':'passed'}]}
            path.write_text(json.dumps(ledger),encoding='utf-8')
            with patch.object(module,'ROOT',root):
                with self.assertRaisesRegex(ValueError,'incomplete'):module.collect([path],False)
            ledger['completed']=True;path.write_text(json.dumps(ledger),encoding='utf-8')
            with patch.object(module,'ROOT',root),patch.object(module,'verify_run',return_value={'record_status':'passed','experiment_status':'passed'}),patch.object(module,'load_one',return_value={'condition':'old'}) as load:
                rows,_,_,_=module.collect([path],False)
                self.assertEqual(rows[0]['condition'],'case_a')
                self.assertEqual(load.call_args.args[1],'pmsm_boundary_dense')


if __name__=='__main__':unittest.main()
