# 项目实现约定

本文供维护执行入口、模型适配器和结果记录的开发者使用。教学操作从 [README](README.md) 开始，模型扩展按 [接入方法](docs/model-integration.md) 执行。

## 执行能力

| 模型 | 实验 | 配置标识 |
|---|---|---|
| rlc_filter | 正弦稳态基准、Rin 参数扫描 | schema_version=1 |
| boost_closed_loop | 闭环基准、参考阶跃、输入电压跌落与升高 | schema_version=2 |

schema_version 标识配置结构。运行模式为 Virtual HIL。入口由 lab.ps1 定位配套 Python，提供 doctor、inspect、smoke、run、sweep、report、verify。

配置参数、单位和判据分别由 [RLC 说明](docs/experiments.md) 与 [Boost 说明](docs/boost-experiments.md) 定义。命令默认值和现行 JSON 配置是执行输入，文档示例需与其保持一致。

## 执行器与适配器

共同执行器负责来源核验、模型复制、编译、加载、互斥、采集、墙钟超时、清理、快照和最终清单。模型适配器负责配置校验、参数映射、信号单位、初始化、事件排程、分析与报告。

结构参数在模型副本中修改并回读，保存后编译。加载成功后发现源和信号，设置并回读运行参数。采集时机由实验决定：RLC 在等待稳态后采集，Boost 在启动前准备采集以覆盖启动和事件。

Boost 的运行副本包含 LabReferenceStep、LabReferenceSum、ReferenceApplied 和 VinMeasured。Step 的内部触发提前一个 100 µs 控制周期，以补偿求和环节传播。输入电压用 executeAt 排程。实际事件由参考或输入电压波形确认。

运行开始前检查 API 会话状态；已有运行时保留现场。执行器只清理自身启动的仿真和采集。

## 记录与状态

每次运行新建目录，保存配置、模型、CSV、采集元数据、日志、指标、代码快照、文件摘要与报告。Boost 保存事件记录，扫描保存子工况与比较汇总。许可不进入产物。

原始 CSV 保持不变，分析拒绝缺失或无效数据。图表、指标及报告指向同一次运行，记录时间包含时区偏移；缺失 UTC 触发时戳保留 null。

| 状态项 | 含义 |
|---|---|
| experiment_status | 实验执行与性能判据的结果 |
| record_status | 文件、代码快照及指标复算的一致性 |
| verify 总 status | 记录一致且实验通过时为 passed |

实验可取 passed、failed、error、skipped。性能 failed 的记录可以复算一致；总状态和退出码仍反映未通过。报告重建记录实际生成代码和产物哈希。已有记录的兼容检查在副本中完成。

## 验证要求

配置、分析与记录逻辑修改后执行脚本测试。运行链或模型修改后实际执行受影响的 Virtual HIL 实验，同时回归 RLC 基准与扫描。

检查事件实际电平、请求及调度时刻、首次变化采样和检测区间。指标使用预先声明的窗口、分母和判据，保留失败项。软件实测与人员独立复现分别验收，状态见 [验证页面](docs/validation.md)。

## 图表和文档维护

图表保留原始数据和处理说明，坐标包含单位，颜色配合线型，成稿需检查图例、窗口及事件标记。完整启动波形与局部视图分别标明时间范围。方法参考：

Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026). *Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents*. [arXiv:2609.00065](https://doi.org/10.48550/arXiv.2609.00065).

文档随功能直接更新，按职责组织：

| 页面 | 维护内容 |
|---|---|
| README | 项目用途、任务选择和统一入口 |
| environment | 安装路径、运行模式和环境检查 |
| first-experiment | 以 RLC 学会完整操作流程 |
| experiments / boost-experiments | 各模型的参数、信号、实验和指标 |
| agent-workflow | 自然语言任务、交付证据与结果核对 |
| troubleshooting | 按失败阶段定位与处理 |
| handoff | 独立复现步骤和交接记录模板 |
| validation | 当前能力、实测结论与待验事项 |
| validation-history | 按日期检索验证证据 |
| model-integration | 模型接入接口、步骤与维护验证 |

日期、测试次数和实测数值集中到验证页面。新增能力应融入其所属章节，并同步受影响的导航与示例。
