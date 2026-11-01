"""Read-only investigation context from saved records; never starts an experiment."""
from .analysis import load_waveforms
from .boost_ai import COLUMNS
from .boost_agent_tools import digest


def history_for(messages):
    history=[]
    for message in messages:
        if message["role"]=="user":history.append({"role":"user","text":message["text"]})
        elif message["role"]=="assistant":
            answer=message["answer"]
            summary=answer.get("assessment",{}).get("summary") or '\n'.join(b.get("text","") for b in answer["blocks"])
            q=answer.get("question")
            if q:summary+='\n上轮问题：'+q["title"]+'；选项：'+'；'.join(o["label"]+'：'+o["description"] for o in q["options"])
            history.append({"role":"assistant","text":summary[:3500]})
    return history[-12:]


def context_for(evidence,runs,root,goal="characterize_response",intent="continue"):
    signals={};config_groups={};disturbances=[];catalog={"none":None}
    for rid,ev in evidence.items():
        d=load_waveforms(root/runs[rid]["path"]/"waveforms.csv",columns=COLUMNS)
        t,current=d["t_simulation_s"],d["Iin_A"]
        index=max(range(len(current)),key=lambda i:abs(current[i]))
        anchor=ev["anchor_s"];after=[i for i,x in enumerate(t) if anchor-1e-9<=x<anchor+.9-1e-9]
        ai=max(after,key=lambda i:abs(current[i]));peak=abs(current[index])
        signals[rid]={"source_csv_sha256":ev["source_csv_sha256"],"sample_count":len(t),
            "anchor_kind":ev["anchor_kind"],"anchor_s":anchor,
            "whole_capture_current_peak":{"absolute_a":peak,"first_simulation_time_s":t[index],
                "relative_to_anchor_s":t[index]-anchor,"equal_max_sample_count":sum(abs(x)==peak for x in current)},
            "aligned_current_peak":{"absolute_a":abs(current[ai]),"first_simulation_time_s":t[ai],
                "relative_to_anchor_s":t[ai]-anchor,"sample_count":len(after)},
            "scope":"10 kHz记录采样点最大绝对值；不是连续PWM峰值，也不据此判定限流。"}
        config_groups.setdefault(digest(ev["config"]),[]).append(rid)
        for operation in ("repeat","baseline"):
            catalog[operation+":"+rid]={"operation":operation,"reference_run":rid}
        events=ev["config"]["events"]
        if events and events[0]["target"]=="input_voltage_v" and events[0]["value"]==28 and events[0]["at_s"]+.05<=2.5:
            catalog["delay_event:"+rid]={"operation":"delay_event","reference_run":rid}
        if ev["config"]["events"]:
            disturbances.append({"run_id":rid,"event_at_s":ev["nominal_anchor_s"],
                "peak_deviation_percent":100*ev["aligned_response"]["peak_deviation_relative"],
                "pre_event_slope_v_per_s":ev["pre_event_trend"]["slope_v_per_s"]})
    disturbances.sort(key=lambda x:(x["event_at_s"],x["run_id"]))
    contrasts=[{"left":a["run_id"],"right":b["run_id"],"peak_change_percentage_points":b["peak_deviation_percent"]-a["peak_deviation_percent"]}
               for a,b in zip(disturbances,disturbances[1:])]
    facts=[]
    def fact(id,claim,scope,refs):
        facts.append({"id":id,"kind":"observation","status":"established","claim":claim,"scope":scope,
                      "reason":"数值由保存的原始采样或原指标直接取得；该项只陈述观测，不作机理归因。","evidence":refs})
    if disturbances:
        fact("disturbance_peaks","跌落实验的峰偏差为"+'；'.join(x['run_id']+f"：{x['peak_deviation_percent']:.6f}%" for x in disturbances)+"。",
             "仅限这些已保存工况，偏差相对固定50 V参考。",[x['run_id']+'.aligned_response' for x in disturbances])
    if contrasts:
        last=contrasts[-1]
        fact("latest_timing_contrast",last['left']+"至"+last['right']+f"的峰偏差变化为{last['peak_change_percentage_points']:.6f}个百分点。",
             "描述性差值，未据此判定统计显著性、等效性或原因贡献。",[last['left']+'.aligned_response',last['right']+'.aligned_response'])
    fact("current_peak_time","各记录整段电流采样峰值的首次发生时刻为"+'；'.join(k+f"：{v['whole_capture_current_peak']['first_simulation_time_s']:.7f} s" for k,v in signals.items())+"。",
         "仅指10 kHz保存样点的整段最大绝对值，不代表连续PWM峰值。",[k+'.signal_stats' for k in signals])
    return {"schema_version":1,"goal":goal,"intent":intent,"signal_stats":signals,"verified_observations":facts,"action_catalog":catalog,
        "run_history":{"run_count":len(runs),"disturbance_runs":disturbances,"adjacent_timing_contrasts":contrasts,
                       "identical_configuration_groups":[v for v in config_groups.values() if len(v)>1],
                       "interpretation":"数值差异是描述性比较；未预设等效界限，不将接近当作独立性或机理贡献证明。"},
        "capabilities":{"available_experiments":["repeat","baseline","delay_event"],
            "measured_signals":list(COLUMNS),"unmeasured_internal_signals":["PI输出","占空比","限幅状态"],
            "requires_new_implementation":["内部信号采集","跌落幅值对照","PI或功率级参数干预"],
            "existing_data_first":"已有CSV可直接定位采样峰值，不为取得这些信息重跑实验。"}}


def context_refs(context):
    return ["investigation.run_history","investigation.capabilities"]+[f"{rid}.signal_stats" for rid in context["signal_stats"]]


def validate_assessment(value,refs,context=None):
    if not isinstance(value,dict) or value.get("decision") not in {"continue","ready_to_conclude","needs_capability","complete"}:
        raise ValueError("结论进展状态无效")
    for key in ("goal","summary","next_requirement"):
        if not isinstance(value.get(key),str) or len(value[key])>2500:raise ValueError("结论进展说明无效")
    if not value["goal"].strip() or not value["summary"].strip():raise ValueError("结论需说明目标和进展")
    if value["decision"]=="needs_capability" and not value["next_requirement"].strip():raise ValueError("需明确新增能力的用途")
    claims=value.get("claims");seen=set()
    if not isinstance(claims,list) or not 1<=len(claims)<=8:raise ValueError("需给出1至8项有范围的结论")
    for c in claims:
        if not isinstance(c,dict) or not isinstance(c.get("id"),str) or not c["id"] or c["id"] in seen:raise ValueError("结论标识无效或重复")
        seen.add(c["id"])
        if c.get("kind") not in ("observation","hypothesis") or c.get("status") not in ("established","supported","weakened","refuted","unresolved"):raise ValueError("命题状态无效")
        if not all(isinstance(c.get(k),str) and c[k].strip() and len(c[k])<=2500 for k in ("claim","scope","reason")):raise ValueError("结论需给出范围和判断依据")
        if not isinstance(c.get("evidence"),list) or not c["evidence"] or any(x not in refs for x in c["evidence"]):raise ValueError("结论缺少有效证据")
        if context is not None and c["kind"]=="observation":
            expected=next((x for x in context["verified_observations"] if x["id"]==c["id"]),None)
            if c!=expected:raise ValueError("已确认观察需绑定复算事实，不得改成机理判断")
        if c["kind"]=="hypothesis" and c["status"] in ("established","refuted"):
            if not all(isinstance(c.get(k),str) and c[k].strip() for k in ("criterion","test_basis")):raise ValueError("假说确认或排除需明确判据与判别性验证依据")
    return value
