"""Shared model transport with request/response provenance and redacted failures."""
import json
from pathlib import Path
import time
import urllib.request
import urllib.error
from .boost_ai import load_service, NoRedirect
from .utils import now, write_json, sha256

def api_call(turn_dir,index,payload,service_path):
    """Save the real request/response; never persist auth or exception bodies."""
    p=Path(turn_dir);stem=f"call-{index:02d}"
    meta={"started_at":now(),"status":"error"};timer=time.monotonic()
    try:
        service,key=load_service(service_path)
        meta.update({k:v for k,v in service.items() if k not in {"api_key_env","env_file"}})
        body={"model":service["model"],"max_tokens":service["max_tokens"],"stream":False,
              "temperature":service.get("temperature",0),**payload}
        if "thinking" in service:body["thinking"]=service["thinking"]
        write_json(p/(stem+".request.json"),body)
        meta["http_request_sha256"]=sha256(p/(stem+".request.json"))
        req=urllib.request.Request(service["base_url"].rstrip("/")+"/chat/completions",
            data=json.dumps(body,ensure_ascii=False,allow_nan=False).encode("utf-8"),
            headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"})
        with urllib.request.build_opener(NoRedirect()).open(req,timeout=service["timeout_s"]) as response:
            raw=response.read(4*1024*1024+1)
        if len(raw)>4*1024*1024:raise ValueError("模型响应超过大小限制")
        (p/(stem+".response.json")).write_bytes(raw)
        result=json.loads(raw.decode("utf-8"));choice=result["choices"][0]
        meta.update({"response_id":result.get("id"),"returned_model":result.get("model"),"usage":result.get("usage"),
                     "finish_reason":choice.get("finish_reason"),"status":"completed"})
        return choice["message"],choice["finish_reason"]
    except Exception as exc:
        meta["error"]={"type":type(exc).__name__,"http_status":getattr(exc,"code",None)}
        if isinstance(exc,urllib.error.HTTPError) and exc.code==400:
            try:
                error=json.loads(exc.read(8192).decode("utf-8")).get("error",{})
                meta["schema_error"]={k:str(error[k]).replace(key,"[redacted]")[:500] for k in ("type","code","param","message") if k in error}
            except (ValueError,UnicodeError,AttributeError,TypeError,KeyError):pass
        raise RuntimeError(f"模型服务调用失败（{type(exc).__name__}，HTTP {getattr(exc,'code','—')}）；请求和已有响应已留存") from None
    finally:
        meta["elapsed_s"]=time.monotonic()-timer;meta["completed_at"]=now()
        write_json(p/(stem+".meta.json"),meta)

