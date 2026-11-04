"""Portable field-data packages and offline recomputation from their snapshots."""
from copy import deepcopy
from pathlib import Path
import shutil
import sys

from .external_records import _compare
from .external_waveforms import relative_file
from .field_analysis import analyze_data
from .field_intake import read_json, validate_intake
from .tle9877 import parse_sample_ldf
from .utils import PROJECT, finalize, now, sha256, write_json
from .versions import record_version_problems

KIND = 'field_test_data'
SNAPSHOTS = ('field_intake.py', 'field_analysis.py', 'field_records.py', 'field_reporting.py',
             'tle9877.py', 'external_waveforms.py', 'external_records.py', 'utils.py', 'versions.py', 'cases.py')


def snapshot_name(source):
    return f"inputs/{source['id']}{'.jsonl' if source['format'] == 'lin_jsonl' else '.csv'}"


def saved_intake(original):
    result = deepcopy(original)
    result['ldf'] = 'inputs/LIN.ldf'
    for source in result['sources']:
        source['file'] = snapshot_name(source)
    return result


def analyze_field(intake_path, input_dir, output_dir):
    started_at = now()
    source, out = Path(input_dir).resolve(), Path(output_dir).resolve()
    intake_path = Path(intake_path).resolve()
    original = validate_intake(read_json(intake_path))
    if out.exists() or out == source or out.is_relative_to(source) or source.is_relative_to(out):
        raise ValueError('output must be new, separate from and not nested with input directory')
    if intake_path.is_relative_to(out):
        raise ValueError('output must not contain the intake file')
    if not source.is_dir():
        raise ValueError('input directory is missing')
    protocol = relative_file(source, original['ldf']) if original.get('ldf') else PROJECT / 'data/tle9877/LIN.ldf'
    ldf = parse_sample_ldf(protocol)
    protocol_digest = sha256(protocol)
    out.mkdir(parents=True)
    (out / 'inputs').mkdir()
    shutil.copyfile(protocol, out / 'inputs/LIN.ldf')
    if sha256(out / 'inputs/LIN.ldf') != protocol_digest or sha256(protocol) != protocol_digest:
        raise ValueError('LDF changed while copying')
    provenance = {'original_intake': original, 'protocol_sha256': protocol_digest, 'sources': []}
    for item in original['sources']:
        path = relative_file(source, item['file'])
        rel = snapshot_name(item)
        digest = sha256(path) if path.is_file() else None
        if digest is not None:
            shutil.copyfile(path, out / rel)
            if sha256(path) != digest or sha256(out / rel) != digest:
                raise ValueError('input changed while copying: ' + item['id'])
        provenance['sources'].append({'id': item['id'], 'original_relative_path': item['file'],
                                      'snapshot': rel, 'sha256': digest, 'available': digest is not None})
    intake = saved_intake(original)
    write_json(out / 'intake.json', intake)
    write_json(out / 'provenance.json', provenance)
    metrics, streams = analyze_data(out, intake, ldf)
    write_json(out / 'metrics.json', metrics)
    write_json(out / 'normalized.json', streams)
    for name in SNAPSHOTS:
        target = out / 'code_snapshot' / name
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(PROJECT / 'src/typhoon_lab' / name, target)
    from .field_reporting import write_field_report
    write_field_report(out, intake, metrics, streams)
    manifest = {'kind': KIND, 'configuration_schema_version': 1, 'analysis_method_version': 1,
        'started_at': started_at, 'environment': {'python': sys.version},
        **{k: metrics[k] for k in ('status', 'data_quality_status', 'analysis_status', 'criteria_status', 'performance_status')},
        'sources': provenance['sources'], 'protocol_sha256': protocol_digest,
        'code_sha256': {n: sha256(out / 'code_snapshot' / n) for n in SNAPSHOTS}}
    finalize(out, manifest)
    return {k: v for k, v in {**metrics, 'run_dir': str(out), 'record_status': None}.items()
            if k not in {'summaries', 'checks', 'synchronization', 'events'}}


def verify_field(run_dir, write=False):
    out = Path(run_dir).resolve()
    problems, metrics = [], {}
    try:
        manifest = read_json(out / 'manifest.json')
        if manifest.get('kind') != KIND:
            raise ValueError('expected field_test_data record')
        version_problems = record_version_problems(manifest)
        for key in ('record_format_version', 'analysis_method_version', 'configuration_schema_version'):
            if type(manifest.get(key)) is not int or manifest[key] != 1:
                version_problems.append('missing or unsupported ' + key)
        problems.extend(version_problems)
        hashes = manifest.get('artifacts', {})
        if not isinstance(hashes, dict):
            raise ValueError('invalid artifact hashes')
        required = {'intake.json', 'provenance.json', 'normalized.json', 'metrics.json',
                    'inputs/LIN.ldf', 'report.md', 'report.html', 'plot-index.json'} | {'code_snapshot/' + n for n in SNAPSHOTS}
        for rel, expected in hashes.items():
            path = relative_file(out, rel)
            if not path.is_file() or sha256(path) != expected:
                problems.append('artifact missing or changed: ' + rel)
        for name in SNAPSHOTS:
            if manifest.get('code_sha256', {}).get(name) != hashes.get('code_snapshot/' + name):
                problems.append('code provenance mismatch: ' + name)
        if manifest.get('protocol_sha256') != hashes.get('inputs/LIN.ldf'):
            problems.append('protocol snapshot differs from declared digest')
        if version_problems:
            problems.append('recomputation skipped for unsupported version; saved code is never executed')
        else:
            intake = validate_intake(read_json(out / 'intake.json'))
            provenance = read_json(out / 'provenance.json')
            original = validate_intake(provenance['original_intake'])
            if intake != saved_intake(original):
                problems.append('intake differs from original declared mapping')
            expected_sources = []
            for item in original['sources']:
                rel = snapshot_name(item)
                available = rel in hashes
                if available:
                    required.add(rel)
                elif (out / rel).exists():
                    problems.append('unhashed input appeared: ' + rel)
                expected_sources.append({'id': item['id'], 'original_relative_path': item['file'], 'snapshot': rel,
                                         'sha256': hashes.get(rel), 'available': available})
            if provenance['sources'] != expected_sources or manifest['sources'] != expected_sources:
                problems.append('source mapping/digests differ from declared originals')
            if provenance.get('protocol_sha256') != hashes.get('inputs/LIN.ldf'):
                problems.append('protocol provenance differs')
            actual, streams = analyze_data(out, intake, parse_sample_ldf(out / 'inputs/LIN.ldf'))
            metrics = read_json(out / 'metrics.json')
            problems.extend(_compare(actual, metrics, 'metrics'))
            problems.extend(_compare(streams, read_json(out / 'normalized.json'), 'normalized'))
            for key in ('status', 'data_quality_status', 'analysis_status', 'criteria_status', 'performance_status'):
                if manifest.get(key) != actual[key]:
                    problems.append('manifest differs from recomputation: ' + key)
            from .field_reporting import figure_specs
            expected_plots = figure_specs(intake, streams)
            if read_json(out / 'plot-index.json') != expected_plots:
                problems.append('plot index differs from available data')
            required.update(s['file'] for s in expected_plots)
        problems.extend('required artifact not hashed: ' + p for p in sorted(required - hashes.keys()))
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        problems.append('verification error: ' + str(exc))
    result = {'status': 'failed' if problems else 'passed', 'record_status': 'failed' if problems else 'passed',
              'run_dir': str(out), 'verified_at': now(), 'problems': problems,
              **{k: metrics.get(k) for k in ('data_quality_status', 'analysis_status', 'criteria_status', 'performance_status')}}
    if write:
        write_json(out / 'verification.json', result)
    return result
