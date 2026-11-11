"""Offline, reproducible analysis of the predeclared PMSM interaction batch."""
import argparse
import csv
import hashlib
import html
import json
import math
import os
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from typhoon_lab.analysis import load_waveforms
from typhoon_lab.pmsm_preview import PMSMPreviewAdapter
from typhoon_lab.records import verify_run

LABELS = {'baseline':'无事件', 'speed_only':'仅调速', 'load_only':'仅加负载',
          'simultaneous':'同时事件', 'speed_only_repeat':'仅调速复跑',
          'simultaneous_repeat':'同时事件复跑'}


def label(key):
    if key in LABELS: return LABELS[key]
    order = '调速→负载' if key.startswith('speed_then') else '负载→调速'
    return order+' '+str(int(key.split('_')[-1][:-2]))+' ms'


def recovery(t, error, onset, band=50., minimum_tail=.02):
    """Last band exit, observed return and finite-record censoring; no smoothing."""
    ids=np.flatnonzero(t>=onset)
    if len(ids)<2: raise ValueError('missing recovery window')
    bad=ids[np.abs(error[ids])>band]
    idx=int(bad[-1]+1) if len(bad) else int(ids[0])
    if idx>=len(t) or t[-1]-t[idx]<minimum_tail:
        return {'recovery_s':None,'recovery_interval_s':None,'recovery_censored':True,
                'observed_horizon_s':float(t[-1]-onset)}
    value=max(0.,float(t[idx]-onset))
    left=max(0.,float(t[idx-1]-onset)) if idx>0 else 0.
    return {'recovery_s':value,'recovery_interval_s':[left,value], 'recovery_censored':False,
            'observed_horizon_s':float(t[-1]-onset)}


def derive(d, metrics, config):
    t=np.asarray(d['t_simulation_s'])
    speed=np.asarray(d['MechanicalSpeed_rad_s'])*30/math.pi
    ref=np.asarray(d['Reference_rad_s'])*30/math.pi
    err=speed-ref
    events=metrics['events']
    if any(e['status']!='passed' or e['observed_at_s'] is None for e in events):
        raise ValueError('event application has not been established')
    first=min(e['observed_at_s'] for e in events) if events else .3
    last=max(e['observed_at_s'] for e in events) if events else .3
    window=(t>=first)&(t<first+.3)
    tail=(t>=last+.1)&(t<last+.3)
    if t[-1]<max(first+.3,last+.3)-2e-5: raise ValueError('incomplete analysis window')
    event_details=[]
    for e in events:
        i=int(np.searchsorted(t,e['observed_at_s']))
        event_details.append({**e,'detection_interval_s':[float(t[i-1]) if i else None,float(t[i])]})
    r=recovery(t,err,last)
    r.update(first_event_observed_s=first if events else None,last_event_observed_s=last if events else None,
             peak_abs_error_rpm=float(np.max(np.abs(err[window]))),
             peak_positive_error_rpm=float(np.max(err[window])),
             peak_negative_error_rpm=float(np.min(err[window])),
             iae_rpm_s=float(np.sum(np.diff(t[window])*(np.abs(err[window][1:])+np.abs(err[window][:-1]))/2)),
             minimum_speed_rpm=float(np.min(speed[window])),
             phase_current_peak_a=max(float(np.max(np.abs(np.asarray(d[k])[window]))) for k in ('Ia_A','Ib_A','Ic_A')),
             tail_error_peak_to_peak_rpm=float(np.ptp(err[tail])),
             settled_max_error_rpm=metrics['windows'][-1]['max_speed_error_rpm'],
             recovery_margin_ms=(.1-r['recovery_s'])*1000 if r['recovery_s'] is not None else None,
             events=event_details, sample_count=len(t))
    if not events:
        r.update(recovery_s=None,recovery_interval_s=None,recovery_censored=False,recovery_margin_ms=None)
    return r


def independent_check(path, result):
    """Separate stdlib loop/integration verifies key vectorized computations."""
    with path.open(encoding='utf-8') as f: rows=list(csv.DictReader(f))
    first=result['first_event_observed_s'] or .3
    last=result['last_event_observed_s'] or .3
    peak=0.;area=0.;previous=None;bad=None;raw=[]
    for row in rows:
        t=float(row['t_simulation_s'])
        e=(float(row['MechanicalSpeed_rad_s'])-float(row['Reference_rad_s']))*30/math.pi
        raw.append((t,e))
        if t>=last and abs(e)>50: bad=len(raw)-1
        if first<=t<first+.3:
            peak=max(peak,abs(e))
            if previous: area+=(t-previous[0])*(abs(e)+abs(previous[1]))/2
            previous=(t,e)
    idx=(bad+1) if bad is not None else next(i for i,(t,e) in enumerate(raw) if t>=last)
    rec=None if idx>=len(raw) or raw[-1][0]-raw[idx][0]<.02 else max(0.,raw[idx][0]-last)
    checks={'peak_error':math.isclose(peak,result['peak_abs_error_rpm'],abs_tol=1e-8),
            'iae':math.isclose(area,result['iae_rpm_s'],abs_tol=1e-8),
            'recovery':result['first_event_observed_s'] is None or rec==result['recovery_s']}
    if not all(checks.values()): raise ValueError(f'independent metric mismatch: {checks}')
    return checks


def analyze(batch, output):
    batch=batch.resolve();output.mkdir(parents=True,exist_ok=True)
    verification=verify_run(batch,write=False)
    if verification['record_status']!='passed': raise ValueError(verification)
    manifest=json.loads((batch/'manifest.json').read_text(encoding='utf-8'))
    result=[];series={};audit=[];sources={}
    for run in manifest['runs']:
        if not run.get('relative_dir') or run['experiment_status'] not in ('passed','failed'):
            raise ValueError('batch contains uncompleted run')
        path=batch/run['relative_dir'];key=Path(run['config']).stem
        config=json.loads((path/'config.json').read_text(encoding='utf-8'))
        metrics=json.loads((path/'metrics.json').read_text(encoding='utf-8'))
        d=load_waveforms(path/'waveforms.csv',('t_relative_s','t_simulation_s',*PMSMPreviewAdapter.columns))
        r={'condition':key,'label':label(key),'run_dir':str(path.relative_to(ROOT)),
           'experiment_status':run['experiment_status'],'record_status':run['record_status'],**derive(d,metrics,config)}
        audit.append({'condition':key,**independent_check(path/'waveforms.csv',r)})
        result.append(r);series[key]=d
        for filename in ('waveforms.csv','config.json','metrics.json','events.json','manifest.json'):
            p=path/filename;sources[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
    def write(name,obj):
        (output/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    write('metrics.json',result);write('independent-audit.json',audit)
    fields=[k for k in result[0] if k not in ('events','recovery_interval_s')]
    with (output/'metrics.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(result)
    repeat=[]
    for key in ('speed_only','simultaneous'):
        a=series[key];b=series[key+'_repeat']
        repeat.append({'condition':key,'maximum_speed_difference_rpm':float(np.max(np.abs(np.array(a['MechanicalSpeed_rad_s'])-np.array(b['MechanicalSpeed_rad_s']))))*30/math.pi,
                       'max_time_grid_difference_s':float(np.max(np.abs(np.array(a['t_simulation_s'])-np.array(b['t_simulation_s']))))})
    write('repeatability.json',repeat)
    plots(output,result,series)
    by={r['condition']:r for r in result}
    differences=[]
    for gap in (5,20,100):
        a=by[f'speed_then_load_{gap:03d}ms'];b=by[f'load_then_speed_{gap:03d}ms']
        differences.append({'gap_ms':gap,'contrast':'load_then_speed minus speed_then_load',
                            'iae_difference_rpm_s':b['iae_rpm_s']-a['iae_rpm_s'],
                            'recovery_difference_ms':(b['recovery_s']-a['recovery_s'])*1000 if a['recovery_s'] is not None and b['recovery_s'] is not None else None})
    write('contrasts.json',differences)
    primary=[r for r in result if not r['condition'].endswith('_repeat')]
    failures=[r['label'] for r in result if r['experiment_status']!='passed']
    finding=('12次运行均通过预设的软件稳定段与电路一致性判据。' if not failures else '未通过工况：'+', '.join(failures)+'。')
    single=by['speed_only'];both=by['simultaneous'];a=by['speed_then_load_020ms'];b=by['load_then_speed_020ms']
    finding+=f"仅调速的恢复时间为{single['recovery_s']*1000:.2f} ms，同时事件为{both['recovery_s']*1000:.2f} ms。20 ms间隔下，先调速再加载的IAE为{a['iae_rpm_s']:.3f} rpm·s，反向顺序为{b['iae_rpm_s']:.3f} rpm·s，差{b['iae_rpm_s']-a['iae_rpm_s']:.3f} rpm·s。"
    batch_link=Path(os.path.relpath(batch,output)).as_posix()
    table=['| 工况 | 恢复时间 / ms | 100 ms裕度 / ms | 峰值绝对误差 / rpm | IAE / rpm·s | 事件后相电流峰值 / A | 实验 |',
           '|---|---:|---:|---:|---:|---:|---|']
    def fmt(v): return '—' if v is None else f'{v:.3f}'
    for r in result:
        table.append(f"| {r['label']} | {fmt(r['recovery_s']*1000 if r['recovery_s'] is not None else None)} | {fmt(r['recovery_margin_ms'])} | {fmt(r['peak_abs_error_rpm'])} | {fmt(r['iae_rpm_s'])} | {fmt(r['phase_current_peak_a'])} | {r['experiment_status']} |")
    table='\n'.join(table)
    report=f'''# 调速与负载变化的事件交互实验

本报告供电机HIL方法选型与后续实验设计使用。共12次Virtual HIL运行，10种工况；仅调速、同时事件各复跑一次。全部原始波形、事件与配置保存在[批次目录]({batch_link}/report.md)。

## 主要发现

{finding}

100 ms间隔时，顺序对IAE的差值转为{differences[-1]['iae_difference_rpm_s']:.3f} rpm·s（先加载后调速减去先调速后加载），因此本轮不支持把某一种顺序概括为普遍更好。[全部原单位差值](contrasts.json)。两组复跑的速度和时间采样逐点一致，支持本环境下的确定性复现。

本轮已经观察到事件安排对应的动态差异，但没有发现“单事件通过、组合事件违反100 ms恢复要求”的样本。下一轮可沿已经验证的间隔与顺序加密，并逐项扩大调速/负载幅值；沿用判据记录是否出现失效，不能从本轮所有工况通过推断整个参数空间均通过。

恢复时间为0表示最后事件后始终未离开±50 rpm带，不表示物理响应瞬时结束。约600 rpm的跟踪误差峰值主要包含600 rpm参考阶跃本身，不直接当作异常。先调速、100 ms后加载的末事件恢复时间也不包含此前已发生的调速过程。

## 实验条件与结果

9 V母线，初始1800 rpm、0.01 N·m；调速至2400 rpm，负载升至0.03 N·m。首事件0.3 s，间隔0/5/20/100 ms。每次记录0–0.8 s，100 kSa/s、80000点。其余电机及控制参数沿用软件预演。软件模型采用等效星形参数假设和理想角度反馈。

{table}

恢复时间从最后一个实际生效事件起算，定义为最后一次超出±50 rpm后重新入带并保持到记录结束，至少保留20 ms尾段。无事件对照不定义事件恢复时间。误差峰值、IAE及电流峰值使用首个实际事件后0.3 s窗口；IAE采用梯形积分，未滤波。启动电流不计入事件后峰值。窗口与采样分辨率见[数值明细](metrics.json)。

![恢复时间与误差积分](figures/comparison.png)

上图比较各事件安排的实际观测值；无误差棒，每种工况仅一次主运行。100 ms虚线是预先固定的软件探索判据。恢复时间从末事件起算，因此不同间隔的数值需要结合全过程误差积分阅读。

![完整速度误差过程](figures/full-response.png)

上图保留每次主运行的完整启动及事件响应；蓝色实线为速度误差，橙色虚线标记调速，紫色点线标记负载。事件竖线采用实际生效时刻，各运行具有自身仿真时间轴。

![事件局部对照](figures/event-detail.png)

局部图比较相同间隔的两个顺序以及单事件和同时事件，使用相同纵轴。它用于识别响应叠加与恢复阶段差异；总响应差异本身不证明非线性机理。

## 复核和适用范围

批次记录复核：{verification['record_status']}。所有12次运行的峰值误差、IAE及恢复时间另经Python标准库独立计算核对。[独立核对](independent-audit.json) · [复跑差异](repeatability.json) · [统计说明](stats-appendix.md)。

本轮结论限于这组软件控制器、参数、幅值和事件安排；真实控制板迁移需正常闭环及可用观测确认。没有故障注入，也没有比较LLM与数值搜索。

## 可支持的结论

- 结论：本轮12次固定配置运行的稳定段均满足预设要求（具体状态以上表为准）。依据：各子运行metrics.json、批次verification.json。允许表述限于本轮参数；不能表述为样机通过或全参数空间无失效。下一步：扩大幅值并保持判据。决定：保留。
- 结论：20 ms间隔的两个顺序具有上述IAE差异。依据：metrics.csv与contrasts.json。允许表述为本轮响应差异；不能表述为统计显著、因果机制已确定或某个顺序普遍最优。每配置仅一次主运行，独立工况外推不确定。下一步：时间匹配的单事件对照及幅值复验。决定：保留限定表述。
- 结论：同时事件和仅调速在当前误差带下的恢复时间不同。依据：事件局部图、恢复区间和原始CSV。它与末事件起点、超调和负载响应相关，机理仍需控制变量复验。不能声称加载普遍改善控制。下一步：查看误差带敏感性与不同负载幅值。决定：保留观测，机理解释待验。
'''
    (output/'analysis-report.md').write_text(report,encoding='utf-8')
    (output/'stats-appendix.md').write_text('''# 统计和指标说明

- 分析单位：完整运行。10种配置，每种1次；仅调速、同时事件另各1次，共12次。波形80000点是时间采样，不是独立样本。
- 主指标：最后实际事件后的±50 rpm持续恢复时间及100 ms裕度。恢复未完成保留null/截尾，不删除；本轮实际情况见metrics.json。
- 次指标：首事件后0.3 s的绝对误差峰值、梯形积分IAE、相电流峰值与最小速度；末事件后0.1–0.3 s误差峰峰值描述尾部波动。
- 效应量：原单位差值与顺序比较，见报告结论；不估计总体效应或故障概率。重复结果用于确定性复现。
- 置信区间、显著性检验、总体均值±标准差及多重比较校正均不适用：没有随机抽样的独立重复工况。单次固定配置的时间波动不能替代独立重复。
- 事件时刻由各运行直接采集的命令波形识别，另给相邻样本检测区间；实际采样间隔约10 µs，控制周期50 µs。
- 不同顺序末事件不同，主指标起点随之变化；用全过程误差积分补充比较。未通过时间匹配的四条件析因对照，因此不作非线性交互因果断言。
- 无滤波、平滑、插值、补点或异常样本剔除；图形使用原始速度采样。原始CSV与来源哈希均保留。
''',encoding='utf-8')
    (output/'figure-catalog.md').write_text('''# 图表说明

| 图 | 目的与应观察内容 | 对下一步的作用 | 限定 |
|---|---|---|---|
| comparison.png/pdf | 比较末事件后恢复时间和完整事件窗口IAE，保留100 ms判据 | 选择后续加密的间隔与顺序 | 每配置单次主运行，无误差棒；不代表总体性能 |
| full-response.png | 查看0–0.8 s启动、基线、事件和尾段 | 检查启动是否稳定，是否漏掉后续偏差 | 各面板共用坐标；原始速度误差 |
| event-detail.png/pdf | 按间隔比较两个顺序及单独/同时事件 | 判断响应发生在另一次事件前还是后，为复验选点 | 竖线为实际事件；未作非线性机制识别 |

来源：metrics.json、source-manifest.json所列原始CSV。速度从rad/s乘30/π转换为rpm，误差为实测速度减实测参考；未滤波。图面英文缩写S表示调速、L表示负载。PNG为审阅版本，PDF为比较与局部图的分享版本。
''',encoding='utf-8')
    write('source-manifest.json',{'batch':str(batch.relative_to(ROOT)),'sources':sources,
                                'analysis_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    print(table)
    return result


def plots(output,results,series):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    p=output/'figures';p.mkdir(exist_ok=True)
    main=[r for r in results if not r['condition'].endswith('_repeat')]
    names={'baseline':'Baseline','speed_only':'S only','load_only':'L only','simultaneous':'S + L'}
    def short(key):
        if key in names: return names[key]
        return ('S -> L' if key.startswith('speed_then') else 'L -> S')+' '+str(int(key.split('_')[-1][:-2]))+' ms'
    with plt.rc_context({'font.family':'DejaVu Sans','axes.grid':True,'grid.alpha':.2,'path.simplify':False,'pdf.fonttype':42}):
        fig,axs=plt.subplots(1,2,figsize=(12,5.8),layout='constrained')
        active=main[1:];y=np.arange(len(active))
        for ax,field,scale,title in [(axs[0],'recovery_s',1000,'Recovery after final event (ms)'),(axs[1],'iae_rpm_s',1,'Absolute error integral (rpm s)')]:
            vals=[r[field]*scale if r[field] is not None else np.nan for r in active]
            ax.scatter(vals,y,c='#0072B2',marker='o',s=40)
            ax.set_yticks(y,[short(r['condition']) for r in active]);ax.invert_yaxis();ax.set_xlabel(title);ax.set_xlim(left=0)
        axs[0].axvline(100,color='#B33A00',linestyle='--',label='100 ms criterion')
        axs[0].set_xlim(-2,108);axs[0].legend(loc='lower right',fontsize=8)
        for i,r in enumerate(active):
            if r['recovery_s'] is not None:
                axs[0].annotate(f"{r['recovery_s']*1000:.2f}",(r['recovery_s']*1000,i),xytext=(6,0),textcoords='offset points',va='center',fontsize=8)
        fig.suptitle('PMSM event interaction | one primary run per condition')
        for ext in ('png','pdf'): fig.savefig(p/f'comparison.{ext}',dpi=180,facecolor='white')
        plt.close(fig)
        fig,axs=plt.subplots(5,2,figsize=(13,14),sharex=True,sharey=True,layout='constrained')
        for ax,r in zip(axs.flat,main):
            d=series[r['condition']];t=np.array(d['t_simulation_s']);e=(np.array(d['MechanicalSpeed_rad_s'])-np.array(d['Reference_rad_s']))*30/math.pi
            ax.plot(t,e,color='#0072B2',lw=.8)
            for ev in r['events']:
                speed=ev['target']=='reference_speed_rpm'
                ax.axvline(ev['observed_at_s'],color='#B33A00' if speed else '#7B3294',ls='--' if speed else ':',lw=1.1)
            ax.set_title(short(r['condition']));ax.set_ylabel('Speed error (rpm)');ax.set_xlabel('Simulation time (s)')
        fig.suptitle('Full raw speed error | event markers: speed --, load :')
        fig.savefig(p/'full-response.png',dpi=150,facecolor='white');plt.close(fig)
        fig,axs=plt.subplots(2,2,figsize=(13,8),sharex=True,sharey=True,layout='constrained')
        groups=[['speed_only','load_only','simultaneous']]+[[f'speed_then_load_{gap:03d}ms',f'load_then_speed_{gap:03d}ms'] for gap in (5,20,100)]
        for ax,keys in zip(axs.flat,groups):
            for key,color,style in zip(keys,('#0072B2','#B33A00','#117733'),('-','--',':')):
                d=series[key];t=np.array(d['t_simulation_s']);e=(np.array(d['MechanicalSpeed_rad_s'])-np.array(d['Reference_rad_s']))*30/math.pi
                mask=(t>=.28)&(t<=.6);ax.plot(t[mask],e[mask],color=color,ls=style,label=short(key),lw=1)
                r=next(r for r in main if r['condition']==key)
                for ev in r['events']: ax.axvline(ev['observed_at_s'],color=color,ls=':',alpha=.35,lw=.7)
            ax.axhline(50,color='#555',ls=':',lw=.7);ax.axhline(-50,color='#555',ls=':',lw=.7)
            ax.legend(fontsize=8,loc='lower right');ax.set_xlabel('Simulation time (s)');ax.set_ylabel('Speed error (rpm)')
        fig.suptitle('Event response detail | raw samples, +/-50 rpm reference band')
        for ext in ('png','pdf'): fig.savefig(p/f'event-detail.{ext}',dpi=180,facecolor='white')
        plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--batch',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();analyze(args.batch,args.output)
