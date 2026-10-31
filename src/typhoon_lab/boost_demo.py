"""Loopback-only meeting demo; simulations use the existing guarded executor."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import mimetypes
import secrets
import threading
import urllib.parse

from .boost_ai import (ACTIONS, read, analyze_boost, create_plan, execute_plan, verify_ai, confirmation_from_plan)
from .config import load_config
from .records import verify_run
from .utils import PROJECT, new_run, runtime_lock, write_json, now

PAGE = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>Typhoon + AI 验证演示</title>
<style>body{font:18px/1.55 "Microsoft YaHei",sans-serif;max-width:1180px;margin:35px auto;color:#16323c;background:#f4f7f8;padding:0 25px}h1{font-size:36px;margin-bottom:6px}h2{font-size:25px}button,select{font:inherit;padding:10px 18px;margin:8px 10px 8px 0}button{background:#14627d;border:0;color:white;border-radius:4px;cursor:pointer}button:disabled{opacity:.4;cursor:wait}.phase{border-top:2px solid #b4c7ce;margin-top:25px;padding-top:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:white;padding:20px;font:16px/1.65 "Microsoft YaHei",sans-serif}a{color:#14627d}iframe{width:100%;height:760px;border:1px solid #b4c7ce;background:white}.status{font-size:20px;color:#91451e}small{font-size:15px}label{display:block}</style>
<h1>Typhoon + AI 验证演示</h1><p>Boost 闭环输入跌落 · Virtual HIL · 研究启动残余趋势对响应的影响</p>
<p>35→28 V，输出参考50 V，10 kHz；峰偏差≤10%，恢复≤0.5 s，最终误差≤2%</p>
<div class="phase"><h2>1　执行 Typhoon 实验并调用模型</h2><button id="start" onclick="act('start')">开始新实验与在线分析</button><span id="status" class="status">准备就绪</span>
<p><small>程序编译、运行并采集波形，复算指标后调用 DeepSeek 官方 API。结果写入新目录。</small></p></div>
<div class="phase"><h2>2　查看建议与配置差异</h2><select id="action"><option value="late">延后至1.0 s施扰</option><option value="repeat">重复原工况</option><option value="baseline">无扰动基准</option></select><button id="propose" onclick="act('plan',{action:document.querySelector('#action').value})">展示验证方案</button><pre id="plan">完成首次分析后显示建议及差异</pre>
<label>操作者：<input id="operator" value="现场操作人员"></label><label><input type="checkbox" id="approve">我已查看模型建议与配置差异，确认执行此方案</label><button id="confirm" onclick="act('confirm',{approved:document.querySelector('#approve').checked,operator:document.querySelector('#operator').value})">确认并运行对照实验</button></div>
<div class="phase"><h2>3　比较证据与更新解释</h2><div id="links"></div><iframe id="report" title="分析报告"></iframe></div>
<p><small>候选原因需要进一步证据；此演示为已有软件案例复现。网络异常时打开离线报告，不宣称本次API成功。</small></p>
<script>const csrf='__TOKEN__';let last='';async function act(name,data={}){if(name==='plan')document.querySelector('#approve').checked=false;let r=await fetch('/api/'+name,{method:'POST',headers:{'Content-Type':'application/json','X-Demo-Token':csrf},body:JSON.stringify(data)});let v=await r.json();if(!r.ok)alert(v.error);refresh()}
async function refresh(){let s=await (await fetch('/api/state')).json();document.querySelector('#status').textContent=s.message;document.querySelector('#start').disabled=s.busy;document.querySelector('#propose').disabled=s.busy||!s.first_ai;document.querySelector('#confirm').disabled=s.busy||!s.plan||!!s.control;document.querySelector('#plan').textContent=s.plan?JSON.stringify(s.plan,null,2):'完成首次分析后显示建议及差异';if(s.report&&s.report!==last){document.querySelector('#report').src=s.report;last=s.report}document.querySelector('#links').innerHTML=(s.report?'<p><a target="_blank" href="'+s.report+'">打开完整离线报告</a></p>':'')+(s.first_run?'<p>首次实验：'+s.first_run+'</p>':'')+(s.control?'<p>对照实验：'+s.control+'</p>':'')}setInterval(refresh,1500);refresh();</script></html>'''


class Demo:
    def __init__(self):
        self.root=new_run("meeting-demo")
        (self.root/"task.md").write_text(f"# 会议演示\n\n开始 {now()}；Boost Virtual HIL + DeepSeek；固定原判据，用户确认后对照。\n",encoding="utf-8")
        self.state={"busy":False,"message":"准备就绪","session_dir":str(self.root)}
        self.guard=threading.Lock()
        self.token=secrets.token_hex(24)
        self.service=PROJECT/"configs/ai_service_deepseek.json"

    def save(self):
        write_json(self.root/"demo_state.json",self.state)

    def url(self,path):
        return "/files/"+urllib.parse.quote(Path(path).resolve().relative_to(PROJECT/"results").as_posix())

    def launch(self,action,data):
        with self.guard:
            if self.state["busy"]: raise ValueError("已有任务在执行")
            if action=="plan":
                if not self.state.get("first_ai"): raise ValueError("先完成首次在线分析")
                if self.state.get("control"): raise ValueError("本次对照已完成，请开始新实验")
                plan_path=self.root/("plan-"+secrets.token_hex(3))
                plan=create_plan(self.state["first_ai"],data.get("action"),plan_path)
                self.state.update({"plan_dir":str(plan_path),"plan":plan,"message":"请查看差异并确认"});self.save();return
            if action=="confirm":
                if data.get("approved") is not True or not self.state.get("plan"): raise ValueError("请先查看方案并勾选确认")
                if self.state.get("control"): raise ValueError("此方案已执行")
                if not str(data.get("operator","")).strip(): raise ValueError("请填写操作者")
                self.state["operator"]=str(data["operator"])[:120]
            elif action!="start": raise ValueError("unknown operation")
            self.state["busy"]=True;self.state["message"]="正在执行 Typhoon / 模型分析，请等待";self.save()
            threading.Thread(target=self.work,args=(action,),daemon=True).start()

    def work(self,action):
        try:
            if action=="start":
                from .runtime import execute_case
                self.state={"busy":True,"message":"Typhoon 编译、运行、采集","session_dir":str(self.root)}
                with runtime_lock():
                    run=new_run("boost-demo-first");m=execute_case(run,load_config(PROJECT/"configs/boost_vin_drop.json"))
                v=verify_run(run)
                self.state["first_run"]=str(run);self.save()
                if m["status"]=="error" or v["record_status"]!="passed": raise ValueError("首次实验或记录异常，查看原始记录")
                out=self.root/("analysis-"+secrets.token_hex(3))
                self.state["message"]="波形已采集并复核；正在调用 DeepSeek";self.save()
                r=analyze_boost([run],out,self.service)
                self.state["report"]=self.url(out/"report.html")
                if r["explanation_status"]!="completed": raise ValueError("模型调用失败；查看 model_call.json 或使用离线备用")
                verify_ai(out,write=True)
                self.state.update({"first_ai":str(out),"message":"首次在线分析完成；请选择并展示验证方案"})
            else:
                plan=self.state["plan"]
                r=execute_plan(self.state["plan_dir"],plan["confirmation_token"],self.state["operator"])
                self.state["control"]=r["run_dir"];self.save()
                if r["record_status"]!="passed" or r["experiment_status"]=="error": raise ValueError("对照记录异常")
                self.state["message"]="对照已采集；正在比较并请求模型更新解释";self.save()
                out=self.root/("comparison-"+secrets.token_hex(3))
                result=analyze_boost([self.state["first_run"],r["run_dir"]],out,self.service,self.state["first_ai"],
                    confirmation_from_plan(self.state["plan_dir"]))
                self.state["report"]=self.url(out/"report.html")
                self.state["comparison"]=str(out);verify_ai(out,write=True)
                if result["explanation_status"]!="completed": raise ValueError("比较证据已保存；模型更新失败，使用离线备用")
                self.state["message"]="对照比较与在线更新解释完成；性能失败项保留"
        except Exception as exc:
            self.state["message"]="流程中止："+str(exc)
        finally:
            self.state["busy"]=False;self.save()


def serve(port=8765):
    demo=Demo()
    class Handler(BaseHTTPRequestHandler):
        def reply(self,code,data,mime="application/json; charset=utf-8"):
            raw=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False).encode("utf-8")
            self.send_response(code);self.send_header("Content-Type",mime);self.send_header("Content-Length",str(len(raw)));self.send_header("Cache-Control","no-store");self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            if self.path=="/": return self.reply(200,PAGE.replace("__TOKEN__",demo.token).encode("utf-8"),"text/html; charset=utf-8")
            if self.path=="/api/state": return self.reply(200,demo.state)
            if self.path.startswith("/files/"):
                target=(PROJECT/"results"/urllib.parse.unquote(self.path[7:])).resolve()
                if target.is_relative_to(PROJECT/"results") and target.is_file() and target.suffix in {".html",".png",".json",".md",".csv"}:
                    return self.reply(200,target.read_bytes(),mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            self.reply(404,{"error":"not found"})
        def do_POST(self):
            if self.headers.get("X-Demo-Token")!=demo.token: return self.reply(403,{"error":"invalid demo token"})
            length=int(self.headers.get("Content-Length","0"))
            if length>4096: return self.reply(413,{"error":"request too large"})
            try:
                data=json.loads(self.rfile.read(length).decode("utf-8"));demo.launch(self.path.removeprefix("/api/"),data)
                self.reply(200,{"accepted":True})
            except Exception as exc: self.reply(400,{"error":str(exc)})
        def log_message(self,*args): pass
    print(f"Demo URL: http://127.0.0.1:{port}\nSession: {demo.root}",flush=True)
    ThreadingHTTPServer(("127.0.0.1",port),Handler).serve_forever()
