"""Decision-oriented analysis and figures for the held-out measured comparison."""

from collections import Counter
import csv
import json
from pathlib import Path

from .kaist_pmsm import LABELS
from .utils import write_json


METHOD_LABELS = {"fixed": "固定规则", "adaptive": "自适应规则", "llm": "DeepSeek Flash"}
CLASS_LABELS = {"healthy": "健康", "interturn": "匝间短路", "intercoil": "线圈间短路"}
STRATUM_LABELS = {"initial_sufficient": "初始参照命中", "additional_evidence": "补充证据后参照命中",
                  "reference_unresolved": "全观测参照仍未命中"}
DECISIONS = {
    "candidate_worth_replication": "达到进入独立批次复验的预设条件",
    "unstable_signal": "部分模型重复达到条件，收益方向尚不稳定",
    "rule_ceiling": "工程基线已达命中上限，未观察到查询节省",
    "limited_discrimination": "当前任务缺少可验证补查价值的案例",
    "no_gain": "可评价补查的留出任务中未达到预设增益条件",
    "service_unavailable": "模型服务未形成可评分答复，本阶段未验收",
}
FOLLOW_UP = {
    "candidate_worth_replication": "在新增的独立采集批次复验，再比较服务模型及部署成本。",
    "unstable_signal": "保留工程基线，先核对不一致案例的选证据和判断变化，再决定独立复验的重点。",
    "rule_ceiling": "保留工程基线。后续比较优先使用初始症状重叠且需要不同测点的实测工况。",
    "limited_discrimination": "下一次采集优先覆盖相近观测下的两种机制，并加入独立的健康和故障重复。",
    "no_gain": "保留工程基线。本次错误轨迹用于判断改进选测点、解释证据或保留未决的优先级。",
    "service_unavailable": "恢复相同模型服务后按原冻结协议完成全量对照。",
}


def _counts(rows):
    transport = sum(row["status"] in ("transport_error", "interrupted") for row in rows)
    return {
        "n": len(rows), "correct": sum(row["correct"] for row in rows),
        "wrong": sum(row["wrong_commit"] for row in rows),
        "undetermined": sum(row["undetermined"] for row in rows),
        "procedure_errors": sum(row["status"] != "completed" for row in rows),
        "transport_errors": transport, "invalid_actions": sum(row["invalid_actions"] for row in rows),
        "initial_correct": sum(row["initial_correct"] for row in rows),
        "corrected_after_query": sum(row["corrected_after_query"] for row in rows),
        "lost_initial_hit": sum(row["lost_initial_hit"] for row in rows),
        "queries": sum(row["queries"] for row in rows),
        "valid_queries": sum(row["valid_queries"] for row in rows),
        "query_histogram": [sum(row["queries"] == count for row in rows) for count in range(3)],
    }


def _method_groups(rows):
    for method in ("fixed", "adaptive"):
        yield method, None, [row for row in rows if row["method"] == method]
    for repeat in sorted({row["repeat"] for row in rows if row["method"] == "llm"}):
        yield "llm", repeat, [row for row in rows if row["method"] == "llm" and row["repeat"] == repeat]


def _compare(adaptive, trial):
    def qualities(row):
        return row["correct"], row["wrong_commit"], row["undetermined"], row["status"]

    pairs = [(adaptive[row["task_id"]], row) for row in trial]
    fault_pairs = [(rule, llm) for rule, llm in pairs if llm["truth"] != "healthy"]
    correct_gain = sum(llm["correct"] - rule["correct"] for rule, llm in fault_pairs)
    wrong_gain = sum(llm["wrong_commit"] - rule["wrong_commit"] for rule, llm in pairs)
    queries_gain = sum(llm["queries"] - rule["queries"] for rule, llm in pairs)
    paired_equal = all(qualities(rule) == qualities(llm) for rule, llm in pairs)
    improve_accuracy = correct_gain > 0 and wrong_gain <= 0
    improve_efficiency = paired_equal and queries_gain < 0
    return {
        "fault_correct_difference": correct_gain,
        "wrong_commit_difference": wrong_gain,
        "queries_difference": queries_gain,
        "same_per_task_quality": paired_equal,
        "improves_accuracy": improve_accuracy, "improves_efficiency": improve_efficiency,
        "qualifies": improve_accuracy or improve_efficiency,
        "correct_only_llm": [llm["task_id"] for rule, llm in pairs if llm["correct"] and not rule["correct"]],
        "correct_only_adaptive": [llm["task_id"] for rule, llm in pairs if rule["correct"] and not llm["correct"]],
    }


def summarize(rows, workflow):
    groups = []
    adaptive = {row["task_id"]: row for row in rows if row["method"] == "adaptive" and not row["mask"]}
    compare = []
    for method, repeat, group in _method_groups(rows):
        main = [row for row in group if not row["mask"]]
        masked = [row for row in group if row["mask"]]
        classes = {label: _counts([row for row in main if row["truth"] == label]) for label in LABELS}
        groups.append({
            "method": method, "repeat": repeat, "main": _counts(main), "missing": _counts(masked),
            "classes": classes,
            "strata": {stratum: _counts([row for row in main if row["stratum"] == stratum])
                       for stratum in STRATUM_LABELS},
            "query_paths": dict(sorted(Counter(" → ".join(row["query_path"]) or "none" for row in main).items())),
        })
        if method == "llm":
            compare.append({"repeat": repeat, **_compare(adaptive, main)})

    if workflow != "completed":
        decision = "service_unavailable"
    elif all(row["qualifies"] for row in compare):
        decision = "candidate_worth_replication"
    elif any(row["qualifies"] for row in compare):
        decision = "unstable_signal"
    elif all(row["correct"] for row in adaptive.values()):
        decision = "rule_ceiling"
    elif not any(row["stratum"] == "additional_evidence" for row in adaptive.values()):
        decision = "limited_discrimination"
    else:
        decision = "no_gain"
    return {
        "main_recordings": len(adaptive),
        "missing_derived_tasks": groups[0]["missing"]["n"],
        "groups": groups, "differences_vs_adaptive": compare, "decision": decision,
        "model_usage": {
            "calls": sum(row["calls"] for row in rows),
            "calls_with_usage": sum(row["calls_with_usage"] for row in rows),
            "input_tokens": sum(row["input_tokens"] for row in rows),
            "output_tokens": sum(row["output_tokens"] for row in rows),
            "request_seconds_sum": sum(row["request_seconds"] for row in rows),
            "returned_models": sorted({model for row in rows for model in row["returned_models"]}),
        },
    }


def _method_name(row):
    name = METHOD_LABELS[row["method"]]
    return f"{name} 第 {row['repeat']} 次" if row["repeat"] is not None else name


def _result_table(groups):
    lines = [
        "| 方法 | 正确 / 全部 | 健康 | 匝间 | 线圈间 | 错定案 | 未决 | 流程错误 | 查询总数 | 缺测正确未决 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for group in groups:
        total, masked = group["main"], group["missing"]
        classes = " | ".join(f"{c['correct']}/{c['n']}" for c in group["classes"].values())
        lines.append(f"| {_method_name(group)} | {total['correct']}/{total['n']} | {classes} | "
                     f"{total['wrong']} | {total['undetermined']} | {total['procedure_errors']} | "
                     f"{total['queries']} | {masked['correct']}/{masked['n']} |")
    return lines


def _write_csv(output, rows, holdout, path):
    truth = {row["task_id"]: row for row in json.loads((output / "tasks-private.json").read_text(encoding="utf-8"))}
    keys = ("motor_w", "severity_pct", *rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            origin = holdout["recordings"][truth[row["task_id"]]["recording_index"]]
            writer.writerow({"motor_w": origin["motor_w"], "severity_pct": origin["severity_pct"], **row})


def _write_figures(output, summary):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    folder = output / "figures"
    folder.mkdir(exist_ok=True)
    groups = summary["groups"]
    labels = ["Fixed", "Adaptive", *[f"LLM {row['repeat']}" for row in groups if row["method"] == "llm"]]
    charts = (
        ("diagnosis-outcomes", "Held-out motor diagnosis outcomes", "Recordings",
         ("Correct", "Wrong", "Undetermined", "Procedure error"),
         ("#146359", "#b34e28", "#dfab52", "#606789"),
         [[row["main"][key] for row in groups] for key in
          ("correct", "wrong", "undetermined", "procedure_errors")]),
        ("query-count", "Queries per recording at the shared budget", "Recordings",
         ("0 queries", "1 query", "2 queries"), ("#adc5d6", "#447fa4", "#1f466e"),
         [[row["main"]["query_histogram"][index] for row in groups] for index in range(3)]),
    )
    for name, title, axis, outcomes, colors, values in charts:
        fig, ax = plt.subplots(figsize=(7.2, 4.2), constrained_layout=True)
        totals = [0] * len(groups)
        for category, color, counts in zip(outcomes, colors, values):
            bars = ax.bar(labels, counts, bottom=totals, color=color, label=category, width=0.68)
            for bar, count, bottom in zip(bars, counts, totals):
                if count:
                    ax.text(bar.get_x() + bar.get_width() / 2, bottom + count / 2, str(count),
                            ha="center", va="center", color="#171717" if color in ("#dfab52", "#adc5d6") else "white")
            totals = [total + count for total, count in zip(totals, counts)]
        ax.set_title(title)
        ax.set_ylabel(axis)
        ax.set_ylim(0, max(totals) * 1.12)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=len(outcomes), frameon=False)
        for extension in ("png", "pdf"):
            fig.savefig(folder / f"{name}.{extension}", dpi=180)
        plt.close(fig)


def _write_review_queue(output, rows):
    errors = [
        row for row in rows if row["method"] == "llm" and
        (row["wrong_commit"] or row["status"] != "completed" or row["invalid_actions"])
    ]
    lines = ["# 模型错误与动作复核", "",
             "下表保留实际评分及可定位的原始答复。解释表述单独核对，原始动作参与评分。", "",
             "| 任务 | 重复 | 期望 | 原始末轮选择 | 执行后的判断 | 状态 | 无效动作 | 记录 |",
             "|---|---:|---|---|---|---|---:|---|"]
    for row in errors:
        path = f"sessions/{row['task_id']}/llm-{row['repeat']}/result.json"
        lines.append(f"| {row['task_id']} | {row['repeat']} | {row['expected']} | {row['raw_final_decision']} "
                     f"| {row['decision']} | {row['status']} | {row['invalid_actions']} | [完整轨迹]({path}) |")
    if not errors:
        lines.append("| — | — | — | — | — | — | 0 | — |")
    (output / "error-review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_report(output, development, holdout, rows, freeze, workflow):
    output = Path(output)
    summary = summarize(rows, workflow)
    write_json(output / "summary.json", summary)
    _write_csv(output, rows, holdout, output / "逐案例对照.csv")
    _write_figures(output, summary)
    _write_review_queue(output, rows)
    usage = summary["model_usage"]
    comparisons = summary["differences_vs_adaptive"]
    groups = summary["groups"]
    strata = groups[0]["strata"]
    label_counts = Counter(row["label"] for row in holdout["recordings"])
    lines = [
        "# PMSM 多机制实测诊断对照", "",
        f"**研究决定：{DECISIONS[summary['decision']]}。** 评价对象是 3.0 kW 留出电机的公开台架实测。"
        f"共 {summary['main_recordings']} 个完整采集条件，含健康 {label_counts['healthy']}、"
        f"匝间短路 {label_counts['interturn']}、线圈间短路 {label_counts['intercoil']}。"
        "诊断从同一摘要出发，在至多两次查询中尝试区分原因。", "",
        "## 实测与现场条件", "",
        f"1.0 和 1.5 kW 电机的 {len(development['recordings'])} 个合格采集条件用于开发。"
        "发布归档以仓库 SHA-256 校验。相同工况的电流和振动按文件条件配对，各自保留原始时基。"
        f"开发组排除 {len(development['excluded'])} 项，留出组排除 {len(holdout['excluded'])} 项。"
        "短路类型为发布方在固定转速和负载下设置的实测条件。"
        "[官方数据 v5](https://data.mendeley.com/datasets/rgn5brrgrn/5)", "",
        "## 全量结果", "",
        *_result_table(groups), "",
        "按冻结的工程参照，"
        + "、".join(f"{name} {strata[key]['n']} 条" for key, name in STRATUM_LABELS.items())
        + "。全部合格采集条件进入主表。分层用于定位补查机会，实际命中按原始发布标签评分。", "",
        "| DeepSeek 重复 | 相对自适应规则多判对的故障数 | 错定案差 | 查询数差 | 达到复验条件 |",
        "|---|---:|---:|---:|---|",
        *[f"| {row['repeat']} | {row['fault_correct_difference']:+d} | {row['wrong_commit_difference']:+d} "
          f"| {row['queries_difference']:+d} | {'是' if row['qualifies'] else '否'} |" for row in comparisons],
        "",
        f"实际记录 {usage['calls']} 次模型调用，其中 {usage['calls_with_usage']} 次有完整用量。"
        f"已有用量合计输入 {usage['input_tokens']:,}、输出 {usage['output_tokens']:,} token。"
        "请求耗时按调用记录，查询次数与模型调用次数分别计算。", "",
        "## 适用范围与后续决定", "",
        "本轮按三次真实服务会话评估同一批记录上的输出稳定性。"
        "健康条件在留出电机上只有一个来源。结果适用于该留出电机、固定速度和负载及两种绕组故障。"
        "独立重复性、误报率和工况迁移仍需新增采集批次。", "",
        FOLLOW_UP[summary["decision"]], "",
        "[逐案例对照](逐案例对照.csv) · [冻结协议](freeze.json) · [统计附录](stats-appendix.md) · "
        "[图表及读法](figure-catalog.md) · [模型错误复核](error-review.md) · [离线复核](verification.json)",
    ]
    (output / "analysis-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    appendix = [
        "# 统计口径与适用范围", "",
        "比较单位为整次采集条件。健康重复别名经字节摘要合并。两种传感数据按发布条件配对。"
        "四个稳态窗用于生成一条记录的观测，缺失观测任务复用对应记录。"
        "留出是一台电机的完整合格条件集合。逐案绝对差和三个服务重复分别呈现。"
        "跨电机总体置信区间与显著性检验缺少独立的留出电机或采集批次。", "",
        "固定和自适应规则使用等权重观察组的标准化绝对距离。"
        "开发的两台电机互为校准验证，错定案、未决和命中的损失为 1、0.5 和 0。"
        "选择宏平均损失最小的停止参数，并列时优先选择错定案更少、查询更少的一组。"
        f"冻结的距离上限为 {freeze['stop']['max_distance']}，最小候选间距为 {freeze['stop']['min_margin']}。", "",
        "频谱以去均值 Hann 窗计算。开发波形确认电流基频在约 200 Hz，正式冻结窗口为 195–205 Hz。"
        "在峰值中心 ±2 Hz 积分功率，其占 20–1000 Hz 频带能量至少 1% 时用于序量和谐波计算。"
        "负序和正序使用基频峰值复数，并取小序与大序之比。"
        "振动取 50 Hz 的前 4 个倍频附近 ±2 Hz 能量占 10–1000 Hz 总能量的比例。"
        "汇总取四窗中位数，合成 RMS 的波动用四窗变异系数。", "",
        "无效、重复、不可用的已提出查询占一个预算。越预算请求被拒绝并记录，"
        "评分保留错误与服务失败。真实请求用量与查询预算分开呈现。", "",
        "## 判断变化", "",
        "| 方法 | 初判命中 | 查证后由错判或未决转为正确 | 失去初判命中 |",
        "|---|---:|---:|---:|",
        *[f"| {_method_name(group)} | {group['main']['initial_correct']} | "
          f"{group['main']['corrected_after_query']} | {group['main']['lost_initial_hit']} |" for group in groups],
        "",
        "初判取首次有效决策，后续变化按实际轨迹统计。轨迹显示补充观测和判断变化的先后，"
        "区分选证据与解释同一证据的贡献仍需额外受控对照。", "",
        "## 主试评查询路径", "",
        "| 方法 | 路径及记录数 |", "|---|---|",
        *[f"| {_method_name(group)} | "
          + "，".join(f"{path} × {count}" for path, count in group["query_paths"].items())
          + " |" for group in groups],
        "",
        "## 调用开销", "",
        f"服务实际返回模型标识为 {', '.join(usage['returned_models']) or '未取得'}。"
        f"已记录请求耗时合计 {usage['request_seconds_sum']:.2f} s。"
        "请求并发执行，耗时合计不能作为整轮墙钟耗时。账单金额采用服务账单口径，本结果未获取账单。", "",
        "[逐案数据](逐案例对照.csv) · [公开数据目录](source-inventory.json) · "
        "[开发与停止判据](freeze.json) · [复核](verification.json)",
    ]
    (output / "stats-appendix.md").write_text("\n".join(appendix) + "\n", encoding="utf-8")

    catalog = [
        "# 图表与读法", "",
        "## 诊断结果", "",
        "[诊断结果图](figures/diagnosis-outcomes.png) · [PDF](figures/diagnosis-outcomes.pdf)", "",
        "显示完整条件下正确、错定案、未决和流程错误的数量。三次 LLM 的柱子重复使用同一批记录。"
        "读图时同时看错定案与未决，避免把更多定案直接解释为更可靠。", "",
        "## 查询次数", "",
        "[查询次数图](figures/query-count.png) · [PDF](figures/query-count.pdf)", "",
        "显示各方法完成或终止时每条记录的查询次数。预算为两次，拒绝的有预算查询计入开销。"
        "结合诊断结果判断查询节省是否保留了逐案可靠性。", "",
        "两图使用 [数值汇总](summary.json) 中的计数。样本为一台留出电机的全部合格条件，"
        "柱中数字为实测计数。", "",
    ]
    (output / "figure-catalog.md").write_text("\n".join(catalog), encoding="utf-8")
    return summary
