"""Frozen-rule selection and offline analysis for expanded PMSM event experiments."""
import argparse
from copy import deepcopy
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from analyze_pmsm_interaction import derive, independent_check
from typhoon_lab.analysis import load_waveforms
from typhoon_lab.pmsm_preview import PMSMPreviewAdapter
from typhoon_lab.records import verify_run
from typhoon_lab.config import validate_config


def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write(path,obj):
    Path(path).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def describe(config):
    es=config['events'];s=[e for e in es if e['target']=='reference_speed_rpm'];l=[e for e in es if e['target']=='load_torque_nm']
    speed=s[-1]['value'] if s else config['parameters']['reference_speed_rpm']
    load=l[-1]['value'] if l else config['parameters']['load_torque_nm']
    if s and l:
        gap=l[0]['at_s']-s[0]['at_s']
        order='simultaneous' if abs(gap)<1e-9 else ('speed_then_load' if gap>0 else 'load_then_speed')
    else: gap=None;order='speed_only' if s else ('load_only' if l else 'baseline')
    return {'speed_rpm':speed,'load_nm':load,'order':order,'signed_load_delay_ms':round(gap*1000,6) if gap is not None else None}


def recovery_verdict(row):
    if row['order']=='baseline':return 'not_applicable'
    if row['recovery_s'] is not None:return 'passed' if row['recovery_s']<=.1 else 'failed'
    # A late apparent return with <20 ms evidence cannot hide an earlier missed deadline.
    return 'failed' if row['observed_horizon_s']-.02>.1 else 'not_evaluable'


def severity(row):
    if row['recovery_s'] is None:
        return (0,-row['settled_max_error_rpm'],-row['iae_rpm_s'],row['condition'])
    return (1,row['recovery_margin_ms'],-row['iae_rpm_s'],row['condition'])


def collect(batches, include_prior=True):
    rows=[];sources={};audits=[];checks=[]
    for batch in batches:
        batch=Path(batch).resolve()
        if batch.is_file():
            ledger=read(batch)
            if ledger.get('kind')!='isolated_runs' or not ledger.get('completed'):
                raise ValueError('isolated execution ledger is incomplete')
            sources[str(batch.relative_to(ROOT))]=digest(batch)
            for entry in ledger['runs']:
                path=ROOT/entry['run_dir'];v=verify_run(path,write=False)
                checks.append({'run':str(path.relative_to(ROOT)),**v})
                if entry['experiment_status']=='error':
                    checks.append({'batch':str(batch.relative_to(ROOT)),'not_evaluable_run':entry,
                                   'scope':'isolated execution error; retained, not a performance failure'})
                    sources[str((path/'manifest.json').relative_to(ROOT))]=digest(path/'manifest.json')
                    continue
                if v['record_status']!='passed' or v['experiment_status'] not in ('passed','failed'):
                    raise ValueError('invalid isolated completed record')
                row=load_one(path,ledger['phase'],sources,audits);row['condition']=entry['condition'];rows.append(row)
            continue
        v=verify_run(batch,write=False)
        manifest=read(batch/'manifest.json')
        if v['record_status']!='passed':
            expected_missing={f"{r['config']}: run has no metrics.json for recomputation"
                              for r in manifest['runs'] if r['experiment_status']=='error'}
            problems=v.get('record_problems',[])
            if manifest.get('experiment_status')!='error' or not problems or set(problems)-expected_missing:
                raise ValueError(f'bad batch record beyond documented incomplete capture: {batch}: {v}')
        checks.append({'batch':str(batch.relative_to(ROOT)),**v})
        for run in manifest['runs']:
            if not run.get('relative_dir') or run['experiment_status'] not in ('passed','failed'):
                checks.append({'batch':str(batch.relative_to(ROOT)),'not_evaluable_run':run,
                               'scope':'execution error or skipped; excluded from performance metrics, retained in attempt ledger'})
                if run.get('relative_dir'):
                    for f in (batch/run['relative_dir']).iterdir():
                        if f.is_file():sources[str(f.relative_to(ROOT))]=digest(f)
                continue
            path=batch/run['relative_dir']
            child_check=verify_run(path,write=False)
            if child_check['record_status']!='passed':raise ValueError(f'inconsistent completed record: {path}')
            phase='pmsm_boundary_coarse' if manifest['case_id']=='pmsm_boundary_retry' else manifest['case_id']
            rows.append(load_one(path,phase,sources,audits))
        for f in (batch/'manifest.json',batch/'inputs'/manifest['case_snapshot'].removeprefix('inputs/')):
            if f.is_file():sources[str(f.relative_to(ROOT))]=digest(f)
    if include_prior:
        prior=ROOT/'results/20261110-225921-case-pmsm_event_interaction-1f69bc/runs'
        for name in ('01-baseline','02-speed_only','03-load_only','04-simultaneous'):
            path=prior/name;v=verify_run(path,write=False)
            if v['record_status']!='passed':raise ValueError('prior record verification failed')
            checks.append({'prior_run':str(path.relative_to(ROOT)),**v})
            rows.append(load_one(path,'prior',sources,audits))
    return rows,sources,audits,checks


def load_one(path,phase,sources,audits):
    config=read(path/'config.json');metrics=read(path/'metrics.json');m=read(path/'manifest.json')
    d=load_waveforms(path/'waveforms.csv',('t_relative_s','t_simulation_s',*PMSMPreviewAdapter.columns))
    row={'condition':path.name,'phase':phase,'run_dir':str(path.relative_to(ROOT)),
         'config_sha256':digest(path/'config.json'),'experiment_status':m['status'],
         'record_status':'passed',**describe(config),**derive(d,metrics,config)}
    row['recovery_verdict']=recovery_verdict(row)
    row['observed_failure_lower_bound_ms']=max(0,(row['observed_horizon_s']-.02)*1000) if row['recovery_s'] is None and row['order']!='baseline' else None
    audits.append({'run_dir':row['run_dir'],**independent_check(path/'waveforms.csv',row)})
    for filename in ('config.json','metrics.json','events.json','waveforms.csv','manifest.json'):
        f=path/filename;sources[str(f.relative_to(ROOT))]=digest(f)
    return row


def create_case(case_id,configs,task,title):
    case=ROOT/'cases'/case_id
    if case.exists():raise ValueError(f'case already exists: {case}')
    case.mkdir()
    (case/'acceptance.md').write_text((task/'protocol.md').read_text(encoding='utf-8'),encoding='utf-8')
    refs=[]
    for name,config in configs:
        validate_config(config)
        p=ROOT/'configs/pmsm_boundary'/f'{name}.json'
        if p.exists():raise ValueError(f'configuration already exists: {p}')
        write(p,config);refs.append(str(p.relative_to(ROOT)).replace('\\','/'))
    write(case/'case.json',{'schema_version':1,'case_id':case_id,'model_id':'pmsm_software_preview',
                          'title':title,'backend':'virtual_hil','model_origin_ref':'models/origin.json',
                          'configs':refs,'acceptance_ref':'acceptance.md'})
    return refs


def select_dense(batches,task):
    rows,sources,audits,checks=collect(batches,include_prior=False)
    combinations={(r['speed_rpm'],round(r['load_nm'],6)) for r in rows if r['order']=='simultaneous'}
    if combinations!={(s,l) for s in (2400,2700,3000) for l in (.03,.06,.1)}:
        raise ValueError('coarse amplitude grid is incomplete; selection is not permitted')
    selected=min((r for r in rows if r['order']=='simultaneous'),key=severity)
    base=read(ROOT/selected['run_dir']/'config.json');configs=[]
    for gap in (.005,.01,.015,.02):
        for order in ('speed_then_load','load_then_speed'):
            c=deepcopy(base)
            for e in c['events']:
                second=(e['target']=='load_torque_nm')==(order=='speed_then_load')
                e['at_s']=.3+(gap if second else 0)
            c['events'].sort(key=lambda e:e['at_s'])
            configs.append((f'dense_{order}_{round(gap*1000):03d}ms',c))
    refs=create_case('pmsm_boundary_dense',configs,task,'PMSM 较小恢复裕度工况的事件间隔加密')
    selection={'rule':'minimum recovery margin; censored first; ties follow protocol',
               'selected':selected,'candidates':sorted((r for r in rows if r['order']=='simultaneous'),key=severity),
               'new_configs':refs,'source_hashes':sources}
    write(task/'selection.json',selection)
    print(json.dumps({'selected_speed_rpm':selected['speed_rpm'],'selected_load_nm':selected['load_nm'],
                      'recovery_s':selected['recovery_s'],'recovery_margin_ms':selected['recovery_margin_ms'],'configs':len(refs)},ensure_ascii=False))


def select_confirmation(batches,task):
    rows,_,_,_=collect(batches,include_prior=False)
    candidates=[r for r in rows if r['order'] in ('simultaneous','speed_then_load','load_then_speed')]
    worst=min(candidates,key=severity)
    reference=next(r for r in rows if r['order']=='simultaneous' and r['speed_rpm']==2400 and math.isclose(r['load_nm'],.03))
    configs=[('confirm_worst',read(ROOT/worst['run_dir']/'config.json')),
             ('confirm_reference',read(ROOT/reference['run_dir']/'config.json'))]
    refs=create_case('pmsm_boundary_confirm',configs,task,'PMSM 较小裕度与首轮桥接工况复跑')
    write(task/'confirmation-selection.json',{'worst':worst,'reference':reference,'new_configs':refs})
    print(json.dumps({'worst':worst['condition'],'recovery_s':worst['recovery_s'],'recovery_verdict':worst['recovery_verdict']},ensure_ascii=False))


def report(batches,output):
    output.mkdir(parents=True,exist_ok=True)
    rows,sources,audits,checks=collect(batches)
    write(output/'metrics.json',rows);write(output/'source-verification.json',checks)
    write(output/'independent-audit.json',audits)
    fields=[k for k in rows[0] if k not in ('events','recovery_interval_s')]
    with (output/'metrics.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
    current=[r for r in rows if r['phase']!='prior']
    primary=[r for r in current if r['phase']!='pmsm_boundary_confirm']
    unevaluable=[c for c in checks if 'not_evaluable_run' in c]
    write(output/'unevaluable-attempts.json',unevaluable)
    execution_errors=sum(c['not_evaluable_run']['experiment_status']=='error' for c in unevaluable)
    skipped=sum(c['not_evaluable_run']['experiment_status']=='skipped' for c in unevaluable)
    pairs=[]
    for i,r in enumerate(rows):
        for q in rows[:i]:
            if q['config_sha256']!=r['config_sha256']:continue
            a=load_waveforms(ROOT/q['run_dir']/'waveforms.csv',('t_relative_s','t_simulation_s',*PMSMPreviewAdapter.columns))
            b=load_waveforms(ROOT/r['run_dir']/'waveforms.csv',('t_relative_s','t_simulation_s',*PMSMPreviewAdapter.columns))
            pairs.append({'a':q['run_dir'],'b':r['run_dir'],
                          'max_speed_difference_rpm':float(np.max(np.abs(np.array(a['MechanicalSpeed_rad_s'])-np.array(b['MechanicalSpeed_rad_s']))))*30/math.pi,
                          'max_time_difference_s':float(np.max(np.abs(np.array(a['t_simulation_s'])-np.array(b['t_simulation_s']))))})
    write(output/'repeatability.json',pairs)
    worst=min((r for r in primary if r['order'] not in ('baseline',)),key=severity)
    tied=[r['condition'] for r in primary if r['recovery_s'] is not None and worst['recovery_s'] is not None
          and abs(r['recovery_s']-worst['recovery_s'])<=1e-5+1e-10]
    failed=[r for r in primary if r['recovery_verdict']=='failed']
    record_failures=[r for r in current if r['experiment_status']!='passed']
    coarse=[r for r in primary if r['phase']=='pmsm_boundary_coarse' and r['order']=='simultaneous']
    dense=[r for r in primary if r['phase']=='pmsm_boundary_dense']
    worst_combination=min((r for r in primary if r['order'] in ('simultaneous','speed_then_load','load_then_speed')),key=severity)
    strongest_load=next(r for r in coarse if r['speed_rpm']==3000 and math.isclose(r['load_nm'],.1))
    lightest_load=next(r for r in coarse if r['speed_rpm']==3000 and math.isclose(r['load_nm'],.03))
    write(output/'summary.json',{'current_runs':len(current),'prior_runs':len(rows)-len(current),
                                'primary_runs':len(primary),'recovery_failure_count':len(failed),
                                'execution_error_attempts':execution_errors,'initial_skipped_entries':skipped,
                                'original_experiment_failure_count':len(record_failures),'worst':worst,
                                'worst_combination':worst_combination,'worst_within_one_sample':tied})
    plots(output,rows,worst)
    def f(x):return '—' if x is None else f'{x:.3f}'
    def rec(r):return ('截尾' if r['recovery_censored'] else '—') if r['recovery_s'] is None else f(r['recovery_s']*1000)
    def table(items):
        out=['| 工况 | 目标 rpm | 最终负载 N·m | 顺序 | 负载相对调速延迟 ms | 恢复 ms | 裕度 ms | IAE rpm·s | 原判据 |',
             '|---|---:|---:|---|---:|---:|---:|---:|---|']
        for r in items:out.append(f"| {r['condition']} | {r['speed_rpm']:g} | {r['load_nm']:.3f} | {r['order']} | {f(r['signed_load_delay_ms'])} | {rec(r)} | {f(r['recovery_margin_ms'])} | {f(r['iae_rpm_s'])} | {r['experiment_status']} |")
        return '\n'.join(out)
    finding=(f"发现{len(failed)}个主运行违反100 ms恢复要求。" if failed else '本轮所执行工况未出现100 ms恢复超时，尚未触及该判据的失效边界。')
    worst_text=(f"恢复时间{rec(worst)} ms，距离100 ms限制还剩{f(worst['recovery_margin_ms'])} ms" if worst['recovery_s'] is not None else f"记录结束仍不能确认恢复，已观察到至少{f(worst['observed_failure_lower_bound_ms'])} ms的保守下界")
    md=f'''# PMSM 幅值扩展与事件间隔加密实验

{finding}本轮恢复裕度最小的主工况为`{worst['condition']}`：{worst_text}。

在一个采样间隔内并列的工况为：{', '.join(tied) or '无可报告的有限恢复时间'}。不根据微小浮点差异认定其中一个具有更高风险，实际复跑选点仍按预先规则与保存的选择文件执行。

本报告供电机HIL技术选型与后续搜索实验设计使用。新增{len(current)}次具有完整数据的Virtual HIL运行，另只读复用{len(rows)-len(current)}条首轮记录。纳入性能比较的完整子记录均通过一致性复核；其中原始实验判据未通过{len(record_failures)}次，具体项与恢复判据分别保留。

另外发生{execution_errors}次执行错误，中断批次共留下{skipped}条跳过记录；后续重试和续跑的完整结果独立保存。这些原始条目保留在[执行尝试清单](unevaluable-attempts.json)。Windows记录Virtual HIL进程崩溃，原错误批次仍为error/record failed。崩溃未确定根因，不能计作电机规格失效，也不能从完整样本中推算总体失效概率。[异常与恢复说明](../execution-incident.md)。

## 条件与实施

母线9 V、初始1800 rpm及0.01 N·m。粗扫描目标2400/2700/3000 rpm × 负载0.03/0.06/0.10 N·m；四个新增单事件对照。根据粗扫描恢复裕度选幅值，再比较两个顺序及5/10/15/20 ms间隔。最后复跑最差组合工况及2400 rpm+0.03 N·m参考。选择规则在[运行前方案](../protocol.md)固定，选择实际输入见[selection.json](../selection.json)。

每次采集0–0.8 s、100 kSa/s、80000行、7个信号。电机等效星形参数、理想角度与软件控制器沿用首轮；没有变更仿真执行器或模型实现。

## 粗扫描

同为3000 rpm同时事件，负载0.03 N·m的恢复时间为{rec(lightest_load)} ms，负载0.10 N·m为{rec(strongest_load)} ms。观测说明恢复风险不能仅按负载大小排序；具体控制机理仍需控制变量与观测补充，不从此表直接作原因归属。

{table([r for r in primary if r['phase']=='pmsm_boundary_coarse'])}

![同时事件的恢复时间](figures/amplitude-map.png)

图中每格是一次独立配置运行，数字为末实际事件后的恢复时间。颜色比较数值大小，失败或截尾另有文字标识；格点之间没有实验，不能据此声称整个连续区域通过。

## 间隔与顺序

{table(dense)}

![间隔对恢复和累计误差的影响](figures/timing-comparison.png)

横轴为两个事件的间隔，每条线用不同标记表示顺序；线仅连接已测点，不是插值模型。恢复从末实际事件起算，IAE从首实际事件起固定0.3 s计算。两指标一起用于判断风险，较短的末事件恢复时间不等于整个测试过程偏差较小。

![最差工况完整与局部响应](figures/worst-response.png)

上图包含启动与事件全过程，以及末事件附近误差和±50 rpm带。所有曲线来自原始样本，没有滤波、平滑、插值或删点。参考阶跃本身会产生瞬时跟踪误差，不将该峰值直接当作失效。

## 指标、复核与解释

- 判据保持100 ms、±50 rpm。原始event_group评价请求时刻后的稳定段；派生恢复以实际生效时刻为起点。原判据与派生判定分别保存，未通过原判据不会被派生分析覆盖。
- 恢复时间为最后一次越出误差带后重新入带并保持至记录结束，至少有20 ms尾证据；0表示一直在误差带内。未恢复用截尾表示，不填0或伪造精确时间。
- 累计误差IAE、峰值误差、事件后相电流峰值及尾段波动见[精确数值](metrics.csv)。每个事件保留实际时刻与相邻采样检测区间。
- 全部主指标另由标准库循环与梯形积分独立复算，[结果](independent-audit.json)。同配置比较见[复跑与环境桥接](repeatability.json)。
- 完整运行是分析单位；每配置一次主运行，没有显著性检验或总体失效概率结论。自适应选出的加密结果属于开发性搜索，不是独立测试集。
- 本轮搜索只覆盖指定正向调速、正向负载和事件间隔，未覆盖减速、反转、参数失配或实体固件。当前适配器允许范围不等于实体设备安全范围。

## 可支持的结论与后续决策

- 结论：{finding}证据：metrics.json中recovery_verdict与各运行原始判据。允许表述限于已执行点；不能声称全参数空间安全、已找到全局边界或样机通过。未测格点与模型迁移仍有不确定性。决定：保留限定结论。
- 结论：本轮最小裕度为上述实测值。证据：原始事件、恢复区间和独立复算；不能将有限网格最差点称为全局最差。下一步：以此点为基准选择新需求或经依据确认的新参数范围。决定：保留。
- 研究决策：若所有已允许点距离阈值仍较远，应报告当前空间对该判据不够苛刻。下一轮可提出减速/反转或控制与电机参数变化的独立问题，在运行前确定范围；不要为制造失败回改本轮阈值。若存在失败，优先补齐时间匹配的单事件对照后细化通过/失败两侧。

## 原始记录

'''
    for b in batches:
        target=Path(b) if Path(b).is_file() else Path(b)/'report.md'
        link=Path(os.path.relpath(target,output)).as_posix();md+=f'- [运行记录 {Path(b).name}]({link})\n'
    (output/'analysis-report.md').write_text(md,encoding='utf-8')
    (output/'stats-appendix.md').write_text(f'''# 统计与方法说明

新增{len(current)}次运行，其中{len(primary)}次主运行，另外{len(rows)-len(current)}条历史记录只读引用。波形采样行不是独立样本。每格n=1；复跑用于确定性检查，不支持总体均值、置信区间或显著性判断，无需多重检验校正。原单位恢复时间/裕度/IAE用于效应描述。

粗扫描到加密的选择规则提前固定，实际结果用于选点；这些点全部属于开发性搜索数据。没有比较搜索算法，也没有把网格覆盖比例当作失效概率。

截尾样本保留：有限记录不能确定精确恢复时间；本实验末事件后约0.48–0.50 s的观测足以判断100 ms要求是否违反。最后不足20 ms的入带不能证明持久恢复。10 µs采样分辨率及50 µs控制周期分别记录，未推断更高时间精度。

比较基准从各运行自己的实际命令时刻确定，非外部时钟强行对齐。event_group原始判据使用请求时刻，派生恢复使用实际时刻；边界附近两种状态须分别报告。

独立审计逐文件重算误差峰值、IAE和恢复时间。原CSV未改写，来源哈希、代码快照与实验版本可查。配置相同的跨批次/复跑比较另存repeatability.json。
''',encoding='utf-8')
    (output/'figure-catalog.md').write_text('''# 图表目录

| 文件 | 目的与观察重点 | 下一步决策 | 限定 |
|---|---|---|---|
| amplitude-map.png/pdf | 检查幅值网格中恢复时间与失败格点 | 选择加密幅值 | 单格n=1；不插值、无误差棒 |
| timing-comparison.png/pdf | 同幅值比较两顺序的恢复与IAE | 选取值得复验的时序 | 连接线只连接实测点；两种时间起点不同 |
| worst-response.png/pdf | 观察最小裕度工况的完整启动与末事件局部 | 核对是否持续恢复、确认后续变量 | 原始样本；速度与实际参考单位rpm |

数据来自metrics.json与source-manifest.json列出的CSV。颜色配合数字、标记或线型。图中S为调速、L为负载。截尾与失败明确标注。PNG用于审阅，PDF用于分享；未按任何期刊指定规格制作。
''',encoding='utf-8')
    write(output/'source-manifest.json',{'sources':sources,'scripts':{str(p.relative_to(ROOT)):digest(p) for p in (Path(__file__),ROOT/'scripts/analyze_pmsm_interaction.py')}})
    print(json.dumps({'new_runs':len(current),'recovery_failures':len(failed),'worst':worst['condition'],'worst_recovery_ms':worst['recovery_s']*1000 if worst['recovery_s'] is not None else None,'minimum_margin_ms':worst['recovery_margin_ms']},ensure_ascii=False))


def plots(output,rows,worst):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    p=output/'figures';p.mkdir(exist_ok=True)
    def save(fig,name):
        for ext in ('png','pdf'):fig.savefig(p/f'{name}.{ext}',dpi=170,facecolor='white')
        plt.close(fig)
    with plt.rc_context({'font.family':'DejaVu Sans','path.simplify':False,'pdf.fonttype':42,'axes.grid':True,'grid.alpha':.2}):
        coarse=[r for r in rows if r['phase']=='pmsm_boundary_coarse' and r['order']=='simultaneous']
        speeds=sorted({r['speed_rpm'] for r in coarse});loads=sorted({r['load_nm'] for r in coarse})
        z=np.full((len(loads),len(speeds)),np.nan)
        for r in coarse:
            if r['recovery_s'] is not None:z[loads.index(r['load_nm']),speeds.index(r['speed_rpm'])]=r['recovery_s']*1000
        fig,ax=plt.subplots(figsize=(8,5.5),layout='constrained');ax.grid(False)
        cmap=plt.get_cmap('Blues').copy();cmap.set_bad('#ddd')
        vmax=max(100,float(np.nanmax(z))) if np.any(np.isfinite(z)) else 100
        im=ax.imshow(z,origin='lower',cmap=cmap,vmin=0,vmax=vmax,aspect='auto',interpolation='nearest')
        ax.set_xticks(range(len(speeds)),[str(int(v)) for v in speeds]);ax.set_yticks(range(len(loads)),[f'{v:.2f}' for v in loads])
        for r in coarse:
            value=r['recovery_s']*1000 if r['recovery_s'] is not None else None
            text='censored' if value is None else f'{value:.2f} ms'
            if r['recovery_verdict']=='failed':text+='\nFAIL'
            ax.text(speeds.index(r['speed_rpm']),loads.index(r['load_nm']),text,ha='center',va='center',color='white' if value is not None and value>vmax*.6 else 'black')
        ax.set(xlabel='Target speed (rpm)',ylabel='Final load (N m)',title='Simultaneous events | recovery criterion: 100 ms')
        fig.colorbar(im,ax=ax,label='Recovery time (ms)');save(fig,'amplitude-map')
        dense=[r for r in rows if r['phase']=='pmsm_boundary_dense']
        fig,axs=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
        for order,color,marker,style,label in [('speed_then_load','#0072B2','o','-','S -> L'),('load_then_speed','#B33A00','s','--','L -> S')]:
            rr=sorted((r for r in dense if r['order']==order),key=lambda r:abs(r['signed_load_delay_ms']))
            x=[abs(r['signed_load_delay_ms']) for r in rr]
            axs[0].plot(x,[r['recovery_s']*1000 if r['recovery_s'] is not None else np.nan for r in rr],color=color,marker=marker,ls=style,label=label)
            axs[1].plot(x,[r['iae_rpm_s'] for r in rr],color=color,marker=marker,ls=style,label=label)
            for r in rr:
                if r['recovery_s'] is None:axs[0].annotate('censored',(abs(r['signed_load_delay_ms']),100),color=color,rotation=90,va='bottom')
        axs[0].axhline(100,color='#555',ls=':',label='100 ms criterion')
        axs[0].set_ylabel('Recovery after final event (ms)');axs[1].set_ylabel('Absolute error integral (rpm s)')
        for ax in axs:ax.set_xlabel('Event gap (ms)');ax.set_ylim(bottom=0);ax.set_xticks([5,10,15,20]);ax.legend(fontsize=8)
        if dense:fig.suptitle(f"Timing sweep | target {dense[0]['speed_rpm']:g} rpm, load {dense[0]['load_nm']:.2f} N m")
        save(fig,'timing-comparison')
        d=load_waveforms(ROOT/worst['run_dir']/'waveforms.csv',('t_relative_s','t_simulation_s',*PMSMPreviewAdapter.columns))
        t=np.array(d['t_simulation_s']);s=np.array(d['MechanicalSpeed_rad_s'])*30/math.pi;ref=np.array(d['Reference_rad_s'])*30/math.pi
        fig,axs=plt.subplots(2,1,figsize=(11,7),layout='constrained')
        axs[0].plot(t,s,color='#0072B2',label='Speed');axs[0].plot(t,ref,color='#B33A00',ls='--',label='Applied reference')
        axs[0].set(xlabel='Simulation time (s)',ylabel='Speed (rpm)')
        last=worst['last_event_observed_s'];mask=t>=last-.02
        axs[1].plot((t[mask]-last)*1000,(s-ref)[mask],color='#0072B2',label='Speed error')
        for band in (-50,50):axs[1].axhline(band,color='#555',ls=':',lw=1)
        axs[1].axvline(100,color='#B33A00',ls='--',label='100 ms criterion')
        axs[1].set(xlabel='Time after final observed event (ms)',ylabel='Speed error (rpm)')
        for e in worst['events']:axs[0].axvline(e['observed_at_s'],color='#777',ls=':',lw=.8)
        for ax in axs:ax.legend(fontsize=9)
        fig.suptitle('Smallest observed margin | '+worst['condition']);save(fig,'worst-response')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['dense','confirm','report']);p.add_argument('--batch',type=Path,action='append',required=True)
    p.add_argument('--task',type=Path,required=True);a=p.parse_args()
    if a.action=='dense':select_dense(a.batch,a.task)
    elif a.action=='confirm':select_confirmation(a.batch,a.task)
    else:report(a.batch,a.task/'analysis')
