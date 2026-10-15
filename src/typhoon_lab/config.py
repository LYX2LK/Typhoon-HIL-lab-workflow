"""Validate supported experiments before starting Typhoon."""
from copy import deepcopy
import json
import math
from pathlib import Path

def number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be finite and in [{low}, {high}]")
    return float(value)

def _validate_rlc(raw, sweep=False):
    c = deepcopy(raw)
    expected = {"schema_version", "model", "backend", "source", "circuit", "capture", "acceptance"}
    if sweep:
        expected.add("sweep")
    if not isinstance(c, dict) or set(c) != expected:
        raise ValueError(f"configuration keys must be exactly {sorted(expected)}")
    if c["schema_version"] != 1 or isinstance(c["schema_version"], bool):
        raise ValueError("schema_version must be 1")
    if c["model"] != "rlc_filter" or c["backend"] != "virtual_hil":
        raise ValueError("this project supports rlc_filter on virtual_hil")
    rules = {
        "source": {"rms_v": (.01,1000), "frequency_hz": (1,5000), "phase_deg": (-360,360)},
        "circuit": {"rin_ohm": (.01,1000), "branch_r_ohm": (.001,100),
                    "l_h": (1e-6,1), "c_f": (1e-9,.1)},
        "capture": {"settle_s": (.001,10), "duration_s": (.001,5),
                    "sample_rate_hz": (1000,200000), "wall_timeout_s": (10,300)},
        "acceptance": {"relative_rms_error": (.0001,.2), "min_samples": (256,100000)}
    }
    for group, limits in rules.items():
        if not isinstance(c[group], dict) or set(c[group]) != set(limits):
            raise ValueError(f"{group} keys must be exactly {sorted(limits)}")
        for key, (low,high) in limits.items():
            c[group][key] = number(c[group][key], f"{group}.{key}",low,high)
    ms = c["acceptance"]["min_samples"]
    if not ms.is_integer():
        raise ValueError("acceptance.min_samples must be an integer")
    c["acceptance"]["min_samples"] = int(ms)
    freq = c["source"]["frequency_hz"]
    cycles = c["capture"]["duration_s"]*freq
    if cycles < 5 or not math.isclose(cycles,round(cycles),abs_tol=1e-6):
        raise ValueError("capture.duration_s must include at least 5 complete source cycles")
    if c["capture"]["sample_rate_hz"] < 20*freq:
        raise ValueError("sample_rate_hz must provide at least 20 samples per source cycle")
    requested_samples = c["capture"]["duration_s"]*c["capture"]["sample_rate_hz"]
    if requested_samples < c["acceptance"]["min_samples"]:
        raise ValueError("capture provides fewer samples than acceptance.min_samples")
    if requested_samples > 100000:
        raise ValueError("capture exceeds the teaching limit of 100000 samples")
    if sweep:
        s = c["sweep"]
        if not isinstance(s,dict) or set(s) != {"parameter","values"}:
            raise ValueError("sweep requires parameter and values")
        if s["parameter"] != "rin_ohm":
            raise ValueError("the first teaching sweep supports rin_ohm")
        if not isinstance(s["values"],list) or not 1 <= len(s["values"]) <= 12:
            raise ValueError("sweep requires 1 to 12 values")
        s["values"] = [number(v,"sweep.values",.01,1000) for v in s["values"]]
        if len(set(s["values"])) != len(s["values"]):
            raise ValueError("sweep values must be distinct")
    return c

def load_config(path,sweep=False):
    return validate_config(json.loads(Path(path).read_text(encoding="utf-8")),sweep=sweep)


def validate_config(raw, sweep=False):
    from .adapters import get_adapter
    if not isinstance(raw, dict):
        raise ValueError("configuration must be an object")
    return get_adapter(raw.get("model")).validate(raw, sweep=sweep)
