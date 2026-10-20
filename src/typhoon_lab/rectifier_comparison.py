"""Offline three-condition comparison, with source record verification."""
from copy import deepcopy
import json
import os
from pathlib import Path
from .utils import new_run,write_json,sha256,finalize,now
from .reporting import _table,_md_table,_write,_metadata,_fmt
from .rectifier_analysis import expected_rectifier

ROLES=("baseline","low_input","heavy_load")

def compare_metrics(records):
    baseline=records["baseline"];low=records["low_input"];heavy=records["heavy_load"]
    b=baseline["config"];l=low["config"];h=heavy["config"]
    for role,record in records.items():
        if record["config"]["model"]!="single_phase_rectifier": raise ValueError(f"{role} is not a rectifier run")
    expected_low=deepcopy(b);expected_low["source"]["rms_v"]*=.8
    expected_heavy=deepcopy(b);expected_heavy["circuit"]["load_ohm"]*=.5
    if l!=expected_low: raise ValueError("low-input configuration must change only baseline input RMS by factor 0.8")
    if h!=expected_heavy: raise ValueError("heavy-load configuration must change only baseline load resistance by factor 0.5")
    checks=[]
    def ratio(name,observed,expected,limit):
        error=abs(observed-expected)/abs(expected)
        checks.append({"name":name,"passed":error<=limit,"observed_ratio":observed,"expected_ratio":expected,"relative_error":error,"limit":limit})
    bm=baseline["metrics"]["signals"];lm=low["metrics"]["signals"];hm=heavy["metrics"]["signals"]
    for signal,metric in (("Vdc_V","mean"),("Vdc_V","ripple_pp"),("Iload_A","mean")):
        ratio("low_input_"+metric+"_"+signal,lm[signal][metric]/bm[signal][metric],.8,.02)
    rb=expected_rectifier(b);rh=expected_rectifier(h)
    for signal,metric,reference_key in (("Vdc_V","mean","mean_v"),("Vdc_V","ripple_pp","ripple_pp_v"),("Iload_A","mean","mean_load_a")):
        ratio("heavy_load_"+metric+"_"+signal,hm[signal][metric]/bm[signal][metric],rh[reference_key]/rb[reference_key],.03)
    for name,passed,observed,expected in (
        ("heavy_load_output_mean_decreases",hm["Vdc_V"]["mean"]<bm["Vdc_V"]["mean"],hm["Vdc_V"]["mean"],bm["Vdc_V"]["mean"]),
        ("heavy_load_ripple_increases",hm["Vdc_V"]["ripple_pp"]>bm["Vdc_V"]["ripple_pp"],hm["Vdc_V"]["ripple_pp"],bm["Vdc_V"]["ripple_pp"]),
        ("heavy_load_current_increases",hm["Iload_A"]["mean"]>bm["Iload_A"]["mean"],hm["Iload_A"]["mean"],bm["Iload_A"]["mean"])):
        checks.append({"name":name,"passed":bool(passed),"observed":observed,"baseline":expected})
    rows=[{"condition":role,"input_rms_v":record["config"]["source"]["rms_v"],"load_ohm":record["config"]["circuit"]["load_ohm"],
           "mean_v":record["metrics"]["signals"]["Vdc_V"]["mean"],"ripple_pp_v":record["metrics"]["signals"]["Vdc_V"]["ripple_pp"],
           "mean_load_a":record["metrics"]["signals"]["Iload_A"]["mean"],"ripple_frequency_hz":record["metrics"]["periodicity"]["dominant_ripple_hz"],
           "captured_input_cycles":record["metrics"]["capture"]["cycles"],"experiment_status":record["metrics"]["status"]} for role,record in records.items()]
    return {"schema_version":1,"model":"single_phase_rectifier","kind":"comparison","status":"passed" if all(x["passed"] for x in checks) and all(x["experiment_status"]=="passed" for x in rows) else "failed",
            "conditions":rows,"checks":checks,"method":"Identical normalized ideal bridge dynamics imply voltage/current/ripple scale with input amplitude. Heavy-load ratios use the independently integrated LC-R equations. Fixed limits: low-input ratios 2%, heavy-load ratios 3%; additionally require lower mean voltage, larger ripple and larger load current."}

def _read_records(paths):
    from .records import verify_run
    records={};sources={}
    for role,path in paths.items():
        path=Path(path).resolve()
        result=verify_run(path,write=False)
        if result["record_status"]!="passed": raise ValueError(f"{role} source record is inconsistent: {result['record_problems']}")
        records[role]={"config":json.loads((path/"config.json").read_text(encoding="utf-8")),"metrics":json.loads((path/"metrics.json").read_text(encoding="utf-8"))}
        sources[role]={"path":str(path),"verification":result,"sha256":{name:sha256(path/name) for name in ("manifest.json","config.json","metrics.json","waveforms.csv")}}
    return records,sources

def write_comparison_report(path,manifest):
    path=Path(path);m=json.loads((path/"metrics.json").read_text(encoding="utf-8"))
    heads=("工况","输入 RMS (V)","负载 (Ω)","输出平均 (V)","纹波峰峰 (V)","负载平均 (A)","纹波频率 (Hz)","输入周期数","状态")
    rows=[tuple(_fmt(row[key]) for key in ("condition","input_rms_v","load_ohm","mean_v","ripple_pp_v","mean_load_a","ripple_frequency_hz","captured_input_cycles","experiment_status")) for row in m["conditions"]]
    checks=[(x["name"],"通过" if x["passed"] else "未通过",_fmt(x.get("observed_ratio",x.get("observed"))),_fmt(x.get("expected_ratio",x.get("baseline"))),_fmt(x.get("limit"))) for x in m["checks"]]
    hp=["<h2>三工况比较</h2>"+_table(heads,rows),"<h2>固定趋势判据</h2>"+_table(("检查","结果","实际值或比值","参照值或比值","误差限"),checks)]
    mp=["## 三工况比较\n\n"+_md_table(heads,rows),"## 固定趋势判据\n\n"+_md_table(("检查","结果","实际值或比值","参照值或比值","误差限"),checks)]
    explanation="低输入只改变源幅值，检验电压、电流和纹波是否同比缩放。重负载只将电阻减半，核对输出均值降低、纹波增加、负载电流增加，并将变化比与独立状态方程参考比较。每条源运行先完成记录复核；源路径和哈希见 inputs.json。"
    hp.append("<p>"+explanation+"</p>");mp.append(explanation)
    hp.append("<h2>来源</h2>"+_table(("字段","记录"),_metadata(manifest)));mp.append("## 来源\n\n"+_md_table(("字段","记录"),_metadata(manifest)))
    return _write(path,"单相桥整流三工况比较",manifest["status"],hp,mp,scope="离线比较三次独立 Virtual HIL 采样；本命令不启动仿真。源记录、条件匹配、趋势和比值均保留。")

def compare_rectifier(baseline,low_input,heavy_load):
    from .runtime import snapshot_code
    paths=dict(zip(ROLES,(baseline,low_input,heavy_load)))
    records,sources=_read_records(paths);metrics=compare_metrics(records)
    path=new_run("rectifier-comparison")
    for role,source in sources.items(): source["path"]=os.path.relpath(paths[role],path).replace("\\","/")
    write_json(path/"inputs.json",sources);write_json(path/"metrics.json",metrics)
    manifest={"schema_version":1,"kind":"comparison","model":"single_phase_rectifier","backend":"virtual_hil","started_at":now(),"status":metrics["status"],"code_sha256":snapshot_code(path)}
    write_comparison_report(path,manifest);finalize(path,manifest)
    return path,metrics

def recompute_comparison(path):
    path=Path(path);sources=json.loads((path/"inputs.json").read_text(encoding="utf-8"))
    if set(sources)!=set(ROLES): raise ValueError("comparison needs three source conditions")
    paths={role:(path/source["path"]).resolve() for role,source in sources.items()}
    for role,source in sources.items():
        for name,expected in source["sha256"].items():
            if sha256(paths[role]/name)!=expected: raise ValueError(f"comparison source changed: {role}/{name}")
    records,_=_read_records(paths)
    return compare_metrics(records)
