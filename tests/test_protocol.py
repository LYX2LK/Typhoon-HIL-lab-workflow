"""Protocol and legacy parity, including native stdout and launcher errors."""
from contextlib import redirect_stdout,redirect_stderr,nullcontext
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from typhoon_lab.cli import main,_publish
from typhoon_lab.utils import write_json

ROOT=Path(__file__).resolve().parents[1]
KEYS={'schema_version','command','status','run_dir','record_status','experiment_status','artifacts','result','error'}


class ProtocolTests(unittest.TestCase):
    def invoke(self,args):
        out=io.StringIO();err=io.StringIO()
        with redirect_stdout(out),redirect_stderr(err):code=main(args)
        value=json.loads(out.getvalue());self.assertEqual(set(value),KEYS)
        return code,value,err.getvalue()

    def test_static_command_preserves_default_and_json_exit_semantics(self):
        out=io.StringIO()
        with redirect_stdout(out):
            default_code=main(['validate-case','--case','rlc_steady_state'])
        default=json.loads(out.getvalue())
        json_code,envelope,_=self.invoke(['validate-case','--case','rlc_steady_state','--json'])
        self.assertEqual(default_code,json_code)
        self.assertEqual(default['status'],envelope['status'])
        self.assertEqual(default['software_support']['status'],envelope['result']['software_support']['status'])
        self.assertIsNone(envelope['record_status'])
        self.assertIsNone(envelope['experiment_status'])

    def test_flag_positions_and_argument_errors(self):
        for args in (['--json','validate-case','--case','rlc_steady_state'],['validate-case','--json','--case','rlc_steady_state']):
            code,r,_=self.invoke(args);self.assertEqual(code,0);self.assertIsNone(r['experiment_status']);self.assertIsNone(r['record_status'])
        code,r,_=self.invoke(['--json','run','--unknown-option'])
        self.assertEqual(code,2);self.assertEqual(r['error']['stage'],'arguments')

    def test_missing_file(self):
        code,r,_=self.invoke(['run','--config','does-not-exist.json','--json'])
        self.assertEqual(code,2);self.assertEqual(r['status'],'error')

    def test_failed_run_does_not_claim_verification_and_report_is_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);write_json(p/'manifest.json',{'status':'failed','artifacts':{}})
            def run(args):_publish({'status':'failed','run_dir':str(p)});return 1
            with patch('typhoon_lab.cli._run',side_effect=run):
                code,r,_=self.invoke(['--json','run'])
            self.assertEqual(code,1);self.assertEqual(r['experiment_status'],'failed')
            self.assertIsNone(r['record_status']);self.assertIsNone(r['error'])
            def report(args):_publish({'status':'generated','files':[]});return 0
            with patch('typhoon_lab.cli._run',side_effect=report):
                code,r,_=self.invoke(['--json','report','--run-dir',str(p)])
            self.assertEqual(code,0);self.assertEqual(r['status'],'passed');self.assertEqual(r['experiment_status'],'failed');self.assertIsNone(r['record_status'])
            write_json(p/'manifest.json',{'status':'error','error':'old execution error','artifacts':{}})
            with patch('typhoon_lab.cli._run',side_effect=report):
                code,r,_=self.invoke(['--json','report','--run-dir',str(p)])
            self.assertEqual(code,0);self.assertEqual(r['experiment_status'],'error');self.assertIsNone(r['error'])

    def test_api_import_failure_keeps_error_record_and_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch('typhoon_lab.cli.new_run',return_value=Path(tmp)),patch('typhoon_lab.cli.runtime_lock',return_value=nullcontext()),patch('typhoon_lab.runtime.api_modules',side_effect=ImportError('injected API unavailable')),patch('typhoon_lab.reporting.write_report',return_value=[]):
                code,r,_=self.invoke(['--json','run','--config','configs/rlc_baseline.json'])
            self.assertEqual(code,1);self.assertEqual(r['status'],'error')
            self.assertIsNone(r['record_status']);self.assertEqual(r['error']['stage'],'execution')
            self.assertIn('injected API unavailable',json.loads((Path(tmp)/'manifest.json').read_text(encoding='utf-8'))['error'])
            saved=json.loads((Path(tmp)/'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['record_format_version'],1)
            self.assertEqual(saved['configuration_schema_version'],1)
            self.assertEqual(saved['analysis_method_version'],1)

    def test_native_and_python_output_cannot_pollute_protocol(self):
        program="""import sys,os
sys.path.insert(0,sys.argv[1])
from unittest.mock import patch
from typhoon_lab.cli import main,_publish
def run(args):
 print('python progress')
 os.write(1,b'native progress\\n')
 _publish({'status':'passed'})
 return 0
with patch('typhoon_lab.cli._run',side_effect=run):
 raise SystemExit(main(['--json','doctor']))
"""
        r=subprocess.run([sys.executable,'-B','-X','utf8','-c',program,str(ROOT/'src')],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(r.stdout)['status'],'passed')
        self.assertIn('python progress',r.stderr);self.assertIn('native progress',r.stderr)

    def test_malformed_saved_metadata_still_returns_one_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);write_json(path/'manifest.json',[])
            def report(args):_publish({'status':'generated','files':[]});return 0
            with patch('typhoon_lab.cli._run',side_effect=report):
                code,r,_=self.invoke(['--json','report','--run-dir',str(path)])
            self.assertEqual(code,2);self.assertEqual(r['status'],'error')
            self.assertEqual(r['error']['stage'],'response')

    def test_report_refuses_unknown_record_version_without_changing_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            manifest={'kind':'run','status':'passed','record_format_version':999,'artifacts':{}}
            write_json(path/'manifest.json',manifest)
            before=(path/'manifest.json').read_bytes()
            code,result,_=self.invoke(['--json','report','--run-dir',str(path)])
            self.assertEqual(code,2)
            self.assertIn('unsupported record_format_version',result['error']['message'])
            self.assertEqual((path/'manifest.json').read_bytes(),before)

    @unittest.skipUnless(os.name=='nt','PowerShell launcher is Windows-specific')
    def test_launcher_error_uses_same_envelope(self):
        env=dict(os.environ,TYPHOON_HOME=str(ROOT/'missing-install-for-test'))
        r=subprocess.run(['powershell.exe','-NoProfile','-File',str(ROOT/'lab.ps1'),'--json','list-cases'],env=env,capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(r.returncode,2);value=json.loads(r.stdout)
        self.assertEqual(set(value),KEYS);self.assertEqual(value['error']['stage'],'launcher')

    def test_entry_import_error_is_structured(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'scripts').mkdir();package=root/'src/typhoon_lab';package.mkdir(parents=True)
            shutil.copy2(ROOT/'scripts/lab_cli.py',root/'scripts/lab_cli.py')
            shutil.copy2(ROOT/'src/typhoon_lab/protocol.py',package/'protocol.py')
            (package/'__init__.py').write_text('',encoding='utf-8')
            (package/'cli.py').write_text("print('import progress')\nraise ImportError('injected entry import')",encoding='utf-8')
            r=subprocess.run([sys.executable,'-B','-X','utf8',str(root/'scripts/lab_cli.py'),'--json','run'],capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(r.returncode,2);self.assertEqual(json.loads(r.stdout)['error']['stage'],'entry_import')
            self.assertIn('import progress',r.stderr)
