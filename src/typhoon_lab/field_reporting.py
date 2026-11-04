"""Offline, source-labelled field reports. Plotting never fills missing samples."""
from collections import defaultdict
import html
import json
from pathlib import Path

from .field_intake import SPEED_ROLES, aligned_time, confirmed
from .utils import write_json


def figure_specs(intake, streams):
    specs, groups = [], defaultdict(list)
    for source in intake['sources']:
        sid = source['id']
        stream = streams[sid]
        if stream['signals'] and any(t is not None for t in stream['time_raw']):
            specs.append({'file': f'plots/source-{sid}.png', 'sources': [sid], 'axis': 'source', 'window_s': None})
            if source.get('detail_window_s') and confirmed(source['time']['unit']):
                specs.append({'file': f'plots/detail-{sid}.png', 'sources': [sid], 'axis': 'source', 'window_s': source['detail_window_s']})
        if source.get('alignment') and any(t is not None for t in stream['aligned_time_s']) and any(s['unit'] is not None for s in stream['signals'].values()):
            groups[source['alignment']['group']].append(sid)
    for group, members in sorted(groups.items()):
        if len(members) > 1:
            specs.append({'file': f'plots/aligned-{group}.png', 'sources': members, 'axis': 'aligned', 'group': group, 'window_s': None})
    return specs


def _family(signal):
    role = signal['role']
    return 'speed' if role in SPEED_ROLES else role


def _plot(out, spec, intake, streams):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    from .field_analysis import event_in_source
    sources = {s['id']: s for s in intake['sources']}
    panels = defaultdict(list)
    plotted_times = []
    for sid in spec['sources']:
        stream = streams[sid]
        axis_times = stream['aligned_time_s'] if spec['axis'] == 'aligned' else (stream['time_s'] if confirmed(sources[sid]['time']['unit']) else stream['time_raw'])
        plotted_times.extend(t for t in axis_times if t is not None)
        for name, signal in stream['signals'].items():
            if spec['axis'] == 'aligned' and signal['unit'] is None:
                continue
            family = f'gate: {sid}.{name}' if signal['role'] == 'gate' else _family(signal)
            panels[(family, signal['unit'] or 'raw (unit unconfirmed)')].append((sid, name, signal))
    colors = ['#0072B2', '#D55E00', '#009E73', '#7A4F9A', '#333333', '#A34B00']
    styles = ['-', '--', '-.', ':']
    limits = spec['window_s'] or ([min(plotted_times), max(plotted_times)] if plotted_times else None)
    with plt.rc_context({'font.size': 10, 'axes.grid': True, 'grid.alpha': .18, 'path.simplify': False}):
        fig, axes = plt.subplots(max(1, len(panels)), 1, figsize=(12, max(3.5, 2.8 * len(panels))),
                                 squeeze=False, layout='constrained')
        fig.get_layout_engine().set(w_pad=.16, h_pad=.08)
        for ax, ((family, unit), lines) in zip(axes.flat, panels.items()):
            for index, (sid, name, signal) in enumerate(lines):
                stream, source = streams[sid], sources[sid]
                times = stream['aligned_time_s'] if spec['axis'] == 'aligned' else (stream['time_s'] if confirmed(source['time']['unit']) else stream['time_raw'])
                values = signal['values'] if signal['unit'] else signal['values_raw']
                gap = source['time'].get('max_gap_s')
                px, py = [], []
                previous = None
                for t, y, native in zip(times, values, stream['time_s']):
                    if gap and native is not None and previous is not None and native - previous > gap + 1e-12:
                        px.append(float('nan')); py.append(float('nan'))
                    px.append(float('nan') if t is None else t)
                    py.append(float('nan') if y is None else y)
                    previous = native
                ax.plot(px, py, color=colors[index % len(colors)], linestyle=styles[index % len(styles)],
                        linewidth=.85, marker='.' if source['format'] != 'waveform_csv' else None,
                        markersize=4, label=f'{sid}.{name}')
            for event in intake.get('events', []):
                if not event['confirmed'] or event['time_s'] is None:
                    continue
                event_source = sources[event['source_id']]
                t = None
                if spec['axis'] == 'source' and confirmed(sources[spec['sources'][0]]['time']['unit']):
                    t, _, _ = event_in_source(event, sources[spec['sources'][0]], sources)
                elif spec['axis'] == 'aligned' and event_source.get('alignment', {}) and event_source['alignment']['group'] == spec['group']:
                    t = aligned_time(event_source, event['time_s'])
                if t is not None and (not limits or limits[0] <= t <= limits[1]):
                    ax.axvline(t, color='#777777', linestyle=':', linewidth=.8)
                    ax.text(t, .98, event['id'], rotation=90, va='top', ha='right', fontsize=8, clip_on=True, transform=ax.get_xaxis_transform())
            for item in intake.get('criteria', []):
                if not item.get('signal') or not item.get('window_s'):
                    continue
                sid, name = item['signal'].split('.')
                if spec['axis'] == 'source' and not confirmed(sources[sid]['time']['unit']):
                    continue
                if not any(s == sid and n == name for s, n, _ in lines):
                    continue
                a, b = item['window_s']
                if spec['axis'] == 'aligned':
                    a, b = aligned_time(sources[sid], a), aligned_time(sources[sid], b)
                if a is not None and b is not None:
                    ax.axvspan(a, b, color='#0072B2', alpha=.055)
            ax.set(ylabel=f'{family} ({unit})')
            ax.legend(loc='upper right', fontsize=8, ncol=2 if len(lines) > 3 else 1)
            if limits and limits[0] < limits[1]:
                ax.set_xlim(*limits)
        if not panels:
            axes[0, 0].text(.5, .5, 'No plottable samples', ha='center')
        xlabel = f"Declared common time (s), group={spec.get('group')}" if spec['axis'] == 'aligned' else (
            f"Source time (s), clock={streams[spec['sources'][0]]['clock_domain']}" if confirmed(sources[spec['sources'][0]]['time']['unit']) else 'Source time (raw, unit unconfirmed)')
        axes[-1, 0].set_xlabel(xlabel)
        fig.suptitle(('Detail window' if spec['window_s'] else 'Full export') + ' | ' + ', '.join(spec['sources']))
        target = out / spec['file']
        target.parent.mkdir(exist_ok=True)
        fig.savefig(target, dpi=140, facecolor='white')
        plt.close(fig)


def _display(value):
    if value is None:
        return '—'
    if isinstance(value, float):
        return f'{value:.7g}'
    return str(value)


def write_field_report(out, intake, metrics, streams):
    out = Path(out)
    specs = figure_specs(intake, streams)
    for spec in specs:
        _plot(out, spec, intake, streams)
    write_json(out / 'plot-index.json', specs)
    title = '样机现场数据分析：' + intake['dataset_id']
    md = ['# ' + title, '', intake['purpose'], '']
    body = ['<h1>' + html.escape(title) + '</h1>', '<p>' + html.escape(intake['purpose']) + '</p>']

    def paragraph(text):
        md.extend([text, ''])
        body.append('<p>' + html.escape(text) + '</p>')

    def heading(text):
        md.extend(['## ' + text, ''])
        body.append('<h2>' + html.escape(text) + '</h2>')

    def table(headers, rows):
        rows = [[_display(c) for c in r] for r in rows]
        md.extend(['| ' + ' | '.join(headers) + ' |', '|' + '|'.join('---' for _ in headers) + '|'])
        md.extend('| ' + ' | '.join(c.replace('|', '\\|').replace('\n', ' ') for c in row) + ' |' for row in rows)
        md.append('')
        body.append('<div class="table"><table><thead><tr>' + ''.join('<th>' + html.escape(h) + '</th>' for h in headers) + '</tr></thead><tbody>' +
                    ''.join('<tr>' + ''.join('<td>' + html.escape(c) + '</td>' for c in row) + '</tr>' for row in rows) + '</tbody></table></div>')

    heading('结果与评价范围')
    table(['数据质量', '分析完成度', '配置判据', '样机性能'], [[metrics[k] for k in ('data_quality_status', 'analysis_status', 'criteria_status', 'performance_status')]])
    paragraph('本报告对所提供文件及已配置项目作离线评价。来源性质来自清单声明，文件哈希不认证设备来源。合成、Mock 与 Virtual HIL 数据不能证明真实板卡通过。记录一致性须另行运行 verify-field-data。')
    heading('来源与时间轴')
    def alignment_text(s):
        a = s.get('alignment')
        return f"{a['group']}: ×{a['scale']}, offset={a['offset_s']}s, ±{a['uncertainty_s']}s" if a else 'not_established'
    table(['来源', '数据性质', '设备', '质量', '记录数', '时钟域', '时间关联'], [
        [s['id'], s['source_kind'], json.dumps(s['device'], ensure_ascii=False), streams[s['id']]['data_quality_status'],
         streams[s['id']]['timing']['samples'], s['time']['clock_domain'],
         alignment_text(s)] for s in intake['sources']])
    paragraph('时间变换为 t_common = scale × t_source_seconds + offset_s，仅用于声明的有效范围。未建立关联的来源使用各自时间轴；报告未自动平移、插值或同步。阴影表示配置的评价窗口，竖线表示已确认的阶段事件。')
    heading('信号摘要')
    table(['信号', '含义', '单位', '有效样本', '缺失样本', '最小值', '最大值', '均值'], [
        [sid + '.' + name, s['role'], s['unit'], s['valid_samples'], s['missing_samples'], s['minimum'], s['maximum'], s['mean']]
        for sid, signals in metrics['summaries'].items() for name, s in signals.items()])
    present = {s['role'] for stream in streams.values() for s in stream['signals'].values()}
    missing = sorted(SPEED_ROLES - present)
    paragraph('未提供的转速来源：' + (', '.join(missing) if missing else '无') + '。各列分别保留，不使用其他来源补齐。反馈电压与电流按各自单位展示。')
    heading('判据、指标与未评估原因')
    table(['项目', '类型', '结果', '指标', '未评估原因'], [[c['id'], c['type'], c['status'],
          json.dumps(c['metrics'], ensure_ascii=False), c['reason']] for c in metrics['checks']])
    paragraph('转速与电流按有效原始样本计算。停止判定检查明确事件后的阈值、截止时间和保持时长；结果受采样间隔及声明的同步误差限制，不将“释放适配器”或“零速码”自动视为停止事件。')
    definition = json.dumps({'criteria': intake.get('criteria', []), 'events': intake.get('events', [])}, ensure_ascii=False, indent=2)
    md += ['~~~json', definition, '~~~', '']
    body.append('<details><summary>查看判据与事件定义</summary><pre>' + html.escape(definition) + '</pre></details>')
    heading('数据问题与 LIN 记录')
    for sid, stream in streams.items():
        frames = stream['frames']
        paragraph(f"{sid}：问题 {len(stream['issues'])} 项；LIN 帧 {len(frames)} 条，其中本机发送记录 {sum(f['direction']=='tx' for f in frames)} 条。发送记录不证明板卡收到。")
        if frames:
            table(['帧状态', '条数'], [[state, sum(f['status'] == state for f in frames)] for state in ('passed', 'failed', 'unverified', 'unsupported')])
        if stream['issues']:
            # Full issues and raw frames are retained in normalized.json; keep reports readable.
            table(['问题（前 20 项，完整列表见规范化数据）'], [[json.dumps(x, ensure_ascii=False)] for x in stream['issues'][:20]])
    heading('完整波形与局部窗口')
    for spec in specs:
        caption = ('已声明关联的时间轴' if spec['axis'] == 'aligned' else '独立来源时间轴') + '：' + ', '.join(spec['sources'])
        caption += '；局部窗口 ' + str(spec['window_s']) + ' s' if spec['window_s'] else '；完整导出范围'
        md += ['![' + caption + '](' + spec['file'] + ')', '', caption, '']
        body.append('<figure><img src="' + spec['file'] + '" alt="' + html.escape(caption, quote=True) + '"><figcaption>' + html.escape(caption) + '</figcaption></figure>')
    heading('复核材料')
    for file, label in [('intake.json', '输入与换算清单'), ('provenance.json', '原始来源与摘要'),
                        ('normalized.json', '规范化数据、原始值和问题'), ('metrics.json', '完整指标与判定'), ('manifest.json', '产物及代码摘要')]:
        md.append(f'- [{label}]({file})')
        body.append('<p><a href="' + file + '">' + label + '</a></p>')
    for source in intake['sources']:
        if (out / source['file']).is_file():
            md.append(f"- [{source['id']} 原始文件]({source['file']})")
            body.append('<p><a href="' + html.escape(source['file'], quote=True) + '">' + source['id'] + ' 原始文件</a></p>')
    paragraph('数据未平滑、未插值，缺失值及声明的采样缺口保留为图中断点；图像不替代包内完整数据。具体模型精度、实时反馈及整机验收仍需相应现场证据。')
    css = 'body{font:16px/1.65 "Segoe UI","Microsoft YaHei",sans-serif;color:#202b38;background:#f6f8fb;margin:0}main{max-width:1240px;margin:24px auto;background:white;padding:30px 38px;border:1px solid #dce2eb;border-radius:10px}h1{font-size:26px}h2{font-size:21px;margin-top:32px}table{border-collapse:collapse;width:100%;font-size:14px}th,td{border:1px solid #dce2eb;text-align:left;padding:8px;vertical-align:top;overflow-wrap:anywhere}th{background:#edf2f8}.table{overflow:auto}img{width:100%;height:auto}figure{margin:24px 0}figcaption{color:#475569}pre{white-space:pre-wrap;font-size:13px;background:#f2f5f9;padding:14px}a{color:#006099}@media(max-width:720px){main{margin:0;padding:18px}h1{font-size:22px}}'
    (out / 'report.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
    (out / 'report.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><title>' + html.escape(title) + '</title><style>' + css + '</style><main>' + '\n'.join(body) + '</main></html>', encoding='utf-8')
