# 验证记录索引

本页按验证日期索引已保存的实际记录，供维护者追溯当时的模型、代码、配置和结论。使用者判断现行能力时查看 [验证状态](validation.md)，实验操作从 [README](../README.md) 开始。

## 2026-10-17：文档职责与重复内容整理

精简技能入口，删除重复的模型接入参考；接入接口由模型接入文档维护，任务记录与历史处理集中到实现约定。Agent 教程保留组员提问与结果核对，交接文档保留复制清单及独立复现步骤。原始内容快照和静态检查见 [整理记录](../results/documentation-review/20261017-document-boundaries/summary.md)。本次完成文档检查；实际软件运行证据仍对应各日期保存的模型、代码与技能快照。

- [四项技能约束调整与离线验收](../results/skill-validation/20261017-task-flexibility-f5764d/summary.md)：扩展能力、数据核对顺序、模型推导及任务深度五项场景通过；本次为只读离线检查。

## 2026-10-16：项目共享 skill 专项验收

创建 typhoon-lab-workflow，衔接 Agent 入口及教学搬迁清单。结构、链接和中文空格路径静态检查通过；新 Agent 实际完成 smoke、RLC 基准及最终复核。Boost 历史副本仍为记录一致、性能 failed；已有模型映射与两项任务准备通过检查。另用未读取记忆/历史提示的上下文复算原始数据并复核方案，修订和复查事件检测区间表述。未新增模型或重新开展 GUI、跨电脑、真人/实体 HIL 验证。

- [专项摘要与全部证据](../results/skill-validation/20261016-typhoon-skill-0c9982/summary.md)
- [最终静态与链接检查](../results/skill-validation/20261016-typhoon-skill-0c9982/static-validation.json)
- [新 Agent RLC 实跑](../results/skill-validation/20261016-typhoon-skill-0c9982/rlc-live/outcome.md)
- [严格材料隔离复核](../results/skill-validation/20261016-typhoon-skill-0c9982/isolated-review/outcome.md)
- [源文件与历史记录保护](../results/skill-validation/20261016-typhoon-skill-0c9982/preservation.json)

## 2026-10-15：教学补全、新案例与复现

包含资源导航、RLC GUI、新 Agent 上下文、本机中文空格目录、单相桥整流三工况及比较、Boost 延后对照。68 项脚本测试通过，整流、RLC 回归与复现通过；Boost 延后两项峰偏差仍越限，保持 failed，记录复算一致。真人组员本轮暂不安排。

- [本轮完成记录](../results/20261015-workflow-completion/summary.md)
- [GUI 证据](../results/20261015-gui-validation/gui-validation.json)
- [Agent 与本机搬迁](../results/20261015-160620-agent-onboarding-ea232d/summary.md)
- [整流、比较、RLC 回归与复核](../results/20261015-rectifier-acceptance/actual_runs.json)
- [脚本测试](../results/20261015-rectifier-acceptance/unit_test_summary.json)
- [图表 QA](../results/20261015-rectifier-acceptance/visual_qa.json)
- [Boost 对照实际命令](../results/20261015-workflow-completion/late-controls.json)
- [Boost 同窗口独立分析](../results/20261015-boost-disturbance-analysis/analysis.json)

## 2026-10-15：统一执行与闭环动态实验

范围包括最小回环、RLC 基准与三工况扫描、Boost 基准、参考阶跃及两项输入电压扰动。脚本测试 54 项通过，全部最终记录复算一致；Boost 两项扰动的最大输出偏差超过 10%，保留 failed。

- [验证说明与全部实际目录](../results/20261015-112422-v2-validation-dd212b/summary.md)
- [实际命令和运行目录](../results/20261015-112422-v2-validation-dd212b/actual-runs.json)
- [报告重建与复核结果](../results/20261015-112422-v2-validation-dd212b/final-checks.json)
- [历史记录副本兼容检查](../results/20261015-112422-v2-validation-dd212b/historical-compatibility.json)
- [独立数值复核](../results/20261015-112422-v2-validation-dd212b/independent-numeric-audit.json)
- [模型保留范围](../results/20261015-112422-v2-validation-dd212b/model-preservation.json)
- [图表核对](../results/20261015-112422-v2-validation-dd212b/plot-qa.json)

## 2026-10-14：环境、回环与 RLC 实验

记录包含软件环境、模型检查、最小回环、RLC 基准和 Rin=1/5/10 Ω 扫描。基准与扫描通过当时配置的 3% RMS 相对误差判据，并保留原始数据、报告和复核结果。

| 项目 | 原始记录 |
|---|---|
| 环境与基准模型设置 | [运行清单](../results/20261014-211038-rlc-18c288/manifest.json) |
| 最小回环 | [清单](../results/20261014-212943-smoke-a2a022/manifest.json)、[实际读数](../results/20261014-212943-smoke-a2a022/readings.json) |
| RLC 基准 | [报告](../results/20261014-211038-rlc-18c288/report.html)、[指标](../results/20261014-211038-rlc-18c288/metrics.json)、[复核](../results/20261014-211038-rlc-18c288/verification.json) |
| RLC 三工况扫描 | [报告](../results/20261014-211142-sweep-db63f4/report.html)、[比较数据](../results/20261014-211142-sweep-db63f4/comparison.csv)、[复核](../results/20261014-211142-sweep-db63f4/verification.json) |

## 索引维护

完成一次验证后保存独立结果目录，再按日期登记范围、结论与证据链接，同时更新验证状态中的能力和实测结论。历史结果及代码快照保留原貌；操作教程直接反映现行用法。
