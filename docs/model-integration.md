# 模型接入与维护

本页供理解模型和 Schematic/HIL API 的维护者使用，说明如何把一个来源明确的模型接入统一执行器。日常实验从 [README](../README.md) 选择 RLC 或 Boost 教程。

## 定义实验

先明确被控对象、模型来源、运行模式、参数及单位、采集信号、事件、分析窗口和判据。RLC 提供结构参数扫描与稳态解析核对参照，Boost 提供闭环初始化、固定时刻事件和动态指标参照。

结构属性需要修改模型副本并重新编译；运行参数在加载后设置并回读。评价标准在采集前确定。按仿真模式确认事件和接口能力，实际观察信号应足以验证所施加的激励。

## 留存模型来源

将模型和必要依赖按字节复制到 models/，在 origin.json 记录来源、软件版本与 SHA-256。每次执行使用结果目录中的副本。许可文件由安装环境管理。

确认移到另一台匹配环境后能定位依赖。组件与端口先通过安装 API 检查，层次路径按该 API 的实际行为处理。

## 实现适配器

在 src/typhoon_lab/adapters/ 中实现适配器并显式注册。共同执行器负责来源核验、复制、编译、加载、互斥、采集、超时、清理、快照和清单。

| 成员／方法 | 职责 |
|---|---|
| model_id、schema_version | 模型标识与配置结构 |
| signals、columns、units、sources | 实际 API 名称、CSV 列序、单位及必需源 |
| capture_before_start、changes | 采集时机与运行副本的结构改动说明 |
| validate(raw, sweep=False) | 返回规范化配置，拒绝未知字段及无效参数、窗口和采样条件 |
| inspect_parameters(api) | 静态参数与表达式的来源 |
| prepare(api, config) | 修改运行副本并回读，返回实际参数 |
| initialize(hil, config) | 加载后设置运行参数并回读，返回实际设置 |
| schedule(hil, config) | 在启动前安排事件并返回排程记录；无事件返回空列表 |
| check_sampling(rate, count, config) | 核对量化后的实际采集条件 |
| analyze(csv_path, config) | 确定性分析原始 CSV，返回指标、检查与方法 |
| report(run_dir, manifest) | 从已有记录生成图和报告，返回输出路径 |

Boost 的 describe_schedule(config) 提供离线排程描述，供 schedule 与 verify 核对使用。接入新的配置结构或事件记录时，需同步分析分派、报告、快照和 verify。

配置结构的现行对应关系为 RLC 的 schema_version=1、Boost 的 schema_version=2。维护不同结构的解析入口，并在既有记录副本上验证兼容性。

## 参数读取与事件时序

Schematic API 加载模型后，初始化命名空间尚未执行。参数使用表达式时，在静态检查中标明数值来源，并通过实际编译验证。Boost 的检查读取模型初始化中的 P、I、I_initial、Ts 四个字面量及 PI 属性表达式。

Boost 运行副本在 Reference 与误差求和器之间使用 LabReferenceStep 和 LabReferenceSum，通过 ReferenceApplied 观测实际参考。LabReferenceSum 的传播为一个 Ts，Step 内部触发设为目标时刻减 Ts。Vin 通过源 executeAt 排程，VinMeasured 观测输入电压。

该时序关系由监测波形验证。更改控制周期、求和器或信号链后重新测定传播，记录请求时刻、内部触发、补偿、调度、首次变化样本、检测区间与分辨率。

## 数据与指标

确定 CSV 时间列、单位、有效采样率和触发元数据，严格检查缺失与无效样本。分析不调用 Typhoon，也不修改原始数据；处理和排除规则在方法记录中说明。

动态指标需定义事件前条件、稳态窗口、容差带、超调分母、调节时间，以及观测结束时未恢复的结果。连续时间解析响应可作为单元测试的独立参照，实际 Virtual HIL 运行单独留证。

实验状态保留 passed、failed、error、skipped，复核区分记录一致性与实验判据。报告显示所有要求工况和未通过项，并标明图中的采样与分析范围。

## 验证与交付

完成配置、独立参考分析、事件异常和清理测试，执行受影响的实际运行及已有模型回归。每个模型至少具备基准和两至三个有判据的实验，逐项复核，重建报告后再次 verify。

交付模型说明、配置、实际目录、操作教程和验证结论。通用入口或数据结构改变时检查历史记录副本，保留原记录。按 [交接流程](handoff.md) 让另一位组员独立复现，结果维护在 [验证状态](validation.md)。

文档按完整现行用法更新：参数和指标放在模型说明，任务示例放在 Agent 页面，通用排错放在排错页，实测数值按日期归入验证记录。新增能力直接融入对应章节与导航。
