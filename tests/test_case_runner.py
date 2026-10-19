"""Orchestration contracts using synthetic CSV records, never simulation."""
from contextlib import ExitStack, nullcontext, redirect_stdout, redirect_stderr
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from typhoon_lab.case_runner import run_case
from typhoon_lab.cases import validate_case
from typhoon_lab.cli import main, verify_run
from typhoon_lab.analysis import analyze
from typhoon_lab.utils import finalize, sha256, write_json
from test_analysis import independent_phasors

ROOT=Path(__file__).resolve().parents[1]


class CaseRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for folder in ('cases/demo','configs','models','results'):(self.root/folder).mkdir(parents=True)
        self.case={'schema_version':1,'case_id':'demo','model_id':'rlc_filter','title':'demo',
                   'backend':'virtual_hil','model_origin_ref':'models/origin.json',
                   'configs':['configs/one.json','configs/two.json'],'acceptance_ref':'acceptance.md'}
        (self.root/'models/rlc_filter.tse').write_bytes(b'synthetic teaching model')
        self.origin={'sha256':sha256(self.root/'models/rlc_filter.tse')}
        write_json(self.root/'models/origin.json',{'rlc_filter':self.origin})
        write_json(self.root/'cases/demo/case.json',self.case)
        (self.root/'cases/demo/acceptance.md').write_text('criterion',encoding='utf-8')
        self.config=json.loads((ROOT/'configs/rlc_baseline.json').read_text(encoding='utf-8'))
        for rel in self.case['configs']:write_json(self.root/rel,self.config)
        self.count=0;self.called=[]
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        def allocate(kind):
            self.count+=1;p=self.root/'results'/f'batch-{self.count}';p.mkdir();return p
        for name,value in [('new_run',allocate),('runtime_lock',lambda:nullcontext()),('snapshot_code',lambda p:{})]:
            self.stack.enter_context(patch('typhoon_lab.case_runner.'+name,side_effect=value))

    def execute(self,path,config,multiplier=1):
        self.called.append(deepcopy(config))
        i,v=independent_phasors(config)
        t=np.arange(400)/20000
        phase=np.exp(2j*np.pi*config['source']['frequency_hz']*t)
        np.savetxt(path/'waveforms.csv',np.column_stack([t,t+.06,np.sqrt(2)*(i*phase).real*multiplier,np.sqrt(2)*(v*phase).real]),
                   delimiter=',',header='t_relative_s,t_simulation_s,I_A,Va1_V',comments='')
        write_json(path/'config.json',config)
        metrics=analyze(path/'waveforms.csv',config);write_json(path/'metrics.json',metrics)
        (path/'report.md').write_text('synthetic fixture',encoding='utf-8')
        snapshot=path/'code_snapshot/models/rlc_filter.tse';snapshot.parent.mkdir(parents=True)
        snapshot.write_bytes((self.root/'models/rlc_filter.tse').read_bytes())
        manifest={'schema_version':1,'kind':'run','status':metrics['status'],'model':'rlc_filter','backend':'virtual_hil',
                  'model_origin':self.origin,'code_sha256':{'models/rlc_filter.tse':self.origin['sha256']}}
        return finalize(path,manifest)

    def test_all_configs_preflight_before_any_execution_or_batch(self):
        invalid=deepcopy(self.config);invalid['source']['rms_v']=True
        write_json(self.root/'configs/two.json',invalid)
        with patch('typhoon_lab.case_runner.execute_case') as execute:
            result=run_case('demo',self.root)
        self.assertEqual(result['status'],'failed');self.assertIsNone(result['run_dir'])
        self.assertIsNone(result['record_status']);execute.assert_not_called()
        self.assertEqual(list((self.root/'results').iterdir()),[])

    def test_missing_dependency_prevents_api_and_keeps_specific_gap(self):
        (self.root/'models/rlc_filter.tse').unlink()
        with patch('typhoon_lab.case_runner.execute_case') as execute:
            result=run_case('demo',self.root)
        execute.assert_not_called();self.assertEqual(result['preflight']['availability'],'missing_local_dependency')
        self.assertFalse(result['simulation_started'])

    def test_serial_runs_automatic_index_and_read_only_evidence(self):
        def execute(path,config):
            self.assertEqual(len(self.called)%2,len(list(path.parent.glob('*/verification.json'))))
            return self.execute(path,config)
        with patch('typhoon_lab.case_runner.execute_case',side_effect=execute):
            first=run_case('demo',self.root);second=run_case('demo',self.root)
        self.assertEqual(first['status'],'passed');self.assertEqual(first['record_status'],'passed')
        self.assertEqual([r['config'] for r in first['runs']],self.case['configs'])
        self.assertEqual(len(self.called),4)
        self.assertTrue((Path(second['run_dir'])/'previous-evidence-index.json').exists())
        index=json.loads(Path(second['evidence_index']).read_text(encoding='utf-8'))
        self.assertEqual(index['case_run_dir'],'results/batch-2')
        self.assertEqual(validate_case('demo',self.root)['runtime_validation']['status'],'completed')
        self.assertEqual(verify_run(first['run_dir'],write=False)['record_status'],'passed')
        raw=Path(first['run_dir'])/first['runs'][0]['run_dir'].split('batch-1/')[-1]/'waveforms.csv'
        raw.write_text(raw.read_text(encoding='utf-8')+'\n',encoding='utf-8')
        self.assertEqual(verify_run(first['run_dir'],write=False)['record_status'],'failed')

    def test_performance_failure_continues_and_record_stays_passed(self):
        with patch('typhoon_lab.case_runner.execute_case',side_effect=lambda p,c:self.execute(p,c,1.5)):
            result=run_case('demo',self.root)
        self.assertEqual(result['status'],'failed');self.assertEqual(result['record_status'],'passed')
        self.assertEqual(result['experiment_status'],'failed');self.assertNotIn('error',result)
        self.assertEqual(len(self.called),2)
        self.assertTrue(validate_case('demo',self.root)['runtime_validation']['simulation_verified'])

    def test_execution_error_stops_and_overwrites_latest_with_actual_attempt(self):
        index=self.root/'results/case-validation/demo/latest.json'
        write_json(index,{'runs':[{'config':'configs/one.json','run_dir':'results/old'}]})
        with patch('typhoon_lab.case_runner.execute_case',side_effect=RuntimeError('injected error')) as execute:
            result=run_case('demo',self.root)
        self.assertEqual(execute.call_count,1);self.assertEqual(result['status'],'error')
        manifest=json.loads((Path(result['run_dir'])/'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['runs'][1]['experiment_status'],'skipped')
        latest=json.loads(index.read_text(encoding='utf-8'))
        self.assertEqual(latest['unrun_configs'],['configs/two.json'])
        self.assertNotEqual(latest['runs'][0]['run_dir'],'results/old')
        self.assertFalse(validate_case('demo',self.root)['runtime_validation']['simulation_verified'])

    def test_sweep_uses_shared_sweep_executor(self):
        config=deepcopy(self.config);config['sweep']={'parameter':'rin_ohm','values':[1,5]}
        write_json(self.root/'configs/two.json',config)
        with patch('typhoon_lab.case_runner.execute_case',side_effect=self.execute), \
             patch('typhoon_lab.runtime.execute_case',side_effect=self.execute), \
             patch('typhoon_lab.runtime.environment',return_value={}):
            result=run_case('demo',self.root)
        self.assertEqual(result['status'],'passed');self.assertEqual(len(self.called),3)
        last=self.root/result['runs'][1]['run_dir']
        self.assertEqual(json.loads((last/'manifest.json').read_text(encoding='utf-8'))['kind'],'sweep')
        self.assertEqual(verify_run(result['run_dir'],write=False)['record_status'],'passed')

    def test_parent_rejects_child_escape_and_configuration_omission(self):
        with patch('typhoon_lab.case_runner.execute_case',side_effect=self.execute):result=run_case('demo',self.root)
        path=Path(result['run_dir']);manifest=json.loads((path/'manifest.json').read_text(encoding='utf-8'))
        manifest['runs'][0]['relative_dir']='../outside';write_json(path/'manifest.json',manifest)
        self.assertEqual(verify_run(path,write=False)['record_status'],'failed')
        manifest['runs']=manifest['runs'][1:];write_json(path/'manifest.json',manifest)
        self.assertEqual(verify_run(path,write=False)['record_status'],'failed')

    def test_json_flag_positions_default_parity_and_preflight(self):
        def invoke(args):
            out=io.StringIO()
            with redirect_stdout(out),redirect_stderr(io.StringIO()):code=main(args)
            return code,json.loads(out.getvalue()[out.getvalue().index('{'):])
        with patch('typhoon_lab.case_runner.PROJECT',self.root),patch('typhoon_lab.case_runner.execute_case',side_effect=self.execute):
            for args in (['--json','run-case','--case','demo'],['run-case','--case','demo','--json']):
                code,result=invoke(args)
                self.assertEqual(code,0);self.assertEqual(result['command'],'run-case')
                self.assertEqual(result['record_status'],'passed');self.assertEqual(result['experiment_status'],'passed')
                self.assertIn('report.md',result['artifacts'])
            code,result=invoke(['run-case','--case','demo'])
            self.assertEqual(code,0);self.assertEqual(result['record_status'],'passed')
            (self.root/'models/rlc_filter.tse').unlink()
            code,result=invoke(['run-case','--case','demo','--json'])
            self.assertEqual(code,1);self.assertIsNone(result['record_status']);self.assertIsNone(result['experiment_status'])

    def test_index_failure_returns_verified_run_directory(self):
        index=self.root/'results/case-validation/demo/latest.json'
        def save(path,value):
            if path==index:raise PermissionError('injected index write failure')
            return write_json(path,value)
        with patch('typhoon_lab.case_runner.execute_case',side_effect=self.execute), \
             patch('typhoon_lab.case_runner.write_json',side_effect=save):
            result=run_case('demo',self.root)
        self.assertEqual(result['status'],'error');self.assertEqual(result['error']['stage'],'evidence_index')
        self.assertEqual(result['record_status'],'passed');self.assertEqual(result['experiment_status'],'passed')
        self.assertEqual(verify_run(result['run_dir'],write=False)['status'],'passed')

    def test_config_change_after_snapshot_is_detected_before_second_execution(self):
        def execute(path,config):
            result=self.execute(path,config)
            modified=deepcopy(self.config);modified['source']['rms_v']=11
            write_json(self.root/'configs/two.json',modified)
            return result
        with patch('typhoon_lab.case_runner.execute_case',side_effect=execute):result=run_case('demo',self.root)
        self.assertEqual(len(self.called),1);self.assertEqual(result['status'],'error')
        self.assertIn('configuration changed',result['error']['message'])

    def test_broken_record_stops_following_configuration(self):
        def execute(path,config):
            result=self.execute(path,config)
            (path/'waveforms.csv').write_text('corrupted',encoding='utf-8')
            return result
        with patch('typhoon_lab.case_runner.execute_case',side_effect=execute):result=run_case('demo',self.root)
        self.assertEqual(len(self.called),1);self.assertEqual(result['status'],'error')
        self.assertEqual(result['record_status'],'failed')
        manifest=json.loads((Path(result['run_dir'])/'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['runs'][1]['experiment_status'],'skipped')
