"""Dependency preparation, preservation and command protocol checks."""
from contextlib import redirect_stdout, redirect_stderr
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from typhoon_lab.cli import main
from typhoon_lab.model_assets import prepare_models
from typhoon_lab.reporting import _metadata
from typhoon_lab.utils import sha256, write_json


class ModelAssetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='typhoon-model-assets-')
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.root = base/'教学项目 with spaces'
        self.install = base/'THCC 安装 with spaces'
        (self.root/'models').mkdir(parents=True)
        self.install.mkdir()
        (self.install/'.version').write_text('2026.3\n', encoding='utf-8')
        self.origins = {}
        for model_id in ('loopback', 'demo'):
            self.origins[model_id] = self.asset(model_id, '.tse')
            self.origins[model_id].update(thcc_version='2026.3', kind='official_teaching_example_local_dependency')
        self.origins['demo']['panel'] = self.asset('demo', '.cus')
        self.save()

    def asset(self, name, suffix):
        relative = f'examples/{name}{suffix}'
        source = self.install/relative
        source.parent.mkdir(exist_ok=True)
        source.write_bytes(b'\x00official bytes\xff'+name.encode()+suffix.encode())
        return {'installation_relative_path':relative, 'sha256':sha256(source)}

    def save(self):
        write_json(self.root/'models/origin.json', self.origins)

    def prepare(self):
        return prepare_models(self.root, self.install)

    def test_prepare_all_including_loopback_and_empty_reserved_directories(self):
        result = self.prepare()
        self.assertEqual(result['summary'], {'total':3, 'copied':3, 'present':0, 'failed':0})
        for item in result['assets']:
            self.assertEqual((self.root/item['path']).read_bytes(), (self.install/item['installation_relative_path']).read_bytes())
        for name in ('vendor', 'custom'):
            self.assertEqual(list((self.root/'models'/name).iterdir()), [])

    def test_repeat_preserves_files_and_does_not_need_source_again(self):
        self.prepare()
        before = {p.name:(sha256(p),p.stat().st_mtime_ns) for p in (self.root/'models').glob('*.*')}
        (self.install/'examples/demo.tse').unlink()
        result = self.prepare()
        self.assertEqual(result['summary'], {'total':3, 'copied':0, 'present':3, 'failed':0})
        self.assertEqual(before, {p.name:(sha256(p),p.stat().st_mtime_ns) for p in (self.root/'models').glob('*.*')})

    def test_changed_local_file_blocks_batch_and_is_preserved(self):
        target = self.root/'models/demo.cus'
        target.write_bytes(b'user edits')
        result = self.prepare()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(target.read_bytes(), b'user edits')
        self.assertFalse((self.root/'models/loopback.tse').exists())
        self.assertFalse((self.root/'models/vendor').exists())
        self.assertIn('local_hash_mismatch', [i['status'] for i in result['assets']])

    def test_missing_installed_panel_blocks_all_copies(self):
        (self.install/'examples/demo.cus').unlink()
        result = self.prepare()
        self.assertEqual(result['status'], 'failed')
        self.assertIn('missing_source', [i['status'] for i in result['assets']])
        self.assertFalse(list((self.root/'models').glob('*.tse')))

    def test_changed_installation_source_does_not_change_manifest(self):
        before = (self.root/'models/origin.json').read_bytes()
        (self.install/'examples/demo.tse').write_bytes(b'new version')
        result = self.prepare()
        self.assertEqual(result['status'], 'failed')
        self.assertIn('source_hash_mismatch', [i['status'] for i in result['assets']])
        self.assertEqual(before, (self.root/'models/origin.json').read_bytes())
        self.assertFalse(list((self.root/'models').glob('*.tse')))

    def test_version_mismatch_and_missing_version_are_reported(self):
        for value in ('2026.4', None):
            with self.subTest(version=value):
                p=self.install/'.version'
                if value is None:
                    p.unlink()
                else:
                    p.write_text(value, encoding='utf-8')
                result=self.prepare()
                self.assertEqual(result['installed_thcc_version'], value)
                self.assertTrue(all(i['status']=='version_mismatch' for i in result['assets']))
                self.assertFalse(list((self.root/'models').glob('*.tse')))

    def test_invalid_metadata_and_escaping_source_paths_never_copy(self):
        for value in ('../outside.tse', 'C:/outside.tse', '//server/share/file.tse', 'examples/file:stream', None):
            with self.subTest(path=value):
                self.origins['demo']['installation_relative_path']=value
                self.save()
                with self.assertRaises(ValueError):
                    self.prepare()
                self.assertFalse((self.root/'models/loopback.tse').exists())

    def test_copy_failure_removes_only_own_partial_file(self):
        with patch('typhoon_lab.model_assets.shutil.copyfileobj', side_effect=OSError('disk full')):
            result=self.prepare()
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(all(i['status']=='copy_error' for i in result['assets']))
        self.assertFalse(list((self.root/'models').glob('*.tse')))
        self.assertFalse(list((self.root/'models').glob('*.cus')))

    def test_nonofficial_entry_is_left_to_its_own_source_policy(self):
        self.origins['mine']={'kind':'self_authored', 'sha256':hashlib.sha256(b'mine').hexdigest()}
        self.save()
        result=self.prepare()
        self.assertEqual(result['summary']['total'], 3)
        self.assertFalse((self.root/'models/mine.tse').exists())

    def test_report_accepts_both_current_and_historical_origin_paths(self):
        for key in ('original_path', 'installation_relative_path'):
            rows=_metadata({'model_origin':{key:'examples/source.tse','sha256':'a'*64}})
            self.assertIn('examples/source.tse', [value for _,value in rows])

    def test_cli_default_and_json_keep_preparation_separate_from_experiment(self):
        for args in (['prepare-models'], ['--json','prepare-models'], ['prepare-models','--json']):
            with self.subTest(args=args):
                out=io.StringIO()
                with patch('typhoon_lab.model_assets.prepare_models', side_effect=self.prepare), redirect_stdout(out), redirect_stderr(io.StringIO()):
                    code=main(args)
                self.assertEqual(code, 0)
                result=json.loads(out.getvalue())
                self.assertEqual(result['status'], 'passed')
                if '--json' in args:
                    self.assertEqual(result['command'], 'prepare-models')
                    self.assertIsNone(result['record_status'])
                    self.assertIsNone(result['experiment_status'])
                    self.assertIsNone(result['run_dir'])

    def test_cli_failed_preparation_returns_nonzero_and_asset_diagnostics(self):
        (self.install/'examples/demo.cus').unlink()
        out=io.StringIO()
        with patch('typhoon_lab.model_assets.prepare_models', side_effect=self.prepare), redirect_stdout(out), redirect_stderr(io.StringIO()):
            code=main(['prepare-models','--json'])
        result=json.loads(out.getvalue())
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'failed')
        self.assertIn('missing_source', [i['status'] for i in result['result']['assets']])
        self.assertIsNone(result['experiment_status'])
