"""Recomputable scalar comparisons for independently captured waveforms."""
from itertools import combinations
from pathlib import Path
from .boost_ai import read


def pair_groups(evidence):
    groups = {}
    for rid in sorted(evidence):
        groups.setdefault(evidence[rid]['family'], []).append(rid)
    pairs = [list(pair) for group in groups.values() for pair in combinations(group, 2)]
    # Explicit comparisons across families remain possible, with their limits stated.
    return pairs or ([sorted(evidence)] if len(evidence) == 2 else [])


def pair_id(run_ids):
    return '__'.join(sorted(run_ids))


def comparison(evidence):
    pairs = []
    for ids in pair_groups(evidence):
        left, right = (evidence[rid] for rid in ids)
        same_family = left['family'] == right['family']
        metrics = {}

        def add(name, label, unit, a, b):
            metrics[name] = {'label': label, 'unit': unit, 'left': a, 'right': b,
                             'delta': b - a, 'ratio': b / a if a != 0 else None}

        a, b = left['metrics'], right['metrics']
        add('max_deviation_V', '最大形态偏离', 'V', a['max_deviation'], b['max_deviation'])
        add('threshold_multiple', '偏离 / 各自规则阈值', '倍',
            a['max_deviation'] / a['deviation_threshold'], b['max_deviation'] / b['deviation_threshold'])
        add('event_count', '检出事件数', '个', len(left['events']), len(right['events']))
        add('event_support_us', '检出事件样本支撑总时长', 'μs',
            sum(x['sample_support_duration_s'] for x in left['events']) * 1e6,
            sum(x['sample_support_duration_s'] for x in right['events']) * 1e6)
        if same_family:
            add('deviation_percent', '偏离 / 各自参考幅度', '%',
                a['max_deviation_fraction'] * 100, b['max_deviation_fraction'] * 100)
            reference = 'baseline' if left['family'] == 'dip' else 'transition_amplitude'
            add('reference_V', '基线' if reference == 'baseline' else '跃迁幅度', 'V', a[reference], b[reference])
            if left['family'] == 'rise':
                add('first_crossing_us', '首次穿越间隔', 'μs',
                    a['first_crossing_interval_s'] * 1e6, b['first_crossing_interval_s'] * 1e6)
        pairs.append({'id': pair_id(ids), 'run_ids': ids, 'family': left['family'] if same_family else 'mixed',
                      'classifications': [left['classification'], right['classification']], 'metrics': metrics,
                      'limits': '各文件使用自己的原始时间轴和分析窗口；差值为右减左，倍率为右除左。分母为零时倍率不定义；未检出事件的时长0仅表示规则未检出。'
                                + ('偏离百分比分母为各自基线。' if same_family and left['family'] == 'dip' else
                                   '偏离百分比分母为各自跃迁幅度；首次穿越间隔不是完整响应时间。' if same_family else
                                   '两条记录使用不同形态规则，幅度和各自阈值的比较不能视为相同器件性能。')})
    if not pairs:
        raise ValueError('所选记录缺少可比较的波形对')
    used = {rid for pair in pairs for rid in pair['run_ids']}
    return {'schema_version': 1, 'pairs': pairs, 'unpaired_run_ids': sorted(set(evidence) - used),
            'method': '仅比较逐文件复算的标量指标；原始时间轴不平移、不插值，不对不同采集记录逐点相减。'}


def comparison_scopes(evidence, completed=()):
    pairs = [ids for ids in pair_groups(evidence) if pair_id(ids) not in completed]
    scopes = list(pairs)
    if len(pairs) > 1:
        scopes.append(sorted({rid for ids in pairs for rid in ids}))
    return scopes


def completed_pairs(root, turns, evidence):
    completed = set()
    for turn in turns:
        path = Path(root) / turn['path']
        if turn['status'] != 'passed' or not (path / 'comparison.json').exists():
            continue
        if read(path / 'manifest.json').get('output_contract') != 'case_report_v3':
            continue
        previous = read(path / 'evidence.json')
        for pair in read(path / 'comparison.json')['pairs']:
            if all(rid in evidence and previous[rid]['source_csv_sha256'] == evidence[rid]['source_csv_sha256'] for rid in pair['run_ids']):
                completed.add(pair['id'])
    return completed
