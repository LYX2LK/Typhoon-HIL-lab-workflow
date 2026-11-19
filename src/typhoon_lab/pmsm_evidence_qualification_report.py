"""Render the frozen cross-motor evidence qualification and its scope."""

import csv

from .pmsm_evidence_qualification import (
    COMBINATIONS, DEVELOPMENT_MOTORS, HOLDOUT_MOTOR, MIN_NET_CORRECT, MIN_PER_FAULT, SCORERS,
)


NAMES = {
    "initial": ("初始摘要", "Initial evidence"),
    "native_phase": ("原始相电流", "Native phase"),
    "sign_phase": ("试算翻号后的相电流", "Sign check, phase only"),
    "native_full": ("原始全证据", "Native, all groups"),
    "sign_full": ("原始全证据仅修正序量", "Sign check, all groups"),
    "phase_reference": ("健康参照幅相", "Health-relative phase"),
    "harmonic_reference": ("健康参照谐波", "Health-relative harmonics"),
    "vibration_reference": ("健康参照振动", "Health-relative vibration"),
    "phase_harmonic_reference": ("健康参照幅相和谐波", "Relative phase + harmonics"),
    "phase_vibration_reference": ("健康参照幅相和振动", "Relative phase + vibration"),
    "harmonic_vibration_reference": ("健康参照谐波和振动", "Relative harmonics + vibration"),
    "full_reference": ("健康参照全证据", "Health-relative, all groups"),
}


def _write(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _plot(output, measured, folds):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    folder = output / "figures"
    folder.mkdir()
    figure, axes = plt.subplots(1, 3, sharex=True, sharey=True, figsize=(11, 5.6), layout="constrained")
    positions = list(range(len(COMBINATIONS)))
    for axis, fold in zip(axes, folds, strict=True):
        motor = fold["test_motor_w"]
        scores = fold["scores"]
        for scorer, marker, color, offset, label in (
            ("median_distance", "o", "#285680", -0.14, "Median distance"),
            ("ridge_linear", "^", "#A24700", 0.14, "Ridge linear"),
        ):
            axis.scatter([scores[name][scorer]["correct"] for name in COMBINATIONS],
                         [index + offset for index in positions], c=color, marker=marker, s=25, label=label)
        role = "historical replay" if motor == HOLDOUT_MOTOR else "development fold"
        axis.set_title(f"{motor / 1000:g} kW • {role}", fontsize=10)
        axis.set_xticks(range(0, 15, 2))
        axis.set_xlim(-0.4, 14.4)
        axis.set_xlabel("Correct / 14 fault recordings")
        axis.grid(color="#E4E7EC", axis="x")
        axis.set_axisbelow(True)
    axes[0].set_yticks(positions, [NAMES[name][1] for name in COMBINATIONS], fontsize=8.5)
    axes[0].invert_yaxis()
    axes[-1].legend(loc="upper right", bbox_to_anchor=(1, -0.12), ncols=2, frameon=False, fontsize=8)
    figure.suptitle("Cross-motor winding-fault evidence qualification", fontsize=14)
    figure.savefig(folder / "motor-evidence.png", dpi=170, facecolor="white")
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(7.1, 3.8), layout="constrained")
    positions = list(range(len(measured)))
    health = [item["healthy_check"] for item in measured.values()]
    axis.scatter([index - 0.13 for index in positions], [check["check_native_median"] for check in health],
                 c="#285680", marker="o", s=48, label="Native orientation")
    axis.scatter([index + 0.13 for index in positions], [check["check_adjusted_median"] for check in health],
                 c="#A24700", marker="^", s=52, label="Sign hypothesis")
    for index, check in enumerate(health):
        axis.plot([index - 0.13, index + 0.13],
                  [check["check_native_median"], check["check_adjusted_median"]], c="#7F8C98", lw=1)
    axis.set_xticks(positions, [f"{int(key) / 1000:g} kW" for key in measured])
    axis.set_xlim(-0.5, len(measured) - 0.5)
    axis.set_ylim(0, 0.78)
    axis.set_ylabel("Normalized three-phase phasor sum")
    axis.set_title("Healthy check windows at 60 s and 90 s")
    axis.grid(color="#E4E7EC", axis="y")
    axis.set_axisbelow(True)
    axis.legend(loc="upper left", frameon=False)
    figure.savefig(folder / "healthy-polarity.png", dpi=170, facecolor="white")
    plt.close(figure)


def write_report(output, measured, folds, summary):
    path = output / "逐条件分型.csv"
    rows = [row for fold in folds for row in fold["predictions"]]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    _plot(output, measured, folds)

    passing = summary["passing_candidates"]
    decision = ("达到开发筛选的补查组合为" + "、".join(NAMES[name][0] for name in passing)
                if passing else "所有预注册的一至两组补查组合均未达到开发筛选门槛")
    _write(output / "analysis-report.md", [
        "# PMSM 跨电机标定与分型证据验证", "",
        f"**{decision}。** 本阶段在已有实测上完成标定假设复算与证据筛选。"
        "独立批次仍需取得新的整次采集，模型比较待独立证据验证后启动。", "",
        "## 原始电流与健康基准", "",
        "以每台电机健康记录的 10、30 秒窗口拟合相对极性和参考，以 60、90 秒窗口检验同记录内的一致性。"
        "表中每个数字为两个检查窗的相量和幅值除以三相幅值之和，再取中位数。"
        "发布材料说明电流传感器安装在 U、V、W 相，通道对应关系与探头方向仍需原采集记录或参考实测验证。"
        " [KAIST 数据与方法](https://pure.kaist.ac.kr/en/publications/vibration-and-current-dataset-of-three-phase-permanent-magnet-syn/) "
        "· [逐窗复算](measurements.json)", "",
        "| 电机 | 候选通道符号 | 原始相量和比例 | 候选相量和比例 | 后两窗与候选一致 |",
        "|---|---|---:|---:|---:|",
        *[f"| {int(motor) / 1000:g} kW | {check['candidate_signs']} | {check['check_native_median']:.4f} | "
          f"{check['check_adjusted_median']:.4f} | {check['check_windows_agree']}/2 |"
          for motor, item in measured.items() for check in (item["healthy_check"],)], "",
        "## 分型对照", "",
        f"42 条故障记录参与两分类，另有 3 条已知健康记录仅作各电机标定。"
        f"开发时 {DEVELOPMENT_MOTORS[0] / 1000:g} 和 {DEVELOPMENT_MOTORS[1] / 1000:g} kW 互留，"
        f"{HOLDOUT_MOTOR / 1000:g} kW 为已曝光的历史敏感性回放。每格依次为中位数距离和岭线性评分的命中数。"
        "每台 14 条故障条件，匝间短路、线圈间短路各 7 条。输入不含故障类型、严重度或旁路电阻。"
        " [冻结记录](freeze.json) · [逐条件数据](逐条件分型.csv)", "",
        "| 证据 | 1.0 kW 开发 | 1.5 kW 开发 | 3.0 kW 历史 |",
        "|---|---:|---:|---:|",
        *["| " + NAMES[name][0] + " | " + " | ".join(
            " / ".join(str(fold["scores"][name][scorer]["correct"]) for scorer in SCORERS)
            for fold in folds) + " |" for name in COMBINATIONS], "",
        f"进入独立证据复验的筛选门槛是同一个一至两组补查组合，在两台开发电机上经两种评分均比各自初判"
        f"净增至少 {MIN_NET_CORRECT}/14 条，且两类分别至少判对 {MIN_PER_FAULT}/7 条。"
        "原始、翻号试算与全证据组合用于查明证据变化。最相似配对、纠正的初判与失去的命中单列。"
        " [统计附录](stats-appendix.md) · [图表读法](figure-catalog.md)", "",
        "## 独立复验条件", "",
        "新批次须包括同工况的独立健康采集和经台架记录核实的两类短路。"
        "记录电机及采集批次编号、通道到相的映射、探头方向与参考、故障配置、转速负载以及传感器时间依据。"
        "若需继续采集电压和电流残差，保存电压与电流的共同触发或可审核的时钟关系。"
        "整次采集进入同一个数据分区，健康标定与健康误报评价分别采集。"
        "本轮证据只覆盖 KAIST 已发布的固定台架工况，两分类结果也以记录已知故障为前提。"
        " [相量候选依据](https://doi.org/10.3390/s22124597) · [电压、电流残差候选依据](https://doi.org/10.1109/TEC.2017.2726142)",
    ])

    _write(output / "stats-appendix.md", [
        "# 统计口径与逐方案变化", "",
        "基本单位为整条有标签的台架测量。四个 2 秒窗口的幅相特征取中位数，每条记录形成一个观测。"
        "两种评分是对相同条件的敏感性分析。三台电机来自同一公开研究，健康每台一份。"
        "没有跨独立批次的方差估计，因此只报告逐条件计数、成对变化和分层命中，不做跨设备显著性检验或总体置信区间。", "",
        "中位数距离采用训练折中位数、四分位距标准化及按证据组等权的绝对距离。"
        "四分位距接近零时使用训练标准差，恒定特征不贡献距离。岭线性评分使用同一标准化，"
        "以每组特征数的平方根缩放，惩罚系数固定为 1，截距不惩罚。"
        "加权判别分数为零时计未决。多个候选按被冻结的同向门槛并列完整报告。", "",
        "基频幅相复用原始电流窗、Hann 窗和已复核的主峰频率。相量序量的翻号组合在健康拟合窗确定。"
        "对翻号不敏感的幅相证据使用三相基频幅值相对健康的对数改变量，以及模 180° 的相间角偏差。"
        "谐波幅比和振动能量占比各自与同传感器的健康参考求对数比。两类信号按发布条件对应，各用各的时基。", "",
        "表中困难配对是同电机同旁路电阻的七组中，初始摘要距离最接近的三组，排序只用于分层统计。"
        "每组需两类均判对才计命中。发布方严重度按其故障比给出。"
        " [旁路电阻原表](https://prod-dcd-datasets-public-files-eu-west-1.s3.eu-west-1.amazonaws.com/4e440d36-d8ec-4af9-906d-a750e57098fa) "
        "· [完整判别分数与配对索引](scores.json)", "",
        "| 电机 | 证据 | 评分 | 匝间判对 / 7 | 线圈间判对 / 7 | 纠正 | 丢失 | 净增 | 困难配对 / 3 |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
        *[f"| {fold['test_motor_w'] / 1000:g} kW | {NAMES[name][0]} | {scorer} | "
          f"{row['correct_by_fault']['interturn']} | {row['correct_by_fault']['intercoil']} | "
          f"{row['fixed_initial_errors']} | {row['lost_initial_hits']} | {row['net_gain']:+d} | "
          f"{row['hard_pairs_both_correct']} |"
          for fold in folds for name, scorers in fold["scores"].items() for scorer, row in scorers.items()],
    ])
    _write(output / "figure-catalog.md", [
        "# 图表读法", "",
        "## 逐电机分型命中", "",
        "横轴是 14 条已知故障中分型正确的计数。两个标记是同一组记录的两种评分法。"
        "前两面板是开发互留，第三面板是历史回放。对照同一电机的初始、原始、翻号和健康参照各行，"
        "查看补查改善是否依赖个别电机或评分法。细分类覆盖与配对净变化以统计附录为准。"
        " [分型图](figures/motor-evidence.png) · [逐条件数据](逐条件分型.csv)", "",
        "## 健康记录的相量和比例", "",
        "每台电机的连线对应同一份健康记录的两种通道符号处理。"
        "纵轴使用两个检查窗口的中位数。曲线下降反映相量抵消变强，"
        "帮助定位应核对的通道。它的含义限于记录内的极性线索，硬件接线须独立确认。"
        " [相量图](figures/healthy-polarity.png) · [逐窗复算](measurements.json)",
    ])
