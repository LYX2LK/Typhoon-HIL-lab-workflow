"""Prepare byte-identical official models from the configured THCC installation."""
from pathlib import Path
import re
import shutil
from .cases import IDENTIFIER, read_json, reference
from .utils import PROJECT, sha256


def prepare_models(root=None, install=None):
    root = Path(root or PROJECT).resolve()
    if install is None:
        from .runtime import installation
        install = installation()
    home = Path(install).resolve()
    models = reference(root, 'models')
    origins = read_json(models/'origin.json')
    if not isinstance(origins, dict) or not origins:
        raise ValueError('models/origin.json must be a nonempty object')
    reserved = [reference(root, f'models/{name}', allowed=models) for name in ('vendor', 'custom')]
    version_path = home/'.version'
    installed_version = version_path.read_text(encoding='utf-8-sig').strip() if version_path.is_file() else None
    items = []
    jobs = []
    for model_id, origin in origins.items():
        if not isinstance(origin, dict) or not IDENTIFIER.fullmatch(model_id):
            raise ValueError(f'invalid model origin: {model_id}')
        if origin.get('kind') not in ('official_teaching_example', 'official_teaching_example_local_dependency'):
            continue
        version = origin.get('thcc_version')
        if not isinstance(version, str) or not version:
            raise ValueError(f'missing THCC version: {model_id}')
        assets = [('model', origin, '.tse')]
        if 'panel' in origin:
            assets.append(('panel', origin['panel'], '.cus'))
        for kind, asset, suffix in assets:
            if not isinstance(asset, dict) or not isinstance(asset.get('sha256'), str) or not re.fullmatch('[0-9a-f]{64}', asset['sha256']):
                raise ValueError(f'invalid {kind} source hash: {model_id}')
            source = reference(home, asset.get('installation_relative_path'))
            target = reference(root, f'models/{model_id}{suffix}', allowed=models)
            item = {'model_id':model_id, 'kind':kind, 'path':target.relative_to(root).as_posix(),
                    'installation_relative_path':asset['installation_relative_path'],
                    'sha256':asset['sha256'], 'thcc_version':version}
            items.append(item)
            if installed_version != version:
                item.update(status='version_mismatch', problem=f'Expected THCC {version}; installed version is {installed_version!r}.')
            elif target.exists():
                if target.is_file() and sha256(target) == asset['sha256']:
                    item['status'] = 'present'
                else:
                    item.update(status='local_hash_mismatch', problem='Existing local asset differs; preserve it and resolve the mismatch before retrying.')
            elif not source.is_file():
                item.update(status='missing_source', problem='Source is missing from the configured THCC installation.')
            elif sha256(source) != asset['sha256']:
                item.update(status='source_hash_mismatch', problem='Installed source differs from the recorded SHA-256.')
            else:
                item['status'] = 'ready_to_copy'
                jobs.append((item, source, target))
    if not items:
        raise ValueError('No official teaching model assets are registered')
    blocked = any(i['status'] not in ('present', 'ready_to_copy') for i in items)
    if blocked:
        for item, _, _ in jobs:
            item.update(status='blocked', problem='No files copied because dependency preflight failed.')
    else:
        for directory in reserved:
            directory.mkdir(exist_ok=True)
        for item, source, target in jobs:
            created = False
            try:
                with source.open('rb') as source_file, target.open('xb') as target_file:
                    created = True
                    shutil.copyfileobj(source_file, target_file)
                if sha256(target) != item['sha256']:
                    raise ValueError('Copied file differs from the recorded SHA-256')
                item['status'] = 'copied'
            except (OSError, ValueError) as exc:
                if created:
                    target.unlink()
                item.update(status='copy_error', problem=str(exc))
    failed = [i for i in items if i['status'] not in ('present', 'copied')]
    return {'status':'failed' if failed else 'passed', 'typhoon_home':str(home),
            'installed_thcc_version':installed_version,
            'summary':{'total':len(items), 'copied':sum(i['status']=='copied' for i in items),
                       'present':sum(i['status']=='present' for i in items), 'failed':len(failed)},
            'assets':items, 'reserved_directories':['models/vendor', 'models/custom'],
            'scope':'Local model preparation and byte/hash checks; no compilation or simulation.'}
