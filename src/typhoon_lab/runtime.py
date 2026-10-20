"""Execute supported models on Virtual HIL and preserve real data."""
from copy import deepcopy
from importlib.metadata import version
from pathlib import Path
import json
import math
import os
import shutil
import sys
import time
import traceback
import numpy as np
from .utils import PROJECT, RESULTS, now, sha256, write_json, note, finalize

def installation():
    value=os.environ.get("TYPHOON_LAB_INSTALL") or os.environ.get("TYPHOON_HOME")
    local=PROJECT/"environment.local.json"
    if not value and local.exists():
        value=json.loads(local.read_text(encoding="utf-8")).get("typhoon_home")
    return Path(value or Path(sys.executable).parent.parent).resolve()

def environment():
    home=installation()
    return {"recorded_at":now(),"python":sys.version,"python_executable":sys.executable,
            "typhoon_home":str(home),"thcc_version":(home/".version").read_text(encoding="utf-8").strip(),
            "typhoon_hil_api":version("typhoon-hil-api"),"typhoontest":version("typhoontest"),
            "numpy":version("numpy"),"matplotlib":version("matplotlib")}

def require(value,step):
    if value is not True:
        raise RuntimeError(f"Typhoon step failed: {step}; returned {value!r}")

def api_modules():
    from typhoon.api.schematic_editor import SchematicAPI
    import typhoon.api.hil as hil
    return SchematicAPI(),hil

def snapshot_code(run_dir):
    files=[PROJECT/"lab.ps1",PROJECT/"scripts"/"lab_cli.py"]
    files.extend(sorted((PROJECT/"src").rglob("*.py")))
    hashes={}
    for p in files:
        rel=p.relative_to(PROJECT)
        target=Path(run_dir)/"code_snapshot"/rel
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(p,target)
        hashes[rel.as_posix()]=sha256(p)
    return hashes

def wait_sim(hil,target,budget_s):
    deadline=time.monotonic()+budget_s
    while True:
        elapsed=hil.get_sim_time()
        if elapsed is None or not math.isfinite(elapsed):
            raise RuntimeError("simulation time is unavailable")
        if elapsed>=target: return float(elapsed)
        if time.monotonic()>=deadline:
            raise TimeoutError(f"simulation did not reach {target:g}s within {budget_s:g} wall seconds")
        if hil.is_simulation_running() is not True:
            raise RuntimeError("simulation stopped before the required simulated time")
        time.sleep(.05)

def component_values(api):
    from .adapters import get_adapter
    return get_adapter("rlc_filter").inspect_parameters(api)


def inspect_model(model_id="rlc_filter"):
    from .adapters import get_adapter
    adapter=get_adapter(model_id)
    api,_=api_modules()
    path=PROJECT/"models"/f"{model_id}.tse"
    require(api.load(filename=str(path)),"load model for inspection")
    result={"model":model_id,"source_model":str(path),"source_sha256":sha256(path),
            "circuit":adapter.inspect_parameters(api),
            "model_settings":{k:api.get_model_property_value(k) for k in
                              ["hil_device","hil_configuration_id","simulation_time_step"]},
            "components":[api.get_name(x) for x in api.get_items()],
            "capture_signals":list(adapter.signals),"units":adapter.units,"per_run_changes":adapter.changes,
            "scope":"schematic inspection; compilation and simulation are separate checks"}
    write_json(RESULTS/("inspection.json" if model_id=="rlc_filter" else f"inspection_{model_id}.json"),result)
    return result


def source_copy(run_dir,smoke=False,model_id="rlc_filter"):
    key="loopback" if smoke else model_id
    source=PROJECT/"models"/f"{key}.tse"
    origin=json.loads((PROJECT/"models"/"origin.json").read_text(encoding="utf-8"))[key]
    if sha256(source)!=origin["sha256"]:
        raise ValueError(f"teaching template {source.name} differs from recorded origin")
    destination=Path(run_dir)/"model.tse"
    shutil.copy2(source,destination)
    if "panel" in origin:
        panel=PROJECT/"models"/f"{key}.cus"
        if sha256(panel)!=origin["panel"]["sha256"]:
            raise ValueError("teaching panel differs from recorded origin")
        shutil.copy2(panel,Path(run_dir)/"official_panel.cus")
    return destination,origin


def no_active_simulation(hil):
    """Query running state only when the API session has a loaded model."""
    model_path = hil.get_model_file_path()
    if model_path is None:
        return
    if not isinstance(model_path, str) or not model_path:
        raise RuntimeError("cannot determine the API session loaded model")
    if hil.is_simulation_running() is True:
        raise RuntimeError("the API session already has a running simulation; stop it before a teaching run")

def cleanup(hil,started,capturing,run_dir):
    problems=[]
    if capturing:
        try:
            if hil.stop_capture() is False: problems.append("stop_capture returned False")
        except Exception as exc: problems.append(f"stop_capture: {exc}")
    if started:
        try: require(hil.stop_simulation(),"stop simulation")
        except Exception as exc: problems.append(f"stop_simulation: {exc}")
    if problems: note(run_dir,"Cleanup issues: "+"; ".join(problems))
    return problems

def execute_smoke(run_dir):
    manifest={"schema_version":1,"kind":"smoke","backend":"virtual_hil","started_at":now(),"status":"error"}
    api=hil=None;started=False
    try:
        api,hil=api_modules()
        manifest["environment"]=environment()
        manifest["code_sha256"]=snapshot_code(run_dir)
        no_active_simulation(hil)
        model_path,origin=source_copy(run_dir,smoke=True)
        manifest["model_origin"]=origin
        require(api.load(filename=str(model_path)),"load loopback model")
        require(api.compile(),"compile loopback model")
        cpd=api.get_compiled_model_file(str(model_path))
        require(hil.load_model(file=cpd,vhil_device=True),"load Virtual HIL")
        require(hil.start_simulation(),"start loopback")
        started=True
        readings=[]
        for set_point in [-10,0,10]:
            require(hil.set_scada_input_value(scadaInputName="Input",value=set_point),"set loopback input")
            wait_sim(hil,float(hil.get_sim_time())+.001,60)
            actual=float(hil.read_analog_signal(name="Probe1"))
            passed=math.isclose(actual,set_point,rel_tol=0,abs_tol=1e-6)
            readings.append({"input":set_point,"measured":actual,"passed":passed})
            note(run_dir,f"Loopback Input={set_point}, Probe1={actual}, passed={passed}")
        write_json(Path(run_dir)/"readings.json",readings)
        manifest["checks"]=readings
        manifest["status"]="passed" if all(x["passed"] for x in readings) else "failed"
    except Exception as exc:
        manifest["error"]=f"{type(exc).__name__}: {exc}"
        note(run_dir,traceback.format_exc())
    finally:
        manifest["cleanup_issues"]=cleanup(hil,started,False,run_dir) if hil is not None else []
        if manifest["cleanup_issues"]: manifest["status"]="error"
    note(run_dir,f"Smoke completed: {manifest['status']}")
    finalize(run_dir,manifest)
    return manifest

def execute_case(run_dir,config):
    from .adapters import get_adapter, records_events
    adapter=get_adapter(config["model"])
    manifest={"schema_version":adapter.schema_version,"kind":"run","model":adapter.model_id,"backend":"virtual_hil",
              "started_at":now(),"status":"error"}
    api=hil=None;write_report=None;started=capturing=False
    try:
        write_json(Path(run_dir)/"config.json",config)
        if records_events(adapter,config):
            write_json(Path(run_dir)/"events.json",{"schema_version":2,"planned":config["events"],"events":[]})
        from .analysis import analyze
        from .reporting import write_report
        api,hil=api_modules()
        manifest["environment"]=environment()
        manifest["code_sha256"]=snapshot_code(run_dir)
        no_active_simulation(hil)
        model_path,origin=source_copy(run_dir,model_id=adapter.model_id)
        manifest["model_origin"]=origin
        require(api.load(filename=str(model_path)),"load teaching model")
        manifest["actual_model_parameters"]=adapter.prepare(api,config)
        if adapter.changes: manifest["model_changes"]=adapter.changes
        require(api.save_as(filename=str(model_path)),"save case model")
        note(run_dir,"Compiling case model")
        require(api.compile(),"compile case model")
        manifest["compilation_messages"]=str(api.last_compilation_messages())
        cpd=api.get_compiled_model_file(str(model_path))
        manifest["compiled_model"]=str(Path(cpd).relative_to(run_dir))
        require(hil.load_model(file=cpd,vhil_device=True),"load Virtual HIL")
        sources=[x for device in hil.get_sources() for x in device]
        signals=[x for device in hil.get_analog_signals() for x in device]
        manifest["discovered_sources"]=sources;manifest["discovered_signals"]=signals
        if any(x not in sources for x in adapter.sources) or any(x not in signals for x in adapter.signals):
            raise ValueError("compiled model is missing required sources or capture signals")
        manifest.update(adapter.initialize(hil,config))
        manifest["event_schedule"]=adapter.schedule(hil,config)
        dt=float(hil.get_sim_step());c=config["capture"]
        decimation=max(1,round(1/(c["sample_rate_hz"]*dt)))
        rate=1/(dt*decimation);n=int(round(c["duration_s"]*rate/2))*2
        if not 256<=n<=100000:
            raise ValueError("actual sample count falls outside validated teaching limits")
        adapter.check_sampling(rate,n,config)
        buffer=[]
        def arm_capture():
            require(hil.start_capture([decimation,len(adapter.signals),n,False],["Forced"],[list(adapter.signals),[]],
                                     dataBuffer=buffer,timeFormat="absolute"),"start waveform capture")
        if adapter.capture_before_start:
            arm_capture();capturing=True
        require(hil.start_simulation(),"start teaching simulation");started=True
        if not adapter.capture_before_start:
            manifest["settled_at_simulation_s"]=wait_sim(hil,c["settle_s"],c["wall_timeout_s"])
            arm_capture();capturing=True
        deadline=time.monotonic()+c["wall_timeout_s"]
        while hil.capture_in_progress():
            if time.monotonic()>deadline: raise TimeoutError("capture exceeded its wall-clock budget")
            if hil.is_simulation_running() is not True: raise RuntimeError("simulation stopped during capture")
            time.sleep(.05)
        capturing=False
        if hil.timeout_occurred() or not buffer:
            raise RuntimeError("waveform capture finished without complete data")
        names,values,times=buffer[0]
        y=np.asarray(values,dtype=float);rel=np.asarray(times["x_data"],dtype=float)
        if list(names)!=list(adapter.signals) or y.shape!=(len(adapter.signals),n) or rel.shape!=(n,):
            raise ValueError("capture returned unexpected signal order or shape")
        trigger=times["trigger_timestamp_sim_time"]
        if trigger is None: raise ValueError("capture did not return a simulation trigger time")
        sim=rel+float(trigger)*1e-9
        np.savetxt(Path(run_dir)/"waveforms.csv",np.column_stack([rel,sim,y.T]),delimiter=",",
                   header=",".join(("t_relative_s","t_simulation_s",*adapter.columns)),comments="",fmt="%.17g")
        info={"signal_names":list(names),"units":adapter.units,"simulation_step_s":dt,
              "decimation":decimation,"sample_rate_hz":rate,"number_of_samples":n,"sample_window_s":n/rate,
              "trigger_timestamp_sim_time_ns":trigger,
              "trigger_timestamp_utc_time_ns":times.get("trigger_timestamp_utc_time"),
              "capture_wall_recorded_at":now(),
              "utc_trigger_note":"Virtual HIL may return null; no UTC trigger time is inferred"}
        write_json(Path(run_dir)/"capture.json",info);manifest["capture"]=info
        require(hil.stop_simulation(),"stop captured simulation");started=False
        note(run_dir,f"Captured {n} samples at {rate:g} samples/s")
        metrics=analyze(Path(run_dir)/"waveforms.csv",config)
        if records_events(adapter,config):
            manifest["events"]=metrics["events"]
            write_json(Path(run_dir)/"events.json",{"schema_version":2,"planned":config["events"],"events":metrics["events"]})
        write_json(Path(run_dir)/"metrics.json",metrics);manifest["status"]=metrics["status"]
    except Exception as exc:
        manifest["error"]=f"{type(exc).__name__}: {exc}";note(run_dir,traceback.format_exc())
    finally:
        manifest["cleanup_issues"]=cleanup(hil,started,capturing,run_dir) if hil is not None else []
        if manifest["cleanup_issues"]: manifest["status"]="error"
    try:
        if write_report is None:
            (Path(run_dir)/"report.md").write_text("# 实验执行异常\n\n"+manifest.get("error","报告模块不可用")+"\n",encoding="utf-8")
        else:
            write_report(Path(run_dir),manifest)
    except Exception as exc:
        manifest["report_error"]=f"{type(exc).__name__}: {exc}"
        manifest["status"]="error";note(run_dir,traceback.format_exc())
    note(run_dir,f"Case completed: {manifest['status']}")
    finalize(run_dir,manifest)
    return manifest


def execute_sweep(path,config):
    """Execute one validated RLC sweep; the caller owns the runtime lock."""
    from .runtime import execute_case,environment,snapshot_code
    from .reporting import write_sweep_report
    manifest={"schema_version":1,"kind":"sweep","model":"rlc_filter","backend":"virtual_hil",
              "started_at":now(),"environment":environment(),"code_sha256":snapshot_code(path),
              "cases":[],"status":"error"}
    write_json(path/"config.json",config)
    for index,value in enumerate(config["sweep"]["values"]):
        case_id=f"case_{index+1:02d}_rin_{value:g}"
        case_path=path/"cases"/case_id;case_path.mkdir(parents=True)
        case_config=deepcopy(config);del case_config["sweep"]
        case_config["circuit"]["rin_ohm"]=value
        note(path,f"Running {case_id}")
        case=execute_case(case_path,case_config)
        manifest["cases"].append({"case_id":case_id,"relative_dir":case_path.relative_to(path).as_posix(),
                                  "status":case["status"],"rin_ohm":value})
    states=[x["status"] for x in manifest["cases"]]
    manifest["status"]="passed" if states and all(x=="passed" for x in states) else ("error" if "error" in states else "failed")
    try: write_sweep_report(path,manifest)
    except Exception as exc:
        manifest["report_error"]=str(exc);manifest["status"]="error";note(path,traceback.format_exc())
    note(path,f"Sweep completed: {manifest['status']}")
    finalize(path,manifest)
    return manifest
