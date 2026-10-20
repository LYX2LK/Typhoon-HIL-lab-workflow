"""Reusable record verification for CLI, cases, and future callers."""
from pathlib import Path
import json
import math
from .config import load_config
from .utils import now, sha256, write_json
from .versions import record_version_problems

def verify_run(run_dir,write=True):
    from .analysis import analyze
    run_dir=Path(run_dir).resolve()
    manifest=json.loads((run_dir/"manifest.json").read_text(encoding="utf-8"))
    version_problems=record_version_problems(manifest)
    problems=list(version_problems)
    child_experiment_problems=[]
    for rel,expected in manifest.get("artifacts",{}).items():
        p=(run_dir/rel).resolve()
        if not p.is_relative_to(run_dir) or not p.is_file(): problems.append(f"missing or invalid artifact: {rel}")
        elif sha256(p)!=expected: problems.append(f"artifact changed: {rel}")
    if not manifest.get("artifacts"): problems.append("manifest has no artifact hashes")
    for rel,expected in manifest.get("code_sha256",{}).items():
        snapshot=(run_dir/"code_snapshot"/rel).resolve()
        if not snapshot.is_relative_to(run_dir) or not snapshot.is_file() or sha256(snapshot)!=expected:
            problems.append(f"code snapshot differs from recorded version: {rel}")
    if version_problems:
        problems.append("metric recomputation skipped for unsupported record or analysis version")
    elif manifest.get("kind")=="run" and (run_dir/"metrics.json").exists():
        try:
            config=load_config(run_dir/"config.json")
            if manifest.get("configuration_schema_version",config["schema_version"])!=config["schema_version"]:
                problems.append("configuration_schema_version differs from saved config")
            actual=analyze(run_dir/"waveforms.csv",config)
            stored=json.loads((run_dir/"metrics.json").read_text(encoding="utf-8"))
            for key in (["status","signals","capture","checks"] if config["model"]=="rlc_filter" else list(actual)):
                if actual.get(key)!=stored.get(key): problems.append(f"recomputed metrics differ: {key}")
            if manifest["status"]!=stored["status"]: problems.append("manifest status differs from metrics")
            if manifest.get("model", "rlc_filter")!=config["model"] or manifest.get("backend")!=config["backend"]:
                problems.append("manifest identity differs from config")
            from .adapters import get_adapter, records_events
            adapter=get_adapter(config["model"])
            if records_events(adapter,config):
                events=json.loads((run_dir/"events.json").read_text(encoding="utf-8"))
                if events!={"schema_version":2,"planned":config["events"],"events":actual["events"]}:
                    problems.append("event record differs from waveform recomputation")
                if manifest.get("events")!=actual["events"]:
                    problems.append("manifest events differ from waveform recomputation")
                schedule=adapter.describe_schedule(config)
                if manifest.get("event_schedule")!=schedule: problems.append("event schedule differs from config")
                for rel in ("waveforms.csv","metrics.json","config.json","capture.json","events.json"):
                    if rel not in manifest.get("artifacts",{}): problems.append(f"required artifact is not hashed: {rel}")
        except Exception as exc: problems.append(f"metric recomputation error: {exc}")
    elif manifest.get("kind")=="run":
        problems.append("run has no metrics.json for recomputation")
    elif manifest.get("kind")=="comparison" and manifest.get("model")=="single_phase_rectifier":
        try:
            from .rectifier_comparison import recompute_comparison
            actual=recompute_comparison(run_dir)
            stored=json.loads((run_dir/"metrics.json").read_text(encoding="utf-8"))
            if actual!=stored: problems.append("recomputed comparison differs from metrics")
            if manifest["status"]!=stored["status"]: problems.append("comparison manifest status differs from metrics")
        except Exception as exc: problems.append(f"comparison recomputation error: {exc}")
    elif manifest.get("kind")=="smoke" and (run_dir/"readings.json").exists():
        readings=json.loads((run_dir/"readings.json").read_text(encoding="utf-8"))
        passed=all(math.isclose(x["input"],x["measured"],rel_tol=0,abs_tol=1e-6) for x in readings)
        if (manifest["status"]=="passed")!=passed: problems.append("loopback readings do not support the recorded status")
    elif manifest.get("kind")=="modeling_practice":
        try:
            from .model_practice import recompute_practice
            actual=recompute_practice(run_dir)
            stored=json.loads((run_dir/"metrics.json").read_text(encoding="utf-8"))
            if actual!=stored: problems.append("recomputed practice metrics differ")
            if manifest["status"]!=actual["status"]: problems.append("practice status differs from metrics")
            if manifest.get("parameter_change",{}).get("Rin_ohm_after")!=8:
                problems.append("practice parameter readback is missing or differs")
            if not {"I","Va1","V_Rin"}.issubset(set(manifest.get("discovered_signals",[]))):
                problems.append("new practice measurement point was not discovered")
            if manifest.get("source_sha256")!=manifest.get("artifacts",{}).get("source_model.tse"):
                problems.append("practice source copy differs from recorded source hash")
            for rel in ("config.json","waveforms.csv","metrics.json","model.tse","source_model.tse"):
                if rel not in manifest.get("artifacts",{}): problems.append(f"required practice artifact is not hashed: {rel}")
        except Exception as exc: problems.append(f"practice recomputation error: {exc}")
    elif manifest.get("kind")=="sweep":
        if "configuration_schema_version" in manifest:
            try:
                config=load_config(run_dir/"config.json",sweep=True)
                if manifest["configuration_schema_version"]!=config["schema_version"]:
                    problems.append("configuration_schema_version differs from saved config")
            except Exception as exc:
                problems.append(f"sweep configuration validation error: {exc}")
        states=[]
        for case in manifest.get("cases",[]):
            path=(run_dir/case["relative_dir"]).resolve()
            if not path.is_relative_to(run_dir): problems.append("case path leaves sweep directory");continue
            result=verify_run(path,write=False)
            problems.extend(f"{case['case_id']}: {e}" for e in result["record_problems"])
            state=result["experiment_status"];states.append(state)
            if case.get("status")!=state: problems.append(f"case status differs: {case['case_id']}")
            if state!="passed": child_experiment_problems.append(f"{case['case_id']}: experiment status is {state}")
        if not states: problems.append("sweep has no cases")
        expected="passed" if states and all(x=="passed" for x in states) else ("error" if "error" in states else "failed")
        if states and manifest.get("status")!=expected: problems.append("sweep status differs from case results")
    elif manifest.get("kind")=="case":
        from .case_runner import verify_case_run
        case_problems,case_experiments=verify_case_run(run_dir,manifest)
        problems.extend(case_problems);child_experiment_problems.extend(case_experiments)
    record_problems=list(problems)
    problems.extend(child_experiment_problems)
    experiment_status=manifest.get("experiment_status") if manifest.get("kind")=="case" else manifest.get("status")
    if experiment_status!="passed": problems.append(f"experiment status is {experiment_status}")
    result={"checked_at":now(),"status":"passed" if not problems else "failed","problems":problems,
            "record_status":"passed" if not record_problems else "failed", "record_problems":record_problems,
            "experiment_status":experiment_status,
            "artifact_count":len(manifest.get("artifacts",{})),
            "scope":"artifact hashes and metric recomputation; not an independent hardware validation"}
    if write: write_json(run_dir/"verification.json",result)
    return result
