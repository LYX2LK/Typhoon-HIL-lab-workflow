"""A shallow wire contract; deterministic projection, never JSON repair."""
from copy import deepcopy
from .boost_agent_schema import obj,enum,array
from .boost_agent_investigation import context_refs


def wire_schema(request_hash,evidence,remaining,context):
    text={"type":"string"};refs=array(enum([f"{rid}.{field}" for rid in evidence for field in ("config","metrics","pre_event_trend","aligned_response")]+context_refs(context)))
    hypothesis=obj({"id":{"type":"string","pattern":"^[A-Za-z0-9_-]{1,48}$"},"claim":text,
                    "status":enum(["supported","weakened","unresolved","established","refuted"]),
                    "scope":text,"reason":text,"evidence":refs,"criterion":text,"test_basis":text})
    block=obj({"type":enum(["markdown","callout","metrics","waveform"]),"title":text,"text":text,
               "evidence":refs,"run_ids":array(enum(evidence)),"view":enum(["full","aligned","pre_event"]),"tone":enum(["info","warning"])})
    actions=["discuss","conclude"]+([] if context["goal"]=="identify_mechanism" else ["deepen"])+(["run_experiment"] if remaining>0 else [])
    option=obj({"id":{"type":"string","pattern":"^[A-Za-z0-9_-]{1,48}$"},"label":text,"description":text,
                "recommended":{"type":"boolean"},"tool":enum(actions),"experiment_key":enum(context["action_catalog"]),
                "event_at_s":{"type":"number","minimum":0,"maximum":2.5},"message":text})
    closing=context["intent"]=="conclude"
    return obj({"request_sha256":enum([request_hash]),"goal":text,
        "decision":enum(["complete"] if closing else ["continue","ready_to_conclude","needs_capability","complete"]),
        "summary":text,"observations":array(enum(f["id"] for f in context["verified_observations"]),"选择已复算事实ID，不重复。"),
        "hypotheses":array(hypothesis,"每个假说给出范围和依据；普通支持/削弱/待定时criterion和test_basis留空。"),
        "next_requirement":text,"blocks":array(block,"模型决定内容与顺序；不使用的文本/数组留空，view用full、tone用info。"),
        "question":enum([""]) if closing else text,
        "options":{"type":"array","items":option,"enum":[[]]} if closing else array(option,"2至4项；非实验的experiment_key=none、event_at_s=0；实验的message留空。")})


def project_answer(wire,context):
    if set(wire)!={"request_sha256","goal","decision","summary","observations","hypotheses","next_requirement","blocks","question","options"}:raise ValueError("报告传输字段不符合契约")
    facts={f["id"]:f for f in context["verified_observations"]}
    selected=wire["observations"]
    if not isinstance(selected,list) or len(set(selected))!=len(selected) or any(x not in facts for x in selected):raise ValueError("观察必须选择唯一且已复算的事实")
    claims=[deepcopy(facts[k]) for k in selected]
    for h in wire["hypotheses"]:
        claims.append({**h,"kind":"hypothesis"})
    options=[]
    for o in wire["options"]:
        if set(o)!={"id","label","description","recommended","tool","experiment_key","event_at_s","message"}:raise ValueError("候选传输字段不符合契约")
        if o["tool"]=="run_experiment":
            key=o["experiment_key"]
            if key=="none" or key not in context["action_catalog"] or o["message"]:raise ValueError("实验候选未引用当前工具目录")
            arguments=deepcopy(context["action_catalog"][key])
            if arguments["operation"]=="delay_event":arguments["event_at_s"]=o["event_at_s"]
            elif o["event_at_s"]!=0:raise ValueError("非延后工况不接受事件时刻")
            if arguments["operation"]=="repeat" and o["recommended"]:raise ValueError("重复工况只作一致性检查，不作为默认诊断推荐")
        else:
            if o["experiment_key"]!="none" or o["event_at_s"]!=0:raise ValueError("讨论或目标选择不接受实验参数")
            arguments={"message":o["message"]}
        options.append({k:o[k] for k in ("id","label","description","recommended","tool")}|{"arguments":arguments})
    if bool(options)!=bool(wire["question"].strip()):raise ValueError("问题文字与选项需同时提供或同时留空")
    return {"request_sha256":wire["request_sha256"],
        "assessment":{k:wire[k] for k in ("goal","decision","summary","next_requirement")}|{"claims":claims},
        "blocks":wire["blocks"],"question":{"title":wire["question"],"options":options} if options else None}
