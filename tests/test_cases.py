"""Case boundaries and static support, without API calls or result writes."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from typhoon_lab.cases import validate_case, list_cases, reference
from typhoon_lab.utils import sha256

ROOT=Path(__file__).resolve().parents[1]


class CaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'project';self.root.mkdir()
        for name in ('cases/demo','models','configs'):(self.root/name).mkdir(parents=True,exist_ok=True)
        self.case={'schema_version':1,'case_id':'demo','model_id':'rlc_filter','title':'测试','backend':'virtual_hil',
                   'model_origin_ref':'models/origin.json','configs':['configs/run.json'],'acceptance_ref':'acceptance.md'}
        (self.root/'models/rlc_filter.tse').write_bytes(b'model fixture')
        self.write('models/origin.json',{'rlc_filter':{'sha256':sha256(self.root/'models/rlc_filter.tse')}})
        self.config=json.loads((ROOT/'configs/rlc_baseline.json').read_text(encoding='utf-8'))
        self.write('configs/run.json',self.config)
        (self.root/'cases/demo/acceptance.md').write_text('criterion',encoding='utf-8')
        self.save()

    def write(self, rel, value):
        (self.root/rel).write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')

    def save(self):self.write('cases/demo/case.json',self.case)
    def check(self):return validate_case('demo',self.root)

    def test_valid_case_is_static_and_read_only(self):
        before={str(p):sha256(p) for p in self.root.rglob('*') if p.is_file()}
        with patch('typhoon_lab.runtime.api_modules',side_effect=AssertionError('API forbidden')):
            r=self.check();all_cases=list_cases(self.root)
        self.assertEqual(r['status'],'passed');self.assertEqual(all_cases['status'],'passed')
        self.assertFalse(r['runtime_validation']['simulation_verified'])
        self.assertEqual(before,{str(p):sha256(p) for p in self.root.rglob('*') if p.is_file()})
        self.assertFalse((self.root/'results').exists())
        self.assertTrue(r['software_support']['capabilities']['run'])
        self.assertEqual(r['software_support']['configuration_checks'][0]['status'],'passed')

    def test_adapter_dependency_is_a_support_gap(self):
        with patch('typhoon_lab.cases.get_adapter',side_effect=ModuleNotFoundError('missing dependency')):
            r=self.check()
        self.assertEqual(r['integrity']['status'],'passed')
        self.assertEqual(r['software_support']['status'],'failed')
        self.assertEqual(r['software_support']['configuration_checks'][0]['code'],'validation_unavailable')
        self.assertFalse(r['runtime_validation']['simulation_verified'])

    def test_unimplemented_validator_is_reported_as_unchecked(self):
        from typhoon_lab.adapters import get_adapter
        adapter=get_adapter('rlc_filter')
        with patch.object(adapter,'validate',side_effect=NotImplementedError()),patch('typhoon_lab.cases.get_adapter',return_value=adapter):
            r=self.check()
        self.assertEqual(r['integrity']['status'],'passed')
        self.assertEqual(r['software_support']['status'],'failed')
        self.assertEqual(r['software_support']['configuration_checks'][0]['status'],'not_checked')

    def test_missing_and_modified_model(self):
        p=self.root/'models/rlc_filter.tse';p.write_bytes(b'changed')
        self.assertEqual(self.check()['integrity']['status'],'failed')
        p.unlink();r=self.check();self.assertEqual(r['status'],'failed')
        self.assertEqual(r['availability'],'missing_local_dependency')
        self.assertEqual(r['missing_local_dependencies'][0]['path'],'models/rlc_filter.tse')
        self.assertEqual(list_cases(self.root)['status'],'passed')

    def test_unknown_adapter_is_distinct_from_material_integrity(self):
        self.case['model_id']='unknown';self.save()
        (self.root/'models/unknown.tse').write_bytes(b'unknown')
        self.write('models/origin.json',{'unknown':{'sha256':sha256(self.root/'models/unknown.tse')}})
        c=deepcopy(self.config);c['model']='unknown';self.write('configs/run.json',c)
        r=self.check();self.assertEqual(r['integrity']['status'],'passed')
        self.assertEqual(r['software_support']['status'],'failed')
        self.assertFalse(r['runtime_validation']['simulation_verified'])

    def test_invalid_configuration_does_not_claim_support(self):
        self.config['source']['rms_v']=True;self.write('configs/run.json',self.config)
        self.assertEqual(self.check()['software_support']['status'],'failed')

    def test_parent_absolute_drive_and_alternate_stream_rejected(self):
        for value in ('../outside','models/../models/origin.json','C:\\secret.json','/tmp/secret','//server/share/file','models/file:stream'):
            with self.subTest(value=value),self.assertRaises(ValueError):reference(self.root,value)
        self.case['acceptance_ref']='../../models/origin.json';self.save()
        self.assertEqual(self.check()['status'],'failed')

    def test_real_directory_link_cannot_escape(self):
        outside=Path(self.tmp.name)/'outside';outside.mkdir()
        (outside/'secret.json').write_text('{}',encoding='utf-8')
        link=self.root/'configs/escape'
        if os.name=='nt':
            import _winapi
            _winapi.CreateJunction(str(outside),str(link))
        else:link.symlink_to(outside,target_is_directory=True)
        with self.assertRaises(ValueError):reference(self.root,'configs/escape/secret.json',allowed=self.root/'configs')

    def test_duplicate_keys_and_wrong_model_are_rejected(self):
        (self.root/'cases/demo/case.json').write_text('{"schema_version":1,"schema_version":1}',encoding='utf-8')
        self.assertEqual(self.check()['status'],'failed')

    def test_normalized_record_is_accepted_but_changed_config_is_stale(self):
        from typhoon_lab.config import validate_config
        run=self.root/'results/run';run.mkdir(parents=True)
        (self.root/'results/case-validation/demo').mkdir(parents=True)
        self.write('results/run/config.json',validate_config(self.config))
        self.write('results/run/manifest.json',{'model':'rlc_filter','backend':'virtual_hil','kind':'run',
                    'model_origin':{'sha256':sha256(self.root/'models/rlc_filter.tse')},
                    'code_sha256':{'models/rlc_filter.tse':sha256(self.root/'models/rlc_filter.tse')}})
        self.write('results/case-validation/demo/latest.json',{'runs':[{'config':'configs/run.json','run_dir':'results/run'}]})
        with patch('typhoon_lab.cli.verify_run',return_value={'record_status':'passed','experiment_status':'failed'}) as verify:
            r=self.check();self.assertTrue(r['runtime_validation']['simulation_verified'])
            self.assertEqual(r['runtime_validation']['runs'][0]['experiment_status'],'failed')
            self.assertEqual(verify.call_args.kwargs,{'write':False})
            self.config['source']['rms_v']=11;self.write('configs/run.json',self.config)
            self.assertFalse(self.check()['runtime_validation']['simulation_verified'])
        self.save();self.config['model']='boost_closed_loop';self.write('configs/run.json',self.config)
        self.assertEqual(self.check()['status'],'failed')

    def test_bad_case_does_not_fail_discovery_or_hide_good_case(self):
        folder=self.root/'cases/broken';folder.mkdir()
        (folder/'case.json').write_text('{bad JSON',encoding='utf-8')
        result=list_cases(self.root)
        self.assertEqual(result['status'],'passed')
        self.assertEqual(result['summary'],{'total':2,'static_passed':1,'static_failed':1,'missing_local_dependency':0})
        self.assertEqual(len(result['cases']),2)
        self.assertEqual(next(c for c in result['cases'] if c['case_id']=='demo')['status'],'passed')

    def test_missing_panel_is_structured_and_hash_mismatch_is_not_missing(self):
        self.write('models/origin.json',{'rlc_filter':{'sha256':sha256(self.root/'models/rlc_filter.tse'),
             'panel':{'sha256':'a'*64,'installation_relative_path':'examples/panel.cus'}}})
        r=self.check();self.assertEqual(r['availability'],'missing_local_dependency')
        self.assertEqual(r['missing_local_dependencies'][0]['kind'],'panel')
        self.assertEqual(r['missing_local_dependencies'][0]['installation_relative_path'],'examples/panel.cus')
        (self.root/'models/rlc_filter.cus').write_bytes(b'wrong hash')
        r=self.check();self.assertEqual(r['availability'],'unavailable')
        self.assertEqual(r['missing_local_dependencies'],[])

    def test_missing_catalog_is_a_discovery_error(self):
        import shutil
        shutil.rmtree(self.root/'cases')
        with self.assertRaises(FileNotFoundError):list_cases(self.root)
