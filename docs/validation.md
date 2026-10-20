# 验证状态与实测结论

本页维护工作流已验证的能力、实验判据结果和待验事项，供使用者判断实验输出的适用范围。最近一次完整验证日期为 **2026-10-19**，模式为 THCC 2026.3 Virtual HIL。案例工具、CLI JSON 与感应电机接入的证据见 [工作组①验收记录](../results/agent-tasks/20261019-case-onboarding/summary.md)。按日期查找其他记录，见 [验证记录索引](validation-history.md)。

脚本与记录检查通过。感应电机 1430/850 rpm 独立启动工况通过预先固定的全窗口 1% 判据；RLC、Boost 参考阶跃、单相桥整流三工况与趋势比较均有通过记录。Boost 两项输入扰动及延后对照的峰偏差仍超过固定 10%，保留 failed。RLC GUI、新 Agent 上下文和本机中文空格路径搬迁已完成。真人与跨电脑验收仍属后续任务。

2026-10-20 的专项推进增加了[从空白图自建 RLC 模型的程序练习](modeling-practice.md)和[1000 rpm 陌生实例受控演练](../cases/im_mid_speed_intake/README.md)，均在 Virtual HIL 运行并完成最终复核。自建模型的真人 GUI 重做、真实外来测试实例与其他组员独立交接继续按各自条件验收。

## 已验证能力

| 项目 | 结论与依据 |
|---|---|
| 环境 | Python 3.11.4、Typhoon-HIL-API 1.32.1、TyphoonTest 1.35.6；见 [环境快照](../results/20261015-112422-v2-validation-dd212b/environment.json) |
| 脚本逻辑 | [完整测试](../results/agent-tasks/20261019-model-assets-prepare-732cd1/unit-tests.stderr.log) 119 项通过，包含模型准备、文件保护、案例路径边界、JSON 异常、1% 边界与窗口端点 |
| 运行与记录 | 感应电机完整接入及 RLC 基准/扫描、Boost 阶跃、整流基准回归，见 [最终命令](../results/agent-tasks/20261019-case-onboarding/release-validation/commands.json)；最小回环与先前能力的证据见验证索引 |
| 案例与 CLI | 六个案例（含 1000 rpm 受控演练）、四个注册适配器；完整性、软件支持和实际证据分开，JSON 两种旗标位置及非零退出码通过；[接口](case-interface.md)、[专项记录](../results/agent-tasks/20261020-modeling-intake-a1c9/task.md) |
| 自建模型与接入演练 | 空白图 9 元件、15 连线，新增 V_Rin 实测 400 点，最大 RMS 相对差 0.20207%；1000 rpm 案例评价窗口 40,000 点，最大相对转速误差 0.1671875%；[建模报告](../results/20261020-152740-modeling-practice-c24cdc/report.md)、[案例批次](../results/20261020-152120-case-im_mid_speed_intake-84c0a8/report.md)均通过最终复核 |
| 公共复核接口 | `records.verify_run` 供 CLI、案例和离线比较调用；旧 RLC passed 与旧 Boost failed 记录只读复算仍保持 record_status=passed；本次 RLC 基准和扫描回归通过。见[任务记录](../results/agent-tasks/20261020-modeling-intake-a1c9/task.md) |
| 感应电机接口 | 相电压、参考/反馈、恒值负载模式与缩放、控制周期、Virtual HIL 短采集均有实际证据；[接口映射](../cases/im_speed_tracking/README.md) |
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
| 最小回环 | passed | passed | [记录](../results/20261015-113018-smoke-903d97/manifest.json) |
| 感应电机 1430 rpm | passed | passed | [报告](../results/20261019-122808-induction_motor_closed_loop-664f11/report.html) |
| 感应电机 850 rpm | passed | passed | [报告](../results/20261019-122914-induction_motor_closed_loop-dc2ad0/report.html) |
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

## 感应电机独立启动

两工况分别显式设置 Speed RPM，Vgrid 为 230 V 相电压 RMS、50 Hz，Load_sel=1、IM_Load=0.5，对应 2 N·m 恒值负载指令。实际步长 0.5 µs、抽取 100，每次采集 4 s、20 kHz、80,000 点；[2,4) s 评价窗口含 40,000 点。

| 参考 / rpm | 平均转速 / rpm | 最大绝对误差 / rpm | 最大相对误差 | 超限点数 | 状态 |
|---:|---:|---:|---:|---:|---|
| 1430 | 1429.635450 | 2.052490 | 0.143531% | 0 | passed |
| 850 | 849.758187 | 1.383179 | 0.162727% | 0 | passed |

这些是参考官方断言建立的项目教学判据：采用独立启动、显式常值负载和 20 kHz，与官方共享仿真连续改速、50 kHz 的条件不同。来源与调整见 [判据说明](../cases/im_speed_tracking/acceptance.md)。速度参考 API 回读及参考/负载全程波形均留存；[CSV 独立复算](../results/agent-tasks/20261019-case-onboarding/release-validation/independent-csv.json) 与指标一致。短采集得到有效的性能 failed，错误输入与不完整数据按 error 处理。

下列 RLC、Boost 与整流详细数值保留其原验证记录；本轮回归路径从工作组①记录查阅。

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
| 人员独立复现 | 用户要求本轮先不安排；后续按 [交接流程](handoff.md) 由本人记录操作与解释 |
| GUI 手动操作路径 | RLC 软件界面已实测；[首次实验](first-experiment.md) 已同步实际步骤和截图。人员操作能力另验 |
| 跨电脑 | 本轮完成同机中文空格路径搬迁；另一台机器的软件、许可和设备条件另行实测 |
| 单相整流原面板 | API 教学路径通过；原面板启动宏需在独立教学副本核对后再验 GUI |
| 感应电机 GUI 面板 | 自动脚本链路已实测；SCADA 面板的 GUI 操作另行验收 |
| 实体 HIL 与外部控制器 | 按具体设备、控制器和实验负责人建立实测记录 |

2026-10-15 教学补全任务、实际命令与证据见 [完成记录](../results/20261015-workflow-completion/summary.md)；此前的详细数值核对见 [上午验证记录](../results/20261015-112422-v2-validation-dd212b/summary.md)。
