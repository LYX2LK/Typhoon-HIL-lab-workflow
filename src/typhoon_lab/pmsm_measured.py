"""Native dual-three-phase measured channels and condition-matched references.

No signal is renamed to model truth. Labels and source filenames stay private.
"""
from pathlib import Path
import hashlib
import json
import re
import shutil
import numpy as np
from scipy.io import loadmat

from .diagnostic_tools import ObservationTools, CATALOG, number
from .utils import now, sha256, write_json

DATA_URL = 'https://zenodo.org/records/13889418'
PAPER_URL = 'https://doi.org/10.1109/IECON49645.2022.9968364'


def channel_mapping():
    result = {}
    def add(native, public, unit, meaning, evidence):
        result[public] = {'native': native, 'unit': unit, 'meaning': meaning,
                          'scale': 1, 'offset': 0, 'unit_evidence': evidence}
    for sub in (1, 2):
        for axis in ('A', 'B', 'C', 'd', 'q'):
            add(f'Currents_SubSys{sub}_{axis}', f'i{sub}_{axis.lower()}', 'A',
                f'子系统{sub}原始{axis}轴电流；保留发布坐标和变换约定',
                '仓库确认电流语义；关联论文图8使用A。文件未附逐通道标定表。')
        for axis in ('d', 'q'):
            add(f'Voltage_SubSys{sub}_{axis}', f'v{sub}_{axis}_control', 'native_control_voltage',
                f'子系统{sub}的{axis}轴电压控制量',
                '仓库确认控制电压语义；导出倍率未明示，保留原数值，不宣称已标定V。')
    for native, public, unit, meaning in (
        ('Speed_rpm', 'measured_speed_rpm', 'rpm', '测得机械速度'),
        ('Speed_requred_rpm', 'reference_speed_rpm', 'rpm', '要求的机械速度，保留原拼写映射'),
        ('Speed_rad_el', 'measured_electrical_speed', 'rad_e/s', '测得电角速度'),
        ('Speed_requred_rad_el', 'reference_electrical_speed', 'rad_e/s', '要求的电角速度'),
        ('SinCos_Electrical_Sin', 'electrical_sin', '1', '电角度正弦'),
        ('SinCos_Electrical_Cos', 'electrical_cos', '1', '电角度余弦')):
        add(native, public, unit, meaning, '发布字段名及仓库说明；电角速度与机械速度分开。')
    return result


MAPPING = channel_mapping()
UNITS = {k: v['unit'] for k, v in MAPPING.items()}
KNOWLEDGE = {
    'topology': 'dual_three_phase_PMSM', 'source': DATA_URL, 'machine_paper': PAPER_URL,
    'speed': '测得速度、给定与电角速度分别记录；无独立模型真值/控制器速度反馈对。',
    'load': '测功机负载为文件名给定的工况元信息，没有测得转矩波形。',
    'voltage': 'dq电压是控制量，保留发布数值；倍率确认前单位为native_control_voltage。',
    'currents': '两组三相和dq量分别查询；dq缩放约定未发布，不重算dq、不跨坐标直接相减。',
    'missing': ['model_speed_rpm', 'controller_speed_rpm', 'torque_nm', 'current_limit_flag'],
    'reference': '仅同负载、同阶段、相近给定和斜率的健康窗口作条件化描述参照，无实体验收阈值。',
}
POLICY = {'window_s': .5, 'speed_abs_tolerance_rpm': 5, 'speed_relative_tolerance': .03,
          'slope_abs_tolerance_rpm_s': 5, 'slope_relative_tolerance': .1,
          'steady_slope_threshold_rpm_s': 2, 'reference_change_threshold_rpm': .001,
          'stage_age_tolerance_s': .05, 'step_sum_abs_tolerance_rpm': 1,
          'step_sum_relative_tolerance': .05}


def native_arrays(path):
    m = loadmat(path, squeeze_me=True)
    expected = {'Time', *(x['native'] for x in MAPPING.values())}
    if {k for k in m if not k.startswith('__')} != expected:
        raise ValueError('native channel schema differs from the inspected release')
    d = {'time_s': np.asarray(m['Time'], dtype=float).reshape(-1)}
    d.update({k: np.asarray(m[v['native']], dtype=float).reshape(-1) for k, v in MAPPING.items()})
    if len({len(v) for v in d.values()}) != 1 or len(d['time_s']) < 10:
        raise ValueError('native channel lengths differ or recording is too short')
    if any(not np.all(np.isfinite(v)) for v in d.values()):
        raise ValueError('non-finite native samples')
    dt = np.diff(d['time_s'])
    if np.any(dt <= 0) or np.max(np.abs(dt - .0001)) > 1e-8:
        raise ValueError('expected increasing native 10kHz time grid')
    # Independent named speed representations cross-check the 10 pole-pair machine.
    for a, b in [('measured_speed_rpm', 'measured_electrical_speed'),
                 ('reference_speed_rpm', 'reference_electrical_speed')]:
        if np.max(np.abs(d[a]*np.pi/30*10 - d[b])) > .01:
            raise ValueError('mechanical/electrical speed scaling differs')
    return d


def condition(data, window):
    start, end = map(number, window)
    t = data['time_s']; mask = (t >= start) & (t < end)
    if end <= start or np.count_nonzero(mask) < 5 or start < t[0] or end > t[-1] + .000100001:
        raise ValueError('invalid condition window')
    x = data['reference_speed_rpm'][mask]; tt = t[mask]
    slope = float(np.polyfit(tt - tt[0], x, 1)[0])
    phase = 'accelerating' if slope > POLICY['steady_slope_threshold_rpm_s'] else 'decelerating' if slope < -POLICY['steady_slope_threshold_rpm_s'] else 'steady'
    ids = np.flatnonzero(np.abs(np.diff(data['reference_speed_rpm'])) > POLICY['reference_change_threshold_rpm']) + 1
    inside = ids[(t[ids] >= start) & (t[ids] < end)]
    previous = ids[t[ids] < start]
    deltas = data['reference_speed_rpm'][inside] - data['reference_speed_rpm'][inside-1]
    if len(inside):
        stage = 'changing_up' if np.all(deltas > 0) else 'changing_down' if np.all(deltas < 0) else 'mixed_changes'
    else:
        stage = 'post_change_hold' if len(previous) else 'no_prior_observed_change'
    return {'window_s': [start, end], 'sample_count': int(mask.sum()),
            'reference_mean_rpm': float(np.mean(x)), 'reference_min_rpm': float(np.min(x)),
            'reference_max_rpm': float(np.max(x)), 'reference_slope_rpm_s': slope,
            'phase': phase, 'stage': stage, 'reference_change_count': len(inside),
            'reference_step_sum_rpm': float(np.sum(deltas)),
            'time_since_previous_change_s': float(start - t[previous[-1]]) if len(previous) else None}


def regimes(data):
    t = data['time_s']; width = POLICY['window_s']
    count = int(np.floor((t[-1] - t[0] + 1e-8)/width))
    return [condition(data, [float(t[0]+i*width), float(t[0]+(i+1)*width)]) for i in range(count)]


def prepare_measured(output, source_dir):
    output, source_dir = Path(output), Path(source_dir)
    if output.exists():
        raise ValueError('output must be a new directory')
    paths = sorted(source_dir.glob('*.mat'))
    if not paths:
        raise ValueError('no native MAT recordings')
    # Validate all sources before writing outputs. This parser is release-specific.
    inputs = []
    for p in paths:
        match = re.fullmatch(r'spd10-5000rpm_flt(\d+)z([uv]?)_(\d+)NM.mat', p.name)
        if not match:
            raise ValueError('unrecognized source conditions')
        inputs.append((p, match, native_arrays(p)))
    output.mkdir(parents=True); (output/'observations').mkdir(); (output/'sources').mkdir()
    cases = {}; private = {}; refs = []
    # Permute IDs independently of the fault label's sorted order.
    order = np.random.default_rng(901).permutation(len(inputs))
    for i, source_i in enumerate(order, 1):
        p, match, data = inputs[source_i]; case_id = f'M{i:03d}'
        target = output/'sources'/p.name; shutil.copy2(p, target)
        receipt = p.with_name(p.name+'.provenance.json')
        if receipt.exists():
            shutil.copy2(receipt, target.with_name(target.name+'.provenance.json'))
        observed = output/'observations'/f'{case_id}.npz'
        np.savez_compressed(observed, **data)
        cases[case_id] = {'observation': f'observations/{case_id}.npz',
                         'load_setpoint_nm': int(match[3]), 'load_basis': 'filename_dynamometer_setpoint',
                         'time_bounds_s': [float(data['time_s'][0]), float(data['time_s'][-1])],
                         'sample_count': len(data['time_s']), 'regimes': regimes(data),
                         'independent_recording_id': case_id}
        private[case_id] = {'source': f'sources/{p.name}', 'source_sha256': sha256(target),
                            'shorted_turns': int(match[1]), 'fault_phase': match[2] or None}
        if int(match[1]) == 0:
            refs.append(case_id)
    if not refs:
        raise ValueError('a released healthy recording is required for reference matching')
    metadata = source_dir.parent/'metadata.raw.json'
    if metadata.exists():
        shutil.copy2(metadata, output/'sources/repository-metadata.json')
    public = {'schema_version': 1, 'source': DATA_URL, 'origin': 'experimental_fault_emulation',
              'topology': 'dual_three_phase_PMSM', 'channels': MAPPING, 'knowledge': KNOWLEDGE,
              'query_tools': CATALOG | {
                  'events': {'arguments': {'channel': 'reference_speed_rpm', 'window_s': '[开始,结束]'},
                             'returns': '大于0.001rpm的实际给定变化，窗口内至多20项；无故障发生时间标签'},
                  'controller_knowledge': {'arguments': {}, 'returns': '实测拓扑、量纲、来源和未记录观测，不沿用本地模型限幅参数'},
                  'normal_reference': {'arguments': {'channels': '开放通道名数组', 'window_s': '0.5秒窗口'},
                                       'returns': '目标工况、匹配正常工况、两侧统计与统计差，样本不跨记录逐点对齐'}},
              'reference_policy': POLICY, 'normal_reference_ids': refs, 'cases': cases,
              'evaluation_readiness': 'mapped_development_queries_only'}
    write_json(output/'dataset.json', public); write_json(output/'private.json', private)
    from .runtime import snapshot_code
    snapshot_code(output)
    hashes = {p.relative_to(output).as_posix(): sha256(p) for p in output.rglob('*') if p.is_file()}
    write_json(output/'manifest.json', {'kind': 'pmsm_measured', 'record_format_version': 1,
               'analysis_method_version': 1, 'created_at': now(), 'status': 'passed', 'artifacts': hashes})
    result = verify_measured(output)
    write_json(output/'verification.json', result)
    return result


def read_data(output, case):
    path = (Path(output)/case['observation']).resolve()
    if not path.is_relative_to((Path(output)/'observations').resolve()):
        raise ValueError('observation path escapes package')
    with np.load(path, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def verify_measured(output):
    output = Path(output); problems = []
    try:
        manifest = json.loads((output/'manifest.json').read_text(encoding='utf-8'))
        if (manifest['kind'], manifest['record_format_version'], manifest['analysis_method_version']) != ('pmsm_measured', 1, 1):
            raise ValueError('unsupported measured record version')
        for rel, digest in manifest['artifacts'].items():
            path = (output/rel).resolve()
            if not path.is_relative_to(output.resolve()) or not path.is_file() or sha256(path) != digest:
                problems.append('artifact differs: '+rel)
        if problems:
            raise ValueError('; '.join(problems))
        public = json.loads((output/'dataset.json').read_text(encoding='utf-8'))
        private = json.loads((output/'private.json').read_text(encoding='utf-8'))
        if public['channels'] != MAPPING or public['reference_policy'] != POLICY or public['knowledge'] != KNOWLEDGE:
            raise ValueError('unsupported channel or condition mapping')
        refs = []
        metadata_path = output/'sources/repository-metadata.json'
        metadata = json.loads(metadata_path.read_text(encoding='utf-8')) if metadata_path.exists() else None
        for case_id, case in public['cases'].items():
            source = (output/private[case_id]['source']).resolve()
            if not source.is_relative_to((output/'sources').resolve()):
                raise ValueError('source path escapes package')
            original = native_arrays(source); mapped = read_data(output, case)
            receipt_path = source.with_name(source.name+'.provenance.json')
            if receipt_path.exists():
                receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
                checksum = 'md5:'+hashlib.md5(source.read_bytes()).hexdigest()
                if receipt['sha256'] != sha256(source) or receipt['repository_checksum'] != checksum:
                    raise ValueError('download provenance differs')
                if metadata is None or not any(f['key']==source.name and f['checksum']==checksum for f in metadata['files']):
                    raise ValueError('repository metadata checksum differs')
            if set(original) != set(mapped) or any(not np.array_equal(original[k], mapped[k]) for k in original):
                raise ValueError('projection differs: '+case_id)
            if (case['regimes'] != regimes(original) or case['sample_count'] != len(original['time_s']) or
                case['time_bounds_s'] != [float(original['time_s'][0]), float(original['time_s'][-1])] or
                case['independent_recording_id'] != case_id):
                raise ValueError('condition mapping differs: '+case_id)
            match = re.fullmatch(r'spd10-5000rpm_flt(\d+)z([uv]?)_(\d+)NM.mat', source.name)
            if (not match or case['load_setpoint_nm'] != int(match[3]) or
                private[case_id]['shorted_turns'] != int(match[1]) or
                private[case_id]['fault_phase'] != (match[2] or None) or private[case_id]['source_sha256'] != sha256(source)):
                raise ValueError('source condition differs')
            if int(match[1]) == 0: refs.append(case_id)
        if public['normal_reference_ids'] != refs:
            raise ValueError('normal reference provenance differs')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        problems.append(str(exc))
    return {'status': 'passed' if not problems else 'failed',
            'record_status': 'passed' if not problems else 'failed', 'experiment_status': None,
            'run_dir': str(output.resolve()), 'problems': problems,
            'scope': '原始MAT到映射通道、工况分段与健康参照来源复算；正式故障区分和物理标定待验。'}


def query_measured(output, case_id, name, args):
    output = Path(output)
    check = verify_measured(output)
    if check['record_status'] != 'passed':
        raise ValueError('measured package verification failed: '+str(check['problems']))
    public = json.loads((output/'dataset.json').read_text(encoding='utf-8'))
    if case_id not in public['cases']:
        raise ValueError('unknown measured case id')
    case = public['cases'][case_id]; data = read_data(output, case)
    tools = ObservationTools(data, UNITS, units=UNITS, knowledge=KNOWLEDGE,
                             event_channels=('reference_speed_rpm',),
                             event_thresholds={'reference_speed_rpm': POLICY['reference_change_threshold_rpm']})
    if not isinstance(args, dict):
        return {'status': 'invalid_query', 'reason': 'arguments must be an object'}
    if not isinstance(name, str):
        return {'status': 'invalid_query', 'reason': 'tool name must be a string'}
    if name in CATALOG:
        # Measured motor coordinates must not be subtracted merely because both are A.
        if name == 'difference':
            a, b = args.get('left', ''), args.get('right', '')
            if isinstance(a, str) and isinstance(b, str) and a in UNITS and b in UNITS and (a.startswith(('i1_', 'i2_')) or b.startswith(('i1_', 'i2_'))):
                if a[-1:] != b[-1:]:
                    return {'status': 'invalid_query', 'reason': 'different current axes or phases; compare statistics instead'}
        return tools.execute(name, args)
    try:
        if name != 'normal_reference' or set(args) != {'channels', 'window_s'}:
            raise ValueError('unknown measured tool or arguments')
        current = tools.execute('statistics', args)
        if current['status'] != 'ok': return current
        target = condition(data, args['window_s'])
        duration = args['window_s'][1] - args['window_s'][0]
        if not np.isclose(duration, POLICY['window_s'], rtol=0, atol=1e-8):
            raise ValueError('normal_reference requires a 0.5s window')
        candidates = []
        for ref_id in public['normal_reference_ids']:
            ref = public['cases'][ref_id]
            if ref_id == case_id or ref['load_setpoint_nm'] != case['load_setpoint_nm']: continue
            for regime in ref['regimes']:
                speed_delta = abs(regime['reference_mean_rpm'] - target['reference_mean_rpm'])
                slope_delta = abs(regime['reference_slope_rpm_s'] - target['reference_slope_rpm_s'])
                speed_tol = max(POLICY['speed_abs_tolerance_rpm'], abs(target['reference_mean_rpm'])*POLICY['speed_relative_tolerance'])
                slope_tol = max(POLICY['slope_abs_tolerance_rpm_s'], abs(target['reference_slope_rpm_s'])*POLICY['slope_relative_tolerance'])
                age_a, age_b = regime['time_since_previous_change_s'], target['time_since_previous_change_s']
                age_matches = age_a is None and age_b is None or age_a is not None and age_b is not None and abs(age_a-age_b) <= POLICY['stage_age_tolerance_s']
                step_tol = max(POLICY['step_sum_abs_tolerance_rpm'], abs(target['reference_step_sum_rpm'])*POLICY['step_sum_relative_tolerance'])
                if (regime['phase'] == target['phase'] and regime['stage'] == target['stage'] and
                    regime['reference_change_count'] == target['reference_change_count'] and age_matches and
                    abs(regime['reference_step_sum_rpm']-target['reference_step_sum_rpm']) <= step_tol and
                    speed_delta <= speed_tol and slope_delta <= slope_tol):
                    candidates.append((speed_delta/speed_tol+slope_delta/slope_tol, ref_id, regime))
        if not candidates:
            return {'status': 'unavailable', 'reason': 'no healthy window from another recording satisfies load, phase, speed and slope policy', 'target_condition': target}
        _, ref_id, best = min(candidates, key=lambda x: (x[0], x[1], x[2]['window_s']))
        ref_data = read_data(output, public['cases'][ref_id])
        reference = ObservationTools(ref_data, UNITS, units=UNITS).execute('statistics', {**args, 'window_s': best['window_s']})
        differences = {k: {field: current['statistics'][k][field] - reference['statistics'][k][field]
                          for field in ('mean', 'rms', 'peak_to_peak')} for k in args['channels']}
        return {'status': 'ok', 'target_condition': target, 'reference_condition': best,
                'load_setpoint_nm': case['load_setpoint_nm'], 'reference_recording_id': ref_id,
                'distinct_reference_recordings': 1, 'eligible_windows': len(candidates),
                'current': current, 'normal_reference': reference, 'statistic_differences': differences,
                'meaning': '不同记录的工况匹配统计参照；记录之间的统计独立性未确认，无时间对齐、因果差值或验收阈值。'}
    except (KeyError, ValueError, TypeError) as exc:
        return {'status': 'invalid_query', 'reason': str(exc)}
