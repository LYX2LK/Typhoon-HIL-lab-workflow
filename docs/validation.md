# 验证状态与实测结论

**2026-11-01 示例波形配对比较：** 默认首轮概览；配对操作计算差值/倍率并分别绘制tu1/tu2、tu3/tu4局部图，展示差异表，完成后不重复推荐相同比较。267项最终回归通过；真实API新对话、配对、追问及旧会话副本升级、页面两图和离线报告复核通过。[实现与验收](../results/agent-tasks/20261101-100310-waveform-pair-comparison-a62f/summary.md)。

**2026-11-01 示例波形追问修复：** 局部选项按所选记录分析，重试保留原问题与范围；261项完整测试及最终23项案例复测通过，真实API与页面连续选择通过，离线报告和最终复核passed。[修复记录](../results/agent-tasks/20261101-093332-waveform-followup-fix-a17b/summary.md)。

**2026-11-01 三案例 Agent：** 首页可选 Boost 输入跌落、四组示例波形、三相整流桥二极管开路，支持直接发送首条问题、绑定案例、追问、图表编排及离线报告。三案例均完成真实API分析、追问和最终复核；两个仿真案例完成确认后的对照执行。256项unittest通过，RLC基准与三点扫描回归、旧Boost版本1会话复核通过。整流桥固定2%数值参考判据通过，Boost原10%峰偏差判据仍failed。使用见[Agent说明](agent.md)，完整证据见[本轮验收](../results/agent-tasks/20261101-three-cases/summary.md)。


选项契约已修正：收尾/深入作为程序声明的目标操作，讨论必须引用非空追问，生成Schema按工具种类限定参数；选项改为独立短标题。以T002实际保存数据复现旧Schema接受、旧校验拒绝的不一致，使用新版测试控制对象通过Schema和业务校验。234项离线测试通过，未调用真实模型或运行实验。[故障与验证记录](../results/agent-tasks/20261031-agent-option-contract-4c92/summary.md)。

报告正文与结构化参数已分离：新协议使用普通Markdown及段落引用，JSON语法、业务校验、正文生成与工具协议错误分别记录。230项离线测试通过，涵盖英文引号/反斜杠、失败后的只读正文、参数/引用篡改和旧协议复核；当前失败会话及原四轮会话只读复核通过。未调用真实模型或运行新实验。[实现与离线验证](../results/agent-tasks/20261031-agent-split-report-8d41/summary.md)。

演示目的与案例衔接已调整：首页先说明控制器测试目标，再展示分析验证流程与Boost先行案例，首轮任务和后续收尾提示同步更新。仅完成Python/JavaScript语法检查及隔离页面预览；未调用大模型，未开展Agent或Virtual HIL实验验证。[修改与静态检查记录](../results/agent-tasks/20261031-agent-purpose-731c/summary.md)。

Agent结论与收尾分支已更新：当前四轮数据重分析为T007，模型推荐形成阶段结论，并提供继续定位机理的选择；已确认观察与假说状态分开，取消新报告的全局固定undetermined。两分支在会话副本中完成真实API与复核，收尾不再提问，深入切换为机理目标并明确新增能力需求。224项测试通过；原四轮与T001–T006/计划共526文件哈希保持，本轮未新增Virtual HIL。[设计与验收](../results/agent-tasks/20261031-agent-conclusions-5a92/summary.md)。

Agent独立使用反馈的输出格式问题已修复：提示框tone缺省采用安全默认样式；新报告改用DeepSeek官方strict函数Schema、temperature=0，不采用自动格式重发。首次、无扰动对照、延后对照3组真实上下文均一次通过解析与本地校验；当前会话已按新协议恢复T004，原2次实验及失败轮次251个文件哈希保持。214项测试通过。[原因与验证](../results/agent-tasks/20261031-agent-json-recovery-a67c/summary.md)。

对话式Agent已完成真实闭环：2次Virtual HIL（0.5/1.2 s施扰）、5轮模型分析、11次DeepSeek官方API调用，实际调用read_evidence与compare_runs；自然语言追问改变区块次序及选项参数，确认后执行所选配置并更新解释。两次记录passed，峰偏差18.2009%/17.8111%，性能仍failed。205项测试、RLC基准与三点扫描回归通过。机理表述经两轮复阅修正，数值与记录校验不代替自然语言因果判断。[使用说明](boost-agent.md)、[本轮交付](../results/agent-tasks/20261031-agent-demo-9b17/delivery/index.html)、[验收总结](../results/agent-tasks/20261031-agent-demo-9b17/summary.md)。

同日界面联动修正：第2步按首次模型回答动态展示建议、顺序及验证目的，人工选择与模型建议分开；改选后旧确认失效。189项unittest与复用既有真实分析的浏览器交互检查通过，本次未新跑仿真或调用API。当前服务生效范围与最后文字修订的加载限制见[修正记录](../results/agent-tasks/20261031-demo-suggestion-link-c82f/summary.md)。

**2026-10-31 会议演示专项：** 已实际跑通 [Boost + AI 在线分析与确认复验](boost-ai-demo.md)：Virtual HIL 输入跌落、真实 DeepSeek 官方API、配置差异展示、用户确认、延后对照及模型更新解释。完整界面彩排通过，184项unittest通过；RLC基准与三工况扫描回归通过。两次Boost记录一致，峰偏差18.2009%/17.8233%仍超过固定10%，性能均failed。交付包括[五页汇报、操作单、离线报告、证据和录屏](../results/agent-tasks/20261031-meeting-demo-6f24/delivery/index.html)，过程与范围见[任务总结](../results/agent-tasks/20261031-meeting-demo-6f24/summary.md)。本地推理、真实故障标签及实体HIL/控制器集成仍待后续验收。

本页维护工作流已验证的能力、实验判据结果和待验事项，供使用者判断实验输出的适用范围。此前专项验证记录：**2026-10-23**：完成简短不完整任务的 Agent 分阶段观察与复核，首次澄清失败、文档修订和新上下文重测均有记录；50 Hz 通过，49.25 Hz 超时及重试保护拦截，低频比较未评价。见[评审报告](../results/skill-validation/20261022-agent-intake-lowfreq-a1/assessment.md)。2026-10-22 的专项验证包括 THCC 2026.3 Virtual HIL 光伏 50/51 Hz 工况、RLC 基准/扫描回归，以及四组外部波形离线检查；见[任务记录](../results/agent-tasks/20261022-waveforms-pv-a1/task.md)。此前完整验证及电机动态、建模、工程回归的证据按日期保存于[验证记录索引](validation-history.md)。

脚本与记录检查通过。感应电机 1430/850 rpm 独立启动工况及 1430→850 rpm 运行中阶跃通过预先固定的项目教学判据；RLC、Boost 参考阶跃、单相桥整流三工况与趋势比较均有通过记录。Boost 两项输入扰动及延后对照的峰偏差仍超过固定 10%，保留 failed。RLC GUI、新 Agent 上下文和本机中文空格路径搬迁已完成。真人与跨电脑验收仍属后续任务。

2026-10-20 的专项推进增加了[从空白图自建 RLC 模型的程序练习](modeling-practice.md)和[1000 rpm 陌生实例受控演练](../cases/im_mid_speed_intake/README.md)，均在 Virtual HIL 运行并完成最终复核。自建模型的真人 GUI 重做、真实外来测试实例与其他组员独立交接继续按各自条件验收。

## 已验证能力

| 项目 | 结论与依据 |
|---|---|
| 环境 | Python 3.11.4、Typhoon-HIL-API 1.32.1、TyphoonTest 1.35.6；见 [环境快照](../results/20261015-112422-v2-validation-dd212b/environment.json) |
| 脚本逻辑 | 267项unittest通过，覆盖原有模型/数据流程、Agent案例选择、数值引用、API失败、局部追问重试、配对差异计算与重复建议限制、确认绑定及原始记录复核；[当前日志](../results/agent-tasks/20261101-100310-waveform-pair-comparison-a62f/full-tests-final.log) |
| 运行与记录 | 感应电机完整接入及 RLC 基准/扫描、Boost 阶跃、整流基准回归，见 [最终命令](../results/agent-tasks/20261019-case-onboarding/release-validation/commands.json)；最小回环与先前能力的证据见验证索引 |
| 案例与 CLI | 八个案例（新增光伏 HzWatt）、五个注册适配器；完整性、软件支持和实际证据分开，JSON 两种旗标位置及非零退出码通过；[接口](case-interface.md)、[动态案例](../cases/im_speed_step/README.md) |
| 能力查询与记录版本 | 五个适配器通过案例静态查询提供字段范围、单位、设置阶段、信号及事件能力；八个案例静态检查可用。新清单区分配置、记录格式和分析方法版本；旧 RLC、Boost 记录只读复核通过。2026-10-20 的四模型基准及 RLC 扫描在 Virtual HIL 复核通过；[工程回归](../results/agent-tasks/20261020-2000-structure-qa-a1/task.md) |
| 自建模型与接入演练 | 空白图 9 元件、15 连线，新增 V_Rin 实测 400 点，最大 RMS 相对差 0.20207%；1000 rpm 案例评价窗口 40,000 点，最大相对转速误差 0.1671875%；[建模报告](../results/20261020-152740-modeling-practice-c24cdc/report.md)、[案例批次](../results/20261020-152120-case-im_mid_speed_intake-84c0a8/report.md)均通过最终复核 |
| 公共复核接口 | `records.verify_run` 供 CLI、案例和离线比较调用；旧 RLC passed 与旧 Boost failed 记录只读复算仍保持 record_status=passed；本次 RLC 基准和扫描回归通过。见[任务记录](../results/agent-tasks/20261020-modeling-intake-a1c9/task.md) |
| 短任务 Agent 验收 | 两个未继承父对话的上下文完成首次观察与修订后重测；新上下文先确认条件再配置复用。基准通过，低频执行error被如实保留，不能认定全部实验通过。[分阶段评审](../results/skill-validation/20261022-agent-intake-lowfreq-a1/assessment.md) |
| 光伏与外部波形 | 光伏 50/51 Hz 独立稳态及 RLC 回归通过；外部四组 CSV 完成离线检查，标签和导出元信息待补。[任务证据](../results/agent-tasks/20261022-waveforms-pv-a1/task.md) |
| 感应电机接口 | 相电压、参考/反馈、恒值负载模式与缩放、控制周期、Virtual HIL 短采集均有实际证据；[接口映射](../cases/im_speed_tracking/README.md) |
| 感应电机动态阶跃 | 每次运行在模型副本接入 Step 与求和节点，参考探针测量控制器实际输入；事件文件参与复算。5 s/20 kHz 实测、事件前后 ±1% 项目判据均通过；[案例](../cases/im_speed_step/README.md)、[任务记录](../results/agent-tasks/20261020-im-speed-step-b47e/task.md) |
| 模型本机准备 | 来源清单统一安装相对路径及模型/面板哈希；不含模型的源码副本一键补齐 9 个文件、重复执行跳过，五案例静态通过；该副本的最小回环、RLC 基准与扫描实跑及复核通过。[证据](../results/agent-tasks/20261019-model-assets-prepare-732cd1/summary.md) |
| 模型属性 | [核对记录](../results/20261015-112422-v2-validation-dd212b/model-preservation.json) 确认 Boost 官方元件属性及 PI 参数保留，教学参考与监测组件的改动范围可查 |
| 数值与图表 | [独立数值复核](../results/20261015-112422-v2-validation-dd212b/independent-numeric-audit.json) 与分析指标一致；[图表核对](../results/20261015-112422-v2-validation-dd212b/plot-qa.json) 包含原始全程和动态细节 |
| 既有记录兼容 | RLC 通过与 Boost 性能失败记录的完整副本均完成 verify→report→verify，原状态保留；[实际命令](../results/agent-tasks/20261019-case-onboarding/release-validation/commands.json)、[原记录保护](../results/agent-tasks/20261019-case-onboarding/preservation.json) |
| 案例发现与编排 | 新 Clone 缺失电机依赖仍可发现 RLC；run-case 串行执行并自动复核、登记索引。107 项测试及电机/RLC/Boost 批次验收通过；Boost 性能失败保持原判据。[证据](../results/agent-tasks/20261019-case-discovery-run-case/summary.md) |
| 新模型和趋势 | 单相桥整流基准、低输入、重载与离线比较均通过；[实际目录与复核](../results/20261015-rectifier-acceptance/actual_runs.json)，[图表 QA](../results/20261015-rectifier-acceptance/visual_qa.json) |
| GUI 操作 | RLC 教学副本编译加载、Virtual HIL、面板参数、信号、周期波形与启停已实测；[证据](../results/20261015-gui-validation/gui-validation.json) |
| Agent 与本机搬迁 | 未继承父对话的新子代理按明确任务和材料完成 RLC 扫描、Boost 阶跃与 CSV 独立复算；中文空格目录、其他 cwd 的环境与实验检查通过；[记录](../results/20261015-160620-agent-onboarding-ea232d/summary.md) |
| 项目共享 skill | 案例发现、材料核对、配置复用与适配器扩展路线已接通；结构检查、[独立 Agent 电机任务](../results/agent-tasks/20261019-case-onboarding/independent/phase2-final-report.md) 与 [入口一致性](../results/agent-tasks/20261019-case-onboarding/entry-parity.json) 通过。先前 RLC 与失败解释行为见 [专项记录](../results/skill-validation/20261016-typhoon-skill-0c9982/summary.md) |
| 原记录与已有修改 | 3601 个既有结果文件哈希未变，14 个原暂存文件内容保留，既有模型与来源条目保持一致；[保护审计](../results/agent-tasks/20261019-case-onboarding/preservation.json) |
| Boost 扰动分析 | 原始数据复算与两项延后对照已完成；[分析说明](boost-disturbance-analysis.md)、[实际命令](../results/20261015-workflow-completion/late-controls.json) |

脚本测试、实际 Virtual HIL、GUI 观察、新 Agent、本机搬迁和真人/跨机复现分别验收。HIL101、Pro 1 表示编译目标与配置；本页的运行证据对应 Virtual HIL。

## 实际运行与记录复核

| 实验 | 实验状态 | 记录一致性 | 实际产物 |
|---|---|---|---|
| Agent 演练：光伏50 Hz | passed | passed | [报告](../results/20261023-010941-generic_pv_plant-0940d4/report.md) |
| Agent 演练：49.25 Hz 首次/重试 | error / error | failed / failed（缺少复算指标） | [超时](../results/20261023-011057-generic_pv_plant-0a32a9/report.md)、[保护拦截](../results/20261023-011720-generic_pv_plant-33bbeb/report.md) |
| 光伏 50/51 Hz 独立稳态 | passed | passed | [批次报告](../results/20261022-200543-case-pv_hzwatt-f08eab/report.md) |
| 最小回环 | passed | passed | [记录](../results/20261015-113018-smoke-903d97/manifest.json) |
| 感应电机 1430 rpm | passed | passed | [报告](../results/20261019-122808-induction_motor_closed_loop-664f11/report.html) |
| 感应电机 850 rpm | passed | passed | [报告](../results/20261019-122914-induction_motor_closed_loop-dc2ad0/report.html) |
| 感应电机 1430→850 rpm 运行中阶跃 | passed | passed | [案例批次](../results/20261020-162211-case-im_speed_step-dc3442/report.md)、[子运行报告](../results/20261020-162211-case-im_speed_step-dc3442/runs/01-im_speed_step_1430_to_850/report.html) |
| 自建 RLC 测量点练习 | passed | passed | [报告](../results/20261020-152740-modeling-practice-c24cdc/report.md) |
| 陌生实例演练：1000 rpm | passed | passed | [批次报告](../results/20261020-152120-case-im_mid_speed_intake-84c0a8/report.md) |
| RLC 基准 | passed | passed | [记录](../results/20261015-113040-rlc-ea344a/report.html) |
| RLC 三工况扫描 | passed | passed | [记录](../results/20261015-113104-sweep-1a2086/report.html) |
| Boost 基准 | passed | passed | [记录](../results/20261015-113207-boost_closed_loop-e9ac14/report.html) |
| Boost 参考阶跃 | passed | passed | [记录](../results/20261015-113237-boost_closed_loop-9e116c/report.html) |
| Boost 输入跌落 | failed | passed | [记录](../results/20261015-113307-boost_closed_loop-caf1cc/report.html) |
| Boost 输入升高 | failed | passed | [记录](../results/20261015-113336-boost_closed_loop-ec9253/report.html) |
| 单相整流基准 | passed | passed | [报告](../results/20261015-161835-single_phase_rectifier-61b0e9/report.html) |
| 单相整流低输入 | passed | passed | [报告](../results/20261015-161912-single_phase_rectifier-59739a/report.html) |
| 单相整流重载 | passed | passed | [报告](../results/20261015-161939-single_phase_rectifier-2b7f4a/report.html) |
| 单相整流三工况趋势 | passed | passed | [报告](../results/20261015-162101-rectifier-comparison-6297c5/report.html) |
| Boost 延后输入跌落 | failed | passed | [报告](../results/20261015-162319-boost_closed_loop-99a226/report.html) |
| Boost 延后输入升高 | failed | passed | [报告](../results/20261015-162354-boost_closed_loop-d2a404/report.html) |

record_status 表示文件与指标复算是否一致，experiment_status 表示实验执行和性能判据的结果。记录一致而性能未达标时，总 status 为 failed，verify 退出码为 1。

## 光伏 HzWatt 与外部波形

两工况分别等待至少 12 s 仿真时间，以 10 kHz 采集 2 s，各 20,000 点参与判定。实测有功与官方参考表比较，误差上限 1%。

| 频率 / Hz | 参考有功 / kW | 实测均值 / kW | 最大相对误差 | 实验 / 记录 |
|---:|---:|---:|---:|---|
| 50 | 250 | 250.000000 | 0.00001831% | passed / passed |
| 51 | 170 | 170.000000 | 0.00002693% | passed / passed |

限额反馈 Pref_fb_kW 在两工况均为 250 kW，来自 HzWatt 前的 Pcurtailment 与额定功率，独立于调频后的输出参考。初次误映射导致的失败及方法版本修正保留在[验证索引](validation-history.md)；当前方法 2 的原始 CSV 独立复算与保存指标一致。操作见[光伏案例](../cases/pv_hzwatt/README.md)。

外部数据已具备基于显式清单的两列 CSV 分析与独立复核入口，范围与操作见[数据接口](external-waveforms.md)。原 tu 批次在新记录格式下保持原数值定义，八份原件哈希不变；未知单位、结构失败及方法不适用保留原因。工具回归、原批次等价性、三个新上下文行为及实际证据见[实施结果](../results/agent-tasks/20261023-capability-intake/summary.md)。

原 tu1–tu4 导出间隔均约 5 ns，tu2/tu3 的截图采集速率不同，采集/导出关系仍待确认。幅值和边沿特征见[接收报告](../results/agent-tasks/20261023-capability-intake/tu-evidence/report.md)。群聊确认批次含两种正常与对应两种异常，逐文件配对仍为形态推断；测点、物理故障原因、控制器验收和回放精度待后续确认。

2026-10-31 已完成[四组波形识别演示](../results/agent-tasks/20261031-tu-diagnosis-a1/explained/report.html)：预设规则判 tu1/tu3 正常，tu2 为电平跌落异常、tu4 为上升过程回落异常，并给出事件位置和数值依据。当前 Codex 会话生成解释后以 JSON 导入，尚未接通自动API或本地推理服务。174项 unittest 通过，原始CSV的标准库独立复算与八份原件哈希检查通过；记录复核passed，性能仍为not_evaluated。这是四条已查看样本的规则演示，尚无独立识别准确率。方法见[识别接口](waveform-diagnosis.md)，完整范围见[实施记录](../results/agent-tasks/20261031-tu-diagnosis-a1/summary.md)。

## 感应电机独立启动

两工况分别显式设置 Speed RPM，Vgrid 为 230 V 相电压 RMS、50 Hz，Load_sel=1、IM_Load=0.5，对应 2 N·m 恒值负载指令。实际步长 0.5 µs、抽取 100，每次采集 4 s、20 kHz、80,000 点；[2,4) s 评价窗口含 40,000 点。

| 参考 / rpm | 平均转速 / rpm | 最大绝对误差 / rpm | 最大相对误差 | 超限点数 | 状态 |
|---:|---:|---:|---:|---:|---|
| 1430 | 1429.635450 | 2.052490 | 0.143531% | 0 | passed |
| 850 | 849.758187 | 1.383179 | 0.162727% | 0 | passed |

这些是参考官方断言建立的项目教学判据：采用独立启动、显式常值负载和 20 kHz，与官方共享仿真连续改速、50 kHz 的条件不同。来源与调整见 [判据说明](../cases/im_speed_tracking/acceptance.md)。速度参考 API 回读及参考/负载全程波形均留存；[CSV 独立复算](../results/agent-tasks/20261019-case-onboarding/release-validation/independent-csv.json) 与指标一致。短采集得到有效的性能 failed，错误输入与不完整数据按 error 处理。

## 感应电机运行中转速阶跃

在同一次 Virtual HIL 中固定 230 V 相电压 RMS、50 Hz、2 N·m 负载，5 s/20 kHz 共采集 100,000 点；模型于仿真时刻 2 s 将实际送入控制器的参考由 1430 rpm 降至 850 rpm。[事件文件](../results/20261020-162211-case-im_speed_step-dc3442/runs/01-im_speed_step_1430_to_850/events.json)记录模型触发时刻 2 s、首个变化采样 2.0001005 s，前后样本检测区间为 `(2.0000505, 2.0001005]` s。事件时序、电平均通过；事件缺失、错时或电平错误归为 `error`。

事件前 `[1.5,2)` s 最大相对误差为 **0.576249%**；实际生效后 2 s 起，即 `[4.0001005,5)` s 的 19,998 个评价点，最大相对误差为 **0.133947%**，越限点 0，固定 ±1% 项目教学判据通过。调节时间 **1.2761 s**；沿降速方向的超出量为阶跃幅值的 **0.006009%**，仅作解释指标。完整[波形](../results/20261020-162211-case-im_speed_step-dc3442/runs/01-im_speed_step_1430_to_850/waveforms.png)、[事件局部图](../results/20261020-162211-case-im_speed_step-dc3442/runs/01-im_speed_step_1430_to_850/response_detail.png)及[原始 CSV](../results/20261020-162211-case-im_speed_step-dc3442/runs/01-im_speed_step_1430_to_850/waveforms.csv)均保存；最终 `record_status=passed`、`experiment_status=passed`。来源与适用范围见[阶跃判据](../cases/im_speed_step/acceptance.md)，完整命令、回归和历史记录副本复核见[任务记录](../results/agent-tasks/20261020-im-speed-step-b47e/task.md)。

下列 RLC、Boost 与整流详细数值保留其原验证记录；2026-10-20 的 RLC 基准/扫描与 Boost 阶跃回归路径见[动态实验任务记录](../results/agent-tasks/20261020-im-speed-step-b47e/task.md)。

## RLC 数值核对

条件为 10 V RMS、1000 Hz、0°；Rin=5 Ω、R=0.1 Ω、L=10 µH、C=500 µF。实际采集 400 点、20 kHz，按全部捕获样本计算 RMS；允许相对误差为 3%。公式与窗口定义见 [RLC 说明](experiments.md)。

| 信号 | 实测 RMS | 解析 RMS | 相对误差 | 状态 |
|---|---:|---:|---:|---|
| 电流 I / A | 1.997625439 | 1.997672528 | 0.002357% | passed |
| 节点电压 Va1 / V | 0.152952070 | 0.152645824 | 0.200626% | passed |

| Rin / Ω | 电流 RMS / A | 节点电压 RMS / V | 电流相对误差 | 电压相对误差 | 状态 |
|---:|---:|---:|---:|---:|---|
| 1 | 9.918259404 | 0.759365298 | 0.010922% | 0.186041% | passed |
| 5 | 1.997615788 | 0.152951998 | 0.002840% | 0.200578% | passed |
| 10 | 0.999430006 | 0.076524264 | 0.001677% | 0.202571% | passed |

基准与扫描中的 Rin=5 Ω 为独立运行，各自保留原始数据。

## Boost 动态结果

四个工况均采集 1.5 s、10 kHz、15,000 点。最终均值窗口为 [1.4,1.5) s，动态事件前窗口为 [0.4,0.5) s。模型和判据定义见 [Boost 说明](boost-experiments.md)。

| 工况 | 最终均值 / V | 稳态相对误差 | 调节／恢复 / s | 超调或最大偏差 | 状态 |
|---|---:|---:|---:|---:|---|
| Boost 基准 | 50.000340 | 0.000680% | — | — | passed |
| 参考 50→60 V | 59.998315 | 0.002809% | 0.2489 | 0.02968% | passed |
| 输入 35→28 V | 49.995309 | 0.009381% | 0.3307 | 18.20093% | failed |
| 输入 35→38.5 V | 50.009795 | 0.019589% | 0.2119 | 16.66905% | failed |

参考超调以 10 V 阶跃幅值归一化；输入扰动最大偏差以 50 V 归一化。两项扰动的事件、最终误差和恢复时间通过，最大偏差分别为 18.20093% 和 16.66905%，超过固定的 10%。官方 PI 参数与原判据保持不变，越限项和失败状态均留在报告中。

三次动态事件的首变采样时刻均为 0.5000005 s，相邻样本检测区间约为 (0.4999005,0.5000005] s，默认分辨率为 100 µs。完整图保留启动瞬态，动态细节图标出局部时间范围。

## 延后扰动对照

按运行前固定方案，将输入事件从 0.5 s 延后到 1.0 s，总采集由 1.5 s 改为 2.0 s，其余模型、PI、事件幅度和判据保持不变。比较统一采用事件后 [0,0.9) s、9000 点，完整报告另保留各自全采集窗口。

| 工况 | 原峰偏差 | 延后峰偏差 | 原恢复 / s | 延后恢复 / s | 正式状态 |
|---|---:|---:|---:|---:|---|
| 输入 35→28 V | 18.200928% | 17.823334% | 0.3307 | 0.3274 | failed |
| 输入 35→38.5 V | 16.669052% | 17.251053% | 0.2119 | 0.2205 | failed |

施扰前残余趋势减小，两项仍超过 10% 峰偏差上限。增加等待不足以使所测两工况通过；当前记录不能确定 PI、饱和或带宽根因。完整数值、来源与候选机制见 [扰动分析](boost-disturbance-analysis.md)。

## 单相桥整流实测

三次独立稳态实验均等待 1.5 s，以 20 kHz 采集 0.2 s，覆盖十个输入周期。独立理想桥 LC-R 数值参考与步长收敛、采样窗口、原模型和副本修改范围见 [整流教程](rectifier-experiments.md)。

| 工况 | 输出均值 / V | 纹波峰峰 / V | 负载均值 / A | 状态 |
|---|---:|---:|---:|---|
| baseline | 316.447953 | 24.066986 | 3.164480 | passed |
| low_input | 253.158352 | 19.262268 | 2.531584 | passed |
| heavy_load | 314.864541 | 45.744904 | 6.297291 | passed |

低输入电压、电流和纹波同比缩放，重载输出均值降低、纹波和电流增加，九项固定趋势检查通过。原官方面板留存来源，脚本采集已验；该面板的启动宏存在不匹配源名的静态发现，GUI 路径单独核对。

## 验证范围与后续事项

| 项目 | 状态与完成方式 |
|---|---|
| 光伏低频执行恢复 | 本轮49.25 Hz无采样；先确认会话归属和时钟读取/清理异常，恢复后使用冻结配置重新运行并独立复算。参见[后续事项](../results/skill-validation/20261022-agent-intake-lowfreq-a1/assessment.md#接下来可做的工作) |
| 人员独立复现 | 用户要求本轮先不安排；后续按 [交接流程](handoff.md) 由本人记录操作与解释 |
| GUI 手动操作路径 | RLC 软件界面已实测；[首次实验](first-experiment.md) 已同步实际步骤和截图。人员操作能力另验 |
| 跨电脑 | 本轮完成同机中文空格路径搬迁；另一台机器的软件、许可和设备条件另行实测 |
| 单相整流原面板 | API 教学路径通过；原面板启动宏需在独立教学副本核对后再验 GUI |
| 感应电机 GUI 面板 | 自动脚本链路已实测；SCADA 面板的 GUI 操作另行验收 |
| 实体 HIL 与外部控制器 | 按具体设备、控制器和实验负责人建立实测记录 |

2026-10-15 教学补全任务、实际命令与证据见 [完成记录](../results/20261015-workflow-completion/summary.md)；此前的详细数值核对见 [上午验证记录](../results/20261015-112422-v2-validation-dd212b/summary.md)。
