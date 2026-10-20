# 项目实现约定

本文供维护执行入口、模型适配器和结果记录的开发者使用。教学操作从 [README](README.md) 开始，模型扩展按 [接入方法](docs/model-integration.md) 执行。

## 执行能力

| 模型 | 实验 | 配置结构 |
|---|---|---|
| rlc_filter | 正弦稳态基准、Rin 参数扫描 | schema_version=1 |
| boost_closed_loop | 闭环基准、参考阶跃、输入电压跌落与升高 | schema_version=2 |
| single_phase_rectifier | 稳态基准、低输入、重载及三工况离线比较 | schema_version=1 |
| induction_motor_closed_loop | 独立启动的转速跟踪、运行中参考阶跃及实际参考与负载指令观测 | schema_version=2；阶跃配置有一项 events |

运行模式为 Virtual HIL。入口由 lab.ps1 定位配套 Python，提供 doctor、prepare-models、inspect、smoke、run、sweep、run-case、report、verify、compare-rectifier。配置中的 `model` 选择适配器，`case_id` 组织测试问题与配置引用，`schema_version` 标识配置结构；事件能力由适配器声明，具体运行是否保存事件记录由适配器按配置判断。

配置参数、单位和判据分别由 [RLC 说明](docs/experiments.md)、[Boost 说明](docs/boost-experiments.md) 与 [单相桥整流说明](docs/rectifier-experiments.md) 定义。命令默认值和现行 JSON 配置是执行输入，文档示例需与其保持一致。

## 执行器与适配器

案例目录、字段与路径边界、显式注册及 JSON 协议见 [案例与 CLI 接口](docs/case-interface.md)。案例标识与模型标识分离；案例文件不选择 Python 类。`list-cases`、`validate-case` 不调用 API 或写结果。`--json` 仅改变输出通道与响应信封，保持相同实验逻辑和退出码；`record_status` 只在实际复核后填写。发现命令的成功不依赖所有案例校验通过，各案例保留其可用性和缺口。`run-case` 先校验全部输入，再复用执行器串行运行并逐项复核，自动保存批次及本机证据索引；性能失败继续，执行或记录异常停止。

`prepare-models` 按 `models/origin.json` 的官方条目定位安装源，预检版本、来源及已有本机文件后补齐缺失资产；源模型路径约定保持不变。来源与预留目录见 [模型说明](models/README.md)。

共同执行器负责来源核验、模型复制、编译、加载、互斥、采集、墙钟超时、清理、快照和最终清单。模型适配器负责配置校验、参数映射、信号单位、初始化、事件排程、分析与报告；接口与模型时序见 [接入方法](docs/model-integration.md#实现适配器)。Boost 保持原有事件记录，感应电机仅在阶跃配置中生成事件记录，旧启动记录继续按无事件格式复核。

记录复核函数位于 `src/typhoon_lab/records.py`，供 CLI、案例编排、案例证据检查与离线比较直接调用。`verify_run(run_dir, write=False)` 只读复核，默认 `write=True` 保存 verification.json；复核保持 `record_status` 与 `experiment_status` 分离。自建模型教学练习使用独立 `practice-model` 命令及专属记录类型，方法和证据见[建模练习](docs/modeling-practice.md)，不改变官方模型适配器及案例加载约定。

结构参数在模型副本中修改并回读，保存后编译。加载成功后发现源和信号，设置并回读运行参数。采集时机由实验决定：RLC 与单相桥整流在等待稳态后采集，Boost 与感应电机在启动前准备采集，保留完整启动波形。

等待仿真时间使用 `get_sim_time()`，墙钟等待仅用于轮询降频与独立超时。运行开始前检查 API 会话状态；已有运行时保留现场，执行器只清理自身启动的仿真和采集。

单相整流三工况比较的来源依赖、哈希及重建顺序见 [比较记录](docs/rectifier-experiments.md#复核单次与三工况比较)。

## 记录与状态

每次运行新建目录，保存配置、模型、CSV、采集元数据、日志、指标、代码快照、文件摘要与报告。Boost 与感应电机阶跃保存事件记录，扫描保存子工况与比较汇总；案例批次保存输入快照、子工况关联、汇总报告和最终复核；单相桥整流的独立三工况比较保存来源与趋势指标。许可不进入产物。

原始 CSV 保持不变，分析拒绝缺失或无效数据。图表、指标及报告指向同一次运行，记录时间包含时区偏移；缺失 UTC 触发时戳保留 null。

| 状态项 | 含义 |
|---|---|
| experiment_status | 实验执行与性能判据的结果 |
| record_status | 文件、代码快照及指标复算的一致性 |
| verify 总 status | 记录一致且实验通过时为 passed |

实验可取 passed、failed、error、skipped。性能 failed 的记录可以复算一致；总状态和退出码仍反映未通过。报告重建记录实际生成代码和产物哈希。

### Agent 任务记录

执行新实验、修改实验实现或交付需复现的分析结果时，在 `results/agent-tasks/<唯一任务标识>/task.md` 留存记录。标识使用本地日期时间、任务短名及防重后缀；记录中的时间注明 +08:00，文本使用 UTF-8。

简单释疑、只读检查及探索性分析可在答复中注明所用资料、关键依据和实际操作；产生需留存或复核的结果时再建立任务记录。按本次任务填写下表中的适用内容。

| 内容 | 要求 |
|---|---|
| 请求 | 用户原始请求、澄清及任务目的 |
| 条件 | 实际模型、配置、参数与单位、固定条件、事件、采集窗口和预设判据 |
| 命令 | 实际命令及 cwd、带时区的起止时间、返回码和关键输出 |
| 运行关联 | 逐条对应命令返回的实际 run_dir、报告、CSV、配置、指标、事件及最终复核文件 |
| 结论 | record_status、experiment_status、未通过项、关键缺口和待验范围 |

任务记录位于实验运行目录之外。已计划但未执行的步骤如实注明。内部证据路径相对于项目根目录保存，交付时给出可打开的实际路径。新实验结果交付时完成报告与最终复核。

### 历史记录处理

分析历史记录先读取已有文件。`verify` 会写入 `verification.json`，`report` 会更新报告、清单与代码快照；需要执行这些操作时，默认将完整记录及相对依赖复制到任务目录，在副本上处理并记录源目录与副本的关系。用户明确要求原地重建时按其指示。

重建报告采用 `verify → report → verify`，最后一次复核对应交付产物；性能未达标时保留原判据和失败状态。

## 验证要求

配置、分析与记录逻辑修改后执行脚本测试。运行链或模型修改后实际执行受影响的 Virtual HIL 实验，同时回归 RLC 基准与扫描。

检查事件实际电平、请求及调度时刻、首次变化采样和检测区间。指标使用预先声明的窗口、分母和判据，保留失败项。软件实测与人员独立复现分别验收，状态见 [验证页面](docs/validation.md)。

## 图表和文档维护

图表保留原始数据和处理说明，坐标包含单位，颜色配合线型，成稿需检查图例、窗口及事件标记。完整启动波形与局部视图分别标明时间范围。方法参考：

Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026). *Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents*. [arXiv:2609.00065](https://doi.org/10.48550/arXiv.2609.00065).

文档随功能直接更新，按职责组织：

| 页面 | 维护内容 |
|---|---|
| AGENTS | 项目长期约束与维护要求 |
| README | 项目用途、任务选择和统一入口 |
| [roadmap](docs/roadmap.md) | 前期能力准备、工程优化、长期扩展方向及启动条件 |
| environment | 安装路径、运行模式和环境检查 |
| first-experiment | 以 RLC 学会完整操作流程 |
| modeling-practice | 从空白模型到脚本采集的练习与 GUI 重做步骤 |
| experiments / boost-experiments / rectifier-experiments | 各模型的参数、信号、实验和指标 |
| agent-workflow | 任务提问示例与结果核对 |
| troubleshooting | 按失败阶段定位与处理 |
| handoff | 独立复现步骤和交接记录模板 |
| validation | 当前能力、实测结论与待验事项 |
| validation-history | 按日期检索验证证据 |
| resources | 官方学习入口、案例选择、版本/模式和实测状态 |
| boost-disturbance-analysis | 原始数据复算、受控对照、现象与候选机制边界 |
| model-integration | 模型接入接口、步骤与维护验证 |
| case-interface / cases | 案例字段、路径边界与 CLI 协议；各案例的接口、配置引用与判据 |

日期、测试次数和实测数值集中到验证页面。新增能力应融入其所属章节，并同步受影响的导航与示例。
