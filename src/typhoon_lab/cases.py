"""Read-only case discovery. Metadata cannot choose imports or escape the project."""
from pathlib import Path, PureWindowsPath
import json
import re
from .utils import PROJECT, sha256
from .adapters import get_adapter, supported_models

FIELDS = {'schema_version', 'case_id', 'model_id', 'title', 'backend',
          'model_origin_ref', 'configs', 'acceptance_ref'}
IDENTIFIER = re.compile(r'[a-z][a-z0-9_-]{0,63}\Z')


def read_json(path):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError(f'duplicate JSON key: {key}')
            out[key] = value
        return out
    def invalid(value):
        raise ValueError(f'nonfinite JSON number: {value}')
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), object_pairs_hook=pairs, parse_constant=invalid)


def reference(root, value, *, base=None, allowed=None):
    root = Path(root).resolve()
    if not isinstance(value, str) or not value or '\x00' in value:
        raise ValueError('reference must be a nonempty relative path')
    value = value.replace('\\', '/')
    p = Path(value)
    if p.is_absolute() or PureWindowsPath(value).drive or ':' in value or '..' in p.parts:
        raise ValueError(f'absolute or parent reference is forbidden: {value}')
    candidate = ((base or root) / p).resolve()
    boundary = Path(allowed or root).resolve()
    if not boundary.is_relative_to(root) or not candidate.is_relative_to(boundary):
        raise ValueError(f'reference leaves allowed project directory: {value}')
    return candidate


def case_path(selector, root):
    boundary = reference(root, 'cases')
    if not isinstance(selector, str) or not selector:
        raise ValueError('case selector is required')
    if IDENTIFIER.fullmatch(selector):
        return reference(root, f'cases/{selector}/case.json', allowed=boundary)
    p = Path(selector)
    if p.is_absolute():
        p = p.resolve()
        if not p.is_relative_to(boundary):
            raise ValueError('case definition must be inside project cases/')
    else:
        p = reference(root, selector, allowed=boundary)
    if p.name != 'case.json':
        raise ValueError('case definition must be named case.json')
    return p


def runtime_evidence(case, configs, origin, root):
    """Local evidence index is optional and is never an execution permission."""
    out = {'status': 'not_verified', 'simulation_verified': False, 'runs': []}
    try:
        index = reference(root, f"results/case-validation/{case['case_id']}/latest.json", allowed=root/'results')
        if not index.is_file():
            return out
        entries = read_json(index)['runs']
        if not isinstance(entries, list):
            raise ValueError('evidence runs must be a list')
        by_config = {}
        for entry in entries:
            config = entry['config']
            if config in by_config:
                raise ValueError('duplicate configuration in evidence index')
            by_config[config] = entry['run_dir']
        for config, config_path in configs.items():
            if config not in by_config:
                raise ValueError(f'no evidence for {config}')
            path = reference(root, by_config[config], allowed=root/'results')
            manifest = read_json(path/'manifest.json')
            if manifest.get('model') != case['model_id'] or manifest.get('backend') != case['backend']:
                raise ValueError('evidence model/backend mismatch')
            normalized = get_adapter(case['model_id']).validate(read_json(config_path), sweep=manifest.get('kind') == 'sweep')
            if normalized != read_json(path/'config.json'):
                raise ValueError('evidence configuration is stale')
            if manifest.get('kind') == 'sweep':
                origins = [read_json(reference(root, e['relative_dir'], base=path, allowed=path)/'manifest.json').get('model_origin', {}) for e in manifest['cases']]
            else:
                origins = [manifest.get('model_origin', {})]
            if not origins or any(o.get('sha256') != origin['sha256'] for o in origins):
                raise ValueError('evidence source model is stale')
            if not manifest.get('code_sha256'):
                raise ValueError('evidence has no execution code provenance')
            for rel, digest in manifest['code_sha256'].items():
                current = reference(root, rel)
                if not current.is_file() or sha256(current) != digest:
                    raise ValueError('evidence code is stale')
            # Lazy offline recomputation; no Typhoon API import and no writes.
            from .records import verify_run
            verification = verify_run(path, write=False)
            out['runs'].append({'config': config, 'run_dir': by_config[config],
                                'record_status': verification['record_status'],
                                'experiment_status': verification['experiment_status']})
            if verification['record_status'] != 'passed' or verification['experiment_status'] not in ('passed', 'failed'):
                raise ValueError('evidence does not establish a complete recorded experiment')
        out.update(status='completed', simulation_verified=True)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        out.update(status='not_verified', reason=str(exc), simulation_verified=False)
    return out


def validate_case(selector, root=None, *, check_evidence=True):
    root = Path(root or PROJECT).resolve()
    integrity = {'status': 'failed', 'problems': []}
    support = {'status': 'not_checked', 'registered': False, 'capabilities': None,
               'configuration_checks': [], 'problems': []}
    runtime = {'status': 'not_verified', 'simulation_verified': False, 'runs': []}
    case = {}
    configs = {}
    missing = []
    origin = None
    try:
        path = case_path(selector, root)
        case = read_json(path)
        if not isinstance(case, dict) or set(case) != FIELDS:
            raise ValueError(f'case fields must be exactly {sorted(FIELDS)}')
        if type(case['schema_version']) is not int or case['schema_version'] != 1:
            raise ValueError('case schema_version must be integer 1')
        for field in ('case_id', 'model_id'):
            if not isinstance(case[field], str) or not IDENTIFIER.fullmatch(case[field]):
                raise ValueError(f'invalid {field}')
        if path.parent.name != case['case_id']:
            raise ValueError('case_id must match its directory name')
        if not isinstance(case['title'], str) or not case['title'].strip() or case['backend'] != 'virtual_hil':
            raise ValueError('case requires a title and virtual_hil backend')
        configs_raw = case['configs']
        if not isinstance(configs_raw, list) or not configs_raw or any(not isinstance(v, str) for v in configs_raw) or len(set(configs_raw)) != len(configs_raw):
            raise ValueError('configs must be a nonempty list of unique references')
        acceptance = reference(root, case['acceptance_ref'], base=path.parent, allowed=path.parent)
        if not acceptance.is_file():
            integrity['problems'].append(f'missing acceptance document: {case["acceptance_ref"]}')
        origin_path = reference(root, case['model_origin_ref'], allowed=root/'models')
        if origin_path != root/'models'/'origin.json':
            raise ValueError('model_origin_ref must reference models/origin.json')
        origin = read_json(origin_path)[case['model_id']]
        if not isinstance(origin, dict) or ('panel' in origin and not isinstance(origin['panel'], dict)):
            raise ValueError('model origin and optional panel must be JSON objects')
        model = reference(root, f'models/{case["model_id"]}.tse', allowed=root/'models')
        for label, source, digest in [('model', model, origin.get('sha256'))] + ([('panel', reference(root, f'models/{case["model_id"]}.cus', allowed=root/'models'), origin['panel'].get('sha256'))] if 'panel' in origin else []):
            if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
                integrity['problems'].append(f'invalid {label} source hash')
            elif not source.is_file():
                integrity['problems'].append(f'missing {label}: {source.name}; run prepare-models with the documented local installation')
                source_origin = origin if label == 'model' else origin['panel']
                missing.append({'kind': label, 'path': source.relative_to(root).as_posix(),
                                'sha256': digest,
                                'installation_relative_path': source_origin.get('installation_relative_path')})
            elif sha256(source) != digest:
                integrity['problems'].append(f'{label} differs from recorded source hash')
        support['registered'] = case['model_id'] in supported_models()
        support['status'] = 'passed' if support['registered'] else 'failed'
        if not support['registered']:
            support['problems'].append('Adapter is not registered; parameter validation and execution are unavailable')
        adapter = None
        if support['registered']:
            try:
                adapter = get_adapter(case['model_id'])
            except (ImportError, AttributeError) as exc:
                support['status'] = 'failed'
                support['problems'].append(f'Adapter dependency or implementation is unavailable: {exc}')
        if adapter is not None:
            operations = ('prepare', 'initialize', 'schedule', 'check_sampling', 'analyze', 'report')
            support['capabilities'] = {
                'configuration_schema_version': getattr(adapter, 'schema_version', None),
                'run': all(callable(getattr(adapter, method, None)) for method in operations),
                'runtime_events': bool(getattr(adapter, 'has_events', False)),
                'capture_signals': list(getattr(adapter, 'signals', ())),
            }
            if not support['capabilities']['run']:
                support['status'] = 'failed'
                support['problems'].append('Adapter does not declare all required run operations')
        for rel in configs_raw:
            config_path = reference(root, rel, allowed=root/'configs')
            raw = read_json(config_path)
            if not isinstance(raw, dict) or raw.get('model') != case['model_id'] or raw.get('backend') != case['backend']:
                raise ValueError(f'configuration identity mismatch: {rel}')
            configs[rel] = config_path
            check = {'config': rel, 'status': 'not_checked', 'code': 'validation_unavailable'}
            support['configuration_checks'].append(check)
            if adapter is not None and callable(getattr(adapter, 'validate', None)):
                try:
                    adapter.validate(raw, sweep='sweep' in raw)
                    check.update(status='passed', code=None)
                except NotImplementedError as exc:
                    support['status'] = 'failed'
                    check['message'] = str(exc) or 'configuration validator is not implemented'
                    support['problems'].append(f'{rel}: configuration validation is not implemented')
                except (ValueError, TypeError, KeyError) as exc:
                    support['status'] = 'failed';support['problems'].append(f'{rel}: {exc}')
                    check.update(status='failed', code='invalid_configuration', message=str(exc))
            elif adapter is not None:
                support['status'] = 'failed'
                support['problems'].append(f'{rel}: configuration validator is unavailable')
        integrity['status'] = 'passed' if not integrity['problems'] else 'failed'
        if check_evidence and integrity['status'] == support['status'] == 'passed':
            runtime = runtime_evidence(case, configs, origin, root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        integrity['problems'].append(str(exc))
    passed = integrity['status'] == support['status'] == 'passed'
    return {'status': 'passed' if passed else 'failed', 'case_id': case.get('case_id') if isinstance(case, dict) else None,
            'availability': 'missing_local_dependency' if missing else ('available' if passed else 'unavailable'),
            'missing_local_dependencies': missing,
            'case': case, 'integrity': integrity, 'software_support': support,
            'runtime_validation': runtime, 'scope': 'read-only static checks; optional evidence recomputation; no API calls or simulation',
            'next_steps': [] if passed else ['Resolve reported material/configuration gaps or implement the missing Adapter before execution.']}


def list_cases(root=None):
    root = Path(root or PROJECT).resolve()
    boundary = reference(root, 'cases')
    if not boundary.is_dir():
        raise FileNotFoundError('project cases/ directory is missing')
    items = [validate_case(p.relative_to(root).as_posix(), root) for p in sorted(boundary.glob('*/case.json'))]
    return {'status': 'passed', 'discovery_status': 'passed',
            'summary': {'total': len(items),
                        'static_passed': sum(i['status'] == 'passed' for i in items),
                        'static_failed': sum(i['status'] != 'passed' for i in items),
                        'missing_local_dependency': sum(i['availability'] == 'missing_local_dependency' for i in items)},
            'cases': items, 'registered_models': list(supported_models()), 'simulation_started': False}
