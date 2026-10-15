"""Bounded command interface for people and coding agents."""
from copy import deepcopy
from pathlib import Path
import argparse
import json
import math
import sys
import traceback
import shutil
import uuid
from .config import load_config
from .utils import PROJECT,RESULTS,new_run,runtime_lock,write_json,sha256,now,note,finalize

def resolve_project_file(value):
    p=Path(value)
    return p.resolve() if p.is_absolute() else (PROJECT/p).resolve()

def verify_run(run_dir,write=True):
    from .analysis import analyze
    run_dir=Path(run_dir).resolve()
    manifest=json.loads((run_dir/"manifest.json").read_text(encoding="utf-8"))
    problems=[]
    for rel,expected in manifest.get("artifacts",{}).items():
        p=(run_dir/rel).resolve()
        if not p.is_relative_to(run_dir) or not p.is_file(): problems.append(f"missing or invalid artifact: {rel}")
        elif sha256(p)!=expected: problems.append(f"artifact changed: {rel}")
    if not manifest.get("artifacts"): problems.append("manifest has no artifact hashes")
    for rel,expected in manifest.get("code_sha256",{}).items():
        snapshot=(run_dir/"code_snapshot"/rel).resolve()
        if not snapshot.is_relative_to(run_dir) or not snapshot.is_file() or sha256(snapshot)!=expected:
            problems.append(f"code snapshot differs from recorded version: {rel}")
    if manifest.get("kind")=="run" and (run_dir/"metrics.json").exists():
        try:
            config=load_config(run_dir/"config.json")
            actual=analyze(run_dir/"waveforms.csv",config)
            stored=json.loads((run_dir/"metrics.json").read_text(encoding="utf-8"))
            for key in ["status","signals","capture","checks"]:
                if actual.get(key)!=stored.get(key): problems.append(f"recomputed metrics differ: {key}")
            if manifest["status"]!=stored["status"]: problems.append("manifest status differs from metrics")
        except Exception as exc: problems.append(f"metric recomputation error: {exc}")
    elif manifest.get("kind")=="smoke" and (run_dir/"readings.json").exists():
        readings=json.loads((run_dir/"readings.json").read_text(encoding="utf-8"))
        passed=all(math.isclose(x["input"],x["measured"],rel_tol=0,abs_tol=1e-6) for x in readings)
        if (manifest["status"]=="passed")!=passed: problems.append("loopback readings do not support the recorded status")
    elif manifest.get("kind")=="sweep":
        for case in manifest.get("cases",[]):
            path=(run_dir/case["relative_dir"]).resolve()
            if not path.is_relative_to(run_dir): problems.append("case path leaves sweep directory");continue
            result=verify_run(path,write=False)
            problems.extend(f"{case['case_id']}: {e}" for e in result["problems"])
    if manifest.get("status")!="passed": problems.append(f"experiment status is {manifest.get('status')}")
    result={"checked_at":now(),"status":"passed" if not problems else "failed","problems":problems,
            "artifact_count":len(manifest.get("artifacts",{})),
            "scope":"artifact hashes and metric recomputation; not an independent hardware validation"}
    if write: write_json(run_dir/"verification.json",result)
    return result

def main(argv=None):
    parser=argparse.ArgumentParser(description="Typhoon Virtual HIL teaching workflow")
    sub=parser.add_subparsers(dest="command",required=True)
    for name in ["doctor","inspect","smoke"]: sub.add_parser(name)
    for name,default in [("run","configs/rlc_baseline.json"),("sweep","configs/rlc_sweep.json")]:
        p=sub.add_parser(name);p.add_argument("--config",default=default)
    for name in ["report","verify"]:
        p=sub.add_parser(name);p.add_argument("--run-dir",required=True)
    args=parser.parse_args(argv)
    path=None;manifest=None
    try:
        if args.command=="doctor":
            from .runtime import environment,api_modules
            from .analysis import analyze
            from .reporting import write_report,write_sweep_report
            info=environment();api_modules()
            info.update({"status":"passed","scope":"Python/API imports and installed versions",
                         "workflow_modules_imported":True,"simulation_verified":False,"next_command":".\\lab.ps1 smoke"})
            write_json(RESULTS/"environment.json",info)
            print(json.dumps(info,ensure_ascii=False,indent=2));return 0
        if args.command=="inspect":
            from .runtime import inspect_model
            with runtime_lock(): info=inspect_model()
            print(json.dumps(info,ensure_ascii=False,indent=2));return 0
        if args.command=="verify":
            result=verify_run(resolve_project_file(args.run_dir))
            print(json.dumps(result,ensure_ascii=False,indent=2))
            return 0 if result["status"]=="passed" else 1
        if args.command=="report":
            from .reporting import write_report,write_sweep_report
            path=resolve_project_file(args.run_dir)
            manifest=json.loads((path/"manifest.json").read_text(encoding="utf-8"))
            report_names={"report.html","report.md","waveforms.png","comparison.csv","comparison.png"}
            for rel,expected in manifest.get("artifacts",{}).items():
                if rel in report_names: continue
                artifact=(path/rel).resolve()
                if not artifact.is_relative_to(path) or not artifact.is_file() or sha256(artifact)!=expected:
                    raise ValueError(f"report input changed or missing: {rel}")
            if manifest["kind"]=="sweep": outputs=write_sweep_report(path,manifest)
            elif manifest["kind"]=="run": outputs=write_report(path,manifest)
            else: raise ValueError("report applies to run or sweep results")
            for output in outputs:
                output=Path(output).resolve()
                if not output.is_relative_to(path): raise ValueError("report output leaves run directory")
                manifest["artifacts"][output.relative_to(path).as_posix()]=sha256(output)
            report_revision=uuid.uuid4().hex[:8]
            report_hashes={}
            for source in [PROJECT/"src"/"typhoon_lab"/"reporting.py",PROJECT/"src"/"typhoon_lab"/"analysis.py",PROJECT/"src"/"typhoon_lab"/"cli.py"]:
                target=path/"report_code_snapshot"/report_revision/source.name
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
                relative=target.relative_to(path).as_posix()
                manifest["artifacts"][relative]=sha256(target);report_hashes[source.name]=sha256(target)
            manifest["report_generator_sha256"]=report_hashes
            manifest["report_regenerated_at"]=now()
            write_json(path/"manifest.json",manifest)
            print(json.dumps({"status":"generated","files":[str(p) for p in outputs]},ensure_ascii=False,indent=2))
            return 0
        if args.command=="smoke":
            from .runtime import execute_smoke
            path=new_run("smoke")
            with runtime_lock(): manifest=execute_smoke(path)
        elif args.command=="run":
            config=load_config(resolve_project_file(args.config))
            from .runtime import execute_case
            path=new_run("rlc")
            with runtime_lock(): manifest=execute_case(path,config)
        elif args.command=="sweep":
            config=load_config(resolve_project_file(args.config),sweep=True)
            from .runtime import execute_case,environment,snapshot_code
            from .reporting import write_sweep_report
            path=new_run("sweep")
            manifest={"schema_version":1,"kind":"sweep","model":"rlc_filter","backend":"virtual_hil",
                      "started_at":now(),"environment":environment(),"code_sha256":snapshot_code(path),
                      "cases":[],"status":"error"}
            write_json(path/"config.json",config)
            with runtime_lock():
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
        print(json.dumps({"status":manifest["status"],"run_dir":str(path)},ensure_ascii=False))
        return 0 if manifest["status"]=="passed" else 1
    except Exception as exc:
        if path is not None and Path(path).is_dir() and args.command in {"smoke","run","sweep"}:
            try:
                manifest=manifest or {"schema_version":1,"kind":args.command,"backend":"virtual_hil","started_at":now()}
                manifest["status"]="error";manifest["error"]=f"{type(exc).__name__}: {exc}"
                note(path,traceback.format_exc());finalize(path,manifest)
                print(json.dumps({"status":"error","run_dir":str(path)},ensure_ascii=False))
            except Exception as record_error:
                print(f"Error record unavailable: {record_error}",file=sys.stderr)
        print(f"ERROR: {type(exc).__name__}: {exc}",file=sys.stderr);return 2
