"""Offline reports of raw teaching captures. Never executes Typhoon."""
from __future__ import annotations
import base64
import csv
import html
import json
from pathlib import Path
from .analysis import SIGNALS, load_waveforms

STATUS = {'passed': '通过', 'failed': '未通过', 'error': '执行异常', 'skipped': '跳过'}
COLORS = ('#0072B2', '#D55E00', '#009E73', '#CC79A7', '#333333')
STYLES = ('-', '--', '-.', ':')
SCOPE = '本报告用于 RLC 教学仿真。Virtual HIL 在电脑上以非实时方式运行，无外部 I/O；结果来自实际软件仿真采样。本次工作尚未验证物理 HIL 硬件、真实控制器闭环或真实电机性能。'
METHOD = '按全部捕获样本计算 RMS = sqrt(Σx²/N)，相对误差 = |采样 RMS − 解析 RMS| / 解析 RMS。解析参照稳态正弦相量：Rin 串联 [L 并联 (R 串联 C)]，Zp=(jωL)·(R+1/jωC)/(jωL+R+1/jωC)，I RMS=|Vrms/(Rin+Zp)|，Va1 RMS=|Vrms·Zp/(Rin+Zp)|。等待时间是配置值，达到等待时间不独立证明瞬态已消失。'
CSS = 'body{font-family:"Microsoft YaHei",Arial,sans-serif;color:#172536;background:#f3f6fa;margin:0;line-height:1.65}main{max-width:1060px;margin:24px auto;padding:28px;background:#fff;border:1px solid #d8e0e9;border-radius:12px}h1{font-size:26px}h2{font-size:20px;margin-top:26px}.scope{background:#eaf2fc;padding:14px;border-left:4px solid #286495}.status{font-size:19px;font-weight:bold}table{border-collapse:collapse;width:100%;font-size:14px}th,td{border-bottom:1px solid #d7dfe8;padding:8px;text-align:left}th{background:#eff4f9}img{width:100%;height:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f7f9;padding:12px}a{color:#14558a}figure{margin:14px 0}figcaption,footer{color:#44546a;font-size:14px}.table-scroll{overflow-x:auto}@media(max-width:700px){main{margin:0;padding:16px}}'


def _json(path):
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError(f'{path.name} must contain a JSON object')
    return value


def _fmt(value, percent=False):
    if value is None:
        return '—'
    if isinstance(value, (int, float)):
        return f'{value * 100:.4g}%' if percent else f'{value:.7g}'
    return str(value)


def _status(value):
    return f'{STATUS.get(value, value or "未完成")} ({value or "unknown"})'


def _table(headers, rows):
    head = ''.join(f'<th scope="col">{html.escape(str(value))}</th>' for value in headers)
    body = ''.join('<tr>' + ''.join(f'<td>{html.escape(str(value))}</td>' for value in row) + '</tr>' for row in rows)
    return f'<div class="table-scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _md_table(headers, rows):
    clean = lambda value: str(value).replace('|', '\\|').replace('\n', ' ')
    lines = ['| ' + ' | '.join(map(clean, headers)) + ' |', '| ' + ' | '.join('---' for _ in headers) + ' |']
    lines.extend('| ' + ' | '.join(map(clean, row)) + ' |' for row in rows)
    return '\n'.join(lines)


def _plot(destination, series, title):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    with plt.rc_context({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.grid': True, 'grid.alpha': .2, 'path.simplify': False, 'figure.facecolor': 'white', 'axes.facecolor': 'white'}):
        figure, axes = plt.subplots(2, 1, sharex=True, figsize=(10, 6.4), layout='constrained')
        figure.suptitle(title, fontsize=13)
        for index, (label, data) in enumerate(series):
            for ax, (signal, unit) in zip(axes, SIGNALS):
                ax.plot([value * 1000 for value in data['t_relative_s']], data[signal], label=label, color=COLORS[index % len(COLORS)], linestyle=STYLES[index % len(STYLES)], linewidth=1.4)
                ax.set_ylabel(f'{signal.rsplit("_", 1)[0]} ({unit})')
        axes[-1].set_xlabel('Time from capture start (ms)')
        for ax in axes:
            ax.axhline(0, color='#555555', linewidth=.6, zorder=0)
            ax.legend(loc='upper right', fontsize=9)
        figure.savefig(destination, dpi=160, facecolor='white', transparent=False,
                       metadata={'Description': 'Raw captured samples; no filtering, smoothing, filling, or resampling. Virtual HIL teaching simulation.'})
        plt.close(figure)


def _image(path, caption):
    encoded = base64.b64encode(path.read_bytes()).decode('ascii')
    return f'<figure><img src="data:image/png;base64,{encoded}" alt="{html.escape(caption)}"><figcaption>{html.escape(caption)}</figcaption></figure>'


def _metadata(manifest):
    names = ('run_id', 'started_at', 'started_at_local', 'completed_at', 'finished_at', 'backend', 'software_version', 'typhoon_version', 'python_version', 'code_version', 'code_hash', 'model_sha256')
    rows = [(name, manifest[name]) for name in names if manifest.get(name) is not None]
    environment = manifest.get('environment', {})
    for name, label in (('thcc_version', 'THCC 版本'), ('python', 'Python 版本'), ('typhoon_hil_api', 'Typhoon HIL API 版本'), ('typhoontest', 'TyphoonTest 版本'), ('numpy', 'NumPy 版本'), ('matplotlib', 'Matplotlib 版本')):
        if environment.get(name) is not None:
            rows.append((label, environment[name]))
    origin = manifest.get('model_origin', {})
    for name, label in (('original_path', '官方模型来源'), ('sha256', '来源模型 SHA256')):
        if origin.get(name) is not None:
            rows.append((label, origin[name]))
    model_hash = manifest.get('artifacts', {}).get('model.tse')
    if model_hash:
        rows.append(('本次模型 SHA256', model_hash))
    if manifest.get('code_sha256'):
        rows.append(('本次代码 SHA256 清单', manifest['code_sha256']))
    return [(name, json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else str(value)) for name, value in rows] or [('运行元数据', '见 manifest.json')]


def _write(run_dir, title, status, html_parts, markdown_parts):
    esc = html.escape
    document = f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><style>{CSS}</style></head><body><main><h1>{esc(title)}</h1><p class="status">实验状态：{esc(_status(status))}</p><p class="scope">{esc(SCOPE)}</p>'
    document += ''.join(html_parts) + '<footer>图表保存全部原始采样点，连续线只连接相邻采样点。未做平滑、滤波、插值或缺失值补齐。HTML 的图像与样式已内嵌，无网络依赖。原始数据链接指向同目录文件。仿真时刻为模型内时间，未补造缺失的 UTC 时戳。</footer></main></body></html>'
    markdown = f'# {title}\n\n实验状态：**{_status(status)}**\n\n{SCOPE}\n\n' + '\n\n'.join(markdown_parts)
    markdown += '\n\n图表保存全部原始采样点，未做平滑、滤波、插值或缺失值补齐。仿真时刻为模型内时间，未补造缺失的 UTC 时戳。\n'
    output = [run_dir / 'report.html', run_dir / 'report.md']
    output[0].write_text(document, encoding='utf-8')
    output[1].write_text(markdown, encoding='utf-8')
    return output


def write_report(run_dir: Path, manifest: dict) -> list[Path]:
    run_dir = Path(run_dir)
    metrics, config = _json(run_dir / 'metrics.json'), _json(run_dir / 'config.json')
    status = manifest.get('status') or metrics.get('status') or 'error'
    if status == 'passed' and (not config or metrics.get('status') != 'passed'):
        status = 'error'
    hp, mp, outputs = [], [], []
    error = manifest.get('error') or manifest.get('errors')
    if error:
        detail = json.dumps(error, ensure_ascii=False, indent=2) if isinstance(error, (dict, list)) else str(error)
        hp.append('<h2>执行记录</h2><pre>' + html.escape(detail) + '</pre>')
        mp.append('## 执行记录\n\n' + detail)
    rows = []
    for signal, unit in SIGNALS:
        value = metrics.get('signals', {}).get(signal, {})
        decision = '通过' if value.get('passed') is True else '未通过' if value.get('passed') is False else '未计算'
        rows.append((signal, unit, _fmt(value.get('rms')), _fmt(value.get('expected_rms')), _fmt(value.get('relative_rms_error'), True), decision))
    headers = ('信号', '单位', '采样 RMS', '解析 RMS', '相对误差', 'RMS 判定')
    hp.append('<h2>指标与判定</h2>' + _table(headers, rows))
    mp.append('## 指标与判定\n\n' + _md_table(headers, rows))
    capture = metrics.get('capture', {})
    cap_rows = [('样本数', _fmt(capture.get('sample_count'))), ('实际采样率 (Hz)', _fmt(capture.get('sample_rate_hz'))), ('采样窗口 N·Δt (s)', _fmt(capture.get('duration_s'))), ('源周期数', _fmt(capture.get('cycles'))), ('首个仿真时刻 (s)', _fmt(capture.get('first_simulation_time_s'))), ('最后仿真时刻 (s)', _fmt(capture.get('last_simulation_time_s')))]
    capture_record = _json(run_dir / 'capture.json') or manifest.get('capture', {})
    for name, label in (('simulation_step_s', '仿真步长 (s)'), ('decimation', '采样降采样因子'), ('trigger_timestamp_utc_time_ns', 'UTC 触发时间戳 (ns；— 表示未提供)')):
        if name in capture_record:
            cap_rows.append((label, _fmt(capture_record[name])))
    hp.append('<h2>采集窗口</h2>' + _table(('项', '值'), cap_rows))
    mp.append('## 采集窗口\n\n' + _md_table(('项', '值'), cap_rows))
    checks = [(check.get('name'), '通过' if check.get('passed') else '未通过', _fmt(check.get('observed')), _fmt(check.get('expected'))) for check in metrics.get('checks', [])]
    if checks:
        hp.append('<h2>检查明细</h2>' + _table(('检查', '结果', '实际值', '参照值'), checks))
        mp.append('## 检查明细\n\n' + _md_table(('检查', '结果', '实际值', '参照值'), checks))
    raw = run_dir / 'waveforms.csv'
    if raw.exists():
        try:
            data = load_waveforms(raw)
        except ValueError as exc:
            status = 'error'
            message = '原始波形未通过完整性检查，未绘图：' + str(exc)
            hp.append('<p>' + html.escape(message) + '</p>')
            mp.append(message)
        else:
            figure = run_dir / 'waveforms.png'
            _plot(figure, [('Captured samples', data)], 'RLC teaching simulation - raw captured waveforms')
            caption = '上下两图分别显示源电流 I (A) 与节点电压 Va1 (V)，共享采样窗口相对时间 (ms)。完整采样数据见 waveforms.csv。'
            hp.append('<h2>原始波形</h2>' + _image(figure, caption))
            mp.append('## 原始波形\n\n![电流与节点电压波形](waveforms.png)\n\n' + caption)
            outputs.append(figure)
    else:
        if status == 'passed':
            status = 'error'
        message = '本次运行没有可用的 waveforms.csv，未生成波形图或补造数据。'
        hp.append('<p>' + message + '</p>')
        mp.append(message)
    hp.append('<h2>分析方法</h2><p>' + html.escape(METHOD) + '</p>')
    mp.append('## 分析方法\n\n' + METHOD)
    warnings = metrics.get('analysis', {}).get('warnings', [])
    if warnings:
        text = '\n'.join(map(str, warnings))
        hp.append('<p>分析提示：</p><pre>' + html.escape(text) + '</pre>')
        mp.append('分析提示：\n\n' + text)
    config_text = json.dumps(config, ensure_ascii=False, sort_keys=True, indent=2)
    hp.append('<h2>实际实验配置</h2><pre>' + html.escape(config_text) + '</pre>')
    mp.append('## 实际实验配置\n\n```json\n' + config_text + '\n```')
    hp.append('<h2>运行来源</h2>' + _table(('字段', '记录'), _metadata(manifest)))
    mp.append('## 运行来源\n\n' + _md_table(('字段', '记录'), _metadata(manifest)))
    links = [name for name in ('waveforms.csv', 'metrics.json', 'config.json', 'capture.json', 'model.tse', 'manifest.json', 'run.log') if (run_dir / name).exists()]
    hp.append('<p>来源文件：' + ' · '.join(f'<a href="{name}">{name}</a>' for name in links) + '</p>')
    mp.append('来源文件：' + ' · '.join(f'[{name}]({name})' for name in links))
    outputs.extend(_write(run_dir, 'RLC 教学实验报告', status, hp, mp))
    return outputs


def write_sweep_report(run_dir: Path, manifest: dict) -> list[Path]:
    run_dir = Path(run_dir)
    rows, tr, series, conditions = [], [], [], []
    for case in manifest.get('cases', []):
        relative = str(case.get('relative_dir', ''))
        case_dir = (run_dir / relative).resolve()
        if not relative or not case_dir.is_relative_to(run_dir.resolve()) or case_dir == run_dir.resolve():
            raise ValueError('Sweep case directory must remain inside the run directory')
        config, metrics = _json(case_dir / 'config.json'), _json(case_dir / 'metrics.json')
        current = metrics.get('signals', {}).get('I_A', {})
        voltage = metrics.get('signals', {}).get('Va1_V', {})
        rin = config.get('circuit', {}).get('rin_ohm')
        status = case.get('status') or metrics.get('status') or 'error'
        if status == 'passed' and (not config or metrics.get('status') != 'passed'):
            status = 'error'
        source, circuit, capture = config.get('source', {}), config.get('circuit', {}), config.get('capture', {})
        conditions.append((case.get('case_id', case_dir.name), _fmt(source.get('rms_v')), _fmt(source.get('frequency_hz')), _fmt(source.get('phase_deg')), _fmt(rin), _fmt(circuit.get('branch_r_ohm')), _fmt(circuit.get('l_h')), _fmt(circuit.get('c_f')), _fmt(capture.get('settle_s')), _fmt(capture.get('duration_s')), _fmt(capture.get('sample_rate_hz'))))
        waveform = case_dir / 'waveforms.csv'
        if waveform.exists():
            try:
                data = load_waveforms(waveform)
            except ValueError:
                status = 'error'
            else:
                series.append((f'{case.get("case_id", case_dir.name)}: Rin={_fmt(rin)} ohm [{status}]', data))
        elif status == 'passed':
            status = 'error'
        row = {'case_id': case.get('case_id', case_dir.name), 'relative_dir': relative, 'rin_ohm': rin, 'status': status, 'sample_count': metrics.get('sample_count'), 'sample_rate_hz': metrics.get('sample_rate_hz'), 'I_rms_A': current.get('rms'), 'I_expected_rms_A': current.get('expected_rms'), 'I_relative_rms_error': current.get('relative_rms_error'), 'Va1_rms_V': voltage.get('rms'), 'Va1_expected_rms_V': voltage.get('expected_rms'), 'Va1_relative_rms_error': voltage.get('relative_rms_error')}
        rows.append(row)
        tr.append((row['case_id'], _fmt(rin), _status(status), _fmt(row['I_rms_A']), _fmt(row['I_expected_rms_A']), _fmt(row['I_relative_rms_error'], True), _fmt(row['Va1_rms_V']), _fmt(row['Va1_expected_rms_V']), _fmt(row['Va1_relative_rms_error'], True)))
    columns = ('case_id', 'relative_dir', 'rin_ohm', 'status', 'sample_count', 'sample_rate_hz', 'I_rms_A', 'I_expected_rms_A', 'I_relative_rms_error', 'Va1_rms_V', 'Va1_expected_rms_V', 'Va1_relative_rms_error')
    comparison = run_dir / 'comparison.csv'
    with comparison.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    headers = ('工况', 'Rin (Ω)', '状态', 'I RMS (A)', 'I解析 (A)', 'I误差', 'Va1 RMS (V)', 'Va1解析 (V)', 'Va1误差')
    status = manifest.get('status') or ('passed' if rows and all(row['status'] == 'passed' for row in rows) else 'error')
    if not rows and status == 'passed':
        status = 'error'
    if status == 'passed' and any(row['status'] != 'passed' for row in rows):
        status = 'failed' if all(row['status'] in ('passed', 'failed') for row in rows) else 'error'
    hp = ['<h2>工况比较</h2>' + _table(headers, tr)]
    mp = ['## 工况比较\n\n' + _md_table(headers, tr)]
    condition_headers = ('工况', '源 RMS (V)', '频率 (Hz)', '相位 (°)', 'Rin (Ω)', '支路 R (Ω)', 'L (H)', 'C (F)', '等待 (s)', '窗口 (s)', '请求采样率 (Hz)')
    hp.append('<h2>实际工况配置</h2>' + _table(condition_headers, conditions))
    mp.append('## 实际工况配置\n\n' + _md_table(condition_headers, conditions))
    outputs = [comparison]
    if series:
        figure = run_dir / 'comparison.png'
        _plot(figure, series, 'Rin sweep - raw captured waveforms')
        caption = '每条曲线来自相应工况独立采集的原始波形，颜色与线型同时区分工况。横轴为各自采样起点后的时间，采样起始源相位可能不同，叠图不用于验证工况间相位差。失败工况若有完整波形也保留展示。'
        hp.append('<h2>波形比较</h2>' + _image(figure, caption))
        mp.append('## 波形比较\n\n![各工况电流与节点电压](comparison.png)\n\n' + caption)
        outputs.append(figure)
    else:
        hp.append('<p>无完整可绘制波形。未补造曲线。</p>')
        mp.append('无完整可绘制波形。未补造曲线。')
    hp.append('<h2>方法与核对</h2><p>' + html.escape(METHOD) + '</p><p>源电压、频率及其余参数以各工况 config.json 为准。RMS 来自 metrics.json。缺失结果显示为 —，comparison.csv 中留空。</p>')
    mp.append('## 方法与核对\n\n' + METHOD + '\n\n源电压、频率及其余参数以各工况 config.json 为准。RMS 来自 metrics.json。缺失结果显示为 —，comparison.csv 中留空。')
    for row in rows:
        relative = row['relative_dir'].replace('\\', '/')
        hp.append(f'<p>{html.escape(str(row["case_id"]))}：' + ' · '.join(f'<a href="{html.escape(relative)}/{name}">{name}</a>' for name in ('report.html', 'config.json', 'metrics.json', 'capture.json', 'manifest.json', 'waveforms.csv')) + '</p>')
        mp.append(f'{row["case_id"]}：' + ' · '.join(f'[{name}]({relative}/{name})' for name in ('report.html', 'config.json', 'metrics.json', 'capture.json', 'manifest.json', 'waveforms.csv')))
    hp.append('<h2>运行来源</h2>' + _table(('字段', '记录'), _metadata(manifest)) + '<p><a href="comparison.csv">比较表 CSV</a> · <a href="manifest.json">manifest.json</a></p>')
    mp.append('## 运行来源\n\n' + _md_table(('字段', '记录'), _metadata(manifest)) + '\n\n[比较表 CSV](comparison.csv) · [manifest.json](manifest.json)')
    outputs.extend(_write(run_dir, 'RLC 参数扫描报告', status, hp, mp))
    return outputs
