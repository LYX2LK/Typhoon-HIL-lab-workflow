"""Freeze, run, and independently replay a held-out PMSM diagnosis study."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import random

from .kaist_pmsm import (
    CURRENT_FUNDAMENTAL_BAND_HZ, LABELS, OBSERVATIONS, RATES_HZ, WINDOW_LENGTH_S, WINDOW_STARTS_S,
    inspect_archives, read_recordings,
)
from .pmsm_evidence_policy import (
    QUERY_BUDGET, RULES, SYSTEM, UNDETERMINED, accepted_label, make_calibration,
    rank_labels, rule_session, session, tune_stop,
)
from .research_model import call_json, load_service
from .utils import PROJECT, finalize, now, sha256, write_json
from .versions import record_version_problems


KIND = "pmsm_measured_comparison"
DEVELOPMENT_MOTORS = (1000, 1500)
HOLDOUT_MOTOR = 3000
REPETITIONS = (1, 2, 3)
ASSIGNMENT_SEED = 20261119
FROZEN_CODE = (
    "kaist_pmsm.py", "pmsm_evidence_policy.py", "pmsm_diagnosis_comparison.py",
    "pmsm_diagnosis_comparison_report.py", "research_model.py",
)


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _source_name(path):
    return path.relative_to(PROJECT).as_posix() if path.is_relative_to(PROJECT) else str(path)


def _code_hashes():
    parent = Path(__file__).resolve().parent
    return {name: sha256(parent / name) for name in FROZEN_CODE}


def _check_coverage(data, motors):
    for motor in motors:
        labels = [row["label"] for row in data["recordings"] if row["motor_w"] == motor]
        if any(labels.count(label) < (1 if label == "healthy" else 2) for label in LABELS):
            raise ValueError(f"{motor} W has insufficient eligible independent conditions: {labels}")


def _input_hashes(data):
    return {
        alias["sha256"] for row in data["recordings"] for sensor in row["sensors"].values()
        for alias in sensor["members"]
    }


def freeze_comparison(output, source, service):
    from .runtime import snapshot_code

    output, source, service = (Path(path).resolve() for path in (output, source, service))
    load_service(service)
    output.mkdir(parents=True, exist_ok=False)
    source_index = inspect_archives(source)
    write_json(output / "source-inventory.json", source_index)
    development = read_recordings(source, source_index, DEVELOPMENT_MOTORS, output)
    write_json(output / "development-private.json", development)
    _check_coverage(development, DEVELOPMENT_MOTORS)
    stop, tuning_rows = tune_stop(development["recordings"], DEVELOPMENT_MOTORS)
    code_snapshot = snapshot_code(output)
    write_json(output / "freeze.json", {
        "kind": KIND,
        "frozen_at": now(),
        "source_dir": _source_name(source),
        "source_inventory_sha256": sha256(output / "source-inventory.json"),
        "development_sha256": sha256(output / "development-private.json"),
        "development_motors_w": list(DEVELOPMENT_MOTORS),
        "holdout_motor_w": HOLDOUT_MOTOR,
        "holdout_waveform_access": "archive and member directory only before freeze",
        "assignment_seed": ASSIGNMENT_SEED,
        "window_starts_s": list(WINDOW_STARTS_S),
        "window_length_s": WINDOW_LENGTH_S,
        "rates_hz": RATES_HZ,
        "current_fundamental_band_hz": list(CURRENT_FUNDAMENTAL_BAND_HZ),
        "observation_features": OBSERVATIONS,
        "query_budget": QUERY_BUDGET,
        "repetitions": list(REPETITIONS),
        "calibration": make_calibration(development["recordings"]),
        "stop": stop,
        "development_tuning": tuning_rows,
        "model_service": {key: value for key, value in _read(service).items()
                          if key not in ("env_file", "api_key_env")},
        "model_service_sha256": sha256(service),
        "system_prompt": SYSTEM,
        "code_sha256": _code_hashes(),
        "code_snapshot": code_snapshot,
    })
    return {"status": "passed", "workflow_status": "frozen", "run_dir": str(output),
            "development_conditions": len(development["recordings"]), "record_status": None}


def _validated_freeze(output, source):
    freeze = _read(output / "freeze.json")
    if (freeze["kind"] != KIND or freeze["code_sha256"] != _code_hashes()
            or freeze["source_dir"] != _source_name(source)
            or freeze["system_prompt"] != SYSTEM
            or freeze["source_inventory_sha256"] != sha256(output / "source-inventory.json")
            or freeze["development_sha256"] != sha256(output / "development-private.json")):
        raise ValueError("frozen protocol, source, or implementation differs")
    inventory = inspect_archives(source)
    if inventory != _read(output / "source-inventory.json"):
        raise ValueError("publication archive inventory differs from the freeze")
    return freeze, inventory


def holdout_cases(recordings):
    shuffled = list(range(len(recordings)))
    rng = random.Random(ASSIGNMENT_SEED)
    rng.shuffle(shuffled)
    groups = {index: f"R{order:02d}" for order, index in enumerate(shuffled, 1)}
    specs = [(index, False) for index in range(len(recordings))]
    for label in LABELS:
        sample = next(index for index in shuffled if recordings[index]["label"] == label)
        specs.append((sample, True))
    rng.shuffle(specs)
    return [
        {
            "task_id": f"K{order:02d}", "recording_id": groups[index], "recording_index": index,
            "label": recordings[index]["label"], "masked": masked,
            "expected": UNDETERMINED if masked else recordings[index]["label"],
            "observations": {} if masked else recordings[index]["observations"],
        }
        for order, (index, masked) in enumerate(specs, 1)
    ]


def _check_exchange(folder, freeze, request):
    if _read(folder / "input.json") != request:
        raise ValueError("model-visible request differs from the frozen public projection")
    meta = _read(folder / "model_call.json")
    if meta["input_sha256"] != sha256(folder / "input.json"):
        raise ValueError("model input digest differs")
    if (folder / "http_request.json").is_file():
        message = _read(folder / "http_request.json")
        messages = message["messages"]
        service = freeze["model_service"]
        if (len(messages) != 2 or messages[0] != {"role": "system", "content": SYSTEM}
                or messages[1]["role"] != "user" or json.loads(messages[1]["content"]) != request
                or message["model"] != service["model"]
                or message["temperature"] != service.get("temperature", 0)
                or message["max_tokens"] != service["max_tokens"]
                or message.get("thinking") != service.get("thinking")):
            raise ValueError("stored HTTP request differs from the frozen policy")
    if meta["status"] != "completed":
        return None, "model_output_error" if (folder / "http_response.json").is_file() else "transport_error"
    response = _read(folder / "http_response.json")
    choice = response["choices"][0]
    answer = json.loads(choice["message"]["content"])
    if (not (folder / "http_request.json").is_file() or choice["finish_reason"] != "stop"
            or meta.get("response_id") != response.get("id")
            or meta.get("returned_model") != response.get("model")
            or meta.get("usage") != response.get("usage")
            or answer != _read(folder / "answer.json")):
        raise ValueError("stored HTTP response and parsed answer differ")
    return answer, None


def _model_session(case, freeze, directory, service=None):
    accessed = []

    def next_answer(turn, request):
        call = directory / f"call-{turn}"
        accessed.append(call)
        if not call.exists():
            if service is None:
                raise ValueError(f"missing replay input {call}")
            try:
                call_json(call, service, SYSTEM, request)
            except RuntimeError:
                # The transport keeps its original safe error metadata.
                pass
        if not (call / "model_call.json").is_file():
            return None, "interrupted"
        return _check_exchange(call, freeze, request)

    result = session(case, freeze["calibration"], next_answer)
    if set(directory.glob("call-*")) != set(accessed):
        raise ValueError(f"unexpected model calls in {directory.name}")
    return result


def _diagnostic_strata(case, calibration, stop):
    if case["masked"]:
        return "no_observations", None, None
    observations = case["observations"]
    truth = case["expected"]
    initial = accepted_label(rank_labels(calibration, {"I0": observations["I0"]}), stop)
    complete = accepted_label(rank_labels(calibration, observations), stop)
    if initial == truth:
        strata = "initial_sufficient"
    else:
        strata = "additional_evidence" if complete == truth else "reference_unresolved"
    return strata, initial, complete


def _result_row(case, outcome, strategy, repeat, freeze, directory=None):
    stratum, initial, complete = _diagnostic_strata(case, freeze["calibration"], freeze["stop"])
    accounting = {"calls": 0, "calls_with_usage": 0, "input_tokens": 0, "output_tokens": 0,
                  "request_seconds": 0.0, "returned_models": []}
    if directory:
        model_names = set()
        for turn in outcome["trace"]:
            metadata = directory / f"call-{turn['turn']}" / "model_call.json"
            accounting["calls"] += 1
            if not metadata.is_file():
                continue
            meta = _read(metadata)
            accounting["request_seconds"] += meta["elapsed_s"]
            if meta.get("returned_model"):
                model_names.add(meta["returned_model"])
            usage = meta.get("usage")
            if usage and isinstance(usage.get("prompt_tokens"), int) and isinstance(usage.get("completion_tokens"), int):
                accounting["calls_with_usage"] += 1
                accounting["input_tokens"] += usage["prompt_tokens"]
                accounting["output_tokens"] += usage["completion_tokens"]
        accounting["returned_models"] = sorted(model_names)
    decision = outcome["decision"]
    first = outcome["trace"][0]
    initial_decision = (first["answer"].get("decision")
                        if first["status"] in ("finish", "query") else None)
    return {
        "task_id": case["task_id"], "recording_id": case["recording_id"], "method": strategy,
        "repeat": repeat, "mask": case["masked"], "truth": case["label"], "expected": case["expected"],
        "stratum": stratum, "initial_reference": initial, "full_reference": complete,
        "decision": decision, "status": outcome["status"], "correct": decision == case["expected"],
        "initial_decision": initial_decision, "initial_correct": initial_decision == case["expected"],
        "corrected_after_query": (initial_decision != case["expected"] and decision == case["expected"]
                                  and outcome["valid_queries"] > 0),
        "lost_initial_hit": initial_decision == case["expected"] and decision != case["expected"],
        "wrong_commit": decision in LABELS and decision != case["expected"],
        "undetermined": decision == UNDETERMINED,
        "raw_final_decision": (outcome["trace"][-1]["answer"].get("decision")
                               if isinstance(outcome["trace"][-1]["answer"], dict)
                               and outcome["trace"][-1]["answer"].get("action") == "finish" else None),
        "queries": outcome["queries"], "valid_queries": outcome["valid_queries"],
        "invalid_actions": outcome["invalid_actions"],
        "query_path": [item["answer"]["action"] for item in outcome["trace"] if item["status"] == "query"],
        **accounting,
    }


def _trial_rows(cases, freeze, output, service=None):
    rows = []
    for case in cases:
        for strategy in RULES:
            outcome = rule_session(case, freeze["calibration"], freeze["stop"], strategy)
            result = output / "sessions" / case["task_id"] / strategy / "result.json"
            if service is None:
                if _read(result) != outcome:
                    raise ValueError(f"engineering baseline replay differs for {case['task_id']}, {strategy}")
            else:
                write_json(result, outcome)
            rows.append(_result_row(case, outcome, strategy, None, freeze))

    def model_one(case, repeat):
        directory = output / "sessions" / case["task_id"] / f"llm-{repeat}"
        outcome = _model_session(case, freeze, directory, service)
        result = directory / "result.json"
        if service is None:
            if _read(result) != outcome:
                raise ValueError(f"LLM replay differs for {case['task_id']}, repeat {repeat}")
        else:
            write_json(result, outcome)
        return _result_row(case, outcome, "llm", repeat, freeze, directory)

    schedule = [(case, repeat) for repeat in REPETITIONS for case in cases]
    if service is None:
        rows.extend(model_one(case, repeat) for case, repeat in schedule)
    else:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(model_one, case, repeat) for case, repeat in schedule]
            for index, future in enumerate(as_completed(futures), 1):
                rows.append(future.result())
                if index % len(cases) == 0:
                    print(f"已记录 {index}/{len(schedule)} 个真实模型会话", flush=True)
    return sorted(rows, key=lambda row: (row["task_id"], row["method"], row["repeat"] or 0))


def run_comparison(output, source, service):
    from .pmsm_diagnosis_comparison_report import write_report

    output, source, service = (Path(path).resolve() for path in (output, source, service))
    if (output / "manifest.json").is_file():
        raise ValueError("comparison already finalized; replay with verify")
    freeze, inventory = _validated_freeze(output, source)
    if freeze["model_service_sha256"] != sha256(service):
        raise ValueError("model service configuration differs from the freeze")
    load_service(service)
    development = _read(output / "development-private.json")
    holdout_path = output / "holdout-private.json"
    holdout = (_read(holdout_path) if holdout_path.is_file()
               else read_recordings(source, inventory, (HOLDOUT_MOTOR,), output))
    write_json(holdout_path, holdout)
    _check_coverage(holdout, (HOLDOUT_MOTOR,))
    if _input_hashes(development) & _input_hashes(holdout):
        raise ValueError("a raw recording was shared by development and holdout")
    cases = holdout_cases(holdout["recordings"])
    write_json(output / "tasks-private.json", cases)
    rows = _trial_rows(cases, freeze, output, service)
    write_json(output / "results.json", rows)
    usable = any(row["method"] == "llm" and row["status"] not in ("transport_error", "interrupted")
                 for row in rows)
    workflow = "completed" if usable else "service_unavailable"
    summary = write_report(output, development, holdout, rows, freeze, workflow)
    finalize(output, {
        "kind": KIND, "status": "passed" if usable else "error", "workflow_status": workflow,
        "started_at": freeze["frozen_at"], "code_sha256": freeze["code_snapshot"],
        "freeze_sha256": sha256(output / "freeze.json"), "source_dir": _source_name(source),
        "task_count": len(cases), "result_count": len(rows),
        "research_decision": summary["decision"],
    })
    return {"status": "passed" if usable else "error", "workflow_status": workflow, "run_dir": str(output),
            "research_decision": summary["decision"], "record_status": None}


def verify_comparison(output, write=False):
    from tempfile import TemporaryDirectory

    from .pmsm_diagnosis_comparison_report import summarize

    output = Path(output).resolve()
    result = {"status": "failed", "record_status": "failed", "run_dir": str(output)}
    try:
        manifest = _read(output / "manifest.json")
        issues = record_version_problems(manifest)
        if manifest["kind"] != KIND or issues:
            raise ValueError(f"unsupported comparison record: {issues}")
        for name, digest in manifest["artifacts"].items():
            path = (output / name).resolve()
            if not path.is_relative_to(output) or not path.is_file() or sha256(path) != digest:
                raise ValueError(f"artifact differs: {name}")
        if manifest["freeze_sha256"] != sha256(output / "freeze.json"):
            raise ValueError("freeze digest differs")
        source = (PROJECT / manifest["source_dir"]).resolve()
        freeze, inventory = _validated_freeze(output, source)
        with TemporaryDirectory(prefix="kaist-verify-") as tmp:
            development = read_recordings(source, inventory, DEVELOPMENT_MOTORS, tmp)
            holdout = read_recordings(source, inventory, (HOLDOUT_MOTOR,), tmp)
        if development != _read(output / "development-private.json") or holdout != _read(output / "holdout-private.json"):
            raise ValueError("raw TDMS provenance, windows, or observations do not replay")
        _check_coverage(development, DEVELOPMENT_MOTORS)
        _check_coverage(holdout, (HOLDOUT_MOTOR,))
        stop, tuning = tune_stop(development["recordings"], DEVELOPMENT_MOTORS)
        if (freeze["calibration"] != make_calibration(development["recordings"]) or stop != freeze["stop"]
                or tuning != freeze["development_tuning"] or _input_hashes(development) & _input_hashes(holdout)):
            raise ValueError("development calibration or source separation differs")
        cases = holdout_cases(holdout["recordings"])
        if cases != _read(output / "tasks-private.json") or len(cases) != manifest["task_count"]:
            raise ValueError("holdout task assignment differs")
        replay = _trial_rows(cases, freeze, output)
        if replay != _read(output / "results.json") or len(replay) != manifest["result_count"]:
            raise ValueError("replayed score or accounting differs")
        summary = summarize(replay, manifest["workflow_status"])
        if summary != _read(output / "summary.json") or summary["decision"] != manifest["research_decision"]:
            raise ValueError("research decision or summary does not replay")
        result.update({
            "status": manifest["status"], "record_status": "passed",
            "workflow_status": manifest["workflow_status"], "research_decision": summary["decision"],
            "raw_recordings_recomputed": len(development["recordings"]) + len(holdout["recordings"]),
            "tasks_replayed": len(cases), "sessions_replayed": len(replay), "checked_at": now(),
        })
    except (ValueError, OSError, KeyError, TypeError) as exc:
        result["problems"] = [str(exc)]
    if write:
        write_json(output / "verification.json", result)
    return result
