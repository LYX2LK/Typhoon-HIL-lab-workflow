"""Small, independent schematic-to-waveform exercise for a self-built RLC model."""

from pathlib import Path
import json
import math
import shutil
import time
import traceback

import numpy as np

from .analysis import expected_rlc_rms, load_waveforms
from .runtime import api_modules, cleanup, environment, no_active_simulation, require, snapshot_code, wait_sim
from .utils import PROJECT, finalize, new_run, note, now, runtime_lock, sha256, write_json


def _validated_practice_source(value):
    path = Path(value)
    path = (path if path.is_absolute() else PROJECT / path).resolve()
    allowed = (PROJECT / "results" / "agent-tasks").resolve()
    if not path.is_relative_to(allowed) or path.name != "rlc_handbuilt.tse" or not path.is_file():
        raise ValueError("practice source must be an existing rlc_handbuilt.tse under results/agent-tasks")
    return path


def recompute_practice(path):
    """Recompute the complete five-column capture without touching its raw CSV."""
    path = Path(path)
    config = json.loads((path / "config.json").read_text(encoding="utf-8"))
    columns = ("t_relative_s", "t_simulation_s", "I_A", "Va1_V", "V_Rin_V")
    data = load_waveforms(path / "waveforms.csv", columns)
    count = len(data["I_A"])
    if count < config["acceptance"]["minimum_samples"]:
        raise ValueError("insufficient practice samples")
    analytic = expected_rlc_rms(config)
    measured = {key: float(np.sqrt(np.mean(np.asarray(data[key], dtype=float) ** 2)))
                for key in ("I_A", "Va1_V", "V_Rin_V")}
    reference = {"I_A": analytic["I_A"], "Va1_V": analytic["Va1_V"],
                 "V_Rin_V": analytic["I_A"] * config["circuit"]["rin_ohm"]}
    errors = {key: abs(measured[key] - reference[key]) / reference[key] for key in measured}
    threshold = config["acceptance"]["max_relative_rms_error"]
    return {"measured_rms": measured, "analytic_rms": reference,
            "relative_errors": errors, "sample_count": count,
            "status": "passed" if all(value <= threshold for value in errors.values()) else "failed",
            "method": "RMS of every raw sample; sinusoidal phasor for Rin + [L || (R+C)]"}


def write_practice_report(path, manifest):
    path = Path(path)
    metrics = json.loads((path / "metrics.json").read_text(encoding="utf-8"))
    lines = ["# 自建 RLC 模型练习", "",
             f"Virtual HIL 实验状态：**{manifest['status']}**。", "",
             "模型从空白原理图建立，Rin 从 5 Ω 改为 8 Ω；新增 V_Rin 测量点并采集。", "",
             f"采样：{metrics['sample_count']} 点；全部原始样本参与 RMS 计算；判据为每个信号相对误差 ≤ 3%。", "",
             "| 信号 | 采样 RMS | 解析 RMS | 相对误差 |", "|---|---:|---:|---:|"]
    for key in ("I_A", "Va1_V", "V_Rin_V"):
        lines.append(f"| {key} | {metrics['measured_rms'][key]:.9g} | "
                     f"{metrics['analytic_rms'][key]:.9g} | {metrics['relative_errors'][key]:.6%} |")
    lines += ["", "原始数据：[waveforms.csv](waveforms.csv)；配置：[config.json](config.json)；"
              "编译和实际信号见 [manifest.json](manifest.json)。", "",
              "本记录仅证明软件 Virtual HIL 运行，图形界面的人工建模操作需由组员独立练习。"]
    report = path / "report.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [report]


def run_practice(source):
    source = _validated_practice_source(source)
    path = new_run("modeling-practice")
    manifest = {"schema_version": 1, "kind": "modeling_practice", "model": "self_built_rlc",
                "backend": "virtual_hil", "started_at": now(), "status": "error",
                "source_model": str(source.relative_to(PROJECT)), "source_sha256": sha256(source),
                "criterion": {"max_relative_rms_error": 0.03, "minimum_samples": 256}}
    api = hil = None
    started = capturing = False
    lock = runtime_lock()
    locked = False
    try:
        lock.__enter__()
        locked = True
        api, hil = api_modules()
        manifest["environment"] = environment()
        manifest["code_sha256"] = snapshot_code(path)
        builder = PROJECT / "scripts" / "build_rlc_practice.py"
        builder_snapshot = path / "code_snapshot" / "scripts" / builder.name
        builder_snapshot.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(builder, builder_snapshot)
        manifest["code_sha256"]["scripts/build_rlc_practice.py"] = sha256(builder)
        no_active_simulation(hil)
        model_path = path / "model.tse"
        shutil.copy2(source, path / "source_model.tse")
        shutil.copy2(source, model_path)
        require(api.load(filename=str(model_path)), "load self-built schematic")
        for name in ("Vs1", "Rin", "R", "L", "C", "I", "Va1", "V_Rin"):
            if api.get_item(name) is None:
                raise ValueError(f"self-built schematic lacks {name}")
        resistor = api.get_item("Rin")
        original = float(api.get_property_value(api.prop(resistor, "resistance")))
        if not math.isclose(original, 5, rel_tol=0, abs_tol=1e-12):
            raise ValueError("source Rin should be 5 ohm before the exercise change")
        api.set_property_value(api.prop(resistor, "resistance"), "8")
        changed = float(api.get_property_value(api.prop(resistor, "resistance")))
        if not math.isclose(changed, 8, rel_tol=0, abs_tol=1e-12):
            raise ValueError("Rin change did not read back as 8 ohm")
        require(api.save_as(filename=str(model_path)), "save changed schematic")
        manifest["parameter_change"] = {"Rin_ohm_before": original, "Rin_ohm_after": changed}
        require(api.compile(), "compile self-built schematic")
        manifest["compilation_messages"] = str(api.last_compilation_messages())
        cpd = api.get_compiled_model_file(str(model_path))
        require(hil.load_model(file=cpd, vhil_device=True), "load Virtual HIL")
        sources = [name for group in hil.get_sources() for name in group]
        signals = [name for group in hil.get_analog_signals() for name in group]
        required_signals = ["I", "Va1", "V_Rin"]
        manifest["discovered_sources"] = sources
        manifest["discovered_signals"] = signals
        if "Vs1" not in sources or any(name not in signals for name in required_signals):
            raise ValueError("compiled source or new measurement point was not discovered")
        require(hil.set_source_sine_waveform("Vs1", rms=10., frequency=1000., phase=0., harmonics_pu=()),
                "set 10 V RMS, 1000 Hz source")
        settings = hil.get_source_settings("Vs1")
        manifest["source_settings"] = settings
        for key, value in (("rms", 10.), ("frequency", 1000.), ("phase", 0.)):
            if not settings or not math.isclose(float(settings[key]), value, rel_tol=0, abs_tol=1e-8):
                raise ValueError(f"source setting readback differs: {key}")
        step = float(hil.get_sim_step())
        decimation = max(1, round(1 / (20000 * step)))
        rate = 1 / (step * decimation)
        count = int(round(.02 * rate / 2)) * 2
        if not 256 <= count <= 100000 or rate < 20000:
            raise ValueError("practice capture resolution is insufficient")
        require(hil.start_simulation(), "start self-built model")
        started = True
        settled = wait_sim(hil, .05, 60)
        buffer = []
        require(hil.start_capture([decimation, len(required_signals), count, False], ["Forced"],
                                  [required_signals, []], dataBuffer=buffer, timeFormat="absolute"),
                "capture all three measured signals")
        capturing = True
        deadline = time.monotonic() + 60
        while hil.capture_in_progress():
            if time.monotonic() > deadline:
                raise TimeoutError("practice capture exceeded 60 wall seconds")
            if hil.is_simulation_running() is not True:
                raise RuntimeError("simulation stopped during practice capture")
            time.sleep(.05)
        capturing = False
        if hil.timeout_occurred() or not buffer:
            raise RuntimeError("practice capture returned no complete data")
        names, values, times = buffer[0]
        values = np.asarray(values, dtype=float)
        relative = np.asarray(times["x_data"], dtype=float)
        if list(names) != required_signals or values.shape != (3, count) or relative.shape != (count,):
            raise ValueError("unexpected practice signal order or sample count")
        trigger = times["trigger_timestamp_sim_time"]
        if trigger is None or not np.all(np.isfinite(values)):
            raise ValueError("practice capture has missing timing or nonfinite data")
        simulation = relative + float(trigger) * 1e-9
        np.savetxt(path / "waveforms.csv", np.column_stack([relative, simulation, values.T]),
                   delimiter=",", header="t_relative_s,t_simulation_s,I_A,Va1_V,V_Rin_V",
                   comments="", fmt="%.17g")
        manifest["capture"] = {"signal_names": list(names), "sample_rate_hz": rate,
                                "number_of_samples": count, "settled_at_simulation_s": settled,
                                "simulation_step_s": step, "decimation": decimation,
                                "trigger_timestamp_sim_time_ns": trigger}
        require(hil.stop_simulation(), "stop practice simulation")
        started = False
        circuit = {"rin_ohm": changed}
        for name, key, output in (("R", "resistance", "branch_r_ohm"),
                                  ("L", "inductance", "l_h"), ("C", "capacitance", "c_f")):
            circuit[output] = float(api.get_property_value(api.prop(api.get_item(name), key)))
        config = {"source": {"rms_v": 10., "frequency_hz": 1000., "phase_deg": 0.},
                  "circuit": circuit,
                  "acceptance": {"max_relative_rms_error": .03, "minimum_samples": 256}}
        write_json(path / "config.json", config)
        metrics = recompute_practice(path)
        write_json(path / "metrics.json", metrics)
        manifest["status"] = metrics["status"]
        write_practice_report(path, manifest)
        note(path, f"Practice captured {count} samples; maximum RMS relative error={max(metrics['relative_errors'].values()):.6g}")
    except Exception as exc:
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        note(path, traceback.format_exc())
    finally:
        try:
            manifest["cleanup_issues"] = cleanup(hil, started, capturing, path) if hil is not None else []
        finally:
            if locked:
                lock.__exit__(None, None, None)
        if manifest["cleanup_issues"]:
            manifest["status"] = "error"
        write_json(path / "summary.json", {"status": manifest["status"],
                                          "source_model": manifest["source_model"],
                                          "parameter_change": manifest.get("parameter_change"),
                                          "capture": manifest.get("capture"),
                                          "error": manifest.get("error")})
        finalize(path, manifest)
    return path, manifest
