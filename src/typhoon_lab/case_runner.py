"""Case orchestration over the shared executors; all simulation stays serial."""
from copy import deepcopy
from pathlib import Path
import shutil
import traceback
from .adapters import get_adapter
from .cases import case_path, read_json, reference, validate_case
from .runtime import execute_case, execute_sweep, snapshot_code
from .utils import PROJECT, finalize, new_run, note, now, runtime_lock, sha256, write_json


def aggregate(states):
    states = list(states)
    if not states or 'error' in states:
        return 'error'
    return 'passed' if all(s == 'passed' for s in states) else 'failed'


def write_case_report(path, manifest):
    path = Path(path)
    rows = [f"# {manifest['case_id']}\n", f"实验状态：{manifest['experiment_status']}；记录状态：{manifest['record_status']}。\n",
            '| 配置 | 实验 | 记录 | 结果 |', '|---|---|---|---|']
    for run in manifest['runs']:
        link = f"[目录]({run['relative_dir']}/)" if run.get('relative_dir') else '未执行'
        rows.append(f"| {run['config']} | {run['experiment_status']} | {run['record_status']} | {link} |")
    if manifest.get('error'):
        rows.append('\n执行问题：' + manifest['error'])
    report = path/'report.md'
    report.write_text('\n'.join(rows)+'\n', encoding='utf-8')
    return [report]


def verify_case_run(path, manifest):
    """Return record and experiment problems without writing child records."""
    from .records import verify_run
    problems, experiments = [], []
    try:
        definition = reference(path, manifest['case_snapshot'])
        case = read_json(definition)
        if case['case_id'] != manifest['case_id'] or case['model_id'] != manifest['model'] or case['backend'] != manifest['backend']:
            raise ValueError('case snapshot identity mismatch')
        runs = manifest['runs']
        if [r['config'] for r in runs] != case['configs']:
            raise ValueError('case run configurations differ from case snapshot')
        records, states, seen = [], [], set()
        for run in runs:
            config = run['config']
            state = run['experiment_status']; states.append(state)
            if state != 'passed':
                experiments.append(f'{config}: experiment status is {state}')
            if run.get('relative_dir') is None:
                if state != 'skipped' or not run.get('reason'):
                    problems.append(f'{config}: missing execution directory or skip reason')
                continue
            child = reference(path, run['relative_dir'], allowed=path/'runs')
            if child in seen:
                raise ValueError('duplicate case execution directory')
            seen.add(child)
            actual = verify_run(child, write=False)
            records.append(actual['record_status'])
            problems.extend(f'{config}: {p}' for p in actual['record_problems'])
            if state != actual['experiment_status'] or run['record_status'] != actual['record_status']:
                problems.append(f'{config}: case summary differs from child verification')
            child_manifest = read_json(child/'manifest.json')
            if child_manifest.get('model') != manifest['model'] or child_manifest.get('backend') != manifest['backend']:
                problems.append(f'{config}: child model/backend mismatch')
            raw = read_json(reference(path, 'inputs/'+config, allowed=path/'inputs/configs'))
            expected = get_adapter(case['model_id']).validate(raw, sweep='sweep' in raw)
            if read_json(child/'config.json') != expected:
                problems.append(f'{config}: child configuration differs from input snapshot')
        record = 'passed' if records and all(s == 'passed' for s in records) else 'failed'
        if manifest['record_status'] != record:
            problems.append('case record summary differs from child records')
        if manifest['experiment_status'] != aggregate(states):
            problems.append('case experiment summary differs from child experiments')
        expected_status = aggregate(states) if record == 'passed' else 'error'
        if manifest['status'] != expected_status:
            problems.append('case overall status differs from child results')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        problems.append(f'case verification error: {exc}')
    return problems, experiments


def run_case(selector, root=None):
    from .records import verify_run
    root = Path(root or PROJECT).resolve()
    preflight = validate_case(selector, root, check_evidence=False)
    if preflight['status'] != 'passed':
        return {'status': 'failed', 'case_id': preflight['case_id'], 'run_dir': None,
                'record_status': None, 'experiment_status': None, 'simulation_started': False,
                'preflight': preflight, 'runs': []}
    # Recheck after acquiring the lock, before any model/API work or batch directory.
    with runtime_lock():
        preflight = validate_case(selector, root, check_evidence=False)
        if preflight['status'] != 'passed':
            return {'status': 'failed', 'case_id': preflight['case_id'], 'run_dir': None,
                    'record_status': None, 'experiment_status': None, 'simulation_started': False,
                    'preflight': preflight, 'runs': []}
        case = preflight['case']
        adapter = get_adapter(case['model_id'])
        plans = []
        for rel in case['configs']:
            raw = read_json(reference(root, rel, allowed=root/'configs'))
            plans.append((rel, adapter.validate(raw, sweep='sweep' in raw)))
        path = new_run('case-'+case['case_id'])
        index = reference(root, f"results/case-validation/{case['case_id']}/latest.json", allowed=root/'results')
        manifest = {'schema_version': 1, 'kind': 'case', 'case_id': case['case_id'],
                    'model': case['model_id'], 'backend': case['backend'], 'started_at': now(),
                    'status': 'error', 'experiment_status': 'error', 'record_status': 'failed',
                    'case_snapshot': 'inputs/'+case_path(selector, root).relative_to(root).as_posix(),
                    'runs': [], 'code_sha256': snapshot_code(path)}
        write_json(path/'manifest.json', manifest)
        # Preserve the previous pointer as evidence before publishing a new attempt.
        if index.is_file():
            shutil.copy2(index, path/'previous-evidence-index.json')
        inputs = [case_path(selector, root), reference(root, case['model_origin_ref']),
                  reference(root, case['acceptance_ref'], base=case_path(selector, root).parent)]
        inputs.extend(reference(root, rel, allowed=root/'configs') for rel, _ in plans)
        for source in inputs:
            target = path/'inputs'/source.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        halted = False
        for number, (rel, config) in enumerate(plans, 1):
            if halted:
                manifest['runs'].append({'config': rel, 'relative_dir': None,
                                         'record_status': None, 'experiment_status': 'skipped',
                                         'reason': 'previous execution or record verification errored'})
                continue
            child = path/'runs'/f'{number:02d}-{Path(rel).stem}'
            child.mkdir(parents=True)
            note(path, f'Running {case["case_id"]}: {rel}')
            try:
                if sha256(reference(root, rel)) != sha256(path/'inputs'/rel):
                    raise ValueError('configuration changed after case preflight')
                execute = execute_sweep if 'sweep' in config else execute_case
                result = execute(child, deepcopy(config))
            except Exception as exc:
                result = {'schema_version': 1, 'kind': 'sweep' if 'sweep' in config else 'run',
                          'model': case['model_id'], 'backend': case['backend'],
                          'started_at': now(), 'status': 'error', 'error': f'{type(exc).__name__}: {exc}'}
                write_json(child/'config.json', config)
                note(child, traceback.format_exc()); finalize(child, result)
            try:
                verification = verify_run(child)
            except Exception as exc:
                verification = {'status': 'failed', 'record_status': 'failed',
                                'experiment_status': result['status'], 'record_problems': [str(exc)]}
                write_json(child/'verification.json', verification)
            manifest['runs'].append({'config': rel, 'relative_dir': child.relative_to(path).as_posix(),
                                     'record_status': verification['record_status'],
                                     'experiment_status': verification['experiment_status']})
            halted = result['status'] == 'error' or verification['record_status'] != 'passed'
            if halted:
                manifest['error'] = result.get('error') or result.get('report_error') or 'execution/record verification errored; see child records'
            write_json(path/'manifest.json', manifest)
        manifest['experiment_status'] = aggregate(r['experiment_status'] for r in manifest['runs'])
        records = [r['record_status'] for r in manifest['runs'] if r['relative_dir'] is not None]
        manifest['record_status'] = 'passed' if records and all(s == 'passed' for s in records) else 'failed'
        manifest['status'] = manifest['experiment_status'] if manifest['record_status'] == 'passed' else 'error'
        write_case_report(path, manifest)
        note(path, f'Case batch completed: {manifest["status"]}')
        finalize(path, manifest)
        verification = verify_run(path)
        entries = [{'config': r['config'], 'run_dir': (path/r['relative_dir']).relative_to(root).as_posix(),
                    'record_status': r['record_status'], 'experiment_status': r['experiment_status']}
                   for r in manifest['runs'] if r['relative_dir'] is not None]
        index_error = None
        try:
            write_json(index, {'schema_version': 1, 'case_id': case['case_id'], 'updated_at': now(),
                               'case_run_dir': path.relative_to(root).as_posix(), 'runs': entries,
                               'unrun_configs': [r['config'] for r in manifest['runs'] if r['relative_dir'] is None]})
        except OSError as exc:
            index_error = {'code': 'evidence_index_error', 'stage': 'evidence_index', 'message': str(exc)}
        result = {'status': manifest['status'] if verification['record_status'] == 'passed' else 'error',
                  'case_id': case['case_id'], 'run_dir': str(path),
                  'record_status': verification['record_status'],
                  'experiment_status': manifest['experiment_status'],
                  'evidence_index': str(index), 'runs': entries}
        if manifest.get('error') or verification['record_status'] != 'passed':
            result['error'] = {'code': 'case_execution_error', 'stage': 'case_execution',
                               'message': manifest.get('error') or str(verification['record_problems'])}
        if index_error:
            result.update(status='error', error=index_error)
        return result
