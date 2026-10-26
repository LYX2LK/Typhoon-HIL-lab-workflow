"""Reports derived from the current dataset and its declared metadata."""
import json
from pathlib import Path
from .external_waveforms import known


def write_external_report(out, intake, profile, arrays):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out = Path(out)
    lines = ["# 外部波形接收报告", "", f"数据集：{intake['dataset_id']}",
             f"任务目的：{intake['purpose']}", "",
             f"数据质量：{profile['data_quality_status']}；分析完成度：{profile['analysis_status']}；"
             "性能判定：not_evaluated。记录一致性由 verify-waveforms 单独复核。",
             "", "时间轴和信号值保留原始采样；单位来自数据清单中标注的依据。"
             "未进行平滑、插值、跨文件同步或探头倍率补偿。", ""]
    results = {r["id"]: r for r in profile["records"]}
    for rec in intake["records"]:
        rid = rec["id"]
        result = results[rid]
        lines += [f"## {rid}", "", f"来源：{rec['csv']}；SHA-256：{result['sha256']}",
                  f"结构检查：{result['data_quality_status']}。"]
        if result.get("error"):
            lines += [f"问题：{result['error']}", ""]
        else:
            lines += [f"样本数：{result['rows']}；分析窗口样本数：{result['analysis_samples']}。",
                      f"原始时间范围：{result['raw_time_range']}；原始数值范围：{result['raw_value_range']}。"]
        lines += ["", "元信息（value / status / source）：", "~~~json",
                  json.dumps(result["metadata"], ensure_ascii=False, indent=2), "~~~",
                  "", "分析定义与结果（若单位可用，时间为 s，幅值单位见 units）：", "~~~json",
                  json.dumps({"definition": rec["analysis"], "units": result.get("units"),
                              "feature": result["feature"]}, ensure_ascii=False, indent=2), "~~~", ""]
        if "acquisition_rate_matches_csv_grid" in result:
            lines += [f"声明的仪器采集率与 CSV 网格率数值是否一致："
                      f"{result['acquisition_rate_matches_csv_grid']}。两者关系仍需结合导出设置解释。", ""]
        if rid not in arrays:
            continue
        t, y = arrays[rid].T
        with plt.rc_context({"font.size": 10, "axes.grid": True, "grid.alpha": .2, "path.simplify": False}):
            detail = rec.get("detail_window")
            fig, axes = plt.subplots(1, 2 if detail else 1, figsize=(12 if detail else 7, 4), squeeze=False,
                                     layout="constrained")
            for ax, window in zip(axes.flat, [None, detail] if detail else [None]):
                mask = (t == t) if window is None else (t >= window[0]) & (t <= window[1])
                ax.plot(t[mask], y[mask], color="#0072B2", linewidth=.8)
                ax.set(title=f"{rid}: {'full export' if window is None else str(window)}",
                       xlabel=f"CSV time ({known(rec['metadata'], 'time_unit') or 'unconfirmed unit'})",
                       ylabel=f"CSV value ({known(rec['metadata'], 'value_unit') or 'unconfirmed unit'})")
                if not mask.any():
                    ax.text(.5, .5, "No samples in declared window", transform=ax.transAxes, ha="center")
            fig.savefig(out / f"{rid}.png", dpi=150, facecolor="white")
            plt.close(fig)
        lines += [f"![{rid}]({rid}.png)", ""]
    lines += ["## 解释与后续用途", "",
              "dip 的比例阈值与 rise 的首次穿越只定义描述性特征；端点中位数是计算基准，"
              "不证明物理稳态平台。首次穿越不等于完整响应时间。"
              "物理标签、故障原因和控制器性能须结合来源与判据另行判断。",
              "", "转入回放或实验前，移交数据清单、复核结果、用途与待补条件，"
              "明确注入位置、接口、幅值/时序误差与评价依据。"]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
