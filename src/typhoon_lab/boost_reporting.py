"""Offline Boost reports: raw data, event evidence and predeclared checks."""
import html
import json
from pathlib import Path
from .analysis import load_waveforms
from .boost_analysis import COLUMNS
from .reporting import _json, _fmt, _status, _table, _md_table, _metadata, _image, _write

SCOPE = "本报告面向 Boost 闭环教学实验，记录 Virtual HIL 的实际软件仿真结果。功率电路与 PI 控制器来自 THCC 2026.3 官方示例；教学副本加入定时参考阶跃和监测点。"
METHOD = "稳态误差使用配置指定的最后一段原始样本均值。动态响应从实际参考或输入电压的首次变化采样时刻计时；调节/恢复时间取进入目标电压容差带并保持至观测末尾的最早采样时刻。参考超调按阶跃幅值归一化；输入扰动最大偏差按目标输出电压归一化。事件检测区间由相邻原始采样时刻限定。判据在运行前保存在 config.json。输入电流峰值为当前采样率下的采样峰值。"


def _plot(path, data, config, metrics, detail=False):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 10, "axes.grid": True,
                         "grid.alpha": .2, "path.simplify": False, "figure.facecolor": "white"}):
        fig, axes = plt.subplots(3, 1, sharex=True, figsize=(11, 8), layout="constrained")
        fig.suptitle("Boost closed-loop Virtual HIL - "+("event detail" if detail else "full raw capture")+" ["+metrics.get("status", "error")+"]")
        t = data["t_simulation_s"]
        ref = [config["parameters"]["reference_voltage_v"] for _ in t]
        for event in config["events"]:
            if event["target"] == "reference_voltage_v":
                ref = [event["value"] if ti >= event["at_s"] else value for ti, value in zip(t, ref)]
        band = config["acceptance"]["settling_band_relative"]
        axes[0].fill_between(t, [v*(1-band) for v in ref], [v*(1+band) for v in ref],
                             color="#666666", alpha=.15, label="Target tolerance band")
        axes[0].plot(t, data["Vout_V"], color="#0072B2", linewidth=1.2, label="Vout")
        axes[0].plot(t, data["ReferenceApplied_V"], color="#D55E00", linestyle="--", linewidth=1.3, label="Actual reference")
        axes[1].plot(t, data["Iin_A"], color="#009E73", linewidth=.9, label="Iin (sampled)")
        axes[2].plot(t, data["VinMeasured_V"], color="#CC79A7", linewidth=1.3, label="Measured Vin")
        for ax, unit in zip(axes, ("Voltage (V)", "Input current (A)", "Input voltage (V)")):
            ax.set_ylabel(unit)
            window = metrics.get("analysis", {}).get("steady_window_s")
            if window: ax.axvspan(*window, color="#009E73", alpha=.08, label="Final analysis window")
            pre = metrics.get("response", {}).get("pre_event_window_s")
            if pre: ax.axvspan(*pre, color="#E69F00", alpha=.07, label="Pre-event window")
            for e in config["events"]:
                ax.axvline(e["at_s"], color="#333333", linestyle=":", linewidth=1.1, label="Planned event")
            for e in metrics.get("events", []):
                interval = e.get("observed_interval_s")
                if interval: ax.axvspan(*interval, color="#0072B2", alpha=.6, label="Observed event interval")
            ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=8)
        if detail:
            start = config["events"][0]["at_s"]-config["acceptance"]["pre_event_window_s"]
            stop = config["capture"]["start_s"]+config["capture"]["duration_s"]
            idx = [k for k, ti in enumerate(t) if start <= ti <= stop]
            values = [[data["Vout_V"][k] for k in idx]+[ref[k]*(1-band) for k in idx]+[ref[k]*(1+band) for k in idx],
                      [data["Iin_A"][k] for k in idx], [data["VinMeasured_V"][k] for k in idx]]
            for ax, visible in zip(axes, values):
                low, high = min(visible), max(visible)
                padding = max((high-low)*.08, max(abs(low),abs(high))*.005, .01)
                ax.set_xlim(start, stop);ax.set_ylim(low-padding, high+padding)
        axes[-1].set_xlabel("Simulation time (s)")
        fig.savefig(path, dpi=160, facecolor="white", transparent=False,
                    metadata={"Description": "All raw capture samples; no filtering or interpolation. Shading marks declared analysis windows and target tolerance."})
        plt.close(fig)


def write_report(run_dir, manifest):
    run_dir = Path(run_dir)
    config, metrics = _json(run_dir/"config.json"), _json(run_dir/"metrics.json")
    status = manifest.get("status", metrics.get("status", "error"))
    if status == "passed" and metrics.get("status") != "passed": status = "error"
    hp, mp, outputs = [], [], []
    def section(title, headers, rows):
        hp.append("<h2>"+html.escape(title)+"</h2>"+_table(headers, rows))
        mp.append("## "+title+"\n\n"+_md_table(headers, rows))
    if manifest.get("error"):
        hp.append("<h2>执行异常</h2><pre>"+html.escape(manifest["error"])+"</pre>")
        mp.append("## 执行异常\n\n"+manifest["error"])
    v, i = metrics.get("signals", {}).get("Vout_V", {}), metrics.get("signals", {}).get("Iin_A", {})
    rows = [("目标输出电压", _fmt(v.get("target_v")), "V"),
            ("最终输出均值", _fmt(v.get("steady_mean")), "V"),
            ("带符号稳态误差", _fmt(v.get("signed_error_v")), "V"),
            ("绝对相对稳态误差", _fmt(v.get("relative_steady_error")*100 if v.get("relative_steady_error") is not None else None), "%"),
            ("输入电流全窗均值", _fmt(i.get("mean")), "A"),
            ("输入电流最终稳态均值", _fmt(i.get("steady_mean")), "A"),
            ("输入电流采样峰值（绝对值）", _fmt(i.get("sampled_peak_abs")), "A")]
    response = metrics.get("response", {})
    if config.get("events"):
        rows += [("事件前输出均值", _fmt(response.get("pre_event_mean_v")), "V"),
                 ("调节／恢复时间", _fmt(response.get("settling_time_s")), "s")]
        key, label = (("overshoot_fraction_of_step", "超调／参考阶跃幅值") if config["events"][0]["target"] == "reference_voltage_v"
                      else ("maximum_deviation_relative", "最大输出偏差／目标电压"))
        value = response.get(key)
        rows.append((label, _fmt(value*100 if value is not None else None), "%"))
        if response.get("settling_reason"):
            rows.append(("调节时间未取得的原因", response["settling_reason"], ""))
    section("指标", ("指标", "值", "单位"), rows)
    event_rows = []
    for e in metrics.get("events", []):
        event_rows.append((e["target"], _fmt(e["expected_before_v"])+" → "+_fmt(e["expected_after_v"]),
            _fmt(e["requested_at_s"]), _fmt(e["scheduled_at_s"]), _fmt(e["observed_at_s"]),
            str(e["observed_interval_s"]), _fmt(e["time_resolution_s"]), _status(e["status"])))
    if event_rows:
        section("事件证据", ("目标", "电平 (V)", "请求 (s)", "调度 (s)", "首变样本 (s)", "检测区间 (s)", "分辨率 (s)", "状态"), event_rows)
    elif not config.get("events"):
        hp.append("<p>基准实验未安排动态事件，参考和输入电压保持检查见下表。</p>")
        mp.append("基准实验未安排动态事件，参考和输入电压保持检查见下表。")
    check_rows = [(x["name"], x["kind"], "通过" if x["passed"] else "未通过", _fmt(x["observed"]), _fmt(x["expected"]), _fmt(x["limit"])) for x in metrics.get("checks", [])]
    hp.append("<p>检查表中的相对量按小数记录，0.02 表示 2%。启动波形完整保留，动态性能判据评价配置事件后的响应。</p>")
    mp.append("检查表中的相对量按小数记录，0.02 表示 2%。启动波形完整保留，动态性能判据评价配置事件后的响应。")
    section("固定判据与检查", ("检查", "类别", "结果", "实际值", "参照值", "阈值"), check_rows)
    capture = metrics.get("capture", {})
    cap_record = _json(run_dir/"capture.json")
    section("采集与分析窗口", ("项", "值"), [("样本数", _fmt(capture.get("sample_count"))),
        ("实际采样率 (Hz)", _fmt(capture.get("sample_rate_hz"))), ("窗口 N·Δt (s)", _fmt(capture.get("duration_s"))),
        ("首末仿真时刻 (s)", str([capture.get("first_simulation_time_s"), capture.get("last_simulation_time_s")])),
        ("最终均值窗口 (s；左闭右开)", str(metrics.get("analysis", {}).get("steady_window_s"))),
        ("事件电平检查的初始化排除时长 (s)", _fmt(metrics.get("analysis", {}).get("observer_initialization_exclusion_s"))),
        ("UTC 触发时戳 (ns；— 表示未提供)", _fmt(cap_record.get("trigger_timestamp_utc_time_ns")))])
    if (run_dir/"waveforms.csv").exists():
        try:
            data = load_waveforms(run_dir/"waveforms.csv", columns=COLUMNS)
            figure = run_dir/"waveforms.png"
            _plot(figure, data, config, metrics)
            caption = "三组图共享仿真时间轴：输出与实际参考、输入电流采样值、实际输入电压。阴影标记分析窗口和目标容差带；事件证据以采样检测区间表达时间分辨率。原始 CSV 保留全部样本。"
            hp.append("<h2>实际采样波形</h2>"+_image(figure, caption))
            mp.append("## 实际采样波形\n\n![Boost 实际波形](waveforms.png)\n\n"+caption)
            outputs.append(figure)
            if config.get("events"):
                detail = run_dir/"response_detail.png"
                _plot(detail, data, config, metrics, detail=True)
                start = config["events"][0]["at_s"]-config["acceptance"]["pre_event_window_s"]
                stop = config["capture"]["start_s"]+config["capture"]["duration_s"]
                caption_detail = f"事件细节视图：{start:g}～{stop:g} s。显示同一原始采集的局部时间与数值范围；完整启动过程保留在上图。动态判据评价事件后的响应。"
                hp.append("<h2>事件区间放大</h2>"+_image(detail, caption_detail))
                mp.append("## 事件区间放大\n\n![事件区间原始波形](response_detail.png)\n\n"+caption_detail)
                outputs.append(detail)
        except ValueError as exc:
            status = "error"
            message = "原始数据完整性检查失败："+str(exc)
            hp.append("<pre>"+html.escape(message)+"</pre>");mp.append(message)
    hp.append("<h2>分析方法</h2><p>"+html.escape(METHOD)+"</p>")
    mp.append("## 分析方法\n\n"+METHOD)
    text = json.dumps(config, ensure_ascii=False, indent=2)
    hp.append("<h2>实际配置</h2><pre>"+html.escape(text)+"</pre>")
    mp.append("## 实际配置\n\n```json\n"+text+"\n```")
    section("运行来源", ("字段", "记录"), _metadata(manifest))
    links = [name for name in ("waveforms.csv", "metrics.json", "events.json", "capture.json", "config.json", "model.tse", "run.log") if (run_dir/name).exists()]+["manifest.json"]
    hp.append("<p>来源文件："+" · ".join(f'<a href="{name}">{name}</a>' for name in links)+"</p>")
    mp.append("来源文件："+" · ".join(f"[{name}]({name})" for name in links))
    outputs.extend(_write(run_dir, "Boost 闭环教学实验报告", status, hp, mp, scope=SCOPE))
    return outputs
