"""Three-phase diode bridge: reproducible schematic and independent ideal reference."""
from copy import deepcopy
from pathlib import Path
import html
import json
import math
import numpy as np
from .utils import PROJECT, sha256, write_json
from .analysis import load_waveforms

MODEL = "three_phase_rectifier_fault"
SOURCE = "https://unbscholar.lib.unb.ca/items/1481f82f-78d4-4fe2-a52d-489c0a3f4dd4"
COLUMNS = ("Va_V", "Vb_V", "Vc_V", "Ia_A", "Ib_A", "Ic_A", "Vdc_V", "Iload_A")


def configuration(fault="none"):
    return {"schema_version": 1, "model": MODEL, "backend": "virtual_hil",
            "source": {"rms_v": 230.0, "frequency_hz": 50.0, "phase_deg": 0.0},
            "circuit": {"load_ohm": 100.0}, "fault": fault,
            "capture": {"settle_s": 0.0, "duration_s": .3, "sample_rate_hz": 20000.0, "wall_timeout_s": 180.0},
            "acceptance": {"normalized_rmse": .02, "min_samples": 6000}}


def build_model(destination):
    """Six independent LC diodes on HIL404 Pro 3; no output filter."""
    from typhoon.api.schematic_editor import SchematicAPI
    api = SchematicAPI()
    try:
        api.create_new_model(name="Three phase diode bridge diagnostic example")
        api.set_model_property_value("hil_device", "HIL404")
        api.set_model_property_value("hil_configuration_id", 3)
        api.set_model_property_value("simulation_time_step", 2.5e-7)
        parts = {}
        def part(kind, name, x, y):
            parts[name] = api.create_component("core/" + kind, name=name, position=(x, y))
            return parts[name]
        def terminal(name, pin):
            return api.term(parts[name], pin)
        def join(a, b):
            if api.create_connection(a, b) is False:
                raise RuntimeError("could not connect bridge schematic")
        neutral = api.create_junction(name="Neutral", position=(7400, 8500))
        plus = api.create_junction(name="DC_plus", position=(8500, 7700))
        minus = api.create_junction(name="DC_minus", position=(8500, 8500))
        ground = part("Ground", "Ground", 7200, 8500)
        join(api.term(ground, "node"), neutral)
        for index, phase in enumerate("abc"):
            x = 7600 + index * 300
            part("Voltage Source", "Source_" + phase, x, 8900)
            part("Current Measurement", "I" + phase, x, 8300)
            part("Voltage Measurement", "V" + phase, x - 100, 8700)
            upper = part("Diode", "D_" + phase + "p", x, 7900)
            lower = part("Diode", "D_" + phase + "n", x, 8100)
            for diode in (upper, lower):
                api.set_property_value(api.prop(diode, "switches_option"), False)
                api.set_property_value(api.prop(diode, "resistance"), 1.0)
            ac = api.create_junction(name="Phase_" + phase, position=(x + 100, 8350))
            join(terminal("Source_" + phase, "n_node"), neutral)
            join(terminal("Source_" + phase, "p_node"), terminal("I" + phase, "p_node"))
            join(terminal("I" + phase, "n_node"), ac)
            join(terminal("D_" + phase + "p", "A"), ac)
            join(terminal("D_" + phase + "p", "K"), plus)
            join(terminal("D_" + phase + "n", "A"), minus)
            join(terminal("D_" + phase + "n", "K"), ac)
            join(terminal("V" + phase, "p_node"), terminal("Source_" + phase, "p_node"))
            join(terminal("V" + phase, "n_node"), neutral)
        part("Current Measurement", "Iload", 8900, 7800)
        part("Resistor", "Rload", 8900, 8200)
        part("Voltage Measurement", "Vdc", 9200, 8100)
        api.set_property_value(api.prop(parts["Rload"], "resistance"), 100.0)
        join(plus, terminal("Iload", "p_node"))
        join(terminal("Iload", "n_node"), terminal("Rload", "p_node"))
        join(terminal("Rload", "n_node"), minus)
        join(terminal("Vdc", "p_node"), plus)
        join(terminal("Vdc", "n_node"), minus)
        if api.save_as(filename=str(destination)) is False:
            raise RuntimeError("could not save bridge schematic")
    finally:
        api.close_model()


def prepare_model():
    path = PROJECT / "models" / (MODEL + ".tse")
    origins = json.loads((PROJECT / "models/origin.json").read_text(encoding="utf-8"))
    if MODEL in origins:
        if not path.is_file() or sha256(path) != origins[MODEL]["sha256"]:
            raise ValueError("self-built rectifier template missing or changed; preserve and resolve its origin")
        return path
    if path.exists():
        raise ValueError("unregistered rectifier template already exists")
    build_model(path)
    origins[MODEL] = {"kind": "self_built", "thcc_version": "2026.3", "sha256": sha256(path),
                     "generator": "src/typhoon_lab/rectifier_fault.py", "reference_url": SOURCE,
                     "scope": "Simplified six-diode resistive bridge; not the thesis system or classifier."}
    write_json(PROJECT / "models/origin.json", origins)
    return path


def ideal_reference(voltages, load, fault="none"):
    """Algebraic conduction reference, independent of Typhoon and run labels."""
    v = np.asarray(voltages, dtype=float)
    upper = np.argmax(v if fault == "none" else np.vstack((np.full(v.shape[1], -np.inf), v[1:])), axis=0)
    lower = np.argmin(v, axis=0)
    indices = np.arange(v.shape[1])
    dc = np.maximum(0, v[upper, indices] - v[lower, indices])
    current = dc / load
    # Ideal equal-potential branches share current; tolerate float32 source quantization.
    top_v = v if fault == "none" else np.vstack((np.full(v.shape[1], -np.inf), v[1:]))
    top = np.abs(top_v - top_v.max(axis=0)) < 1e-4
    bottom = np.abs(v - v.min(axis=0)) < 1e-4
    phases = current * (top / top.sum(axis=0) - bottom / bottom.sum(axis=0))
    return dc, current, phases


def analyze_bridge(path, config):
    data = load_waveforms(path, ("t_relative_s", "t_simulation_s", *COLUMNS))
    t = np.asarray(data["t_relative_s"])
    if len(t) != 6000 or not math.isclose(float(np.median(np.diff(t))), 1 / 20000, rel_tol=1e-7, abs_tol=1e-12):
        raise ValueError("bridge CSV must contain 6000 samples on the original 20 kHz grid")
    mask = (t >= t[0] + .1 - 1e-10) & (t < t[0] + .3 - 1e-10)
    v = np.asarray([data[x] for x in COLUMNS[:3]])[:, mask]
    dc, load, phases = ideal_reference(v, config["circuit"]["load_ohm"], config["fault"])
    references = {"Vdc_V": dc, "Iload_A": load, **dict(zip(COLUMNS[3:6], phases))}
    metrics, checks = {}, []
    for name, reference in references.items():
        actual = np.asarray(data[name])[mask]
        scale = float(np.max(np.abs(reference)))
        # A disconnected direction may be zero; phase references still have nonzero RMS.
        error = float(np.sqrt(np.mean((actual - reference) ** 2)) / max(scale, 1e-12))
        metrics[name] = {"mean": float(actual.mean()), "rms": float(np.sqrt(np.mean(actual ** 2))),
                         "minimum": float(actual.min()), "maximum": float(actual.max()),
                         "peak_to_peak": float(np.ptp(actual)), "normalized_rmse": error}
        checks.append({"name": name + "_reference", "passed": error <= config["acceptance"]["normalized_rmse"],
                       "value": error, "limit": config["acceptance"]["normalized_rmse"]})
    missing = []
    for phase, name in zip("ABC", COLUMNS[3:6]):
        actual = np.asarray(data[name])[mask]
        scale = float(max(np.max(np.abs(actual)), 1e-12))
        if actual.max() < .02 * scale:
            missing.append(phase + "_positive")
        if -actual.min() < .02 * scale:
            missing.append(phase + "_negative")
    checks.append({"name": "minimum_samples", "passed": len(t) >= config["acceptance"]["min_samples"], "value": len(t)})
    return {"status": "passed" if all(c["passed"] for c in checks) else "failed", "sample_count": len(t),
            "analysis_window_relative_s": [.1, .3], "analysis_samples": int(mask.sum()), "signals": metrics,
            "missing_conduction_directions": missing, "checks": checks,
            "method": "Last 0.2 s; ideal conducting upper maximum/lower minimum; NRMSE divided by reference peak. No interpolation.",
            "scope": "Numerical agreement with simplified circuit; not equipment acceptance or independent diagnostic accuracy."}


class BridgeAdapter:
    model_id = MODEL
    schema_version = 1
    has_events = False
    capture_before_start = True
    signals = ("Va", "Vb", "Vc", "Ia", "Ib", "Ic", "Vdc", "Iload")
    columns = COLUMNS
    units = {x: "V" if x.endswith("_V") else "A" for x in COLUMNS}
    sources = ("Source_a", "Source_b", "Source_c")
    changes = ["Compile-time deletion of D_ap for A-upper diode open circuit; other five diodes unchanged."]
    numeric_rules = {"source": {"rms_v": (230, 230), "frequency_hz": (50, 50), "phase_deg": (0, 0)},
                     "circuit": {"load_ohm": (100, 100)},
                     "capture": {"settle_s": (0, 0), "duration_s": (.3, .3), "sample_rate_hz": (20000, 20000), "wall_timeout_s": (30, 300)},
                     "acceptance": {"normalized_rmse": (.02, .02), "min_samples": (6000, 6000)}}
    setting_stages = {"source": "after_load_before_start", "circuit": "model_copy_before_compile",
                      "capture": "capture_setup", "acceptance": "analysis_only"}
    event_capabilities = {"max_per_run": 0, "targets": {}}
    conditional_constraints = ["fixed_reference_conditions", "fault_none_or_A_upper_open"]

    def validate(self, raw, sweep=False):
        if sweep or not isinstance(raw, dict) or raw.get("fault") not in ("none", "A_upper_open"):
            raise ValueError("bridge supports fixed healthy or A-upper-open configurations")
        if type(raw.get("schema_version")) is not int:
            raise ValueError("schema version must be an integer")
        expected = configuration(raw["fault"])
        if set(raw) != set(expected):
            raise ValueError("unexpected bridge configuration fields")
        for key in expected:
            if key != "capture" and raw[key] != expected[key]:
                raise ValueError("bridge reference configuration is fixed: " + key)
        cap = raw["capture"]
        if not isinstance(cap, dict) or set(cap) != set(expected["capture"]):
            raise ValueError("invalid bridge capture")
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in cap.values()):
            raise ValueError("capture values must be finite numbers")
        if any(cap[k] != expected["capture"][k] for k in cap if k != "wall_timeout_s") or not 30 <= cap["wall_timeout_s"] <= 300:
            raise ValueError("bridge capture conditions are fixed")
        return deepcopy(raw)

    def inspect_parameters(self, api):
        return {"load_ohm": float(api.get_property_value(api.prop(api.get_item("Rload"), "resistance"))),
                "D_ap_present": api.get_item("D_ap") is not None}

    def prepare(self, api, config):
        if config["fault"] == "A_upper_open":
            api.delete_item(api.get_item("D_ap"))
        actual = self.inspect_parameters(api)
        if actual != {"load_ohm": 100.0, "D_ap_present": config["fault"] == "none"}:
            raise ValueError("bridge model readback differs")
        return actual

    def initialize(self, hil, config):
        from .runtime import require
        settings = {}
        for name, phase in zip(self.sources, (0, -120, 120)):
            require(hil.set_source_sine_waveform(name, rms=230, frequency=50, phase=phase, harmonics_pu=()), "set bridge source")
            actual = hil.get_source_settings(name)
            if any(not math.isclose(float(actual[k]), v, abs_tol=1e-9) for k, v in (("rms", 230), ("frequency", 50), ("phase", phase))):
                raise ValueError("bridge source readback differs")
            settings[name] = actual
        return {"actual_source_settings": settings}

    def schedule(self, hil, config):
        return []

    def check_sampling(self, rate, count, config):
        if not math.isclose(rate, 20000, abs_tol=1e-6) or count != 6000:
            raise ValueError("bridge requires 6000 samples at 20 kHz")

    def analyze(self, path, config):
        return analyze_bridge(path, config)

    def report(self, path, manifest):
        path = Path(path)
        metrics = json.loads((path / "metrics.json").read_text(encoding="utf-8")) if (path / "metrics.json").exists() else {}
        title = "三相整流桥二极管开路：简化模型数值验证"
        text = "# " + title + "\n\n公开问题依据：" + SOURCE + "\n\n" + json.dumps(metrics, ensure_ascii=False, indent=2)
        (path / "report.md").write_text(text, encoding="utf-8")
        (path / "report.html").write_text('<!doctype html><meta charset="utf-8"><h1>' + title + '</h1><pre>' + html.escape(text) + '</pre>', encoding="utf-8")
        return [path / "report.html", path / "report.md"]
