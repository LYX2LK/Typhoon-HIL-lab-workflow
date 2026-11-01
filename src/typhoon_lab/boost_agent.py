"""A persistent, tool-using Boost analysis agent with human-approved experiments."""
from copy import deepcopy
import json
from pathlib import Path
import secrets
import shutil
import threading
import time
import urllib.request
import urllib.error

from .boost_ai import read, load_service, NoRedirect
from .boost_agent_tools import (build_config, evidence_for, compare, digest, ids,
                                TOOLS, system_prompt, validate_answer)
from .boost_agent_schema import strict_tools,response_answer
from .boost_agent_investigation import context_for,context_refs,history_for
from .boost_agent_wire import project_answer
from .boost_agent_prose import NARRATIVE_REQUEST,index_narrative,project_compact
from .config import load_config
from .records import verify_run
from .utils import PROJECT, new_run, now, write_json, sha256, runtime_lock, finalize

MAX_CALLS=5
MAX_RUNS=8


from .agent_service import api_call


from .agent_state import PersistentSession


class AgentSession(PersistentSession):
    def __init__(self,session_dir=None,service_path=None):
        self.guard=threading.RLock();self.worker=None
        self.service=Path(service_path or PROJECT/"configs/ai_service_agent.json")
        if session_dir is None:
            self.root=new_run("boost-agent")
            self.state={"schema_version":1,"kind":"boost_agent_session","created_at":now(),"busy":False,
                "status":"ready","message":"准备就绪，可开始案例验证。",
                "messages":[],"runs":{},"turns":[],"active_turn":None,"pending":None,"revision":0}
            (self.root/"task.md").write_text(f"# 控制器波形分析与验证：Boost先行案例\n\n创建：{now()}\n面向控制器测试，验证波形采集、大模型分析与对照复验的协同流程，为后续水泵控制器测试接入提供基础。\n本例判断输入跌落是否导致输出偏差超限，评估启动残余解释，并根据证据提出后续验证。首次固定Boost输入跌落；后续由模型提出选项、人员确认后执行。原判据固定，Virtual HIL软件证据；实验结论与流程完成范围分别说明。\n",encoding="utf-8")
            self.persist("session_created",{})
        else:
            self.root=Path(session_dir).resolve()
            if not self.root.is_relative_to(PROJECT/"results"):raise ValueError("会话必须位于项目results内")
            self.state=read(self.root/"session.json")
            if self.state.get("kind")!="boost_agent_session" or self.state.get("schema_version")!=1:raise ValueError("不支持该Agent会话版本")
            if self.state.get("busy"):raise ValueError("该会话记录仍为运行中；保留现场，不能自动恢复或执行")
            check=verify_session(self.root)
            if check["record_status"]!="passed":raise ValueError("会话复核失败，不能恢复")


    def snapshot(self):
        from .boost_agent_render import message_html
        with self.guard:state={**deepcopy(self.state),"session_dir":str(self.root)}
        for message in state["messages"]:
            if message["role"]=="assistant":message["html"]=message_html(self.root,message)
        return state




    def launch(self,operation,data):
        with self.guard:
            if data.get("case_id") not in (None, "boost_input_disturbance"):
                raise ValueError("旧版Boost会话仅支持Boost；请新建会话选择其他案例")
            if self.state["busy"]:raise ValueError("Agent正在处理当前任务，请等待")
            if operation=="start":
                if self.state["runs"]:raise ValueError("本会话已开始，请继续对话或新建会话")
                text=("以Boost输入跌落为先行案例，验证面向控制器测试的波形分析与对照复验流程，为后续水泵控制器测试接入提供基础。"
                      "请先按固定判据判断输出电压偏差是否超限，再结合波形证据解释动态响应、评估启动残余能否充分解释下冲，并提出下一步验证建议。")
                self.add("user",text)
                job=("initial",text,None)
            elif operation in {"say","retry"}:
                if not self.state["runs"]:raise ValueError("请先开始案例验证")
                text=data.get("text","") if operation=="say" else "请根据当前已有实验重新分析并给出下一步建议。"
                if not isinstance(text,str) or not text.strip() or len(text)>4000:raise ValueError("请输入1到4000字的追问")
                self.add("user",text);job=("analysis",text,None)
            elif operation=="choose":
                turn,option=self._option(data.get("turn_id"),data.get("option_id"))
                if option["tool"] in {"discuss","conclude","deepen"}:
                    if option["tool"]=="deepen":
                        self.state["investigation_goal"]="identify_mechanism"
                        self.persist("investigation_goal_changed",{"goal":"identify_mechanism","option_id":option["id"]})
                    text=option["arguments"]["message"];self.add("user",option["label"]+"："+text)
                    job=("analysis",text,{"intent":"conclude" if option["tool"]=="conclude" else "continue"})
                else:
                    if len(self.state["runs"])>=MAX_RUNS:raise ValueError("本演示会话最多8次实验，请导出后新建会话")
                    config,anchor,diff=build_config(option["arguments"],self.state["runs"],self.root)
                    ref=option["arguments"]["reference_run"]
                    plan_id=secrets.token_hex(8);p=self.root/"plans"/plan_id;p.mkdir(parents=True)
                    write_json(p/"config.json",config)
                    plan={"schema_version":1,"id":plan_id,"created_at":now(),"turn_id":turn["id"],"option":option,
                        "answer_sha256":sha256(self.root/turn["path"]/"answer.json"),
                        "reference_run":ref,"reference_manifest_sha256":sha256(self.root/self.state["runs"][ref]["path"]/"manifest.json"),
                        "config_sha256":sha256(p/"config.json"),"anchor_s":anchor,"differences":diff,
                        "confirmation_token":secrets.token_hex(16)}
                    write_json(p/"plan.json",plan)
                    self.state["pending"]=plan;self.persist("option_prepared",{"plan_id":plan_id,"turn_id":turn["id"],"option_id":option["id"]})
                    return {"accepted":True,"pending":plan}
            elif operation=="confirm":
                pending=self.state["pending"]
                if not pending or data.get("plan_id")!=pending["id"] or data.get("approved") is not True:
                    raise ValueError("请先选择建议、查看差异并确认当前计划")
                if not secrets.compare_digest(str(data.get("token","")),pending["confirmation_token"]):raise ValueError("确认标识不匹配")
                operator=data.get("operator","")
                if not isinstance(operator,str) or not operator.strip() or len(operator)>120:raise ValueError("请填写实际确认操作者")
                turn,option=self._option(pending["turn_id"],pending["option"]["id"])
                p=self.root/"plans"/pending["id"]
                plan=read(p/"plan.json")
                c,anchor,_=build_config(option["arguments"],self.state["runs"],self.root)
                ref=self.root/self.state["runs"][plan["reference_run"]]["path"]
                if plan!=pending or option!=plan["option"] or c!=read(p/"config.json") or sha256(p/"config.json")!=plan["config_sha256"]:
                    raise ValueError("待确认配置或模型选项已变化，请重新选择")
                if sha256(self.root/turn["path"]/"answer.json")!=plan["answer_sha256"] or sha256(ref/"manifest.json")!=plan["reference_manifest_sha256"]:
                    raise ValueError("模型回答或来源记录已变化，拒绝执行")
                if verify_run(ref,write=False)["record_status"]!="passed":raise ValueError("来源记录复核失败")
                confirmation={"at":now(),"operator":operator,"plan_sha256":sha256(p/"plan.json"),"config_sha256":plan["config_sha256"]}
                with (p/"confirmation.json").open("x",encoding="utf-8") as f:json.dump(confirmation,f,ensure_ascii=False,indent=2)
                text="确认执行“"+option["label"]+"”。"
                self.add("user",text,confirmation=confirmation)
                job=("experiment",text,{"plan":plan,"config":c,"anchor":anchor})
            else:raise ValueError("不支持该操作")
            self.state.update(busy=True,status="running",pending=None,active_turn=None,message="Agent正在处理任务")
            self.persist("job_started",{"operation":job[0]})
            self.worker=threading.Thread(target=self.work,args=job,daemon=True);self.worker.start()
            return {"accepted":True}

    def run_experiment(self,config,anchor,plan=None):
        from .runtime import execute_case
        m_id=self.tool_status("Typhoon Virtual HIL：编译、运行并采集波形",details={"config":config})
        with runtime_lock():
            run_id=f"R{len(self.state['runs'])+1:03d}"
            p=self.root/"runs"/run_id;p.mkdir(parents=True)
            manifest=execute_case(p,config)
        checked=verify_run(p)
        entry={"id":run_id,"path":p.relative_to(self.root).as_posix(),"anchor_s":anchor,
               "manifest_sha256":sha256(p/"manifest.json"),"experiment_status":manifest["status"],"record_status":checked["record_status"],
               "plan_id":plan["id"] if plan else None}
        with self.guard:
            self.state["runs"][run_id]=entry;self.persist("experiment_finished",entry)
        if plan:write_json(self.root/"plans"/plan["id"]/"execution.json",entry)
        self.tool_status("",message_id=m_id,status="completed" if checked["record_status"]=="passed" and manifest["status"]!="error" else "error",details=entry)
        if manifest["status"]=="error" or checked["record_status"]!="passed":raise RuntimeError("实验执行或记录异常，原始记录已保存；本轮不交给模型作性能解释")
        e_id=self.tool_status("复算指标、判断异常并组织波形证据")
        evidence=evidence_for(entry,self.root)
        write_json(self.root/"derived"/run_id/"evidence.json",evidence)
        self.tool_status("",message_id=e_id,status="completed",details={"run_id":run_id,"record_status":entry["record_status"],"experiment_status":entry["experiment_status"]})
        return run_id

    def work(self,operation,text,context):
        try:
            if operation=="initial":
                self.run_experiment(load_config(PROJECT/"configs/boost_vin_drop.json"),.5)
            elif operation=="experiment":
                self.run_experiment(context["config"],context["anchor"],context["plan"])
            self.respond(text,new_experiment=operation in {"initial","experiment"},intent=(context or {}).get("intent","continue"))
            messages={"ready_to_conclude":"已有阶段结论，可选择收尾或继续定位机理","complete":"阶段结论已形成；可继续追问或开启新会话", "needs_capability":"继续定位需要明确新增观测或干预方案"}
            with self.guard:self.state.update(status="waiting",message=messages.get(self.state.get("investigation_phase"),"选择建议或继续追问，Agent将据此推进"))
        except Exception as exc:
            self.add("error",str(exc));self.state.update(status="error",message="本轮中止；已有实验和调用记录已保存")
        finally:
            with self.guard:
                self.state["busy"]=False;self.persist("job_finished",{"status":self.state["status"]})
            self.export()

    def respond(self,text,new_experiment=False,intent="continue"):
        from .boost_agent_render import prepare_assets, render_answer
        valid_runs={k:v for k,v in self.state["runs"].items() if v["record_status"]=="passed" and v["experiment_status"]!="error"}
        evidence={k:evidence_for(v,self.root) for k,v in valid_runs.items()}
        if not evidence:raise ValueError("没有可复核的实验记录")
        last_success=next((t for t in reversed(self.state["turns"]) if t["status"]=="passed"),None)
        analyzed_runs=read(self.root/last_success["path"]/"manifest.json").get("run_refs",{}) if last_success else {}
        needs_comparison=len(evidence)>1 and (new_experiment or not set(evidence).issubset(analyzed_runs))
        investigation=context_for(evidence,valid_runs,self.root,self.state.get("investigation_goal","characterize_response"),intent)
        turn_id=f"T{len(self.state['turns'])+1:03d}";p=self.root/"turns"/turn_id;p.mkdir(parents=True)
        for source in [*(PROJECT/"src"/"typhoon_lab").glob("boost_agent*.py"), *(PROJECT/"src"/"typhoon_lab").glob("agent*.py")]:
            target=p/"code_snapshot"/source.name;target.parent.mkdir(exist_ok=True);shutil.copy2(source,target)
        shutil.copy2(PROJECT/"src"/"typhoon_lab"/"boost_agent_page.html",p/"code_snapshot"/"boost_agent_page.html")
        history=history_for(self.state["messages"])
        inp={"schema_version":1,"user_request":text,"history":history,
            "run_index":[{"id":k,"config":v["config"],"record_status":v["record_status"],"experiment_status":v["experiment_status"],"anchor_kind":v["anchor_kind"]} for k,v in evidence.items()],
            "available_evidence":[f"{k}.{field}" for k in evidence for field in ("config","metrics","pre_event_trend","aligned_response")]+context_refs(investigation),
            "evidence_sha256":digest(evidence),"remaining_experiments":MAX_RUNS-len(self.state["runs"]),
            "model_facts":{k:read(self.root/v["path"]/"manifest.json").get("actual_model_parameters",{}) for k,v in valid_runs.items()},
            "investigation_context":investigation,"investigation_sha256":digest(investigation),
            "prior_assessment":read(self.root/last_success["path"]/"answer.json").get("assessment") if last_success else None,
            "scope":"Virtual HIL软件证据；本次分析为已有实验复现，不是独立故障盲测。"}
        write_json(p/"input.json",inp);request_hash=sha256(p/"input.json")
        write_json(p/"evidence.json",evidence)
        write_json(p/"investigation_context.json",investigation)
        record={"id":turn_id,"path":p.relative_to(self.root).as_posix(),"status":"running"}
        with self.guard:self.state["turns"].append(record);self.persist("agent_turn_started",{"id":turn_id})
        api_messages=[{"role":"system","content":system_prompt(request_hash)},
                      {"role":"user","content":json.dumps({"request_sha256":request_hash,"input":inp},ensure_ascii=False)}]
        answer=None;final_index=None;tool_outputs=[];narrative=None;text_index=None
        manifest={"kind":"boost_agent_turn","record_format_version":1,"analysis_method_version":1,"started_at":now(),"status":"error",
                  "request_sha256":request_hash,"run_refs":{k:valid_runs[k] for k in evidence},"output_contract":"strict_tool_v6","wire_protocol":"markdown_refs_v3"}
        if self.state.get("kind")=="agent_session":manifest["case_id"]=self.state["case_id"]
        try:
            for index in range(1,MAX_CALLS+1):
                have_compare=any(x["name"]=="compare_runs" for x in tool_outputs)
                read_runs={rid for x in tool_outputs if x["name"]=="read_evidence" for rid in x["arguments"]["run_ids"]}
                name="compare_runs" if needs_comparison and not have_compare else ("read_evidence" if set(evidence)-read_runs else "present_report")
                if name=="present_report" and narrative is None:
                    if index>=MAX_CALLS:raise ValueError("本轮未留出正文与控制参数预算；已有证据已保存")
                    narrative_messages=[*api_messages,{"role":"user","content":NARRATIVE_REQUEST}]
                    ui=self.tool_status("生成分析正文",details={"turn_id":turn_id})
                    message,finish=api_call(p,index,{"messages":narrative_messages,"tool_choice":"none"},self.service)
                    self.tool_status("",message_id=ui,status="completed",details=read(p/f"call-{index:02d}.meta.json"))
                    try:
                        if finish!="stop" or message.get("tool_calls"):raise ValueError(f"正文输出未正常完成（finish_reason={finish}）")
                        candidate=message.get("content");text_index=index_narrative(candidate)
                    except (ValueError,TypeError) as exc:
                        report_error(p,index,exc,"narrative_output")
                    narrative=candidate;(p/"narrative.md").write_text(narrative,encoding="utf-8")
                    write_json(p/"narrative_index.json",text_index);manifest["narrative_call_index"]=index
                    api_messages=narrative_messages+[{"role":"assistant","content":narrative},{"role":"user","content":json.dumps({"stage":"report_controls",
                        "narrative_sha256":sha256(p/"narrative.md"),"narrative_index":text_index,
                        "instruction":"调用present_report。question不超过60字；选项label用短标题，description用一句话说明目的、不超过120字，不引用整段；conclude/deepen是目标操作，message_ref必须为空，discuss的message_ref必须引用非空段落。恰好一个analysis显示完整正文。"},ensure_ascii=False)}]
                    continue
                if index==MAX_CALLS and name!="present_report":raise ValueError("本轮证据读取未完成；已有实验已保存")
                definitions=strict_tools(request_hash,evidence,valid_runs,self.root,MAX_RUNS-len(self.state["runs"]),investigation,text_index,3)
                if text_index is None:definitions=definitions[:2]
                choice={"type":"function","function":{"name":name}} if name!="present_report" or index==MAX_CALLS else "auto"
                call_ui=self.tool_status("组织页面与验证选项" if choice=="auto" else f"读取或比较证据：第{index}次调用",details={"turn_id":turn_id,"provider":"DeepSeek official API","strict":True})
                message,finish=api_call(p,index,{"messages":api_messages,"tools":definitions,"tool_choice":choice},self.service)
                self.tool_status("",message_id=call_ui,status="completed",details=read(p/f"call-{index:02d}.meta.json"))
                calls=message.get("tool_calls") or []
                if finish!="tool_calls" or not 1<=len(calls)<=3 or any(c["function"]["name"] not in {t["function"]["name"] for t in definitions} for c in calls):
                    report_error(p,index,ValueError("模型返回了未开放的调用或未按工具接口提交"),"tool_protocol")
                reports=[c for c in calls if c["function"]["name"]=="present_report"]
                if reports:
                    if len(calls)!=1 or set(evidence)-read_runs or (needs_comparison and not have_compare):raise ValueError("报告提交前需完成本轮证据读取与必要比较")
                    call=reports[0]
                    try:wire=json.loads(call["function"]["arguments"])
                    except json.JSONDecodeError as exc:report_error(p,index,exc,"json_syntax")
                    try:answer=validate_answer(project_compact(wire,investigation,text_index,narrative,3),request_hash,evidence,valid_runs,self.root,investigation)
                    except (ValueError,TypeError,KeyError) as exc:report_error(p,index,exc,"report_validation")
                    final_index=index;manifest.update(report_call_id=call["id"])
                    write_json(p/"wire_answer.json",wire)
                    write_json(p/"answer.json",answer);break
                if index==MAX_CALLS:raise ValueError("本轮工具调用已达预算；已有实验与证据已保存")
                api_messages.append({"role":"assistant","content":message.get("content"),"tool_calls":calls})
                for call in calls:
                    name=call["function"]["name"]
                    try:arguments=json.loads(call["function"]["arguments"])
                    except json.JSONDecodeError as exc:report_error(p,index,exc,"json_syntax")
                    try:
                        if not isinstance(arguments,dict) or set(arguments)!={"run_ids"}:raise ValueError("模型请求了未开放的参数")
                        selected=ids(arguments["run_ids"],evidence,2 if name=="compare_runs" else 1)
                    except (ValueError,TypeError,KeyError) as exc:report_error(p,index,exc,"report_validation")
                    tool_ui=self.tool_status("读取实验数值证据" if name=="read_evidence" else "比较事件对齐响应与施扰前趋势",details=arguments)
                    output={k:evidence[k] for k in selected} if name=="read_evidence" else compare(evidence,selected)
                    item={"call_id":call["id"],"name":name,"arguments":arguments,"output":output};tool_outputs.append(item)
                    write_json(p/"tool_calls.json",tool_outputs)
                    api_messages.append({"role":"tool","tool_call_id":call["id"],"content":json.dumps(output,ensure_ascii=False)})
                    self.tool_status("",message_id=tool_ui,status="completed",details={"run_ids":selected})
            if answer is None:raise ValueError("模型未在本轮预算内给出完整报告")
            assets=prepare_assets(p,answer,evidence,valid_runs,self.root)
            write_json(p/"render_assets.json",assets)
            body=render_answer(answer,evidence,assets,lambda name:"/files/"+(p/name).relative_to(self.root).as_posix())
            manifest.update(status="passed",final_call_index=final_index)
            record.update(status="passed",request_sha256=request_hash)
            self.add("assistant",answer=answer,html=body,turn_id=turn_id)
            with self.guard:
                self.state["active_turn"]=turn_id if answer.get("question") else None
                self.state["investigation_phase"]=answer["assessment"]["decision"]
        except Exception as exc:
            if narrative is not None:
                from .boost_agent_render import markdown
                self.add("draft",text=narrative,html=markdown(narrative),turn_id=turn_id)
            manifest["error"]={"type":type(exc).__name__,"message":str(exc)};record["status"]="error"
            for m in self.state["messages"]:
                if m["role"]=="tool" and m.get("status")=="running":m["status"]="error"
            raise
        finally:
            finalize(p,manifest)
            with self.guard:self.persist("agent_turn_finished",{"id":turn_id,"status":manifest["status"]})

    def export(self):
        from .boost_agent_render import export_session
        with self.guard:export_session(self.root,self.state)



def report_error(path,index,exc,category):
    value={"call_index":index,"category":category,"type":type(exc).__name__,"message":str(exc)}
    write_json(path/"format_error.json",value)
    if category=="json_syntax":
        message=f"JSON解析失败：模型工具参数不是合法JSON（第{exc.lineno}行，第{exc.colno}列）"
    else:
        label={"report_validation":"结构化参数校验失败","narrative_output":"正文生成未完成","tool_protocol":"工具调用协议错误"}[category]
        message=label+"："+str(exc)
    raise ValueError(message+"；原始响应与已有实验已保存，可重新分析已有证据。") from None


def verify_session(root,write=False):
    root=Path(root).resolve();problems=[];state=read(root/"session.json")
    if not ((state.get("kind")=="boost_agent_session" and state.get("schema_version")==1) or (state.get("kind")=="agent_session" and state.get("schema_version")==2 and state.get("case_id")=="boost_input_disturbance")):problems.append("unsupported session version")
    previous="0"*64;last=None
    for line in (root/"events.jsonl").read_text(encoding="utf-8").splitlines():
        row=json.loads(line);signature=row.pop("sha256")
        if row["previous_sha256"]!=previous or digest(row)!=signature:problems.append("event journal hash differs")
        previous=signature;last=row
    if last is None or last["state_sha256"]!=digest(state):problems.append("session state differs from journal")
    evidence={}
    def safe(rel):
        p=(root/rel).resolve()
        if not p.is_relative_to(root):raise ValueError("path leaves agent session")
        return p
    for rid,entry in state["runs"].items():
        try:
            p=safe(entry["path"])
            if sha256(p/"manifest.json")!=entry["manifest_sha256"] or verify_run(p,write=False)["record_status"]!="passed":problems.append("source record differs: "+rid)
            if entry["record_status"]=="passed":evidence[rid]=evidence_for(entry,root)
        except Exception as exc:problems.append("source verification failed: "+rid+" / "+type(exc).__name__)
    for turn in state["turns"]:
        try:
            p=safe(turn["path"]);m=read(p/"manifest.json")
            if m.get("kind")!="boost_agent_turn" or m.get("analysis_method_version")!=1:raise ValueError("unknown turn version")
            if state.get("kind")=="agent_session" and m.get("case_id")!=state["case_id"]:raise ValueError("turn case differs")
            for required in ("input.json","evidence.json"):
                if required not in m.get("artifacts",{}):problems.append("required turn artifact is not hashed: "+required)
            for rel,h in m["artifacts"].items():
                f=(p/rel).resolve()
                if not f.is_relative_to(p) or not f.is_file() or sha256(f)!=h:problems.append("turn artifact differs: "+turn["id"]+"/"+rel)
            ev={rid:evidence[rid] for rid in m["run_refs"]}
            if read(p/"evidence.json")!=ev or read(p/"input.json")["evidence_sha256"]!=digest(ev):problems.append("recomputed turn evidence differs: "+turn["id"])
            investigation=None
            if m.get("output_contract") in {"strict_tool_v3","strict_tool_v4","strict_tool_v5","strict_tool_v6"}:
                inp=read(p/"input.json");saved=inp["investigation_context"]
                investigation=context_for(ev,m["run_refs"],root,saved["goal"],saved["intent"])
                if "investigation_context.json" not in m["artifacts"] or saved!=investigation or read(p/"investigation_context.json")!=investigation or inp["investigation_sha256"]!=digest(investigation):
                    problems.append("recomputed investigation context differs: "+turn["id"])
            text_index=None;narrative=None
            if m.get("output_contract") in {"strict_tool_v4","strict_tool_v5","strict_tool_v6"} and "narrative_call_index" in m:
                if m.get("wire_protocol")!={"strict_tool_v4":"markdown_refs_v1","strict_tool_v5":"markdown_refs_v2","strict_tool_v6":"markdown_refs_v3"}[m["output_contract"]]:raise ValueError("unknown report protocol")
                ni=m["narrative_call_index"]
                for required in ("narrative.md","narrative_index.json",f"call-{ni:02d}.response.json"):
                    if required not in m["artifacts"]:raise ValueError("missing narrative artifact")
                narrative=(p/"narrative.md").read_text(encoding="utf-8")
                text_index=index_narrative(narrative)
                response=read(p/f"call-{ni:02d}.response.json")["choices"][0]
                request=read(p/f"call-{ni:02d}.request.json")
                if response["message"].get("content")!=narrative or response["finish_reason"]!="stop" or response["message"].get("tool_calls") or request.get("tool_choice")!="none" or request.get("tools"):
                    raise ValueError("narrative differs from actual API response or request stage")
                if read(p/"narrative_index.json")!=text_index:raise ValueError("narrative index differs")
            if m["status"]=="passed":
                for required in ("answer.json","render_assets.json",f"call-{m['final_call_index']:02d}.response.json"):
                    if required not in m.get("artifacts",{}):problems.append("required completed-turn artifact is not hashed: "+required)
                answer=validate_answer(read(p/"answer.json"),sha256(p/"input.json"),ev,m["run_refs"],root,investigation)
                raw=read(p/f"call-{m['final_call_index']:02d}.response.json")
                if m.get("output_contract") not in (None,"strict_tool_v1","strict_tool_v3","strict_tool_v4","strict_tool_v5","strict_tool_v6"):raise ValueError("unknown output contract")
                actual=response_answer(raw,m.get("report_call_id"))
                if m.get("output_contract")=="strict_tool_v3":
                    if m.get("wire_protocol")!="flat_report_v1" or "wire_answer.json" not in m["artifacts"] or actual!=read(p/"wire_answer.json"):raise ValueError("unknown or inconsistent report wire protocol")
                    actual=project_answer(actual,investigation)
                if m.get("output_contract") in {"strict_tool_v4","strict_tool_v5","strict_tool_v6"}:
                    if narrative is None or "wire_answer.json" not in m["artifacts"] or actual!=read(p/"wire_answer.json"):raise ValueError("inconsistent report controls")
                    actual=project_compact(actual,investigation,text_index,narrative,3 if m.get("output_contract")=="strict_tool_v6" else (2 if m.get("output_contract")=="strict_tool_v5" else 1))
                if actual!=answer:problems.append("answer differs from actual API response")
                if m.get("output_contract") in {"strict_tool_v1","strict_tool_v3","strict_tool_v4","strict_tool_v5","strict_tool_v6"}:
                    request=read(p/f"call-{m['final_call_index']:02d}.request.json")
                    definitions=strict_tools(sha256(p/"input.json"),ev,m["run_refs"],root,read(p/"input.json")["remaining_experiments"],investigation,text_index,3 if m.get("output_contract")=="strict_tool_v6" else (2 if m.get("output_contract")=="strict_tool_v5" else 1))
                    modern=m.get("output_contract") in {"strict_tool_v3","strict_tool_v4","strict_tool_v5","strict_tool_v6"}
                    expected=definitions if modern else [next(t for t in definitions if t["function"]["name"]=="present_report")]
                    valid_choice=request.get("tool_choice")=={"type":"function","function":{"name":"present_report"}} or (modern and request.get("tool_choice")=="auto")
                    if not valid_choice or request.get("tools")!=expected:
                        problems.append("report was not generated through strict tool schema")
                    if m.get("output_contract") in {"strict_tool_v4","strict_tool_v5","strict_tool_v6"}:
                        bindings=[]
                        for message in request["messages"]:
                            if message.get("role")=="user":
                                try:value=json.loads(message.get("content",""))
                                except (ValueError,TypeError):continue
                                if isinstance(value,dict) and value.get("stage")=="report_controls":bindings.append(value)
                        if len(bindings)!=1 or bindings[0].get("narrative_index")!=text_index or bindings[0].get("narrative_sha256")!=sha256(p/"narrative.md"):
                            problems.append("report controls were not bound to the narrative")
            if (p/"tool_calls.json").exists():
                received={}
                for response_file in p.glob("call-*.response.json"):
                    for call in read(response_file)["choices"][0]["message"].get("tool_calls",[]) or []:
                        received[call["id"]]=call["function"]
                for tool in read(p/"tool_calls.json"):
                    selected=ids(tool["arguments"]["run_ids"],ev,2 if tool["name"]=="compare_runs" else 1)
                    expected={rid:ev[rid] for rid in selected} if tool["name"]=="read_evidence" else compare(ev,selected)
                    function=received.get(tool["call_id"])
                    if not function or function["name"]!=tool["name"] or json.loads(function["arguments"])!=tool["arguments"] or expected!=tool["output"]:
                        problems.append("model tool call or recomputed output differs: "+turn["id"])
        except Exception as exc:problems.append("turn verification failed: "+turn["id"]+" / "+type(exc).__name__)
    for p in (root/"plans").glob("*/confirmation.json") if (root/"plans").exists() else []:
        try:
            plan=read(p.parent/"plan.json");conf=read(p);c=safe((p.parent/"config.json").relative_to(root))
            if conf["plan_sha256"]!=sha256(p.parent/"plan.json") or conf["config_sha256"]!=sha256(c):problems.append("confirmed plan hash differs")
            turn=next(x for x in state["turns"] if x["id"]==plan["turn_id"])
            answer_path=safe(turn["path"])/"answer.json"
            option=next(x for x in read(answer_path)["question"]["options"] if x["id"]==plan["option"]["id"])
            expected,_,_=build_config(option["arguments"],state["runs"],root)
            if option!=plan["option"] or sha256(answer_path)!=plan["answer_sha256"] or expected!=read(c):problems.append("approved option/config differs")
            execution=read(p.parent/"execution.json")
            if sha256(safe(execution["path"])/"config.json")!=conf["config_sha256"]:problems.append("executed config differs from approval")
        except Exception as exc:problems.append("confirmation verification failed: "+type(exc).__name__)
    result={"checked_at":now(),"status":"passed" if not problems else "failed","record_status":"passed" if not problems else "failed",
        "experiment_status":None,"problems":problems,"run_count":len(state["runs"]),"model_turn_count":len(state["turns"]),
        "run_dir":str(root),"scope":"原始记录、指标复算、请求/响应、模型页面结构、确认链和会话日志；不复跑模型，不验收自然语言因果正确性。"}
    if write:write_json(root/"verification.json",result)
    return result
