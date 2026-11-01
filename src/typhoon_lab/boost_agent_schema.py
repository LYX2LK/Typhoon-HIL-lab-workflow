"""Generation-time schemas for DeepSeek strict function calls."""
from copy import deepcopy
from .boost_ai import read


def obj(properties):
    return {"type":"object","properties":properties,"required":list(properties),"additionalProperties":False}


def enum(values):
    return {"type":"string","enum":list(values)}


def array(items, description=""):
    return {"type":"array","items":items,"description":description}


def report_schema(request_hash,evidence,runs,root,remaining,investigation=None):
    if investigation is not None:
        from .boost_agent_wire import wire_schema
        return wire_schema(request_hash,evidence,remaining,investigation)
    text={"type":"string"};run_ids=array(enum(evidence),"已存在且不重复的运行ID，至少一项。")
    refs=array(enum(f"{rid}.{field}" for rid in evidence for field in ("config","metrics","pre_event_trend","aligned_response")))
    prose={"title":text,"text":text,"evidence":refs}
    blocks=[obj({"type":enum(["markdown"]),**prose}),
            obj({"type":enum(["callout"]),**prose,"tone":enum(["info","warning"])}),
            obj({"type":enum(["metrics"]),"title":text,"run_ids":run_ids}),
            obj({"type":enum(["waveform"]),"title":text,"run_ids":run_ids,"view":enum(["full","aligned","pre_event"])})]
    arguments=[]
    for rid,entry in runs.items():
        for op in ("repeat","baseline"):
            arguments.append(obj({"operation":enum([op]),"reference_run":enum([rid])}))
        config=read(root/entry["path"]/"config.json");events=config["events"]
        if events and events[0]["target"]=="input_voltage_v" and events[0]["value"]==28 and events[0]["at_s"]+.05<=2.5:
            arguments.append(obj({"operation":enum(["delay_event"]),"reference_run":enum([rid]),
                                  "event_at_s":{"type":"number","minimum":events[0]["at_s"]+.05,"maximum":2.5,
                                                "description":"100微秒网格上的新事件时刻。"}}))
    common={"id":{"type":"string","pattern":"^[A-Za-z0-9_-]{1,48}$"},"label":text,"description":text,"recommended":{"type":"boolean"}}
    options=[obj({**common,"tool":enum(["discuss"]),"arguments":obj({"message":text})})]
    if remaining>0:options.append(obj({**common,"tool":enum(["run_experiment"]),"arguments":{"anyOf":arguments}}))
    question=obj({"title":text,"options":array({"anyOf":options},"2至4项；最多一项recommended；不重复实验配置。")})
    # Legacy contract is kept byte-for-byte compatible with saved strict_tool_v1 requests.
    return obj({"request_sha256":enum([request_hash]),"cause_status":enum(["undetermined"]),
                "blocks":array({"anyOf":blocks},"1至10个区块；模型决定顺序。"),
                "question":{"anyOf":[question,{"type":"null"}]}})


def strict_tools(request_hash,evidence,runs,root,remaining,investigation=None,text_index=None,control_version=1):
    from .boost_agent_tools import TOOLS
    tools=deepcopy(TOOLS)
    for tool in tools:
        fn=tool["function"];fn["strict"]=True
        fn["parameters"]["properties"]["run_ids"]["items"]=enum(evidence)
        fn["parameters"]["properties"]["run_ids"]["enum"]=[list(evidence)]
    if text_index is None:
        description="提交本轮报告区块与验证候选，模型决定内容和编排。候选实验经人员选择并确认后执行。"
        schema=report_schema(request_hash,evidence,runs,root,remaining,investigation)
    else:
        from .boost_agent_prose import compact_schema
        description="用正文段落编号、证据、状态及受控参数提交页面编排和验证候选，不在参数中重写长文。"
        schema=compact_schema(request_hash,evidence,remaining,investigation,text_index,control_version)
    tools.append({"type":"function","function":{"name":"present_report","strict":True,
        "description":description,"parameters":schema}})
    return tools


def response_answer(raw,report_call_id=None):
    message=raw["choices"][0]["message"]
    import json
    if report_call_id is None:return json.loads(message["content"])
    calls=message.get("tool_calls",[])
    if len(calls)!=1 or calls[0]["id"]!=report_call_id or calls[0]["function"]["name"]!="present_report":
        raise ValueError("最终报告与模型结构化提交不匹配")
    return json.loads(calls[0]["function"]["arguments"])
