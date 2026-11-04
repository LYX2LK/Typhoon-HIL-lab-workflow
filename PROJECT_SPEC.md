# 项目实现约定

本文供维护执行入口、模型适配器和结果记录的开发者使用。教学操作从 [README](README.md) 开始，模型扩展按 [接入方法](docs/model-integration.md) 执行。

## 执行能力

当前案例、模型注册、配置字段、信号与事件支持通过 `lab.ps1 list-cases --json` 和 `validate-case --case <标识> --json` 查询，协议见 [案例与 CLI 接口](docs/case-interface.md)。能力声明、环境可运行性和实际实验结论分别核对。

实验运行模式为 Virtual HIL，入口由 lab.ps1 定位配套 Python。配置中的 model 选择适配器，case_id 组织测试问题与配置引用，schema_version 标识配置结构。参数、单位和判据以对应案例引用的配置、模型说明与当前校验实现为准。

外部数据使用 analyze-waveforms / verify-waveforms，输入范围、清单字段、计算方法和退出码由 [外部数据接口](docs/external-waveforms.md) 定义；其记录独立于仿真模型和编译产物。

本次寄送板卡的参数/接口检查与 LIN 离线编解码使用独立准备命令，不调用设备或实时反馈；事实配置与 PMSM 软件预演假设分开保存。命令、输入范围与状态含义见[样机软件准备](docs/tle9877-software-preparation.md)。PMSM 预演复用 run 类型及公共执行器，样机接入与性能状态另行验收。

LIN 主节点接口与 Mock 使用 [LIN 适配约定](docs/tle9877-lin-adapter.md)；当前只提供离线 Mock 命令，不绑定厂家 SDK。I/O 合同和电机参数接收表是工作资料，原有静态检查规则保持。实体 smoke 先保存 plan.json，设备执行器和反馈链实现前不进入现有 Virtual HIL case.json 注册。

多来源现场文件由 [field-data](docs/field-data.md) 的独立入口处理，记录类型为 field_test_data，配置/方法/记录版本分别登记。保留原始文件、包内 LDF、显式转换与时间依据；只对已确认项目作离线判定。专用复核默认只读并从包内材料重算，通用 verify 可分派；experiment_status 保持 null。报告更新通过新建分析包完成。

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

新运行清单用 `configuration_schema_version` 表示所用配置结构版本（适用于单次运行与扫描），用 `record_format_version` 表示清单和结果目录格式，用 `analysis_method_version` 表示当前记录类型及模型所用确定性分析方法版本。三个版本彼此独立；原有 `schema_version` 字段保留历史含义，CLI JSON 信封、案例文件和 `events.json` 各有自己的 `schema_version`。代码快照与 SHA-256 记录精确实现，方法版本只表示兼容的计算约定。

### 外部数据记录

external_waveforms 类型复用文件哈希、记录版本与方法版本机制，保存输入字节副本、清单与来源映射、分析结果、报告和代码快照。独立复核核对必需产物及来源，再从包内 CSV 重算；旧批次专用报告不会自动迁移，采用新方法时新建结果。

外部数据的 data_quality_status、analysis_status、record_status 与 performance_status 分别表示结构质量、分析完成度、记录一致性及性能评价。当前性能保持 not_evaluated，CLI 信封的 experiment_status 为 null；复核通过不改变数据质量或性能结论。verify-waveforms 默认只读，显式 --write 才保存复核；通用 verify 保持默认写入行为。

waveform_diagnosis 是外部数据包派生的独立分析记录，保存源包副本、固定规则、分类与事件、模型请求及可选解释回答。计算分类与模型解释分别表达；分类不读取参考标签。接入、状态、版本、独立复算及解释来源约定见[波形识别接口](docs/waveform-diagnosis.md)。

boost_ai 是Boost仿真记录派生的模型解释记录，复用原数值分析并补充趋势及同窗口比较。真实API请求/响应、白名单建议、人员确认、对照执行和前次解释分别绑定。原仿真性能不由模型改写；派生记录的完成状态与原实验状态独立。接口及复核范围见[Boost + AI](docs/boost-ai-demo.md)。

boost_agent_session 使用session.json标识有状态对话，events.jsonl记录带哈希关联的事件；不可变的boost_agent_turn保存模型工具调用、证据、响应与声明式页面编排。实验仍使用run记录。参数化建议经人员确认、来源与配置哈希校验后执行；模型读取工具与实验执行的权限分开。复核和会话恢复见[对话式Agent接口](docs/boost-agent.md)。

Agent旧版strict_tool_v1报告绑定真实present_report调用ID及生成时的动态Schema。复核同时核对原始函数参数、回答和strict请求Schema；旧content-JSON报告仍按原协议读取。生成约束与本地证据/执行校验分别保留，不自动改写或重发失败报告。

新报告使用strict_tool_v6及markdown_refs_v3：先保留独立普通Markdown正文narrative.md，再以narrative_index段落编号及独立短标题传递控制参数；复核原始正文响应、可复算目录、参数请求绑定、wire_answer和answer投影。正文作为唯一主文，结构化依据折叠且相同段落去重，图表编排仍由模型决定。问题与选项说明独立生成短句；首轮与同事件时刻重复记录不开放默认总结/深入分支，实际时刻对照后再判断是否足以收尾。JSON语法错误与业务校验分别记录；参数失败时正文可只读展示，实验选项不可执行。无自动JSON修补或格式重发。conclude/deepen是程序定义的目标操作，无需模型提供追问；discuss需要非空正文引用。新Schema按操作种类限定message_ref及参数。旧strict_tool_v4/markdown_refs_v1和strict_tool_v5/markdown_refs_v2保持原字段与校验复核。

strict_tool_v3/flat_report_v1按旧协议保留复核：wire_answer按复算事实和受控动作目录投影到answer。investigation_context保存可复算辅助观察、历史覆盖与能力范围，assessment按命题评估进展；收尾/深入由用户选择。旧v1兼容分支保留。研发中的v2草案未用于用户会话，不作为受支持的交付格式。

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

缺少新增版本字段的历史清单按旧格式读取，不自动补写。`verify` 使用当前支持的分析实现复算并报告差异；旧代码快照用于追溯，不自动执行。遇到未知记录格式或分析方法版本时，停止指标复算并明确报告不支持；`report` 也拒绝重建，不把版本不兼容误称为数据被篡改。需要采用新方法重新分析时，在完整副本上操作，记录来源、方法版本和新旧结论。

重建报告采用 `verify → report → verify`，最后一次复核对应交付产物；性能未达标时保留原判据和失败状态。

## 验证要求

配置、分析与记录逻辑修改后执行脚本测试。运行链或模型修改后实际执行受影响的 Virtual HIL 实验，同时回归 RLC 基准与扫描。

检查事件实际电平、请求及调度时刻、首次变化采样和检测区间。指标使用预先声明的窗口、分母和判据，保留失败项。软件实测与人员独立复现分别验收，状态见 [验证页面](docs/validation.md)。

## 图表和文档维护

图表保留原始数据和处理说明，坐标包含单位，颜色配合线型，成稿需检查图例、窗口及事件标记。完整启动波形与局部视图分别标明时间范围。方法参考：

Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026). *Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents*. [arXiv:2609.00065](https://doi.org/10.48550/arXiv.2609.00065).

文档随功能直接更新，按职责组织：

各教程、接口和专题页的用途见[文档导航](docs/document-index.md)。

| 文档类别 | 维护职责 |
|---|---|
| AGENTS / README | 长期工作原则 / 稳定任务入口 |
| roadmap | 建设方向、优先级与扩展触发条件 |
| PROJECT_SPEC 与接口文档 | 架构不变量、接口、记录和验证约定；每项规则保持一个权威定义 |
| Skill | 任务判断、工具选择、核查与交付；细节按需引用 |
| 方法与教学材料 | 原理、适用条件、操作与独立学习 |
| 配置、案例与需求材料 | 对象及批次事实、工况、判据和待补条件 |
| validation / validation-history / results | 当前验证范围 / 历史证据索引 / 实际结果与任务记录 |

日期、测试次数和实测数值集中到验证页面。新增能力应融入其所属章节，并同步受影响的导航与示例。

## 对话式 Agent 案例接口

新入口 `agent` / `verify-agent` 与旧 Boost 命令共用同一服务和验证分派。`GET /api/cases` 返回代码注册的三个案例；`POST /api/start` 接收 `case_id` 和可选 `text`，首次提交将案例绑定到版本2会话。后续不允许改案例，新会话保留旧证据。外部波形无仿真实验能力；可执行动作及参数由所属案例的工具Schema与校验器共同约束。

公共状态、传输、页面和服务分别位于 `agent_state`、`agent_service`、`agent_page.html` 和 `agent_server`，Boost专属策略与历史协议继续独立维护。版本2会话保存case_id；整流桥轮次为agent_turn/case_report_v2，示例波形新轮次为case_report_v3（旧v1/v2按原协议复核），Boost轮次沿用原协议并保存case_id。每轮数值引用须对应复算字段；复核检查实际工具响应、正文和控制参数的绑定。实验计划绑定回答、来源、配置与确认，执行结果关联同一配置。

示例波形的版本2比较工具从逐文件证据计算独立comparison.json，报告须包含逐对局部图、差异表及经程序校验的差值或倍率引用。比较使用原始时间轴及逐文件窗口；零分母、不同规则和未配对记录显式说明。完成范围仅从已通过轮次及相同源CSV哈希推导，供Schema限制重复建议；旧版比较工具保持原输出。具体使用与单位约定见[Agent接口](docs/agent.md)。

整流桥为项目自建模型，源文件与哈希纳入版本管理；官方模型继续按安装依赖准备。模型细节、固定条件和参考判据在所属案例维护。使用方式见[Agent操作说明](docs/agent.md)。
