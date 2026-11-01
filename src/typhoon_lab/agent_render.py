"""Shared Agent report shell with case-specific real-data charts."""
import base64
import html
import re
from pathlib import Path
from .boost_agent_render import STYLE, markdown
from .boost_ai import read
from .agent_cases import BOOST, WAVEFORMS, BRIDGE, case_spec, series
from .utils import write_json, sha256, now


def table(headings, rows):
    return '<div class="table-wrap"><table><thead><tr>' + ''.join('<th>' + html.escape(str(x)) + '</th>' for x in headings) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join('<td>' + html.escape(str(x)) + '</td>' for x in row) + '</tr>' for row in rows) + '</tbody></table></div>'


def metrics_table(case_id, evidence, selected):
    rows = []
    for rid in selected:
        e = evidence[rid]
        if case_id == WAVEFORMS:
            m = e['metrics']
            rows.append([rid, e['classification'], e['sample_count'], f"{m['dt_s'] * 1e9:.6g}",
                         f"{m['max_deviation']:.6g}",
                         '; '.join(f"{x['first_sample_s']*1e6:.6g}至{x['last_sample_s']*1e6:.6g} μs / 支撑{x['sample_support_duration_s']*1e6:.6g} μs" for x in e['events']) or '未检出'])
        else:
            m = e['metrics']
            rows.append([rid, e['classification'], f"{m['Vdc_V']['mean']:.6g}", f"{m['Vdc_V']['peak_to_peak']:.6g}",
                         ', '.join(e['missing_conduction_directions']) or '未检出', e['record_status'] + ' / ' + e['experiment_status']])
    headings = ['记录', '规则分类', '原始点数', 'CSV间隔 / ns', '最大偏离 / V', '越限区间 / 样本支撑时长'] if case_id == WAVEFORMS else ['记录', '形态', '直流均值 / V', '峰峰值 / V', '缺失导通方向', '记录 / 数值参考']
    return table(headings, rows)


def comparison_table(value):
    body = []
    for pair in value['pairs']:
        left, right = pair['run_ids']
        rows = []
        for metric in pair['metrics'].values():
            unit = metric['unit']
            delta_unit = '百分点' if unit == '%' else unit
            rows.append([metric['label'], f"{metric['left']:.6g} {unit}", f"{metric['right']:.6g} {unit}",
                         f"{metric['delta']:+.6g} {delta_unit}",
                         '不定义（分母为0）' if metric['ratio'] is None else f"{metric['ratio']:.6g}"])
        body.append('<h3>' + html.escape(left + ' / ' + right + ' · ' + pair['family']) + '</h3>')
        body.append(table(['指标', left, right, right + ' − ' + left, right + ' / ' + left], rows))
        body.append('<p class="muted">' + html.escape(pair['limits']) + '</p>')
    body.append('<p class="muted">' + html.escape(value['method']) + '</p>')
    if value['unpaired_run_ids']:
        body.append('<p class="muted">未找到同类配对的记录：' + html.escape(', '.join(value['unpaired_run_ids'])) + '；本轮保留其单条证据，不计算配对差值。</p>')
    return ''.join(body)


def prepare_assets(turn_dir, controls, case_id, evidence, runs, root):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    assets = {}
    colors = ['#0072B2', '#D55E00', '#009E73', '#CC79A7']
    for index, view in enumerate(controls['views']):
        if view['type'] in ('metrics', 'analysis', 'comparison'):
            continue
        names = []
        if view['type'] == 'source_image':
            for rid in view['run_ids']:
                source = series(case_id, runs[rid], root)['image']
                name = f"source-{index:02d}-{rid}.png"
                (Path(turn_dir) / name).write_bytes(source.read_bytes())
                names.append(name)
        else:
            fig, ax = plt.subplots(figsize=(9, 4.8), layout='constrained')
            for number, rid in enumerate(view['run_ids']):
                data = series(case_id, runs[rid], root)
                t = np.asarray(data['time'])
                if view['view'] == 'phase_currents':
                    mask = (t >= .1) & (t < .14)
                    for phase, (signal, values) in enumerate(data['currents'].items()):
                        ax.plot(t[mask], np.asarray(values)[mask], label=rid + ' ' + signal,
                                color=colors[phase], linestyle=['-', '--', '-.', ':'][number % 4], linewidth=1)
                else:
                    mask = np.ones(len(t), dtype=bool)
                    if view['view'] == 'detail':
                        mask = (t >= data['detail'][0]) & (t <= data['detail'][1])
                    ax.plot(t[mask] * (1e6 if case_id == WAVEFORMS else 1), np.asarray(data['voltage'])[mask],
                            label=rid, color=colors[number % 4], linestyle=['-', '--', '-.', ':'][number % 4], linewidth=1.2)
                    if case_id == WAVEFORMS and view['view'] == 'detail':
                        for event in evidence[rid]['events']:
                            ax.axvspan(event['first_sample_s'] * 1e6, event['last_sample_s'] * 1e6,
                                       color=colors[number % 4], alpha=.12)
            ax.set_xlabel('Original time (μs)' if case_id == WAVEFORMS else 'Capture-relative time (s)')
            ax.set_ylabel('Phase current (A)' if view['view'] == 'phase_currents' else 'Voltage (V)')
            ax.grid(alpha=.2)
            ax.legend()
            name = f'waveform-{index:02d}.png'
            fig.savefig(Path(turn_dir) / name, dpi=150)
            plt.close(fig)
            names.append(name)
        assets[str(index)] = names
    return assets


def validation_panel(case_id, root, runs):
    root = Path(root)
    if case_id == WAVEFORMS:
        path = root / next(iter(runs.values()))['path']
        diagnosis = read(path / 'diagnosis.json')
        rules = read(path / 'rules.json')
        body = table(['文件', '规则结果', '参考标签', '相符'], [[x['id'], x['predicted'], x['expected'], x['matches']] for x in diagnosis['reference_comparison']])
        body += '<p>' + html.escape(rules['label_context']['expected_labels_source']) + '</p><p>' + html.escape(rules['label_context']['acquisition_statement']) + '</p><p>逐文件截图参数、CSV网格和点数保留在源数据包；来源说明、数据质量及设备性能分别表达。四条样本用于规则演示，独立准确率未评价。</p>'
    else:
        rows = []
        for rid, entry in runs.items():
            path = root / entry['path']
            config = read(path / 'config.json')
            metrics = read(path / 'metrics.json')
            rows.append([rid, config['fault'], ', '.join(metrics['missing_conduction_directions']) or '未检出',
                         max(x['normalized_rmse'] for x in metrics['signals'].values()), metrics['status']])
        body = table(['记录', '实际注入配置', '电流检出方向', '最大归一化误差', '2%数值参考判定'], rows)
        body += '<p>上表注入配置在分析后核对，未送入本轮模型证据。六个独立二极管、纯电阻负载；仿真采用LC二极管数值模型。波形支持导通通路异常，具体器件与接线需要额外证据区分。</p>'
    return '<details class="evidence-details"><summary>分析后核对来源、参考标签与验证范围</summary>' + body + '</details>'


def render_answer(root, turn_dir, answer, evidence, assets, runs, url):
    case_id = answer['case_id']
    body = [] if any(x['type'] == 'analysis' for x in answer['controls']['views']) else [markdown(answer['narrative'])]
    for index, view in enumerate(answer['controls']['views']):
        if view['type'] == 'analysis':
            body.append(markdown(answer['narrative']))
            continue
        body.append('<h2>' + html.escape(view['title']) + '</h2>')
        if view['type'] == 'metrics':
            body.append(metrics_table(case_id, evidence, view['run_ids']))
        elif view['type'] == 'comparison':
            body.append(comparison_table(read(Path(turn_dir) / 'comparison.json')))
        else:
            for name in assets[str(index)]:
                body.append('<figure><img loading="lazy" alt="' + html.escape(view['title'], quote=True) + '" src="' + html.escape(url(name), quote=True) + '"><figcaption>' + html.escape(', '.join(view['run_ids']) + ' · ' + view['view']) + ' · 原始数据未平滑或重采样</figcaption></figure>')
    rows = [[x['run_id'], x['classification'], '; '.join(f"{f['ref']} = {f['value']}" for f in x['facts'])] for x in answer['controls']['diagnoses']]
    if answer['controls'].get('comparison_facts'):
        rows.append(['配对差异', '已复算', '; '.join(f"{f['ref']} = {f['value']}" for f in answer['controls']['comparison_facts'])])
    body.append('<details class="evidence-details"><summary>查看程序已校验的分类与数值引用</summary>' + table(['记录', '分类', '数值证据'], rows) + '</details>')
    body.append(validation_panel(case_id, root, runs))
    return ''.join(body)


def message_html(root, message):
    answer = message['answer']
    if 'controls' not in answer:
        from .boost_agent_render import message_html as boost_html
        return boost_html(root, message)
    path = Path(root) / 'turns' / message['turn_id']
    manifest = read(path / 'manifest.json')
    return render_answer(root, path, answer, read(path / 'evidence.json'), read(path / 'render_assets.json'), manifest['run_refs'],
                         lambda name: '/files/' + (path / name).relative_to(root).as_posix())


def export_session(root, state):
    root = Path(root)
    spec = case_spec(state.get('case_id') or BOOST)
    body = ['<h1>Typhoon Agent · ' + html.escape(spec['title']) + '</h1><p>' + html.escape(spec['description']) + '</p><p>' + html.escape(spec['conditions']) + '</p><p class="muted">' + html.escape(spec['scope']) + '</p>']
    for message in state['messages']:
        role = message['role']
        if role == 'assistant':
            rendered = message_html(root, message)
            def embed(match):
                source = (root / match.group(1)).resolve()
                if not source.is_relative_to(root.resolve()):
                    raise ValueError('export image leaves session')
                return 'src="data:image/png;base64,' + base64.b64encode(source.read_bytes()).decode('ascii') + '"'
            rendered = re.sub(r'src="/files/([^"]+)"', embed, rendered)
            body.append('<article><p class="speaker">Agent</p>' + rendered + '</article>')
            question = message['answer'].get('question')
            if question:
                body.append('<section class="question"><h3>' + html.escape(question['title']) + '</h3>')
                for option in question['options']:
                    body.append('<p><strong>' + html.escape(option['label']) + '</strong> · ' + html.escape(option['description']) + '</p>')
                body.append('</section>')
        elif role == 'draft':
            body.append('<article><p>正文已保存，控制参数未通过；当前无可执行选项。</p>' + markdown(message['text']) + '</article>')
        else:
            body.append('<article class="' + ('user-message' if role == 'user' else 'tool-line') + '">' + html.escape(message.get('text', '')) + '</article>')
    body.append('<h2>原始数据与记录</h2><ul>')
    for rid, entry in state['runs'].items():
        base = html.escape(entry['path'], quote=True)
        body.append('<li>' + html.escape(rid) + ' · <a href="' + base + '/report.html">原记录报告</a> · <a href="' + base + '/manifest.json">清单</a></li>')
    body.append('</ul>')
    output = root / 'report.html'
    output.write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Typhoon Agent 分析报告</title><style>' + STYLE + '</style><main>' + ''.join(body) + '</main></html>', encoding='utf-8')
    write_json(root / 'export_manifest.json', {'created_at': now(), 'case_id': state.get('case_id'), 'report_sha256': sha256(output), 'inline_images': True, 'runs': list(state['runs']), 'model_turns': len(state['turns'])})
