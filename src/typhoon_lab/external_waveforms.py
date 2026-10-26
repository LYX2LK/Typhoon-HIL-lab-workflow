"""Two-column external waveform intake; no simulator or device operations."""
import csv
import json
import math
import re
from pathlib import Path
import numpy as np
from .utils import sha256

TIME_UNITS = {"s": 1.0, "ms": 1e-3, "us": 1e-6, "ns": 1e-9}
VALUE_UNITS = {"V": ("V", 1.0), "mV": ("V", 1e-3), "A": ("A", 1.0), "mA": ("A", 1e-3)}
METHODS = {"summary", "dip", "rise"}


def relative_file(root, value):
    """Resolve local relative files, including symlink target checks."""
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ValueError(f"expected a relative POSIX path: {value!r}")
    rel = Path(value)
    base = Path(root).resolve()
    path = (base / rel).resolve()
    if rel.is_absolute() or ".." in rel.parts or not path.is_relative_to(base):
        raise ValueError(f"path leaves input directory: {value}")
    return path


def _keys(value, allowed, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    extra = set(value) - set(allowed)
    if extra:
        raise ValueError(f"{label}: unsupported fields {sorted(extra)}")


def _number(value, label):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return value


def _window(value, label):
    if value is not None:
        if not isinstance(value, list) or len(value) != 2:
            raise ValueError(f"{label} needs two endpoints")
        if _number(value[0], label) >= _number(value[1], label):
            raise ValueError(f"{label} endpoints must increase")


def validate_intake(data):
    _keys(data, {"schema_version", "dataset_id", "purpose", "records"}, "intake")
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("unsupported intake schema_version")
    for key in ("dataset_id", "purpose"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f"intake needs {key}")
    if not isinstance(data.get("records"), list) or not data["records"]:
        raise ValueError("intake needs nonempty records")
    ids = set()
    for rec in data["records"]:
        _keys(rec, {"id", "csv", "image", "format", "metadata", "analysis", "detail_window"}, "record")
        rid = rec.get("id")
        if not isinstance(rid, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", rid) or rid in ids:
            raise ValueError("record id must be unique letters/digits/underscore/hyphen")
        ids.add(rid)
        for key in ("csv", "image"):
            if key == "csv" or rec.get(key) is not None:
                relative_file(Path.cwd(), rec.get(key))
        fmt = rec.get("format")
        _keys(fmt, {"encoding", "header", "time_column", "value_column"}, f"{rid}.format")
        if fmt.get("encoding") != "utf-8-sig" or type(fmt.get("header")) is not bool:
            raise ValueError("supported format: UTF-8 CSV, explicit header boolean")
        if (type(fmt.get("time_column")) is not int or type(fmt.get("value_column")) is not int
                or {fmt["time_column"], fmt["value_column"]} != {0, 1}):
            raise ValueError("exactly two columns; time_column/value_column must be 0 and 1")
        meta = rec.get("metadata")
        _keys(meta, {"time_unit", "value_unit", "measurement_point", "channel", "probe_ratio",
                    "trigger", "label", "acquisition", "export", "image_pairing"}, f"{rid}.metadata")
        for key, field in meta.items():
            _keys(field, {"value", "status", "source"}, f"{rid}.{key}")
            if field.get("status") not in {"confirmed", "inferred", "unconfirmed"}:
                raise ValueError(f"{rid}.{key}: invalid metadata status")
            if not isinstance(field.get("source"), str):
                raise ValueError(f"{rid}.{key}: source must be text")
            if field["status"] != "unconfirmed" and (field.get("value") is None or not field["source"].strip()):
                raise ValueError(f"{rid}.{key}: known metadata needs value and source")
        for key, units in (("time_unit", TIME_UNITS), ("value_unit", VALUE_UNITS)):
            unit = meta.get(key, {}).get("value")
            if unit is not None and (not isinstance(unit, str) or unit not in units):
                raise ValueError(f"{rid}.{key}: unsupported unit {unit!r}")
        analysis = rec.get("analysis")
        _keys(analysis, {"method", "window", "baseline_fraction", "drop_fraction",
                        "low_fraction", "high_fraction"}, f"{rid}.analysis")
        method = analysis.get("method")
        if method not in METHODS:
            raise ValueError(f"unsupported analysis method: {method}")
        allowed = {"method", "window"}
        if method in {"dip", "rise"}:
            allowed.add("baseline_fraction")
            fraction = _number(analysis.get("baseline_fraction"), "baseline_fraction")
            if not 0 < fraction <= 0.5:
                raise ValueError("baseline_fraction must be in (0, 0.5]")
        if method == "dip":
            allowed.add("drop_fraction")
            if not 0 < _number(analysis.get("drop_fraction"), "drop_fraction") < 1:
                raise ValueError("drop_fraction must be in (0, 1)")
        if method == "rise":
            allowed.update(("low_fraction", "high_fraction"))
            lo = _number(analysis.get("low_fraction"), "low_fraction")
            hi = _number(analysis.get("high_fraction"), "high_fraction")
            if not 0 < lo < hi < 1:
                raise ValueError("rise fractions must satisfy 0 < low < high < 1")
        if set(analysis) - allowed:
            raise ValueError(f"{rid}: parameters do not apply to method {method}")
        _window(analysis.get("window"), "analysis.window")
        _window(rec.get("detail_window"), "detail_window")
    return data


def load_intake(path):
    return validate_intake(json.loads(Path(path).read_text(encoding="utf-8-sig")))


def read_csv(path, fmt):
    rows = []
    with Path(path).open(encoding=fmt["encoding"], newline="") as stream:
        reader = csv.reader(stream)
        if fmt["header"]:
            header = next(reader, None)
            if header is None or len(header) != 2:
                raise ValueError("header must have exactly two columns")
        for lineno, row in enumerate(reader, 2 if fmt["header"] else 1):
            if len(row) != 2:
                raise ValueError(f"line {lineno}: expected two columns, found {len(row)}")
            try:
                values = [float(v) for v in row]
            except ValueError as exc:
                raise ValueError(f"line {lineno}: invalid numeric value") from exc
            if not all(math.isfinite(v) for v in values):
                raise ValueError(f"line {lineno}: nonfinite value")
            rows.append([values[fmt["time_column"]], values[fmt["value_column"]]])
    if len(rows) < 3:
        raise ValueError(f"at least three samples required; found {len(rows)}")
    return np.asarray(rows, dtype=float)


def known(meta, key):
    field = meta.get(key, {})
    return field.get("value") if field.get("status") in {"confirmed", "inferred"} else None


def crossing(t, y, level):
    indices = np.flatnonzero((y[:-1] < level) & (y[1:] >= level)) + 1
    if not len(indices):
        return None
    i = int(indices[0])
    return {"last_below_s": float(t[i - 1]), "first_at_or_above_s": float(t[i])}


def features(t, y, analysis):
    method = analysis["method"]
    result = {"status": "computed", "method": method}
    if method == "summary":
        return result
    count = max(1, int(len(y) * analysis["baseline_fraction"]))
    low = float(np.median(y[:count]))
    high = float(np.median(y[-count:]))
    result["baseline_samples"] = count
    if method == "dip":
        if low <= 0:
            return {**result, "status": "not_applicable", "reason": "dip requires a positive starting baseline"}
        step = float(np.median(np.diff(t)))
        threshold = low * (1 - analysis["drop_fraction"])
        indices = np.flatnonzero(y < threshold)
        groups = np.split(indices, np.where(np.diff(indices) > 1)[0] + 1) if len(indices) else []
        group = max(groups, key=len) if groups else None
        result.update(baseline=low, threshold=threshold, max_drop=float(low - y.min()),
                      below_threshold_samples=int(len(indices)), longest_segment=None)
        if group is not None:
            result["longest_segment"] = {
                "first_sample_s": float(t[group[0]]), "last_sample_s": float(t[group[-1]]),
                "sample_count": int(len(group)), "sample_support_duration_s": float(len(group) * step),
                "duration_resolution_s": step}
    else:
        if high <= low:
            return {**result, "status": "not_applicable", "reason": "rise requires ending median above starting median"}
        c_low = crossing(t, y, low + analysis["low_fraction"] * (high - low))
        c_high = crossing(t, y, low + analysis["high_fraction"] * (high - low))
        result.update(low=low, high=high, crossing_low=c_low, crossing_high=c_high)
        if c_low is None or c_high is None or c_high["first_at_or_above_s"] <= c_low["first_at_or_above_s"]:
            return {**result, "status": "not_applicable",
                    "reason": "ordered, separately resolved first crossings are unavailable"}
        mask = (t >= c_low["last_below_s"]) & (t <= c_high["first_at_or_above_s"])
        selected = y[mask]
        result.update(first_crossing_interval_s=c_high["first_at_or_above_s"] - c_low["first_at_or_above_s"],
                      max_drawdown=float(np.max(np.maximum.accumulate(selected) - selected)),
                      largest_single_sample_fall=float(np.max(-np.diff(y))))
    return result


def analyze_record(root, rec):
    source = relative_file(root, rec["csv"])
    result = {"id": rec["id"], "csv": rec["csv"], "sha256": sha256(source),
              "metadata": rec["metadata"], "analysis": rec["analysis"],
              "data_quality_status": "failed", "performance_status": "not_evaluated",
              "feature": {"status": "not_evaluated", "method": rec["analysis"]["method"]}}
    if rec.get("image"):
        result["image_sha256"] = sha256(relative_file(root, rec["image"]))
    try:
        array = read_csv(source, rec["format"])
        t_raw, y_raw = array.T
        dt_raw = np.diff(t_raw)
        if np.any(dt_raw <= 0):
            raise ValueError("time must be strictly increasing; duplicate or reversed timestamp")
        time_unit = known(rec["metadata"], "time_unit")
        value_unit = known(rec["metadata"], "value_unit")
        time_scale = TIME_UNITS.get(time_unit)
        tolerance = max(1e-15 / time_scale if time_scale else 1e-15,
                        abs(float(np.median(dt_raw))) * 1e-4)
        if np.any(np.abs(dt_raw - np.median(dt_raw)) > tolerance):
            raise ValueError("nonuniform time intervals exceed declared rounding tolerance")
        result.update(data_quality_status="passed", rows=len(array),
                      raw_time_range=[float(t_raw[0]), float(t_raw[-1])],
                      raw_value_range=[float(y_raw.min()), float(y_raw.max())])
        window = rec["analysis"].get("window")
        mask = np.ones(len(array), dtype=bool) if window is None else (t_raw >= window[0]) & (t_raw <= window[1])
        result["analysis_samples"] = int(mask.sum())
        if time_scale is None or value_unit is None:
            result["feature"]["reason"] = "time/value units remain unconfirmed; only raw structure/ranges checked"
            return result, array
        canonical_unit, value_scale = VALUE_UNITS[value_unit]
        t, y = t_raw * time_scale, y_raw * value_scale
        step = float(np.median(np.diff(t)))
        result.update(units={"time": "s", "value": canonical_unit}, t_start_s=float(t[0]),
                      t_end_s=float(t[-1]), dt_median_s=step, csv_grid_rate_hz=1 / step,
                      min_value=float(y.min()), max_value=float(y.max()),
                      mean=float(y.mean()), std_population=float(y.std()))
        if result["analysis_samples"] < 3:
            result["feature"].update(status="not_applicable", reason="analysis window has fewer than three samples")
        else:
            result["feature"] = features(t[mask], y[mask], rec["analysis"])
        acquisition = known(rec["metadata"], "acquisition")
        if isinstance(acquisition, dict) and type(acquisition.get("sample_rate_hz")) in (int, float):
            rate = acquisition["sample_rate_hz"]
            if math.isfinite(rate) and rate > 0:
                result["acquisition_rate_matches_csv_grid"] = bool(np.isclose(1 / step, rate, rtol=1e-5))
        return result, array
    except (ValueError, UnicodeError, OverflowError) as exc:
        result["error"] = str(exc)
        return result, None


def analyze_dataset(root, intake):
    records, arrays = [], {}
    for rec in intake["records"]:
        result, array = analyze_record(root, rec)
        records.append(result)
        if array is not None:
            arrays[rec["id"]] = array
    quality = "passed" if all(r["data_quality_status"] == "passed" for r in records) else "failed"
    complete = quality == "passed" and all(r["feature"]["status"] == "computed" for r in records)
    return {"dataset_id": intake["dataset_id"], "purpose": intake["purpose"], "records": records,
            "data_quality_status": quality, "analysis_status": "completed" if complete else "incomplete",
            "performance_status": "not_evaluated"}, arrays
