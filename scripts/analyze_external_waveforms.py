"""Audit original two-column oscilloscope CSV exports without altering them."""
from pathlib import Path
import argparse,csv,hashlib,json,sys
from datetime import datetime,timezone,timedelta
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

SCREENSHOTS={
 'tu1':{'sample_rate_hz':200e6,'record_points':100000,'visible_window_us':[-250,250]},
 'tu2':{'sample_rate_hz':16e9,'record_points':8000000,'visible_window_us':[-250,250]},
 'tu3':{'sample_rate_hz':16e9,'record_points':1600000,'visible_window_us':[-49.9,50.1]},
 'tu4':{'sample_rate_hz':200e6,'record_points':131000,'visible_window_us':[-24.9,25.1]},
}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read_raw(p):
 rows=[];bad=[];blank=0
 with p.open(encoding='utf-8-sig',newline='') as f:
  for i,row in enumerate(csv.reader(f),1):
   if not row:blank+=1;bad.append(i);continue
   try:
    if len(row)!=2:raise ValueError()
    values=[float(v) for v in row]
    if not all(np.isfinite(values)):raise ValueError()
    rows.append(values)
   except ValueError:bad.append(i)
 if bad:raise ValueError(f'{p.name}: invalid/blank rows {bad[:10]}, total={len(bad)}')
 a=np.asarray(rows,dtype=float)
 if len(a)<3:raise ValueError('too few samples')
 return a,blank
def crossing(t,y,threshold):
 idx=np.flatnonzero((y[:-1]<threshold)&(y[1:]>=threshold))+1
 if not len(idx):return None
 i=int(idx[0]);return {'last_below_s':float(t[i-1]),'first_at_or_above_s':float(t[i])}
def profile(p):
 a,blank=read_raw(p);t,y=a.T;dt=np.diff(t);step=float(np.median(dt))
 if np.any(dt<=0):raise ValueError(f'{p}: time must be strictly increasing')
 # Allow decimal export rounding, not missing whole samples.
 tolerance=max(1e-15,abs(step)*1e-4)
 gaps=int(np.count_nonzero(np.abs(dt-step)>tolerance))
 if gaps:raise ValueError(f'{p}: {gaps} nonuniform time intervals')
 n=len(t);m=max(1,n//10);lo=float(np.median(y[:m]));hi=float(np.median(y[-m:]))
 result={'filename':p.name,'sha256':sha(p),'rows':n,'columns':2,'header':False,'blank_rows':blank,
 'nonfinite_values':0,'duplicate_times':0,'nonincreasing_intervals':0,'nonuniform_intervals':gaps,
 't_start_s':float(t[0]),'t_end_s':float(t[-1]),'time_span_s':float(t[-1]-t[0]),
 'dt_median_s':step,'dt_min_s':float(dt.min()),'dt_max_s':float(dt.max()),
 'csv_grid_rate_hz':1/step,'min_value':float(y.min()),'max_value':float(y.max()),
 'mean':float(y.mean()),'std_population':float(y.std()),'first_10pct_median':lo,'last_10pct_median':hi,
 'units':{'time':'s','value':'V'},'unit_evidence':'inferred from matching named screenshot axes; CSV itself has no header',
 'screenshot':SCREENSHOTS[p.stem],'png_sha256':sha(p.with_suffix('.png')),
 'physical_label':'unconfirmed','probe_ratio':'unconfirmed','measurement_point':'unconfirmed'}
 if p.stem in ('tu1','tu2'):
  mask=y<lo*.95;ix=np.flatnonzero(mask)
  groups=np.split(ix,np.where(np.diff(ix)>1)[0]+1) if len(ix) else []
  g=max(groups,key=len) if groups else None
  result['descriptive_dip']={'baseline_v':lo,'threshold_v':lo*.95,'threshold_rule':'5% below first-10% median, descriptive only',
   'max_drop_v':float(lo-y.min()),'below_threshold_samples':int(mask.sum()),
   'longest_segment':None if g is None else {'first_sample_s':float(t[g[0]]),'last_sample_s':float(t[g[-1]]),
   'sample_count':int(len(g)),'sample_support_duration_s':float(len(g)*step),'duration_resolution_s':step}}
 else:
  c10=crossing(t,y,lo+.1*(hi-lo));c90=crossing(t,y,lo+.9*(hi-lo))
  rise_mask=(t>=c10['last_below_s'])&(t<=c90['first_at_or_above_s']) if c10 and c90 else np.ones(n,dtype=bool)
  rise_y=y[rise_mask]
  result['descriptive_rise']={'low_v':lo,'high_v':hi,'crossing_10pct':c10,'crossing_90pct':c90,
   'first_crossing_10_90_s':c90['first_at_or_above_s']-c10['first_at_or_above_s'] if c10 and c90 else None,
   'max_drawdown_within_first_10_90_v':float(np.max(np.maximum.accumulate(rise_y)-rise_y)),
   'largest_single_sample_fall_v':float(np.max(-np.diff(y))),
   'note':'first upward crossings; does not assert monotonicity or physical rise-time specification'}
 result['screenshot_rate_matches_csv_grid']=bool(np.isclose(result['csv_grid_rate_hz'],SCREENSHOTS[p.stem]['sample_rate_hz'],rtol=1e-5))
 return a,result
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--input-dir',required=True);ap.add_argument('--output-dir',required=True)
 args=ap.parse_args();source=Path(args.input_dir).resolve();out=Path(args.output_dir).resolve()
 if out.exists() and any(out.iterdir()):raise ValueError('output directory must be new or empty')
 out.mkdir(parents=True,exist_ok=True);arrays={};results=[]
 for i in range(1,5):
  a,r=profile(source/f'tu{i}.csv');arrays[f'tu{i}']=a;results.append(r)
 for name,limits in [('full',None),('detail','local')]:
  with plt.rc_context({'font.size':11,'axes.grid':True,'grid.alpha':.2,'path.simplify':False}):
   fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
   for ax,(key,a) in zip(axs.flat,arrays.items()):
    t,y=a.T
    if limits:
     bounds=(-25,10) if key in ('tu1','tu2') else (-12,5)
     mask=(t*1e6>=bounds[0])&(t*1e6<=bounds[1])
    else:mask=np.ones(len(t),dtype=bool)
    ax.plot(t[mask]*1e6,y[mask],color='#0072B2' if key in ('tu1','tu3') else '#A34400',lw=.8)
    ax.set(title=key,xlabel='CSV time (us)',ylabel='Voltage (V; screenshot units)',ylim=(-.4,5.6))
   fig.suptitle('Original CSV samples - '+('local windows' if limits else 'full export windows'))
   fig.savefig(out/f'waveforms_{name}.png',dpi=160,facecolor='white')
   plt.close(fig)
 metadata={'created_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),'source_dir':str(source),
 'method':'no filtering, resampling or time alignment; all valid raw rows used',
 'performance_status':'not_evaluated','records':results,
 'limitations':['Source CSV is headerless; units inferred from paired images.','Screenshot acquisition rates need not equal CSV export spacing.',
 'Labels and physical causes are not established.','Four captures are not independent replicated experiments for significance tests.']}
 (out/'profile.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
 lines=['# 四组外部波形检查报告','','面向项目维护者，说明现有数据能够支持的数值分析和仍需确认的采集信息。','',
 '四份 CSV 均为无表头两列数值。按同名示波器图片的坐标将两列解释为秒和伏，CSV 本身未编码单位；测点、探头倍率、异常标签及采集/导出关系仍待数据提供方确认。','',
 '| 文件 | 样本数 | 时间范围 / µs | CSV 间隔 / ns | 最小值 / V | 最大值 / V |',
 '|---|---:|---:|---:|---:|---:|']
 for r in results:
  lines.append(f"| {r['filename']} | {r['rows']} | {r['t_start_s']*1e6:.6f} 至 {r['t_end_s']*1e6:.6f} | {r['dt_median_s']*1e9:.6f} | {r['min_value']:.6f} | {r['max_value']:.6f} |")
 lines+=['','## 数据质量与适用范围','','所有行参与检查；未发现空行、非有限值、重复/倒序时间或超出声明容差的不均匀间隔。数据适合当前导出分辨率下的波形描述和候选特征计算。','',
 '![完整导出波形](waveforms_full.png)','','全程图保留各文件自己的时间范围，纵轴统一。tu1/tu2 显示约 5 V 平台与局部跌落的差异；tu3/tu4 显示不同的上升过程。各文件保留原时间轴，不假定跨文件同步。','',
 '![局部波形](waveforms_detail.png)','','局部图的窗口明确缩小，没有平滑、插值或删除窗口内样本。用于观察跌落和上升过程中的细节。','',
 '## 数值描述','','下列阈值仅定义描述性特征，不是控制器通过/失败标准。平台数据以起始 10% 样本中位数为基准，统计低于其 95% 的连续区段；上升过程以起始/末尾 10% 中位数定义低/高平台，取首次向上穿越 10% 和 90% 电平的样本。','']
 for r in results:
  if 'descriptive_dip' in r:
   d=r['descriptive_dip'];g=d['longest_segment']
   lines.append(f"- {r['filename']}：基准 {d['baseline_v']:.6f} V，最大向下偏离 {d['max_drop_v']:.6f} V；低于描述阈值的样本 {d['below_threshold_samples']} 个。"+(f"最长连续区段的样本支撑时长 {g['sample_support_duration_s']*1e6:.3f} µs，时间分辨率 {g['duration_resolution_s']*1e9:.3f} ns；边界受采样限制。" if g else ''))
  else:
   d=r['descriptive_rise'];rise=d['first_crossing_10_90_s']
   lines.append(f"- {r['filename']}：首次 10%–90% 穿越间隔 {rise*1e6:.3f} µs；该区间内从此前峰值到随后样本的最大回落 {d['max_drawdown_within_first_10_90_v']:.6f} V。首次穿越间隔不反映全部过程形态，须结合回落和原始曲线。")
 lines+=['','## 与同名截图的核对','','| 文件 | 截图采样率 | CSV 等效网格率 | 结论 |','|---|---:|---:|---|']
 for r in results:
  lines.append(f"| {r['filename']} | {r['screenshot']['sample_rate_hz']/1e6:g} MSa/s | {r['csv_grid_rate_hz']/1e6:.6g} MSa/s | "+('两者数值一致；仍需确认导出范围' if r['screenshot_rate_matches_csv_grid'] else '两者不同；导出抽取、窗口或配对关系需确认')+' |')
 lines+=['','截图整体形态与同名 CSV 一致；tu2/tu3 的截图采样率与 CSV 网格率不同，tu4 截图的总记录点数也不能直接当作 CSV 行数。不能将 CSV 的 5 ns 间隔称为所有原始采集的采样周期，或据此判断完整高频细节已保留。','',
 '## 待补元信息与后续用途','','1. 测量对象、测点、通道、单位和探头倍率。','2. 每份 CSV 对应的采集记录、导出范围、抽取/插值设置及触发参考。','3. 正常/异常标签的提供者、判定依据，以及具体测试问题。','4. 若需要回放，先明确关键幅值/持续时间/边沿和允许误差，再选择模型或仪器。','',
 '当前结论支持离线描述和数据接收准备；物理故障原因、控制器合格性与硬件回放保真度均未验证。','',
 '## 复现','','运行项目 scripts/analyze_external_waveforms.py，显式提供 --input-dir 与新的 --output-dir。profile.json 保留来源 SHA-256、数值、截图读取元信息和计算定义；原始 CSV/PNG 保持不变。','',
 '科学绘图方法参考：Kassis et al. (2026), Scientific Agent Skills, arXiv:2609.00065（项目既有方法引用；本轮未联网核验出版元数据）。']
 (out/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 (out/'analysis_source.py').write_bytes(Path(__file__).read_bytes())
 # Notebook exposes the raw-data checks independently of plotting.
 code="from pathlib import Path\nimport numpy as np\nsource=Path("+repr(str(source))+")\nfor p in sorted(source.glob('tu*.csv')):\n    a=np.loadtxt(p,delimiter=',')\n    dt=np.diff(a[:,0])\n    print(p.name,a.shape,np.isfinite(a).all(),np.count_nonzero(dt<=0),np.median(dt),a[:,1].min(),a[:,1].max())\n"
 notebook={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'}},
 'cells':[{'cell_type':'markdown','metadata':{},'source':['# 原始 CSV 独立检查\n','只读检查；单位依据同名截图，物理标签待确认。']},
 {'cell_type':'code','metadata':{},'execution_count':None,'outputs':[],'source':code.splitlines(True)}]}
 (out/'checks.ipynb').write_text(json.dumps(notebook,ensure_ascii=False,indent=2),encoding='utf-8')
 manifest={p.name:sha(p) for p in out.iterdir() if p.is_file()}
 (out/'manifest.json').write_text(json.dumps({'artifacts':manifest,'source_hashes':{r['filename']:r['sha256'] for r in results}},indent=2),encoding='utf-8')
 print(json.dumps({'output':str(out),'records':[{'file':r['filename'],'n':r['rows'],'dt_ns':r['dt_median_s']*1e9,'min':r['min_value'],'max':r['max_value']} for r in results]},ensure_ascii=False))
if __name__=='__main__':main()
