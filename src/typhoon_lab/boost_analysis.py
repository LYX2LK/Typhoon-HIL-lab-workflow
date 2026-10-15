"""Deterministic Boost dynamics from unmodified capture samples."""
import math
from pathlib import Path
from statistics import median
from .analysis import load_waveforms
from .adapters.boost import BoostAdapter, CONTROL_PERIOD_S

COLUMNS = ("t_relative_s", "t_simulation_s", *BoostAdapter.columns)
LEVEL_TOLERANCE_V = 1e-4


def _mean(values):
    if not values:
        raise ValueError("analysis window contains no samples")
    value = math.fsum(values)/len(values)
    if not math.isfinite(value):
        raise ValueError("non-finite aggregate")
    return value


def analyze(csv_path, config):
    config = BoostAdapter().validate(config)
    d = load_waveforms(Path(csv_path), columns=COLUMNS)
    t, y = d["t_simulation_s"], d["Vout_V"]
    n = len(t)
    c, a, p = config["capture"], config["acceptance"], config["parameters"]
    if n < a["min_samples"]:
        raise ValueError(f"Insufficient samples: {n}; required at least {a['min_samples']}")
    dt = median(b-a0 for a0, b in zip(t, t[1:]))
    rate, duration = 1/dt, t[-1]-t[0]+dt
    eps = max(1e-10, dt*1e-5)
    end = c["start_s"]+c["duration_s"]
    final_start = end-a["steady_window_s"]
    checks = []
    def check(name, passed, observed, expected, limit=None, kind="performance"):
        checks.append({"name": name, "passed": bool(passed), "observed": observed,
                       "expected": expected, "limit": limit, "kind": kind})
    check("sample_count", n == round(c["duration_s"]*c["sample_rate_hz"]), n,
          round(c["duration_s"]*c["sample_rate_hz"]), kind="data")
    check("sample_rate", abs(rate-c["sample_rate_hz"])/c["sample_rate_hz"] <= .01,
          rate, c["sample_rate_hz"], .01, "data")
    check("capture_duration", abs(duration-c["duration_s"]) <= max(dt, c["duration_s"]*.01),
          duration, c["duration_s"], max(dt, c["duration_s"]*.01), "data")
    check("capture_start", abs(t[0]-c["start_s"]) <= dt+eps, t[0], c["start_s"], dt, "data")
    final_indices = [i for i, v in enumerate(t) if final_start-eps <= v < end-eps]
    if len(final_indices) < max(2, round(a["steady_window_s"]*rate*.99)):
        raise ValueError("final steady-state window is incomplete")
    target = p["reference_voltage_v"]
    declared = config["events"][0] if config["events"] else None
    if declared and declared["target"] == "reference_voltage_v":
        target = declared["value"]
    final_mean = _mean([y[i] for i in final_indices])
    signed_error = final_mean-target
    relative_error = abs(signed_error)/abs(target)
    check("steady_state_error", relative_error <= a["steady_state_relative_error"],
          relative_error, 0, a["steady_state_relative_error"])
    records, response = [], {}
    # SP observer outputs may initialize on the first control tick. Keep these
    # raw samples; exclude only the first two control/sample periods from level checks.
    observer_ready = 2*max(CONTROL_PERIOD_S, dt)
    observed = None
    observed_index = None
    for e in config["events"]:
        ref_event = e["target"] == "reference_voltage_v"
        column = "ReferenceApplied_V" if ref_event else "VinMeasured_V"
        trace = d[column]
        initial, final = p[e["target"]], e["value"]
        direction = 1 if final > initial else -1
        candidates = [i for i, (ti, value) in enumerate(zip(t, trace))
                      if ti >= observer_ready-eps and direction*(value-initial) >= abs(final-initial)/2]
        idx = candidates[0] if candidates else None
        observed = t[idx] if idx is not None else None
        observed_index = idx
        interval = [t[idx-1], t[idx]] if idx is not None and idx > 0 else None
        scheduled = round(e["at_s"]/CONTROL_PERIOD_S)*CONTROL_PERIOD_S
        timing = (interval is not None and interval[0]-eps <= scheduled <= interval[1]+eps
                  and observed <= scheduled+max(CONTROL_PERIOD_S, dt)+eps)
        before = [v for ti, v in zip(t, trace) if observer_ready-eps <= ti < (observed if observed is not None else scheduled)-eps]
        after = trace[idx:] if idx is not None else []
        levels = (bool(before) and bool(after) and all(abs(v-initial) <= LEVEL_TOLERANCE_V for v in before)
                  and all(abs(v-final) <= LEVEL_TOLERANCE_V for v in after))
        check("event_observed", idx is not None, observed, scheduled, kind="event")
        check("event_timing", timing, interval, scheduled, max(CONTROL_PERIOD_S, dt), "event")
        check("event_levels", levels, {"before_mean_v": _mean(before) if before else None,
                                      "after_mean_v": _mean(after) if after else None},
              {"before_v": initial, "after_v": final}, LEVEL_TOLERANCE_V, "event")
        records.append({"target": e["target"], "requested_at_s": e["at_s"], "scheduled_at_s": scheduled,
            "mechanism": "model_step" if ref_event else "source_executeAt", "signal_column": column,
            "model_step_trigger_at_s": (round(e["at_s"]/CONTROL_PERIOD_S)-1)*CONTROL_PERIOD_S if ref_event else None,
            "pipeline_compensation_s": CONTROL_PERIOD_S if ref_event else 0,
            "expected_before_v": initial, "expected_after_v": final, "observed_at_s": observed,
            "observed_interval_s": interval, "time_resolution_s": dt,
            "observed_before_mean_v": _mean(before) if before else None,
            "observed_after_mean_v": _mean(after) if after else None,
            "status": "passed" if idx is not None and timing and levels else "error"})
        pre = [i for i, ti in enumerate(t) if scheduled-a["pre_event_window_s"]-eps <= ti < scheduled-eps]
        if len(pre) < max(2, round(a["pre_event_window_s"]*rate*.99)):
            raise ValueError("pre-event window is incomplete")
        pre_mean = _mean([y[i] for i in pre])
        pre_error = abs(pre_mean-p["reference_voltage_v"])/abs(p["reference_voltage_v"])
        check("pre_event_steady_state", pre_error <= a["pre_event_relative_error"], pre_error, 0, a["pre_event_relative_error"])
        settling = None
        reason = "event_not_observed"
        overshoot = deviation = None
        if idx is not None:
            bad = [i for i in range(idx, n) if abs(y[i]-target) > abs(target)*a["settling_band_relative"]]
            start = bad[-1]+1 if bad else idx
            if start < n:
                settling = max(0.0, t[start]-observed)
                reason = None
            else:
                reason = "not_settled_within_capture"
            deviation = max(abs(v-target) for v in y[idx:])/abs(target)
            if ref_event:
                delta = e["value"]-p["reference_voltage_v"]
                overshoot = max(0.0, max((1 if delta > 0 else -1)*(v-target) for v in y[idx:]))/abs(delta)
        check("settling_time", settling is not None and settling <= a["max_settling_time_s"]+eps,
              settling, 0, a["max_settling_time_s"])
        if ref_event:
            check("reference_overshoot", overshoot is not None and overshoot <= a["max_overshoot_fraction"],
                  overshoot, 0, a["max_overshoot_fraction"])
        else:
            check("disturbance_peak_deviation", deviation is not None and deviation <= a["max_deviation_relative"],
                  deviation, 0, a["max_deviation_relative"])
        response = {"pre_event_mean_v": pre_mean, "pre_event_relative_error": pre_error,
                    "settling_time_s": settling, "settling_reason": reason,
                    "settling_band_v": [target*(1-a["settling_band_relative"]), target*(1+a["settling_band_relative"])],
                    "overshoot_fraction_of_step": overshoot, "maximum_deviation_relative": deviation,
                    "observed_event_at_s": observed,
                    "pre_event_window_s": [scheduled-a["pre_event_window_s"], scheduled]}
    for field, column in (("reference_voltage_v", "ReferenceApplied_V"), ("input_voltage_v", "VinMeasured_V")):
        if not declared or declared["target"] != field:
            values = [v for ti, v in zip(t, d[column]) if ti >= observer_ready-eps]
            check(f"{field}_held", bool(values) and all(abs(v-p[field]) <= LEVEL_TOLERANCE_V for v in values),
                  {"min_v": min(values) if values else None, "max_v": max(values) if values else None},
                  p[field], LEVEL_TOLERANCE_V, "event")
    state = "error" if any(not x["passed"] and x["kind"] in {"data", "event"} for x in checks) else (
            "passed" if all(x["passed"] for x in checks) else "failed")
    return {"schema_version": 2, "model": "boost_closed_loop", "backend": "virtual_hil", "status": state,
        "source_csv": Path(csv_path).name, "sample_count": n, "sample_rate_hz": rate,
        "capture": {"sample_count": n, "sample_rate_hz": rate, "duration_s": duration, "span_s": t[-1]-t[0],
                    "first_simulation_time_s": t[0], "last_simulation_time_s": t[-1]},
        "signals": {"Vout_V": {"unit": "V", "steady_mean": final_mean, "target_v": target,
                    "signed_error_v": signed_error, "relative_steady_error": relative_error},
                    "Iin_A": {"unit": "A", "mean": _mean(d["Iin_A"]),
                              "steady_mean": _mean([d["Iin_A"][i] for i in final_indices]),
                              "sampled_peak_abs": max(abs(v) for v in d["Iin_A"]), "peak_scope": "maximum of captured samples"}},
        "events": records, "response": response, "checks": checks,
        "analysis": {"steady_window_s": [final_start, end], "settling_definition": "first sample inside target +/- configured band, remaining inside until capture end; measured from observed event",
            "overshoot_definition": "directional excess beyond final target divided by absolute reference step",
            "filtering": "none", "interpolation": "none", "missing_values": "reject",
            "observer_initialization_exclusion_s": observer_ready,
            "event_level_tolerance_v": LEVEL_TOLERANCE_V,
            "warnings": ["Input current peak is a sampled peak at the recorded rate, not a continuous PWM peak."]}}
