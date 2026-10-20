"""Bounded command interface for people and coding agents."""
from contextvars import ContextVar
from pathlib import Path
import argparse
import json
from .records import verify_run
import sys
import traceback
import shutil
import uuid
from .config import load_config
from .utils import PROJECT,RESULTS,new_run,runtime_lock,write_json,sha256,now,note,finalize

_RESULT = ContextVar('command_result', default=None)
_ERROR = ContextVar('command_error', default=None)


def _publish(value, indent=None):
    sink = _RESULT.get()
    if sink is None:
        print(json.dumps(value, ensure_ascii=False, indent=indent))
    else:
        sink.append(value)

def resolve_project_file(value):
    p=Path(value)
    return p.resolve() if p.is_absolute() else (PROJECT/p).resolve()

def _run(argv=None):
    parser=argparse.ArgumentParser(description="Typhoon Virtual HIL teaching workflow")
    sub=parser.add_subparsers(dest="command",required=True)
    for name in ["doctor","smoke","prepare-models"]: sub.add_parser(name)
    from .adapters import supported_models
    p=sub.add_parser("inspect");p.add_argument("--model",choices=supported_models(),default="rlc_filter")
    sub.add_parser("list-cases")
    p=sub.add_parser("validate-case");p.add_argument("--case",required=True)
    p=sub.add_parser("run-case");p.add_argument("--case",required=True)
    p=sub.add_parser("practice-model");p.add_argument("--model-file",required=True)
    for name,default in [("run","configs/rlc_baseline.json"),("sweep","configs/rlc_sweep.json")]:
        p=sub.add_parser(name);p.add_argument("--config",default=default)
    for name in ["report","verify"]:
        p=sub.add_parser(name);p.add_argument("--run-dir",required=True)
    p=sub.add_parser("compare-rectifier")
    for condition in ("baseline","low-input","heavy-load"):
        p.add_argument("--"+condition,required=True)
    args=parser.parse_args(argv)
    path=None;manifest=None
    try:
        if args.command == "prepare-models":
            from .model_assets import prepare_models
            result = prepare_models()
            _publish(result, indent=2)
            return 0 if result["status"] == "passed" else 1
        if args.command in {"list-cases", "validate-case"}:
            from .cases import list_cases, validate_case
            result = list_cases() if args.command == "list-cases" else validate_case(args.case)
            _publish(result, indent=2)
            return 0 if result["status"] == "passed" else 1
        if args.command=="run-case":
            from .case_runner import run_case
            result=run_case(args.case)
            if result.get("error"): _ERROR.set(result["error"])
            _publish(result,indent=2)
            return 0 if result["status"]=="passed" else 1
        if args.command=="practice-model":
            from .model_practice import run_practice

            path, result = run_practice(args.model_file)
            _publish({"status": result["status"], "run_dir": str(path),
                      "source_model": result["source_model"],
                      "error": result.get("error")}, indent=2)
            return 0 if result["status"] == "passed" else 1
        if args.command=="compare-rectifier":
            from .rectifier_comparison import compare_rectifier
            path,result=compare_rectifier(resolve_project_file(args.baseline),resolve_project_file(args.low_input),resolve_project_file(args.heavy_load))
            _publish({"status":result["status"],"run_dir":str(path)})
            return 0 if result["status"]=="passed" else 1
        if args.command=="doctor":
            from .runtime import environment,api_modules
            from .analysis import analyze
            from .reporting import write_report,write_sweep_report
            info=environment();api_modules()
            info.update({"status":"passed","scope":"Python/API imports and installed versions",
                         "workflow_modules_imported":True,"simulation_verified":False,"next_command":".\\lab.ps1 smoke"})
            write_json(RESULTS/"environment.json",info)
            _publish(info,indent=2);return 0
        if args.command=="inspect":
            from .runtime import inspect_model
            with runtime_lock(): info=inspect_model(args.model)
            _publish(info,indent=2);return 0
        if args.command=="verify":
            result=verify_run(resolve_project_file(args.run_dir))
            _publish(result,indent=2)
            return 0 if result["status"]=="passed" else 1
        if args.command=="report":
            from .reporting import write_report,write_sweep_report
            path=resolve_project_file(args.run_dir)
            manifest=json.loads((path/"manifest.json").read_text(encoding="utf-8"))
            report_names={"report.html","report.md","waveforms.png","response_detail.png","comparison.csv","comparison.png"}
            for rel,expected in manifest.get("artifacts",{}).items():
                if rel in report_names: continue
                artifact=(path/rel).resolve()
                if not artifact.is_relative_to(path) or not artifact.is_file() or sha256(artifact)!=expected:
                    raise ValueError(f"report input changed or missing: {rel}")
            if manifest["kind"]=="sweep": outputs=write_sweep_report(path,manifest)
            elif manifest["kind"]=="run": outputs=write_report(path,manifest)
            elif manifest["kind"]=="comparison" and manifest.get("model")=="single_phase_rectifier":
                from .rectifier_comparison import write_comparison_report
                outputs=write_comparison_report(path,manifest)
            elif manifest["kind"]=="case":
                from .case_runner import write_case_report
                outputs=write_case_report(path,manifest)
            elif manifest["kind"]=="modeling_practice":
                from .model_practice import write_practice_report
                outputs=write_practice_report(path,manifest)
            else: raise ValueError("report applies to run, sweep or case results")
            for output in outputs:
                output=Path(output).resolve()
                if not output.is_relative_to(path): raise ValueError("report output leaves run directory")
                manifest["artifacts"][output.relative_to(path).as_posix()]=sha256(output)
            report_revision=uuid.uuid4().hex[:8]
            report_hashes={}
            for source in sorted((PROJECT/"src").rglob("*.py")):
                source_relative=source.relative_to(PROJECT/"src")
                target=path/"report_code_snapshot"/report_revision/source_relative
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
                relative=target.relative_to(path).as_posix()
                manifest["artifacts"][relative]=sha256(target);report_hashes[source_relative.as_posix()]=sha256(target)
            manifest["report_generator_sha256"]=report_hashes
            manifest["report_regenerated_at"]=now()
            write_json(path/"manifest.json",manifest)
            _publish({"status":"generated","files":[str(p) for p in outputs]},indent=2)
            return 0
        if args.command=="smoke":
            from .runtime import execute_smoke
            path=new_run("smoke")
            with runtime_lock(): manifest=execute_smoke(path)
        elif args.command=="run":
            config=load_config(resolve_project_file(args.config))
            from .runtime import execute_case
            path=new_run("rlc" if config["model"]=="rlc_filter" else config["model"])
            with runtime_lock(): manifest=execute_case(path,config)
        elif args.command=="sweep":
            config=load_config(resolve_project_file(args.config),sweep=True)
            from .runtime import execute_sweep
            path=new_run("sweep")
            with runtime_lock(): manifest=execute_sweep(path,config)
        _publish({"status":manifest["status"],"run_dir":str(path)})
        return 0 if manifest["status"]=="passed" else 1
    except Exception as exc:
        _ERROR.set({"code":type(exc).__name__,"stage":"execution","message":str(exc)})
        if path is not None and Path(path).is_dir() and args.command in {"smoke","run","sweep"}:
            try:
                manifest=manifest or {"schema_version":1,"kind":args.command,"backend":"virtual_hil","started_at":now()}
                manifest["status"]="error";manifest["error"]=f"{type(exc).__name__}: {exc}"
                note(path,traceback.format_exc());finalize(path,manifest)
                _publish({"status":"error","run_dir":str(path)})
            except Exception as record_error:
                print(f"Error record unavailable: {record_error}",file=sys.stderr)
        print(f"ERROR: {type(exc).__name__}: {exc}",file=sys.stderr);return 2


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if '--json' not in argv:
        return _run(argv)
    from .protocol import command_name, decorate, emit, progress_to_stderr, response
    argv = [a for a in argv if a != '--json']
    command = command_name(argv)
    results = []
    result_token = _RESULT.set(results)
    error_token = _ERROR.set(None)
    failure = None
    try:
        with progress_to_stderr() as output:
            try:
                code = _run(argv)
            except SystemExit as exc:
                code = int(exc.code or 0)
                if code:
                    failure = {'code':'invalid_arguments','stage':'arguments','message':'Invalid command arguments; details on stderr.'}
                else:
                    results.append({'status':'passed','help_on_stderr':True})
            except Exception as exc:
                code = 2
                traceback.print_exc(file=sys.stderr)
                failure = {'code':type(exc).__name__,'stage':'execution','message':str(exc)}
            failure = failure or _ERROR.get()
            data = results[-1] if results else {'status':'error' if code else 'passed'}
            try:
                value = decorate(command, data, argv, PROJECT, failure)
            except Exception as exc:
                traceback.print_exc(file=sys.stderr)
                code = 2
                value = response(command, status='error', error={
                    'code':type(exc).__name__,'stage':'response','message':str(exc)})
        try:
            emit(value, output)
        except (TypeError, ValueError) as exc:
            emit(response(command, status='error', error={'code':'serialization_error','stage':'response','message':str(exc)}), output)
            return 2
        return code
    finally:
        _RESULT.reset(result_token)
        _ERROR.reset(error_token)
