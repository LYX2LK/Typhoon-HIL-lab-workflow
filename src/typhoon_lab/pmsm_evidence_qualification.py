"""Freeze and replay a cross-motor winding-evidence qualification, without model calls."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from .kaist_pmsm import CURRENT_FUNDAMENTAL_BAND_HZ, WINDOW_LENGTH_S, inspect_archives
from .pmsm_calibration import CHECK_WINDOWS, REFERENCE_WINDOWS, SHARE_FLOOR, SIGN_CANDIDATES, measure_motor
from .pmsm_diagnosis_comparison import DEVELOPMENT_MOTORS, HOLDOUT_MOTOR, _source_name
from .utils import PROJECT, finalize, now, sha256, write_json
from .versions import record_version_problems


KIND = "pmsm_evidence_qualification"
FAULTS = ("interturn", "intercoil")
SCORERS = ("median_distance", "ridge_linear")
MOTORS = (*DEVELOPMENT_MOTORS, HOLDOUT_MOTOR)
BYPASS_OHMS = (6, 5, 4, 3, 2, 1, 0.5)
HARD_PAIR_COUNT = 3
MIN_NET_CORRECT = 2
MIN_PER_FAULT = 4
RIDGE_PENALTY = 1.0
TIE = 1e-12

COMBINATIONS = {
    "initial": ("I0",),
    "native_phase": ("I0", "Q1"),
    "sign_phase": ("I0", "Q1-sign"),
    "native_full": ("I0", "Q1", "Q2", "Q3"),
    "sign_full": ("I0", "Q1-sign", "Q2", "Q3"),
    "phase_reference": ("I0", "Q1-ref"),
    "harmonic_reference": ("I0", "Q2-ref"),
    "vibration_reference": ("I0", "Q3-ref"),
    "phase_harmonic_reference": ("I0", "Q1-ref", "Q2-ref"),
    "phase_vibration_reference": ("I0", "Q1-ref", "Q3-ref"),
    "harmonic_vibration_reference": ("I0", "Q2-ref", "Q3-ref"),
    "full_reference": ("I0", "Q1-ref", "Q2-ref", "Q3-ref"),
}
EVIDENCE_CANDIDATES = tuple(name for name in COMBINATIONS if name.endswith("_reference")
                            and name != "full_reference")
SOURCE_FILES = ("source-inventory.json", "development-private.json", "holdout-private.json")
REQUIRED = ("freeze.json", "measurements.json", "scores.json", "summary.json", "逐条件分型.csv",
            "analysis-report.md", "stats-appendix.md", "figure-catalog.md",
            "figures/motor-evidence.png", "figures/healthy-polarity.png")
METHOD_FILES = ("kaist_pmsm.py", "pmsm_calibration.py", "pmsm_evidence_qualification.py",
                "pmsm_evidence_qualification_report.py")


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _protocol():
    base = Path(__file__).resolve().parent
    return {
        "current_fundamental_band_hz": list(CURRENT_FUNDAMENTAL_BAND_HZ),
        "window_length_s": WINDOW_LENGTH_S,
        "healthy_reference_starts_s": list(REFERENCE_WINDOWS),
        "healthy_check_starts_s": list(CHECK_WINDOWS),
        "healthy_use": "one available known-healthy acquisition per motor, enrollment only",
        "candidate_signs": [list(signs) for signs in SIGN_CANDIDATES],
        "share_ratio_floor": SHARE_FLOOR,
        "development_test_motors_w": list(DEVELOPMENT_MOTORS),
        "historical_test_motor_w": HOLDOUT_MOTOR,
        "test_unit": "whole verified fault recording of one seeded condition",
        "candidates": {key: list(value) for key, value in COMBINATIONS.items()},
        "scorers": list(SCORERS),
        "ridge_penalty": RIDGE_PENALTY,
        "tie_tolerance": TIE,
        "matched_bypass_resistances_ohm": list(BYPASS_OHMS),
        "most_similar_initial_pairs_per_fold": HARD_PAIR_COUNT,
        "engineering_screen": {
            "eligible_candidates": list(EVIDENCE_CANDIDATES),
            "minimum_net_correct_over_initial": MIN_NET_CORRECT,
            "minimum_correct_per_fault": MIN_PER_FAULT,
            "required": "one same candidate passes both development folds under both scorers",
            "role_of_3000_w": "previously exposed historical replay, no candidate selection",
        },
        "independent_batch_available": False,
        "method_sha256": {name: sha256(base / name) for name in METHOD_FILES},
    }


def _source_inputs(parent):
    manifest = _read(parent / "manifest.json")
    verified = _read(parent / "verification.json")
    if (manifest["kind"] != "pmsm_measured_comparison" or manifest["status"] != "passed"
            or record_version_problems(manifest)
            or verified["record_status"] != "passed" or verified["raw_recordings_recomputed"] != 45):
        raise ValueError("source must be a verified 45-condition measured comparison")
    for relative in SOURCE_FILES:
        if sha256(parent / relative) != manifest["artifacts"][relative]:
            raise ValueError(f"verified source artifact changed: {relative}")
    return (PROJECT / manifest["source_dir"]).resolve(), _read(parent / SOURCE_FILES[0])


def _measure(source, parent, index, motors, source_file, work):
    records = _read(parent / source_file)["recordings"]
    if {row["motor_w"] for row in records} != set(motors):
        raise ValueError("verified source motor allocation differs")
    return {
        str(motor): measure_motor(source, index["motors"][str(motor)]["archive"],
                                 [row for row in records if row["motor_w"] == motor], work)
        for motor in motors
    }


def _scaled_values(train, test, groups):
    train_groups, test_groups = [], []
    for group in groups:
        features = sorted(train[0]["features"][group])
        training = np.array([[row["features"][group][key] for key in features] for row in train])
        testing = np.array([[row["features"][group][key] for key in features] for row in test])
        if not np.isfinite(training).all() or not np.isfinite(testing).all():
            raise ValueError(f"nonfinite values in {group}")
        lower, middle, upper = np.quantile(training, [0.25, 0.5, 0.75], axis=0)
        iqr = upper - lower
        spread = training.std(axis=0)
        scale = np.where(iqr > TIE, iqr, np.where(spread > TIE, spread, np.inf))
        train_groups.append((training - middle) / scale)
        test_groups.append((testing - middle) / scale)
    return train_groups, test_groups


def _class_scores(training, testing, labels):
    median_scores = np.zeros((len(testing[0]), 2))
    for train_group, test_group in zip(training, testing, strict=True):
        centers = np.array([np.median(train_group[labels == label], axis=0) for label in FAULTS])
        median_scores -= np.abs(test_group[:, None, :] - centers).mean(axis=2) / len(testing)

    def design(groups):
        return np.column_stack([np.ones(len(groups[0])), *[x / np.sqrt(x.shape[1]) for x in groups]])

    train = design(training)
    expected = np.where(labels == FAULTS[0], 1.0, -1.0)
    penalty = np.eye(train.shape[1]) * (RIDGE_PENALTY * len(train))
    penalty[0, 0] = 0
    coefficients = np.linalg.solve(train.T @ train + penalty, train.T @ expected)
    linear_scores = design(testing) @ coefficients
    return {"median_distance": median_scores[:, 0] - median_scores[:, 1],
            "ridge_linear": linear_scores}


def _matched_pairs(rows, scaled_initial):
    by_fault = [sorted((index for index, row in enumerate(rows) if row["label"] == label),
                       key=lambda index: float(rows[index]["severity_pct"])) for label in FAULTS]
    pairs = [
        {"bypass_ohm": ohms, "indices": list(pair),
         "initial_distance": float(np.abs(scaled_initial[pair[0]] - scaled_initial[pair[1]]).mean())}
        for ohms, pair in zip(BYPASS_OHMS, zip(*by_fault, strict=True), strict=True)
    ]
    return sorted(pairs, key=lambda pair: (pair["initial_distance"], pair["bypass_ohm"]))


def _evaluate(train, test, test_motor):
    if {row["current_sha256"] for row in train} & {row["current_sha256"] for row in test}:
        raise ValueError("current waveform appears in both training and scoring")
    actual = np.array([row["label"] for row in test])
    labels = np.array([row["label"] for row in train])
    _, initial = _scaled_values(train, test, COMBINATIONS["initial"])
    pairs = _matched_pairs(test, initial[0])
    difficult = [pair["indices"] for pair in pairs[:HARD_PAIR_COUNT]]
    predictions = []
    summary = {}
    baseline_hits = {}
    for name, groups in COMBINATIONS.items():
        train_vectors, test_vectors = _scaled_values(train, test, groups)
        variants = _class_scores(train_vectors, test_vectors, labels)
        summary[name] = {}
        for scorer, margins in variants.items():
            predicted = np.where(margins > TIE, FAULTS[0], np.where(margins < -TIE, FAULTS[1], "undetermined"))
            hit = predicted == actual
            if name == "initial":
                baseline_hits[scorer] = hit
            previous = baseline_hits[scorer]
            summary[name][scorer] = {
                "correct": int(hit.sum()),
                "correct_by_fault": {label: int(hit[actual == label].sum()) for label in FAULTS},
                "fixed_initial_errors": int((hit & ~previous).sum()),
                "lost_initial_hits": int((~hit & previous).sum()),
                "net_gain": int(hit.sum() - previous.sum()),
                "hard_pairs_both_correct": sum(bool(hit[pair].all()) for pair in difficult),
                "all_pairs_both_correct": sum(bool(hit[pair["indices"]].all()) for pair in pairs),
            }
            predictions.extend({
                "motor_w": test_motor, "label": row["label"], "severity_pct": row["severity_pct"],
                "combination": name, "scorer": scorer, "prediction": str(predicted[index]),
                "margin_interturn_over_intercoil": float(margins[index]),
                "correct": bool(hit[index]), "initial_correct": bool(previous[index]),
            } for index, row in enumerate(test))
    return {"train_motors_w": sorted({row["motor_w"] for row in train}), "test_motor_w": test_motor,
            "n_faults": len(test), "scores": summary, "predictions": predictions,
            "pairs": [{**pair, "severity_pct": [test[index]["severity_pct"] for index in pair["indices"]]}
                      for pair in pairs]}


def _development_scores(measured):
    return [
        _evaluate(measured[str(other)]["records"], measured[str(test)]["records"], test)
        for test, other in (DEVELOPMENT_MOTORS, DEVELOPMENT_MOTORS[::-1])
    ]


def _summarize(measured, folds):
    lookup = {fold["test_motor_w"]: fold["scores"] for fold in folds}
    passing = []
    for candidate in EVIDENCE_CANDIDATES:
        checks = [lookup[motor][candidate][scorer] for motor in DEVELOPMENT_MOTORS for scorer in SCORERS]
        if all(row["net_gain"] >= MIN_NET_CORRECT and min(row["correct_by_fault"].values()) >= MIN_PER_FAULT
               for row in checks):
            passing.append(candidate)
    return {
        "decision": "candidate_for_independent_evidence_test" if passing else "evidence_screen_not_met",
        "passing_candidates": passing,
        "fault_records": sum(len(item["records"]) for item in measured.values()),
        "healthy_reference_records": len(measured),
        "scores": {str(motor): results for motor, results in lookup.items()},
        "independent_batch_available": False,
    }


def _recompute(source, parent, inventory, work):
    if inspect_archives(source) != inventory:
        raise ValueError("publisher archive inventory or checksums differ from the verified comparison")
    measured = _measure(source, parent, inventory, DEVELOPMENT_MOTORS, SOURCE_FILES[1], work)
    folds = _development_scores(measured)
    measured.update(_measure(source, parent, inventory, (HOLDOUT_MOTOR,), SOURCE_FILES[2], work))
    train = [row for motor in DEVELOPMENT_MOTORS for row in measured[str(motor)]["records"]]
    folds.append(_evaluate(train, measured[str(HOLDOUT_MOTOR)]["records"], HOLDOUT_MOTOR))
    return measured, folds, _summarize(measured, folds)


def qualify_evidence(output, parent):
    from .pmsm_evidence_qualification_report import write_report
    from .runtime import snapshot_code

    output, parent = (Path(item).resolve() for item in (output, parent))
    source, inventory = _source_inputs(parent)
    output.mkdir(parents=True, exist_ok=False)
    freeze = {"frozen_at": now(), "source_run": _source_name(parent),
              "source_manifest_sha256": sha256(parent / "manifest.json"),
              "source_verification_sha256": sha256(parent / "verification.json"),
              "protocol": _protocol()}
    write_json(output / "freeze.json", freeze)
    snapshot = snapshot_code(output)
    measured, folds, summary = _recompute(source, parent, inventory, output)
    write_json(output / "measurements.json", measured)
    write_json(output / "scores.json", folds)
    write_json(output / "summary.json", summary)
    write_report(output, measured, folds, summary)
    finalize(output, {
        "kind": KIND, "status": "passed", "workflow_status": "completed",
        "started_at": freeze["frozen_at"], "code_sha256": snapshot,
        "freeze_sha256": sha256(output / "freeze.json"), "research_decision": summary["decision"],
    })
    return {"status": "passed", "workflow_status": "completed", "run_dir": str(output),
            "research_decision": summary["decision"], "fault_recordings": summary["fault_records"],
            "record_status": None}


def verify_evidence(output, write=False):
    output = Path(output).resolve()
    result = {"status": "failed", "record_status": "failed", "run_dir": str(output)}
    try:
        manifest = _read(output / "manifest.json")
        freeze = _read(output / "freeze.json")
        artifacts = manifest["artifacts"]
        if (manifest["kind"] != KIND or record_version_problems(manifest)
                or not set(REQUIRED).issubset(artifacts)
                or freeze["protocol"] != _protocol()
                or manifest["freeze_sha256"] != sha256(output / "freeze.json")):
            raise ValueError("qualification record, method, or freeze differs")
        for name, digest in artifacts.items():
            path = (output / name).resolve()
            if not path.is_relative_to(output) or sha256(path) != digest:
                raise ValueError(f"qualification artifact differs: {name}")
        parent = (PROJECT / freeze["source_run"]).resolve()
        if (sha256(parent / "manifest.json") != freeze["source_manifest_sha256"]
                or sha256(parent / "verification.json") != freeze["source_verification_sha256"]):
            raise ValueError("source comparison or completion verification changed")
        source, inventory = _source_inputs(parent)
        with TemporaryDirectory(prefix="evidence-replay-", dir=output) as temporary:
            measured, folds, summary = _recompute(source, parent, inventory, temporary)
        if (measured != _read(output / "measurements.json")
                or folds != _read(output / "scores.json") or summary != _read(output / "summary.json")
                or manifest["research_decision"] != summary["decision"]):
            raise ValueError("original phasors, matched cases, or recorded scores do not replay")
        result.update({"status": "passed", "record_status": "passed", "workflow_status": "completed",
                       "raw_current_recordings_recomputed": summary["fault_records"] + len(MOTORS),
                       "predictions_replayed": sum(len(fold["predictions"]) for fold in folds),
                       "research_decision": summary["decision"], "checked_at": now()})
    except (ValueError, OSError, KeyError, TypeError) as exc:
        result["problems"] = [str(exc)]
    if write:
        write_json(output / "verification.json", result)
    return result
