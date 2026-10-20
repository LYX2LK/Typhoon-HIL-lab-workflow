# 验证记录索引

本页按验证日期索引已保存的实际记录，供维护者追溯当时的模型、代码、配置和结论。使用者判断现行能力时查看 [验证状态](validation.md)，实验操作从 [README](../README.md) 开始。

## 2026-10-20：感应电机运行中转速阶跃

在本机 THCC 2026.3 Virtual HIL 上完成同一次仿真中的 1430→850 rpm 参考阶跃，5 s/20 kHz 共 100,000 点。事件首变采样为 2.0001005 s，模型触发时刻为 2 s；事件前最大相对误差 0.576249%，实际生效后 2 s 起的最大相对误差 0.133947%，均满足预设 ±1% 项目教学判据。调节时间 1.2761 s，沿降速方向的超出量为阶跃幅值的 0.006009%，后者只作解释。案例批次与直接运行均为 `record_status=passed`、`experiment_status=passed`。126 项 unittest 通过；原有电机两种启动、Boost 阶跃、RLC 基准与扫描回归通过，历史电机记录在副本上完成 `verify → report → verify`。

- [任务记录与命令](../results/agent-tasks/20261020-im-speed-step-b47e/task.md)、[案例教程](../cases/im_speed_step/README.md)、[固定判据](../cases/im_speed_step/acceptance.md)
- [案例批次报告](../results/20261020-162211-case-im_speed_step-dc3442/report.md)、[子运行最终复核](../results/20261020-162211-case-im_speed_step-dc3442/runs/01-im_speed_step_1430_to_850/verification.json)、[事件证据](../results/20261020-162211-case-im_speed_step-dc3442/runs/01-im_speed_step_1430_to_850/events.json)
- [直接运行最终复核](../results/20261020-161748-induction_motor_closed_loop-a89a34/verification.json)、[历史启动记录副本](../results/agent-tasks/20261020-im-speed-step-b47e/historic-startup-copy/verification.json)

## 2026-10-20：自建模型、陌生实例与复核接口

从空白图建立 RLC 模型，新增输入电阻压降测量点并以 Virtual HIL 采集 400 点；三项 RMS 相对差最大为 0.20207%，3% 教学判据通过。用已有感应电机适配器接入新的 1000 rpm 独立启动案例，批次及记录复核通过；`[2,4)` s 的 40,000 点中最大相对转速误差为 0.1671875%，低于固定 1% 判据。复核函数从 CLI 分离后，RLC 基准与三工况扫描回归通过，旧 RLC passed 与旧 Boost failed 记录只读复算保持原状态。真人 GUI 自建、真实外来实例与跨电脑复现另行验收。

- [任务记录与范围](../results/agent-tasks/20261020-modeling-intake-a1c9/task.md)
- [自建模型教程](modeling-practice.md)、[运行报告](../results/20261020-152740-modeling-practice-c24cdc/report.md)、[最终复核](../results/20261020-152740-modeling-practice-c24cdc/verification.json)
- [陌生实例演练](../cases/im_mid_speed_intake/README.md)、[批次报告](../results/20261020-152120-case-im_mid_speed_intake-84c0a8/report.md)、[最终复核](../results/20261020-152120-case-im_mid_speed_intake-84c0a8/verification.json)
- [RLC 基准复核](../results/20261020-152217-rlc-165441/verification.json)、[三工况扫描复核](../results/20261020-152240-sweep-fb7e46/verification.json)

## 2026-10-19：官方模型统一为本机依赖

完成安装相对路径、模型及面板哈希统一，新增 prepare-models，根目录官方模型/面板取消 Git 跟踪并保留本机副本；vendor/ 与 custom/ 预留为空。119 项测试通过；不含模型的源码导出在中文空格路径和其他 cwd 下补齐 9 个文件，重复执行全部跳过，五案例静态检查通过。该副本的 Virtual HIL 最小回环、RLC 基准和扫描均通过，记录复核通过。属于同机准备与软件运行验证。

- [完整验收](../results/agent-tasks/20261019-model-assets-prepare-732cd1/summary.md)
- [实际命令](../results/agent-tasks/20261019-model-assets-prepare-732cd1/commands.json)
- [干净源码准备](../results/agent-tasks/20261019-model-assets-prepare-732cd1/clean-checkout.json)
- [实际运行与复核](../results/agent-tasks/20261019-model-assets-prepare-732cd1/live-results.json)
- [模型与历史结果保护](../results/agent-tasks/20261019-model-assets-prepare-732cd1/preservation.json)

## 2026-10-19：新 Clone 发现与案例串行编排

发现与单案例校验分开返回，缺失本机依赖提供结构化标记。新增 run-case 统一预检、串行执行、复核与自动索引。107 项单元测试通过；新 Clone 无电机模型时仍可发现 RLC，预检受阻不写结果。电机两工况、RLC 基准与扫描通过；Boost 四项扰动保留性能 failed，全部记录复核通过。批次报告重建及再次复核通过，既有结果哈希不变。

- [完整验收与命令](../results/agent-tasks/20261019-case-discovery-run-case/summary.md)
- [新 Clone 检查](../results/agent-tasks/20261019-case-discovery-run-case/clone-check.json)
- [实际批次与关联](../results/agent-tasks/20261019-case-discovery-run-case/live-results.json)

## 2026-10-19：案例接收、CLI JSON 与感应电机接入

完成模型技术预验、五个案例描述、显式适配器注册、只读发现/校验、版本化 JSON 与共享 skill 路线选择。感应电机实际核实相电压定义、速度参考和负载选择；1430/850 rpm 两工况通过全窗口 1% 项目教学判据。93 项单元测试通过，RLC 基准/扫描、Boost 阶跃、整流基准回归及历史记录副本兼容检查完成。原始记录与已有暂存修改保留，新增官方模型和面板作为本机依赖排除 Git。

- [完整验收与交付范围](../results/agent-tasks/20261019-case-onboarding/summary.md)
- [模型接口与实际短采集](../cases/im_speed_tracking/README.md)
- [最终命令、返回码和运行目录](../results/agent-tasks/20261019-case-onboarding/release-validation/commands.json)
- [CSV 独立复算](../results/agent-tasks/20261019-case-onboarding/release-validation/independent-csv.json)
- [脚本测试](../results/agent-tasks/20261019-case-onboarding/unit-tests.log)
- [材料与原记录保护](../results/agent-tasks/20261019-case-onboarding/preservation.json)
- [文档与技能静态检查](../results/agent-tasks/20261019-case-onboarding/static-validation.json)
- [独立 Agent 实跑与复算](../results/agent-tasks/20261019-case-onboarding/independent/phase2-final-report.md)
- [默认与 JSON 入口一致性](../results/agent-tasks/20261019-case-onboarding/entry-parity.json)

独立 Agent 的当前任务与实际执行证据在完整验收中单列。真人、跨电脑、实体 HIL 与证据发布继续按后续工作组推进。

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
