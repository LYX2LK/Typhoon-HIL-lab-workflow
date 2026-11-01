"""Code-owned Agent case catalog and evidence adapters; no dynamic imports from metadata."""
from copy import deepcopy
from pathlib import Path
from .boost_ai import read
from .utils import PROJECT, sha256, write_json
from .analysis import load_waveforms
from .external_records import analyze_external
from .waveform_diagnosis import run_diagnosis
from .rectifier_fault import MODEL, COLUMNS, configuration, analyze_bridge, prepare_model

BOOST = "boost_input_disturbance"
WAVEFORMS = "oscilloscope_tu"
BRIDGE = "rectifier_diode_open"
CASES = {
    BOOST: {"id": BOOST, "title": "Boost 输入跌落", "source_kind": "virtual_hil",
            "description": "判断输出电压偏差，评估启动残余解释，通过确认后的对照更新结论。",
            "conditions": "35→28 V 输入 · 50 V 参考 · 10 kHz · 首轮采集 1.5 s",
            "start_action": "运行 Boost 并分析", "placeholder": "例如：分析输出下冲，并建议怎样验证启动残余解释。",
            "default_question": "请判断 Boost 输入跌落后输出偏差是否超限，结合波形评估启动残余解释，并提出下一步验证。",
            "scope": "Typhoon Virtual HIL 软件实验；对照运行需确认。"},
    WAVEFORMS: {"id": WAVEFORMS, "title": "示例波形", "source_kind": "external_waveforms",
            "description": "分析四组示波器 CSV，识别电平跌落与上升过程回落，比较两组对应波形。",
            "conditions": "四组原始 CSV 与截图 · μs 时间显示 · 固定规则与原始时间轴",
            "start_action": "导入四组波形并分析", "placeholder": "例如：比较两组正常和异常波形，指出异常的位置与幅度。",
            "default_question": "请先概览四组示例波形，说明正常或异常及主要异常位置，再建议需要进一步查看的波形。",
            "scope": "原始采集数据的形态分析；逐文件参考标签为推断，测点与器件原因待确认。"},
    BRIDGE: {"id": BRIDGE, "title": "整流桥二极管开路", "source_kind": "virtual_hil",
            "description": "运行三相整流桥的两个工况，根据电压和三相电流识别导通缺失，再查看注入记录核对。",
            "conditions": "230 V 相电压有效值 · 50 Hz ABC · 100 Ω · 20 kHz · 采集 0.3 s",
            "start_action": "运行整流桥对照并分析", "placeholder": "例如：从三相电流判断哪个导通方向缺失，并解释输出纹波的变化。",
            "default_question": "请先依据两个记录的电压和三相电流判断异常，定位缺失的导通方向，解释直流输出差异并提出对照建议。",
            "scope": "公开研究问题的简化 Virtual HIL 复现；分析窗口为最后 0.2 s，对照运行需确认。"},
}


def catalog():
    return deepcopy(list(CASES.values()))


def case_spec(case_id):
    if case_id not in CASES:
        raise ValueError("未知案例，请从三个案例中选择")
    return deepcopy(CASES[case_id])


def prepare_waveforms(root):
    data = Path(root) / "data"
    data.mkdir()
    analyze_external(PROJECT / "configs/external_tu_intake.json", PROJECT.parent / "docs/tu/tu", data / "import")
    run_diagnosis(data / "import", PROJECT / "configs/tu_diagnosis_rules.json", data / "diagnosis")
    path = data / "diagnosis"
    return {rid: {"id": rid, "path": path.relative_to(root).as_posix(), "source_kind": "external_waveforms",
                  "record_id": rid, "manifest_sha256": sha256(path / "manifest.json"),
                  "record_status": "passed", "experiment_status": None, "plan_id": None}
            for rid in ("tu1", "tu2", "tu3", "tu4")}


def evidence_for(case_id, entry, root):
    path = Path(root) / entry["path"]
    if case_id == BOOST:
        from .boost_agent_tools import evidence_for as boost_evidence
        return boost_evidence(entry, root)
    if case_id == WAVEFORMS:
        diagnosis = read(path / "diagnosis.json")
        prediction = next(x for x in diagnosis["records"] if x["id"] == entry["record_id"])
        profile = next(x for x in read(path / "source/profile.json")["records"] if x["id"] == entry["record_id"])
        record = next(x for x in read(path / "source/intake.json")["records"] if x["id"] == entry["record_id"])
        return {"run_id": entry["id"], "case_id": case_id, "classification": prediction["classification"],
                "family": prediction["family"], "metrics": prediction["evidence"], "events": prediction["events"],
                "reason": prediction["reason"], "sample_count": profile["rows"],
                "metadata": record["metadata"], "record_status": "passed", "experiment_status": None,
                "source_csv_sha256": sha256(path / "source" / record["csv"]),
                "source_manifest_sha256": sha256(path / "manifest.json"),
                "detail_window_s": record["detail_window"], "performance_status": "not_evaluated",
                "scope": "规则仅识别形态；测点和具体原因未确认，参考标签不参与预测。"}
    if case_id == BRIDGE:
        config = read(path / "config.json")
        metrics = analyze_bridge(path / "waveforms.csv", config)
        # Fault injection, analytical template choice and reference errors stay outside model input.
        visible = {name: {k: v for k, v in values.items() if k != "normalized_rmse"}
                   for name, values in metrics["signals"].items()}
        return {"run_id": entry["id"], "case_id": case_id,
                "classification": "abnormal" if metrics["missing_conduction_directions"] else "normal",
                "metrics": visible, "missing_conduction_directions": metrics["missing_conduction_directions"],
                "source_conditions": {"source": config["source"], "circuit": config["circuit"]},
                "analysis_window_relative_s": metrics["analysis_window_relative_s"],
                "sample_count": metrics["sample_count"], "analysis_samples": metrics["analysis_samples"],
                "record_status": entry["record_status"], "experiment_status": entry["experiment_status"],
                "source_manifest_sha256": sha256(path / "manifest.json"), "source_csv_sha256": sha256(path / "waveforms.csv"),
                "scope": "导通方向来自原始电流；输入不含注入配置。只对当前简化电路解释。"}
    raise ValueError("unsupported case")


def compare(case_id, evidence, run_ids, version=1):
    if not isinstance(run_ids, list) or len(run_ids) < 2 or len(set(run_ids)) != len(run_ids) or any(x not in evidence for x in run_ids):
        raise ValueError("比较需要至少两个本会话中不同的记录")
    if case_id == BOOST:
        from .boost_agent_tools import compare as boost_compare
        return boost_compare(evidence, run_ids)
    if any(evidence[x]["case_id"] != case_id for x in run_ids):
        raise ValueError("禁止跨案例比较")
    if case_id == WAVEFORMS and version == 2:
        from .agent_comparison import comparison
        return comparison({rid: evidence[rid] for rid in run_ids})
    if version != 1:
        raise ValueError("不支持的比较工具版本")
    return {"case_id": case_id, "rows": [deepcopy(evidence[x]) for x in run_ids],
            "method": "使用各文件原始时间轴和固定分析窗口；不插值、不假设文件同步。" if case_id == WAVEFORMS else
                      "相同源、负载、采样和最后 0.2 s 窗口；方向、均值和纹波来自原始 CSV。"}


def series(case_id, entry, root):
    path = Path(root) / entry["path"]
    if case_id == WAVEFORMS:
        from .external_waveforms import read_csv
        record = next(x for x in read(path / "source/intake.json")["records"] if x["id"] == entry["record_id"])
        a = read_csv(path / "source" / record["csv"], record["format"])
        return {"time": a[:, 0], "voltage": a[:, 1], "detail": record["detail_window"],
                "image": path / "source" / record["image"]}
    d = load_waveforms(path / "waveforms.csv", ("t_relative_s", "t_simulation_s", *COLUMNS))
    return {"time": d["t_relative_s"], "voltage": d["Vdc_V"],
            "currents": {x: d[x] for x in ("Ia_A", "Ib_A", "Ic_A")}}


def build_config(case_id, arguments, runs, root):
    if case_id == BOOST:
        from .boost_agent_tools import build_config as boost_config
        return boost_config(arguments, runs, root)
    if case_id != BRIDGE or not isinstance(arguments, dict) or set(arguments) != {"operation", "reference_run"}:
        raise ValueError("本案例没有该实验操作")
    ref = arguments["reference_run"]
    if ref not in runs:
        raise ValueError("引用记录不存在")
    base = read(Path(root) / runs[ref]["path"] / "config.json")
    op = arguments["operation"]
    if op == "repeat":
        config = deepcopy(base)
    elif op in ("baseline", "fault"):
        config = configuration("none" if op == "baseline" else "A_upper_open")
    else:
        raise ValueError("未知整流桥实验动作")
    from .boost_ai import differences
    return config, 0.0, differences(base, config)
