"""Screen measured terminal voltage on an independent PMSG laboratory bench."""

from collections import Counter
import csv
import json
from pathlib import Path
import re

import numpy as np
from scipy.io import loadmat

from .pmsm_calibration import phase_change
from .pmsm_diagnosis_comparison import _source_name
from .pmsm_evidence_qualification import FAULTS, SCORERS, TIE, _class_scores, _scaled_values
from .utils import PROJECT, finalize, now, sha256, write_json
from .versions import record_version_problems


KIND = "pmsg_voltage_screen"
NAME = re.compile(r"(?:FAULT_(TURNS|WINDINGS)_D(\d{2})_D(\d{2})_R026|HEALTHY)_S1800_T80\.mat")
DOI = "10.5281/zenodo.15741561"
RELEASE_COMMIT = "e02fba475cf82b375412a7382143dc29da5241ef"
TAP_GROUPS = ((1, 4, 6, 7), (11, 12, 21, 22), (13, 16, 18, 19))
PRE = (-0.35, -0.15)
POST = (0.15, 0.35)
RATE_HZ = 20_000
FUNDAMENTAL_HZ = 60
DOMINANT_BAND_HZ = (20, 300)
COMBINATIONS = {"current": ("I",), "current_voltage": ("I", "V"), "current_ratio": ("I", "Z")}
FEATURES = ("mean_log_amplitude_change", "spread_log_amplitude_change", "phase_spacing_rms_change_deg")


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _window(t, anchor, endpoints):
    start, end = endpoints
    # Convert seconds to sample indices on the verified uniform capture clock.
    return slice(int(round((anchor + start - t[0]) * RATE_HZ)), int(round((anchor + end - t[0]) * RATE_HZ)))


def _phasor(values):
    size = values.shape[1]
    taper = np.hanning(size)
    phase = np.exp(-2j * np.pi * FUNDAMENTAL_HZ * np.arange(size) / RATE_HZ)
    return 2 * ((values - values.mean(axis=1, keepdims=True)) * taper) @ phase / taper.sum()


def _dominant_hz(values):
    size = values.shape[1]
    windowed = (values - values.mean(axis=1, keepdims=True)) * np.hanning(size)
    power = (np.abs(np.fft.rfft(windowed, axis=1)) ** 2).sum(axis=0)
    frequencies = np.fft.rfftfreq(size, 1 / RATE_HZ)
    band = (frequencies >= DOMINANT_BAND_HZ[0]) & (frequencies <= DOMINANT_BAND_HZ[1])
    return float(frequencies[band][power[band].argmax()])


def _record(path, label):
    signals = ("t", "Ia", "Ib", "Ic", "Va", "Vb", "Vc", "Ifault", "Fault_relay", "Spd", "Torq_mec")
    raw = loadmat(path, variable_names=signals, squeeze_me=True)
    x = {name: raw[name] for name in signals}
    if any(values.shape != (60001,) or not np.isfinite(values).all() for values in x.values()):
        raise ValueError(f"required PMSG channels differ in size or quality: {path.name}")
    t = x["t"]
    if abs(t[0]) > 1e-8 or not np.allclose(np.diff(t), 1 / RATE_HZ, rtol=1e-6, atol=1e-8):
        raise ValueError(f"invalid native clock: {path.name}")
    relay = x["Fault_relay"] > 0
    events = t[np.flatnonzero(relay)]
    if label != "healthy" and not events.size:
        raise ValueError(f"recorded fault lacks a relay event: {path.name}")
    anchor = float(events[0]) if events.size else 1.0
    pre, post = (_window(t, anchor, endpoints) for endpoints in (PRE, POST))
    if not 0 <= pre.start < pre.stop < post.start < post.stop <= len(t):
        raise ValueError(f"registered windows exceed capture: {path.name}")
    current = np.stack([x[name] for name in ("Ia", "Ib", "Ic")])
    voltage = np.stack([x[name] for name in ("Va", "Vb", "Vc")])
    peaks = {name: [_dominant_hz(values[:, window]) for window in (pre, post)]
             for name, values in (("current", current), ("voltage", voltage))}
    if any(not np.isclose(value, FUNDAMENTAL_HZ) for pair in peaks.values() for value in pair):
        raise ValueError(f"registered fundamental disagrees with measured current or voltage: {path.name}")
    current_pre, current_post = (_phasor(current[:, window]) for window in (pre, post))
    voltage_pre, voltage_post = (_phasor(voltage[:, window]) for window in (pre, post))
    if min(np.min(np.abs(v)) for v in (current_pre, current_post, voltage_pre, voltage_post)) <= TIE:
        raise ValueError(f"missing terminal fundamental: {path.name}")
    phasors = {"I": (current_pre, current_post), "V": (voltage_pre, voltage_post),
               "Z": (voltage_pre / current_pre, voltage_post / current_post)}
    features = {}
    for name, (before, during) in phasors.items():
        unit = before / np.abs(before)
        relative = (unit * unit[[1, 2, 0]].conjugate()) ** 2
        features[name] = dict(zip(FEATURES, phase_change(during, (np.abs(before), relative)).tolist()))
    rms_pre, rms_post = [float(np.sqrt(np.mean(x["Ifault"][window] ** 2))) for window in (pre, post)]
    energized = bool(relay[post].all() and not relay[pre].any()
                     and rms_post > max(5 * rms_pre, 0.01))
    return {"samples": len(t), "relay_anchor_s": anchor, "pre_indices": [pre.start, pre.stop],
            "post_indices": [post.start, post.stop], "fault_current_pre_rms_a": rms_pre,
            "fault_current_post_rms_a": rms_post, "fault_window_verified": energized,
            "pre_spd_channel_value": float(x["Spd"][pre].mean()),
            "post_spd_channel_value": float(x["Spd"][post].mean()),
            "measured_peak_hz_pre_post": peaks,
            "pre_torque_nm": float(x["Torq_mec"][pre].mean()),
            "post_torque_nm": float(x["Torq_mec"][post].mean()), "features": features}


def _analyze(source):
    receipt = _read(source / "receipt.json")
    if (receipt["doi"] != DOI or receipt["commit"] != RELEASE_COMMIT
            or receipt["speed_rpm"] != 1800 or receipt["torque_nm"] != 8):
        raise ValueError("source receipt does not describe the pinned PMSG operating block")
    rows = []
    seen = set()
    for item in receipt["files"]:
        name = NAME.fullmatch(item["filename"])
        path = source / "raw" / item["filename"]
        if not name or path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
            raise ValueError(f"PMSG file differs from receipt: {item['filename']}")
        if item["sha256"] in seen:
            raise ValueError("duplicate PMSG capture")
        seen.add(item["sha256"])
        label = {None: "healthy", "TURNS": FAULTS[0], "WINDINGS": FAULTS[1]}[name[1]]
        taps = [int(name[2]), int(name[3])] if label != "healthy" else []
        group = next((index for index, tap_group in enumerate(TAP_GROUPS, 1)
                      if taps and set(taps).issubset(tap_group)), None)
        rows.append({"file": path.name, "label": label, "taps": taps, "held_group": group, **_record(path, label)})
    if Counter(row["label"] for row in rows) != {"healthy": 1, FAULTS[0]: 12, FAULTS[1]: 12}:
        raise ValueError("PMSG operating block does not contain the complete class coverage")

    predictions = []
    for held in range(1, len(TAP_GROUPS) + 1):
        train = [row for row in rows if row["held_group"] not in (None, held) and row["fault_window_verified"]]
        test = [row for row in rows if row["held_group"] == held]
        if Counter(row["label"] for row in test) != {FAULTS[0]: 2, FAULTS[1]: 4}:
            raise ValueError(f"PMSG tap group {held} differs from the registered class allocation")
        if not all(row["fault_window_verified"] for row in test) or set(r["label"] for r in train) != set(FAULTS):
            continue
        labels = np.array([row["label"] for row in train])
        for combination, groups in COMBINATIONS.items():
            training, testing = _scaled_values(train, test, groups)
            for scorer, margins in _class_scores(training, testing, labels).items():
                for row, margin in zip(test, margins, strict=True):
                    prediction = "undetermined" if abs(margin) <= TIE else FAULTS[int(margin < 0)]
                    predictions.append({"file": row["file"], "label": row["label"], "held_group": held,
                                        "combination": combination, "scorer": scorer,
                                        "margin_interturn_over_interwinding": float(margin),
                                        "prediction": prediction, "correct": prediction == row["label"]})
    scores = {}
    for combination in COMBINATIONS:
        scores[combination] = {}
        for scorer in SCORERS:
            measured = [r for r in predictions if (r["combination"], r["scorer"]) == (combination, scorer)]
            hits = {label: sum(r["label"] == label and r["correct"] for r in measured) for label in FAULTS}
            counts = Counter(r["label"] for r in measured)
            balanced = float(np.mean([hits[label] / counts[label] for label in FAULTS])) if len(counts) == 2 else None
            scores[combination][scorer] = {"hit_counts": hits, "condition_counts": dict(counts),
                                          "balanced_accuracy": balanced, "fold_hits": [
                sum(r["held_group"] == group and r["correct"] for r in measured) for group in range(1, 4)]}
    complete = len(predictions) == 18 * len(SCORERS) * len(COMBINATIONS)
    positive = complete and all(
        scores["current_voltage"][scorer]["balanced_accuracy"] >=
        scores["current"][scorer]["balanced_accuracy"] + 0.05
        for scorer in SCORERS
    )
    decision = ("voltage_candidate_signal" if positive else "voltage_screen_not_met") if complete else "screen_unscorable"
    return rows, predictions, {"native_records": len(rows),
                                "verified_fault_windows": sum(row["fault_window_verified"]
                                                              for row in rows if row["label"] != "healthy"),
                                "diagnosis_records": len({row["file"] for row in predictions}),
                                "decision": decision, "scores": scores}


def _protocol(source):
    module_folder = Path(__file__).resolve().parent
    methods = (Path(__file__).name, "pmsm_calibration.py", "pmsm_evidence_qualification.py")
    return {"source": _source_name(source), "receipt_sha256": sha256(source / "receipt.json"),
            "method_sha256": {name: sha256(module_folder / name) for name in methods},
            "pre_seconds_vs_relay": list(PRE), "post_seconds_vs_relay": list(POST),
            "fundamental_hz": FUNDAMENTAL_HZ, "dominant_band_hz": list(DOMINANT_BAND_HZ),
            "speed_channel_use": "raw metadata only; mechanical interpretation is unconfirmed",
            "tap_groups": [list(group) for group in TAP_GROUPS],
            "candidate": "current_voltage", "supporting_variant": "current_ratio",
            "gate": "18 scored recordings and pooled balanced accuracy at least 0.05 above current for both scorers"}


def run_screen(output, source):
    from .runtime import snapshot_code

    output, source = (Path(path).resolve() for path in (output, source))
    protocol = _protocol(source)
    output.mkdir(parents=True, exist_ok=False)
    frozen_at = now()
    write_json(output / "freeze.json", {"frozen_at": frozen_at, "protocol": protocol})
    snapshot = snapshot_code(output)
    records, predictions, summary = _analyze(source)
    write_json(output / "records.json", records)
    write_json(output / "predictions.json", predictions)
    write_json(output / "summary.json", summary)
    if predictions:
        with (output / "逐条件分型.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(predictions[0]))
            writer.writeheader()
            writer.writerows(predictions)
    finalize(output, {"kind": KIND, "status": "passed", "workflow_status": "completed",
                      "started_at": frozen_at, "code_sha256": snapshot, "research_decision": summary["decision"]})
    return {"status": "passed", "run_dir": str(output), "record_status": None,
            "research_decision": summary["decision"], **summary}


def verify_screen(output, write=False):
    output = Path(output).resolve()
    result = {"status": "failed", "record_status": "failed", "run_dir": str(output)}
    try:
        manifest = _read(output / "manifest.json")
        artifacts = manifest["artifacts"]
        if (manifest["kind"] != KIND or record_version_problems(manifest)
                or not {"freeze.json", "records.json", "predictions.json", "summary.json"}.issubset(artifacts)):
            raise ValueError("unsupported or incomplete PMSG record")
        for relative, expected in artifacts.items():
            path = (output / relative).resolve()
            if not path.is_relative_to(output) or sha256(path) != expected:
                raise ValueError(f"PMSG artifact differs: {relative}")
        protocol = _read(output / "freeze.json")["protocol"]
        source = (PROJECT / protocol["source"]).resolve()
        if protocol != _protocol(source):
            raise ValueError("PMSG source or protocol differs")
        rows, predictions, summary = _analyze(source)
        if (rows != _read(output / "records.json") or predictions != _read(output / "predictions.json")
                or summary != _read(output / "summary.json") or manifest["research_decision"] != summary["decision"]):
            raise ValueError("PMSG signals or scores do not replay")
        result.update({"status": "passed", "record_status": "passed", "workflow_status": "completed",
                       "native_records": len(rows), "predictions_replayed": len(predictions),
                       "research_decision": summary["decision"], "checked_at": now()})
    except (ValueError, OSError, KeyError, TypeError) as exc:
        result["problems"] = [str(exc)]
    if write:
        write_json(output / "verification.json", result)
    return result
