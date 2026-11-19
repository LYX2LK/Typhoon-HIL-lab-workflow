"""Healthy-reference checks and features for the KAIST PMSM recordings."""

from collections import Counter
import math
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import numpy as np

from .kaist_pmsm import LABELS, _waveform_clock
from .utils import sha256


REFERENCE_WINDOWS = (10, 30)
CHECK_WINDOWS = (60, 90)
SIGN_CANDIDATES = ((1, 1, 1), (-1, 1, 1), (1, -1, 1), (1, 1, -1))
PHASE_PAIRS = ((0, 1), (1, 2), (2, 0))
SHARE_FLOOR = 1e-6


def _read_phasors(path, sensor, capture_properties):
    from nptdms import TdmsFile

    rate = sensor["sample_rate_hz"]
    phasors = {}
    properties = []
    with TdmsFile.open(path) as tdms:
        channels = sorted((channel for group in tdms.groups() for channel in group.channels()),
                          key=lambda channel: channel.path)
        if ([channel.path for channel in channels] != [item["channel"] for item in sensor["channels"]]
                or any(len(channel) != sensor["sample_count"] for channel in channels)
                or any(_waveform_clock(channel, rate) != sensor["clock"] for channel in channels)):
            raise ValueError("current channels or clock differ from the verified source")
        if capture_properties:
            properties = [{"path": channel.path, "properties": {
                name: str(value) for name, value in channel.properties.items()
            }} for channel in channels]
        for item in sensor["windows"]:
            start, stop = item["indices"]
            waveform = np.stack([channel[start:stop] for channel in channels]).astype(float, copy=False)
            taper = np.hanning(stop - start)
            hz = item["metrics"]["electrical_fundamental_hz"]
            bin_index = round(hz * (stop - start) / rate)
            spectrum = np.fft.rfft((waveform - waveform.mean(axis=1, keepdims=True)) * taper, axis=1)
            vector = 2 * spectrum[:, bin_index] / taper.sum()
            if not np.isfinite(vector).all() or np.any(np.abs(vector) <= 0):
                raise ValueError("current window has an invalid phase fundamental")
            phasors[round(start / rate)] = vector
            if not math.isclose(sequence_ratio(vector), item["metrics"]["sequence_minor_major"], rel_tol=1e-8):
                raise ValueError("recomputed native sequence ratio differs from the verified source")
    if set(phasors) != set(REFERENCE_WINDOWS + CHECK_WINDOWS):
        raise ValueError("current windows differ from the registered healthy-reference protocol")
    return phasors, properties


def sequence_ratio(vector):
    rotation = np.exp(2j * np.pi / 3)
    first = abs(vector @ np.array([1, rotation, rotation ** 2]))
    second = abs(vector @ np.array([1, rotation ** 2, rotation]))
    return float(min(first, second) / max(first, second))


def _phasor_sum_ratio(vector, signs):
    return float(abs(vector @ signs) / np.abs(vector).sum())


def sign_check(windows):
    """Fit a relative sign convention on healthy windows and check later windows."""
    by_window = {start: [_phasor_sum_ratio(vector, signs) for signs in SIGN_CANDIDATES]
                 for start, vector in sorted(windows.items())}
    fit = np.median([by_window[start] for start in REFERENCE_WINDOWS], axis=0)
    choice = int(fit.argmin())
    return SIGN_CANDIDATES[choice], {
        "candidate_signs": list(SIGN_CANDIDATES[choice]),
        "check_windows_agree": sum(int(np.argmin(by_window[start])) == choice for start in CHECK_WINDOWS),
        "check_native_median": float(np.median([by_window[start][0] for start in CHECK_WINDOWS])),
        "check_adjusted_median": float(np.median([by_window[start][choice] for start in CHECK_WINDOWS])),
        "candidate_sum_ratios_by_window": {str(start): values for start, values in by_window.items()},
    }


def _paired_phase(vector):
    unit = vector / np.abs(vector)
    return np.array([(unit[i] * unit[j].conjugate()) ** 2 for i, j in PHASE_PAIRS])


def healthy_reference(windows):
    vectors = [windows[start] for start in REFERENCE_WINDOWS]
    amplitude = np.median(np.abs(vectors), axis=0)
    orientation = np.mean([_paired_phase(vector) for vector in vectors], axis=0)
    if np.any(np.abs(orientation) < 1e-6):
        raise ValueError("healthy phase spacing has no stable circular reference")
    return amplitude, orientation


def phase_change(vector, reference):
    amplitude, orientation = reference
    log_change = np.log(np.abs(vector) / amplitude)
    angle_change = np.rad2deg(np.angle(_paired_phase(vector) / orientation)) / 2
    return np.array([log_change.mean(), log_change.std(), np.sqrt(np.mean(angle_change ** 2))])


def _share_changes(healthy, features):
    baseline = healthy["windows"][:len(REFERENCE_WINDOWS)]
    if [round(item["seconds_from_record_start"][0]) for item in baseline] != list(REFERENCE_WINDOWS):
        raise ValueError("sensor does not cover the registered healthy-reference windows")
    return {
        key: math.log((features[key] + SHARE_FLOOR) /
                      (float(np.median([item["metrics"][key] for item in baseline])) + SHARE_FLOOR))
        for key in features
    }


def measure_motor(source, archive, rows, workdir):
    """Reuse the old verified summaries and recompute phase evidence from native current."""
    if Counter(row["label"] for row in rows) != dict(zip(LABELS, (1, 7, 7))):
        raise ValueError("calibration expects one healthy and seven records of each fault per motor")
    healthy = next(row for row in rows if row["label"] == "healthy")
    readings = {}
    properties = []
    with TemporaryDirectory(prefix="kaist-current-", dir=workdir) as scratch:
        with ZipFile(Path(source) / archive) as bundle:
            for row in rows:
                sensor = row["sensors"]["current"]
                member = sensor["members"][0]
                local = Path(scratch) / "current.tdms"
                with bundle.open(member["member"]) as raw, local.open("wb") as copy:
                    shutil.copyfileobj(raw, copy, length=2 ** 20)
                if sha256(local) != member["sha256"]:
                    raise ValueError(f"native current digest differs: {member['member']}")
                key = (row["label"], row["severity_pct"])
                readings[key], channel_props = _read_phasors(local, sensor, row is healthy)
                if row is healthy:
                    properties = channel_props

    healthy_currents = readings[("healthy", healthy["severity_pct"])]
    signs, check = sign_check(healthy_currents)
    reference = healthy_reference(healthy_currents)
    check["check_phase_change"] = [phase_change(healthy_currents[start], reference).tolist()
                                   for start in CHECK_WINDOWS]
    check["healthy_native_channels"] = properties
    results = []
    for row in rows:
        if row is healthy:
            continue
        key = (row["label"], row["severity_pct"])
        phasors = readings[key]
        observed = row["observations"]
        aligned = float(np.median([sequence_ratio(vector * signs) for vector in phasors.values()]))
        phase = np.median([phase_change(vector, reference) for vector in phasors.values()], axis=0)
        results.append({
            "motor_w": row["motor_w"], "label": row["label"], "severity_pct": row["severity_pct"],
            "current_sha256": row["sensors"]["current"]["members"][0]["sha256"],
            "features": {
                **observed,
                "Q1-sign": {**observed["Q1"], "sequence_minor_major": aligned},
                "Q1-ref": dict(zip(("mean_log_amplitude_change", "spread_log_amplitude_change",
                                    "phase_spacing_rms_change_deg"), phase.tolist())),
                "Q2-ref": _share_changes(healthy["sensors"]["current"], observed["Q2"]),
                "Q3-ref": _share_changes(healthy["sensors"]["vibration"], observed["Q3"]),
            },
            "current_fundamentals_a": {str(start): [[float(z.real), float(z.imag)] for z in vector]
                                       for start, vector in phasors.items()},
        })
    print(f"标定复算 {healthy['motor_w']} W：1 条健康参照、{len(results)} 条故障分型记录", flush=True)
    return {"healthy_check": check, "records": results}
