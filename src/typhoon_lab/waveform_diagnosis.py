"""Evidence-based morphology rules and portable, separately attributed LLM explanations."""
from copy import deepcopy
import json
import math
from pathlib import Path
import shutil
import numpy as np
from .external_records import _compare, verify_external
from .external_waveforms import analyze_dataset, load_intake, TIME_UNITS, VALUE_UNITS, known, relative_file
from .utils import PROJECT, finalize, now, sha256, write_json
from .versions import record_version_problems

KIND = "waveform_diagnosis"
SNAPSHOTS = ("waveform_diagnosis.py", "diagnosis_reporting.py", "external_waveforms.py",
             "external_records.py", "utils.py", "versions.py")
CLASS_LABELS = {"normal": "正常（按演示规则）", "abnormal": "异常（按演示规则）",
                "inconclusive": "无法判定"}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def validate_rules(rules):
    required = {"schema_version", "purpose", "threshold_source", "dip_fraction",
                "rise_drawdown_fraction", "minimum_duration_s", "label_context"}
    if not isinstance(rules, dict) or set(rules) != required or type(rules["schema_version"]) is not int or rules["schema_version"] != 1:
        raise ValueError("unsupported diagnosis rule schema")
    for key in ("purpose", "threshold_source"):
        if not isinstance(rules[key], str) or not rules[key].strip():
            raise ValueError(f"rules need {key}")
    for key in ("dip_fraction", "rise_drawdown_fraction", "minimum_duration_s"):
        v = rules[key]
        if type(v) not in (int, float) or not math.isfinite(v) or v <= 0:
            raise ValueError(f"invalid {key}")
        if key != "minimum_duration_s" and v >= 1:
            raise ValueError(f"invalid {key}")
    context = rules["label_context"]
    if not isinstance(context, dict) or not isinstance(context.get("expected_labels", {}), dict):
        raise ValueError("label_context needs expected_labels object")
    if context.get("expected_labels_status") not in {"inferred", "confirmed", "unconfirmed"}:
        raise ValueError("label status required")
    if any(v not in {"normal", "abnormal"} for v in context.get("expected_labels", {}).values()):
        raise ValueError("invalid expected label")
    return rules


def segments(mask, t, dt, severity, minimum):
    indices = np.flatnonzero(mask)
    groups = np.split(indices, np.where(np.diff(indices) > 1)[0] + 1) if len(indices) else []
    result = []
    for group in groups:
        duration = len(group) * dt
        if duration + dt * 1e-6 < minimum:
            continue
        peak = int(group[int(np.argmax(severity[group]))])
        result.append({"first_sample_s": float(t[group[0]]), "last_sample_s": float(t[group[-1]]),
                       "sample_count": int(len(group)), "sample_support_duration_s": float(duration),
                       "max_deviation": float(severity[peak]), "max_deviation_time_s": float(t[peak])})
    return result


def classify(record, array, rules):
    """Never consult record id, CSV name or expected labels to predict."""
    result = {"id": record["id"], "classification": "inconclusive", "cause_status": "undetermined",
              "family": record["analysis"]["method"], "events": [], "evidence": {}}
    if record["data_quality_status"] != "passed" or record["feature"]["status"] != "computed":
        return {**result, "reason": "结构、单位或特征计算不满足分析条件"}
    method, feature = result["family"], record["feature"]
    if method not in {"dip", "rise"}:
        return {**result, "reason": "当前规则只支持正基准电平跌落和上升沿回落"}
    recmeta = record["metadata"]
    t = array[:, 0] * TIME_UNITS[known(recmeta, "time_unit")]
    y = array[:, 1] * VALUE_UNITS[known(recmeta, "value_unit")][1]
    window = record["analysis"].get("window")
    if window is not None:
        scale = TIME_UNITS[known(recmeta, "time_unit")]
        mask = (t >= window[0] * scale) & (t <= window[1] * scale)
        t, y = t[mask], y[mask]
    dt = record["dt_median_s"]
    if dt > rules["minimum_duration_s"]:
        return {**result, "reason": "采样间隔大于最短事件持续时间，时序分辨能力不足"}
    evidence = {"time_unit": "s", "value_unit": record["units"]["value"],
                "dt_s": dt, "analysis_samples": len(t), "window_s": [float(t[0]), float(t[-1])],
                "minimum_duration_s": rules["minimum_duration_s"],
                "raw_min": float(y.min()), "raw_max": float(y.max())}
    if method == "dip":
        threshold = feature["baseline"] * rules["dip_fraction"]
        severity = feature["baseline"] - y
        evidence.update(baseline=feature["baseline"], deviation_threshold=threshold,
                        level_threshold=feature["baseline"] - threshold,
                        max_deviation=float(severity.max()),
                        max_deviation_fraction=float(severity.max() / feature["baseline"]))
    else:
        low, high = feature["low"], feature["high"]
        mask = (t >= feature["crossing_low"]["last_below_s"]) & (t <= feature["crossing_high"]["first_at_or_above_s"])
        t, y = t[mask], y[mask]
        if len(t) < 2:
            return {**result, "reason": "上升沿窗口不足"}
        severity = np.maximum.accumulate(y) - y
        threshold = (high - low) * rules["rise_drawdown_fraction"]
        trough = int(np.argmax(severity))
        peak = int(np.argmax(y[:trough + 1]))
        evidence.update(low_reference=low, high_reference=high, transition_amplitude=high-low,
                        first_crossing_interval_s=feature["first_crossing_interval_s"],
                        inspected_transition_window_s=[float(t[0]), float(t[-1])],
                        deviation_threshold=threshold, max_deviation=float(severity.max()),
                        max_deviation_fraction=float(severity.max() / (high - low)),
                        drawdown_peak_time_s=float(t[peak]), drawdown_trough_time_s=float(t[trough]),
                        drawdown_peak_value=float(y[peak]), drawdown_trough_value=float(y[trough]))
    events = segments(severity > threshold, t, dt, severity, rules["minimum_duration_s"])
    result.update(classification="abnormal" if events else "normal", evidence=evidence, events=events,
                  reason=("检测到满足幅度和持续时间阈值的跌落" if method == "dip" else
                          "检测到满足幅度和持续时间阈值的上升过程回落") if events else "在指定方法和窗口内未检出满足规则的事件")
    return result


def diagnose(source, rules):
    rules = validate_rules(rules)
    intake = load_intake(Path(source) / "intake.json")
    profile, arrays = analyze_dataset(source, intake)
    predictions = [classify(r, arrays.get(r["id"]), rules) for r in profile["records"]]
    expected = rules["label_context"].get("expected_labels", {})
    # Reference comparison is attached only AFTER all predictions are computed.
    comparisons = [{"id": p["id"], "expected": expected[p["id"]], "predicted": p["classification"],
                    "matches": expected[p["id"]] == p["classification"]}
                   for p in predictions if p["id"] in expected]
    return {"schema_version": 1, "method_version": 1, "dataset_id": profile["dataset_id"],
            "status": "completed" if all(p["classification"] != "inconclusive" for p in predictions) else "incomplete",
            "performance_status": "not_evaluated", "cause_status": "undetermined",
            "records": predictions, "reference_comparison": comparisons,
            "reference_status": rules["label_context"]["expected_labels_status"],
            "validation_scope": "四条已查看样本的规则演示；参考标签为逐文件形态推断，不构成独立准确率评估"}


def make_request(diagnosis):
    return {"schema_version": 1, "task": "解释数值规则的波形识别结果",
            "instruction": "只根据 records 中的数值证据解释正常/异常与异常位置。分类由规则给出，不得改写。正常只表示当前窗口未检出规则事件。不得确认测点、器件故障或控制器合格；cause_status 必须为 undetermined。每条解释列出实际使用的 evidence_keys（evidence 内键或 events），不把首次穿越间隔称为完整响应时间。返回 JSON：schema_version=1、request_sha256（请求文件哈希）、provider、model、transport、context、records；每条 record 含 id、classification、summary、evidence_keys、cause_status。",
            "records": diagnosis["records"], "scope": diagnosis["validation_scope"]}


def validate_explanation(response, request, request_hash):
    if not isinstance(response, dict) or response.get("schema_version") != 1 or response.get("request_sha256") != request_hash:
        raise ValueError("explanation request hash/schema mismatch")
    for key in ("provider", "model", "transport", "context"):
        if not isinstance(response.get(key), str) or not response[key].strip():
            raise ValueError(f"explanation needs {key} provenance")
    answers = response.get("records")
    if not isinstance(answers, list) or len(answers) != len(request["records"]):
        raise ValueError("explanation record count differs")
    by_id = {r.get("id"): r for r in answers if isinstance(r, dict)}
    if len(by_id) != len(answers) or set(by_id) != {r["id"] for r in request["records"]}:
        raise ValueError("explanation ids differ or duplicate")
    for rec in request["records"]:
        answer = by_id[rec["id"]]
        if answer.get("classification") != rec["classification"] or answer.get("cause_status") != "undetermined":
            raise ValueError("explanation changed classification or claimed a cause")
        if not isinstance(answer.get("summary"), str) or not answer["summary"].strip():
            raise ValueError("empty explanation")
        keys = answer.get("evidence_keys")
        allowed = set(rec["evidence"]) | {"events"}
        if not isinstance(keys, list) or not keys or any(not isinstance(k, str) or k not in allowed for k in keys):
            raise ValueError("explanation refers to missing evidence")
    return response


def new_output(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists() or output == source or output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("output must be new and separate from source")
    return source, output


def save_bundle(out, source_origin, response=None):
    rules = validate_rules(read_json(out / "rules.json"))
    diagnosis = diagnose(out / "source", rules)
    write_json(out / "diagnosis.json", diagnosis)
    write_json(out / "llm_request.json", make_request(diagnosis))
    explanation_status = "pending"
    if response is not None:
        validate_explanation(response, read_json(out / "llm_request.json"), sha256(out / "llm_request.json"))
        write_json(out / "llm_response.json", response)
        explanation_status = "completed"
    for name in SNAPSHOTS:
        target = out / "code_snapshot" / name
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(PROJECT / "src/typhoon_lab" / name, target)
    from .diagnosis_reporting import write_diagnosis_report
    write_diagnosis_report(out, diagnosis, rules, response)
    manifest = {"kind": KIND, "configuration_schema_version": 1, "analysis_method_version": 1,
                "started_at": now(), "source_origin": str(source_origin),
                "source_manifest_sha256": sha256(out / "source/manifest.json"),
                "status": "passed" if diagnosis["status"] == "completed" else "failed",
                "analysis_status": diagnosis["status"], "explanation_status": explanation_status,
                "performance_status": "not_evaluated", "cause_status": "undetermined",
                "explanation_validation_scope": "请求关联、分类及引用字段校验；自然语言正确性由人工复阅，不等于自动验证",
                "code_sha256": {name: sha256(out / "code_snapshot" / name) for name in SNAPSHOTS}}
    finalize(out, manifest)
    return {"status": manifest["status"], "run_dir": str(out), "analysis_status": diagnosis["status"],
            "explanation_status": explanation_status, "performance_status": "not_evaluated", "record_status": None}


def run_diagnosis(source, rules_path, output):
    source, out = new_output(source, output)
    rules_path = Path(rules_path).resolve()
    if rules_path.is_relative_to(out):
        raise ValueError("output must not contain rule source")
    rules = validate_rules(read_json(rules_path))
    verification = verify_external(source)
    if verification["record_status"] != "passed":
        raise ValueError(f"source record failed verification: {verification['problems']}")
    out.mkdir(parents=True)
    shutil.copytree(source, out / "source")
    write_json(out / "rules.json", rules)
    write_json(out / "source_verification.json", verification)
    return save_bundle(out, source)


def attach_explanation(source, response_path, output):
    source, out = new_output(source, output)
    if verify_diagnosis(source)["record_status"] != "passed":
        raise ValueError("diagnosis source failed verification")
    response = read_json(response_path)
    validate_explanation(response, read_json(source / "llm_request.json"), sha256(source / "llm_request.json"))
    shutil.copytree(source, out)
    (out / "verification.json").unlink(missing_ok=True)
    return save_bundle(out, source, response)


def verify_diagnosis(run_dir, write=False):
    out = Path(run_dir).resolve()
    problems = []
    try:
        manifest = read_json(out / "manifest.json")
        if manifest.get("kind") != KIND:
            raise ValueError("expected waveform_diagnosis")
        problems.extend(record_version_problems(manifest))
        for key in ("configuration_schema_version", "record_format_version", "analysis_method_version"):
            if type(manifest.get(key)) is not int or manifest[key] != 1:
                problems.append(f"unsupported {key}")
        hashes = manifest.get("artifacts", {})
        required = {"rules.json", "diagnosis.json", "llm_request.json", "report.md", "report.html",
                    "source/manifest.json", "source_verification.json"} | {f"code_snapshot/{n}" for n in SNAPSHOTS}
        if manifest.get("explanation_status") == "completed":
            required.add("llm_response.json")
        elif manifest.get("explanation_status") != "pending":
            problems.append("invalid explanation status")
        if not isinstance(hashes, dict):
            raise ValueError("invalid artifact hashes")
        problems.extend(f"required artifact not hashed: {r}" for r in sorted(required - hashes.keys()))
        for rel, digest in hashes.items():
            path = relative_file(out, rel)
            if not path.is_file() or sha256(path) != digest:
                problems.append(f"artifact missing or changed: {rel}")
        for name in SNAPSHOTS:
            if manifest.get("code_sha256", {}).get(name) != hashes.get(f"code_snapshot/{name}"):
                problems.append(f"code provenance mismatch: {name}")
        if manifest.get("source_manifest_sha256") != sha256(out / "source/manifest.json"):
            problems.append("source manifest hash differs")
        if not problems:
            source_result = verify_external(out / "source")
            problems.extend(source_result["problems"])
            actual = diagnose(out / "source", read_json(out / "rules.json"))
            problems.extend(_compare(actual, read_json(out / "diagnosis.json"), "diagnosis"))
            problems.extend(_compare(make_request(actual), read_json(out / "llm_request.json"), "llm_request"))
            for key, value in {"analysis_status": actual["status"], "performance_status": "not_evaluated",
                               "cause_status": "undetermined", "status": "passed" if actual["status"] == "completed" else "failed"}.items():
                if manifest.get(key) != value:
                    problems.append(f"manifest {key} differs")
            if manifest.get("explanation_status") == "completed":
                validate_explanation(read_json(out / "llm_response.json"), make_request(actual), sha256(out / "llm_request.json"))
            elif (out / "llm_response.json").exists():
                problems.append("response exists but explanation is pending")
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        problems.append(f"verification error: {exc}")
    result = {"status": "failed" if problems else "passed", "record_status": "failed" if problems else "passed",
              "run_dir": str(out), "verified_at": now(), "problems": problems,
              "performance_status": "not_evaluated", "experiment_status": None}
    if write:
        write_json(out / "verification.json", result)
    return result
