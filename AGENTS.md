# Typhoon 教学项目指令

## 任务与读者

为有专业基础但不熟悉 Typhoon/Python 的组员执行可复现教学实验。先说明实验问题、参数与单位，再执行并解释实际结果。

## 入口与任务路由

- 在本目录使用 `.\lab.ps1 doctor / smoke / inspect / run / sweep / report / verify`；相对配置路径相对于本项目解析。
- 开始工作先读 README.md。环境问题看 docs/environment.md；RLC 看 docs/first-experiment.md 与 docs/experiments.md；Boost 看 docs/boost-experiments.md；排错看 docs/troubleshooting.md。
- 公开资源和案例选择看 docs/resources.md；Boost 抗扰动解释看 docs/boost-disturbance-analysis.md。
- 模型接入看 docs/model-integration.md，执行器和记录约定看 PROJECT_SPEC.md。支持 `rlc_filter`、`boost_closed_loop`、`single_phase_rectifier`，运行模式为 `virtual_hil`。单相桥整流看 docs/rectifier-experiments.md；三工况离线比较用 `compare-rectifier`。
- 使用安装包自带 Python，由 lab.ps1 定位。本地 API 资料位于安装目录 Documentation/ 和 typhoon/help/，名称与行为以匹配安装为准。
- 任务存在多个合理参数或比较条件时先澄清；采用基准值时明确所用配置。判据在运行前固定，失败后不自动放宽。

## 模型与运行

- 结构参数由 Schematic API 写入每次运行的模型副本，回读、保存后编译；运行参数由 HIL API 设置并回读。
- RLC 的 API 顶层组件为 Rin/R/L/C，源为 Vs1，信号为 I/Va1。get_item 不接收点分隔的层次路径。
- Boost 初始化 Vin、Reference、PWM Enable 和 Load；采集 Vout、Iin、ReferenceApplied、VinMeasured。四份配置分别运行，sweep 支持 RLC Rin 扫描。
- 单相桥整流源为 Va1，采集 Va2/Iload1/Icdc1；副本修改 La1/Cdc1/Rload1，并关闭 Va2 原有 2 Hz 低通。三份配置独立运行，独立桥 LC-R 数值参考、逐周期稳定性与趋势比较分别复核。
- 配置 schema_version 表示结构版本，model 表示案例；事件记录使用适配器 has_events 能力，不用版本号推断模型种类。
- Boost 参考事件由 Step 执行，并补偿 LabReferenceSum 的一个控制周期传播延迟；输入源用 executeAt 排程。改动信号处理链后重测事件时序。
- 等待仿真时间用 get_sim_time() 判断；墙钟 sleep 只降低轮询频率。采集有独立墙钟超时与异常停止。
- 互斥锁限制一个执行器。已有仿真运行或 GUI 占用时报告并保留现场；不结束用户的 Typhoon、Office 或 WPS 进程。

## 结果与证据

- 保存配置、模型、代码快照、原始 CSV、采集时间元数据、日志、指标、图与报告。动态实验保存 events.json。
- 结果图和结论来自原始采样。RLC 的解析参考、单相桥整流的独立数值参考与模拟测量分别列出；动态事件通过实际信号及采样检测区间核对。
- passed / failed / error / skipped 如实区分。doctor 的模块导入通过不能代替 smoke 或实验通过。
- verify 核验文件哈希并复算指标；区分 record_status 与 experiment_status。report 从已有数据重建报告，生成代码纳入快照。
- Virtual HIL 的 UTC 触发时戳可以为 null，保留原值。运行时间记录 +08:00 偏移。
- 每次给出实际目录、判定依据和 verify 结果。软件实测、脚本测试与组员独立复现分别记录。

## 文件、设备与编码

- 安装目录作为依赖和官方资料来源。模型按字节复制，实验改动与新结果保存在本项目内。
- 许可文件不进入教学项目或报告。实体设备、固件和控制器任务先明确设备、操作范围与实验负责人。
- PowerShell 文本 cmdlet 显式指定 -Encoding UTF8；Python/Node 使用自身的显式编码参数。
- 配置、分析和记录逻辑修改后运行 tests；运行链或模型修改后做相应实际 Virtual HIL 检查。使用配套解释器和 unittest discover，不联网安装测试依赖。

## 文档维护

- 日常文档说明完整的现行用法，按读者任务和模型组织；功能变化直接修订所属章节、示例与导航，不按发布版次在文末追加说明。
- README 提供任务入口；环境、实验、排错和交接各有独立职责。参数及指标定义集中在对应模型说明，其他页面引用它。单相桥整流的官方面板包含不匹配源名的启动宏，原件留存与GUI面板实测分开记录。
- 验证状态只维护当前能力与结论；按日期查阅的证据集中在 docs/validation-history.md，原始运行记录保持不变。
- 软件版本、schema_version、文件哈希和真实证据路径按技术含义保留。实际成绩与测试次数不复制到操作教程。
