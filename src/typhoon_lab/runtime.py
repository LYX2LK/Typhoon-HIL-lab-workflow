"""Execute supported models on Virtual HIL and preserve real data."""
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
    output={}
    for key,item_name,prop_name in [
        ("rin_ohm","Rin","resistance"),("branch_r_ohm","R","resistance"),
        ("l_h","L","inductance"),("c_f","C","capacitance")
    ]:
        item=api.get_item(item_name)
        if item is None: raise ValueError(f"model is missing required component {item_name}")
        output[key]=float(api.get_property_value(api.prop(item,prop_name)))
    return output

def inspect_model():
    api,_=api_modules()
    path=PROJECT/"models"/"rlc_filter.tse"
    require(api.load(filename=str(path)),"load model for inspection")
    result={"model":"rlc_filter","source_model":str(path),"source_sha256":sha256(path),
            "circuit":component_values(api),
            "model_settings":{k:api.get_model_property_value(k) for k in
                              ["hil_device","hil_configuration_id","simulation_time_step"]},
            "components":[api.get_name(x) for x in api.get_items()],
            "scope":"schematic inspection; compilation and simulation are separate checks"}
    write_json(RESULTS/"inspection.json",result)
    return result

def source_copy(run_dir,smoke=False):
    key="loopback" if smoke else "rlc_filter"
    source=PROJECT/"models"/f"{key}.tse"
    origin=json.loads((PROJECT/"models"/"origin.json").read_text(encoding="utf-8"))[key]
    if sha256(source)!=origin["sha256"]:
        raise ValueError(f"teaching template {source.name} differs from recorded origin")
    destination=Path(run_dir)/"model.tse"
    shutil.copy2(source,destination)
    return destination,origin

def no_active_simulation(hil):
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
    manifest={"schema_version":1,"kind":"run","model":"rlc_filter","backend":"virtual_hil",
              "started_at":now(),"status":"error"}
    api=hil=None;write_report=None;started=capturing=False
    try:
        write_json(Path(run_dir)/"config.json",config)
        from .analysis import analyze
        from .reporting import write_report
        api,hil=api_modules()
        manifest["environment"]=environment()
        manifest["code_sha256"]=snapshot_code(run_dir)
        no_active_simulation(hil)
        model_path,origin=source_copy(run_dir)
        manifest["model_origin"]=origin
        require(api.load(filename=str(model_path)),"load RLC model")
        for key,item_name,prop_name in [
            ("rin_ohm","Rin","resistance"),("branch_r_ohm","R","resistance"),
            ("l_h","L","inductance"),("c_f","C","capacitance")
        ]:
            item=api.get_item(item_name)
            if item is None: raise ValueError(f"required component {item_name} was not found")
            api.set_property_value(api.prop(item,prop_name),str(config["circuit"][key]))
        actual=component_values(api)
        for key,value in actual.items():
            if not math.isclose(value,config["circuit"][key],rel_tol=1e-12):
                raise ValueError(f"model read-back mismatch for {key}")
        manifest["actual_model_parameters"]=actual
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
        if "Vs1" not in sources or any(x not in signals for x in ["I","Va1"]):
            raise ValueError("compiled model is missing the teaching source or capture signals")
        s=config["source"]
        require(hil.set_source_sine_waveform("Vs1",rms=s["rms_v"],frequency=s["frequency_hz"],
                                           phase=s["phase_deg"],harmonics_pu=()),"set sine source")
        settings=hil.get_source_settings("Vs1");manifest["actual_source_settings"]=settings
        for key,expected in [("rms",s["rms_v"]),("frequency",s["frequency_hz"]),("phase",s["phase_deg"])]:
            if settings is None or not math.isclose(float(settings[key]),expected,rel_tol=1e-10,abs_tol=1e-10):
                raise ValueError(f"source read-back mismatch for {key}")
        dt=float(hil.get_sim_step());c=config["capture"]
        decimation=max(1,round(1/(c["sample_rate_hz"]*dt)))
        rate=1/(dt*decimation);n=int(round(c["duration_s"]*rate/2))*2
        if not 256<=n<=100000 or rate<20*s["frequency_hz"]:
            raise ValueError("actual capture sampling falls outside validated teaching limits")
        if not math.isclose(n/rate*s["frequency_hz"],round(n/rate*s["frequency_hz"]),abs_tol=1e-5):
            raise ValueError("quantized sampling would not capture complete source cycles")
        require(hil.start_simulation(),"start RLC simulation");started=True
        manifest["settled_at_simulation_s"]=wait_sim(hil,c["settle_s"],c["wall_timeout_s"])
        buffer=[]
        require(hil.start_capture([decimation,2,n,False],["Forced"],[["I","Va1"],[]],
                                 dataBuffer=buffer,timeFormat="absolute"),"start waveform capture")
        capturing=True;deadline=time.monotonic()+c["wall_timeout_s"]
        while hil.capture_in_progress():
            if time.monotonic()>deadline: raise TimeoutError("capture exceeded its wall-clock budget")
            time.sleep(.05)
        capturing=False
        if hil.timeout_occurred() or not buffer:
            raise RuntimeError("waveform capture finished without complete data")
        names,values,times=buffer[0]
        y=np.asarray(values,dtype=float);rel=np.asarray(times["x_data"],dtype=float)
        if list(names)!=["I","Va1"] or y.shape!=(2,n) or rel.shape!=(n,):
            raise ValueError("capture returned unexpected signal order or shape")
        trigger=times["trigger_timestamp_sim_time"]
        if trigger is None: raise ValueError("capture did not return a simulation trigger time")
        sim=rel+float(trigger)*1e-9
        np.savetxt(Path(run_dir)/"waveforms.csv",np.column_stack([rel,sim,y.T]),delimiter=",",
                   header="t_relative_s,t_simulation_s,I_A,Va1_V",comments="",fmt="%.17g")
        info={"signal_names":list(names),"units":{"I_A":"A","Va1_V":"V"},"simulation_step_s":dt,
              "decimation":decimation,"sample_rate_hz":rate,"number_of_samples":n,"sample_window_s":n/rate,
              "trigger_timestamp_sim_time_ns":trigger,
              "trigger_timestamp_utc_time_ns":times.get("trigger_timestamp_utc_time"),
              "capture_wall_recorded_at":now(),
              "utc_trigger_note":"Virtual HIL may return null; no UTC trigger time is inferred"}
        write_json(Path(run_dir)/"capture.json",info);manifest["capture"]=info
        note(run_dir,f"Captured {n} samples at {rate:g} samples/s")
        metrics=analyze(Path(run_dir)/"waveforms.csv",config)
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
