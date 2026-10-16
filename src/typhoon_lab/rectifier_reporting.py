"""Offline report for the single phase rectifier, retaining all raw samples."""
import html
import json
from pathlib import Path
from .analysis import load_waveforms
from .rectifier_analysis import COLUMNS
from .reporting import _json,_fmt,_table,_md_table,_metadata,_write,_image,COLORS

SCOPE="单相二极管桥整流教学实验。Virtual HIL 在电脑上按仿真时间推进；波形来自实际软件采样，数值参考来自独立的理想桥 LC-R 状态方程。"

def write_rectifier_report(run_dir,manifest):
    path=Path(run_dir);m=_json(path/"metrics.json");c=_json(path/"config.json")
    status=manifest.get("status",m.get("status","error"));hp=[];mp=[];outputs=[]
    if manifest.get("error"):
        hp.append("<h2>执行记录</h2><pre>"+html.escape(manifest["error"])+"</pre>")
        mp.append("## 执行记录\n\n"+manifest["error"])
    rows=[]
    for x in m.get("checks",[]):
        rows.append((x["name"],"通过" if x["passed"] else "未通过",_fmt(x["observed"]),_fmt(x["expected"]),_fmt(x["limit"])))
    heads=("检查","结果","实际值","参照值","误差限或阈值")
    hp.append("<h2>指标与判定</h2>"+_table(heads,rows));mp.append("## 指标与判定\n\n"+_md_table(heads,rows))
    if (path/"waveforms.csv").exists():
        d=load_waveforms(path/"waveforms.csv",COLUMNS)
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        with plt.rc_context({"font.family":"DejaVu Sans","font.size":10,"axes.grid":True,"grid.alpha":.2,"path.simplify":False}):
            fig,axes=plt.subplots(3,1,sharex=True,figsize=(10,8),layout="constrained")
            fig.suptitle("Single phase bridge - raw steady-state capture")
            for ax,col,color in zip(axes,COLUMNS[2:],COLORS):
                ax.plot([v*1000 for v in d["t_relative_s"]],d[col],color=color,linewidth=1,label=col)
                ax.set_ylabel("Vdc (V)" if col=="Vdc_V" else col.replace("_A"," (A)"));ax.legend(loc="upper right")
            axes[-1].set_xlabel("Time from capture start (ms)")
            plot=path/"waveforms.png";fig.savefig(plot,dpi=160,facecolor="white",metadata={"Description":"All raw samples; no filtering, filling or resampling."});plt.close(fig)
        caption="依次显示输出电压、负载电流和电容电流；电压测量低通在本次模型副本中关闭。原始采样覆盖完整输入周期。"
        hp.append("<h2>原始波形</h2>"+_image(plot,caption));mp.append("## 原始波形\n\n![原始采样波形](waveforms.png)\n\n"+caption);outputs.append(plot)
    for heading,value in (("独立参考与适用条件",m.get("reference",{})),("稳态周期核对",m.get("periodicity",{})),("采集与分析方法",{**m.get("capture",{}),**m.get("analysis",{})}),("实际配置",c)):
        text=json.dumps(value,ensure_ascii=False,indent=2)
        hp.append("<h2>"+heading+"</h2><pre>"+html.escape(text)+"</pre>");mp.append("## "+heading+"\n\n```json\n"+text+"\n```")
    hp.append("<h2>运行来源</h2>"+_table(("字段","记录"),_metadata(manifest)))
    mp.append("## 运行来源\n\n"+_md_table(("字段","记录"),_metadata(manifest)))
    hp.append('<p><a href="waveforms.csv">原始 CSV</a> · <a href="metrics.json">指标</a> · <a href="manifest.json">清单</a></p>')
    mp.append("[原始 CSV](waveforms.csv) · [指标](metrics.json) · [清单](manifest.json)")
    outputs.extend(_write(path,"单相桥整流实验报告",status,hp,mp,scope=SCOPE))
    return outputs
