# Typhoon HIL 与 AI Agent 教学工作流

本项目提供修改参数、采集波形、比较结果和编写报告的实验流程。已有电机或电力电子基础的读者可直接按任务进入；初次接触芯片、电路和控制的读者，先读[样机测试零基础教程](docs/beginner/README.md)。常规案例采用官方示例模型；另有从空白原理图建立的 RLC 教学练习。运行使用软件自带 Python，通过统一入口执行。

仿真实验采用 **Virtual HIL**：模型在电脑上按仿真时间推进，以非实时方式运行，没有外部 I/O。每次实验保存配置、模型副本、代码快照、实际数据和判定依据。

## 按任务开始

| 想完成的任务 | 入口 |
|---|---|
| 从零理解本次样机、芯片、电路与控制 | [离线图文教程](docs/beginner/index.html)、[学习路线与 Markdown 正文](docs/beginner/README.md) |
| 入门学习与复现实验 | [首次实验](docs/first-experiment.md)、[建模练习](docs/modeling-practice.md) |
| 执行和复核已有案例 | [案例发现与 CLI](docs/case-interface.md)、[Agent 工作流](docs/agent-workflow.md) |
| 演示 Typhoon + 模型分析与确认复验 | [Boost + AI 演示操作](docs/boost-ai-demo.md) |
| 与Agent对话并开展多轮复验 | [Typhoon实验分析Agent](docs/agent.md) |
| 接收和识别外部波形 | [波形接收与复核](docs/external-waveforms.md)、[异常识别与大模型解释](docs/waveform-diagnosis.md)、[数据接收 Skill](.agents/skills/external-test-data-intake/SKILL.md) |
| 接入新模型或测试要求 | [模型接入方法](docs/model-integration.md)、[资源与案例选择](docs/resources.md) |
| 准备本次寄送控制板联调 | [控制板引线、LIN 与电机参数](docs/tle9877-hil-intake.md) |
| 执行样机软件准备与 PMSM 预演 | [参数检查、LIN 离线编解码与预演命令](docs/tle9877-software-preparation.md) |
| 手动做一次模拟样机测试 | [Typhoon 图形界面预演](docs/tle9877-gui-practice.md) |
| 准备样机现场联调 | [I/O 合同、参数与现场记录](docs/tle9877-field-commissioning.md)、[LIN Mock](docs/tle9877-lin-adapter.md) |
| 整理样机现场数据与判定 | [多来源文件、时间关联与离线判据](docs/field-data.md)、[采集交接说明](docs/tle9877-data-collection.md) |
| 查看验证状态与交付证据 | [当前验证状态](docs/validation.md)、[历史证据](docs/validation-history.md)、[交接验收](docs/handoff.md) |

需要按页面查找教程、接口和专题说明时，见[文档导航](docs/document-index.md)。

首次使用建议先做 RLC，再通过资源导航选择后续案例。已有案例用 `list-cases --json` 发现，用 `validate-case --case <标识> --json` 查询材料、配置、代码支持与实际证据。案例标识表示测试问题，模型标识选择适配器；一个模型可以对应多个案例。

发现成功与单案例可运行性分别判断；缺少本机模型标为 missing_local_dependency，静态检查不替代实际编译和采集。官方模型与面板通过 prepare-models 从匹配安装补齐，来源规则见 [模型说明](models/README.md)。外部数据检查独立于仿真准备流程。

## 准备环境并运行

按 [环境配置](docs/environment.md) 指定 Typhoon 安装目录，在包含 `lab.ps1` 的目录执行：

```powershell
Set-Location 'D:\Typhoon\lab-workflow'
.\lab.ps1 doctor
.\lab.ps1 prepare-models
.\lab.ps1 smoke
.\lab.ps1 inspect --model rlc_filter
.\lab.ps1 run --config configs/rlc_baseline.json
```

`doctor` 检查解释器、版本和模块；`prepare-models` 补齐并核对官方模型与面板；`smoke` 实际完成最小编译、加载、运行、读取和停止。`run` 输出本次 `run_dir`，后续核对均使用这个目录。

| 操作 | 命令 |
|---|---|
| 发现案例 | `.\lab.ps1 list-cases --json` |
| 查询所选案例的配置与能力 | `.\lab.ps1 validate-case --case <标识> --json` |
| 串行执行案例并复核 | `.\lab.ps1 run-case --case <标识> --json` |
| 运行指定配置 | `.\lab.ps1 run --config <配置路径> --json` |
| 接收与复核外部 CSV | 按 [外部波形流程](docs/external-waveforms.md) 使用 analyze-waveforms / verify-waveforms |

RLC 参数扫描、各模型的动态工况和比较方法按案例材料与对应教程执行；自建模型练习见 [建模练习](docs/modeling-practice.md)。

`run-case` 按案例配置顺序执行，自动复核各结果并更新本机证据索引；返回的 `run_dir` 为包含各工况的批次目录。性能失败保留原结论并继续，执行或记录异常时停止并登记未运行项。

实验配置的相对路径由入口相对于项目根目录解析。更改工况时另存配置，运行前确定参数、单位、采集窗口和判据。

## 核对结果

以下步骤用于仿真实验；外部数据按[离线复核](docs/external-waveforms.md)使用 verify-waveforms。将占位路径换成本次实际目录：

```powershell
.\lab.ps1 verify --run-dir 'results/本次实际目录'
.\lab.ps1 report --run-dir 'results/本次实际目录'
.\lab.ps1 verify --run-dir 'results/本次实际目录'
```

`report` 根据已有数据重建报告；`verify` 核对文件哈希并复算指标。两条命令均不启动新仿真。

| 要核对的内容 | 对应文件 |
|---|---|
| 实际参数、模型与执行环境 | `config.json`、`model.tse`、`manifest.json` |
| 原始数据、信号单位和采集时间 | `waveforms.csv`、`capture.json` |
| 指标、分析窗口与判据 | `metrics.json` |
| 动态事件的实际生效证据 | Boost 或电机阶跃运行目录的 `events.json` |
| 图表、解释与执行问题 | `report.html` / `report.md`、`run.log` |
| 源码与结果复核 | `code_snapshot/`、`verification.json` |

RLC 扫描另有 `cases/`、`comparison.csv` 和 `comparison.png`。Boost 与电机阶跃动态工况同时提供完整启动波形和事件区间细节图。结果始终写入新目录。

实验状态分为 `passed`、`failed`、`error`、`skipped`。复核输出中的 `record_status` 表示记录与复算是否一致，`experiment_status` 表示实验是否满足判据；总状态要求两者均通过。具体已验证能力、未达标项目和证据集中在 [验证状态](docs/validation.md)。

## 继续使用和维护

- 执行异常：按 [故障排查](docs/troubleshooting.md) 根据阶段定位。
- 其他人接手：按 [交接验收](docs/handoff.md) 独立复现。
- 查看输入扰动的现象与候选机制：阅读 [Boost 扰动分析](docs/boost-disturbance-analysis.md)。
- 接入其他模型：按 [模型接入方法](docs/model-integration.md) 建立参数、信号、判据和实际证据。
- 自行建模：按 [建模练习](docs/modeling-practice.md)复现电路、测量点、编译、采集与结果复核。
- 维护入口、记录或文档：阅读 [实现约定](PROJECT_SPEC.md) 与 [Agent 项目指令](AGENTS.md)。
- 安排后续建设：参照 [能力准备与长期规划](docs/roadmap.md)，按近期优先级和长期扩展条件确定范围。
- 选择后续案例：按[案例层次与选择依据](docs/resources.md#案例层次与选择依据)比较教学案例、具体需求及供应商应用资源；水泵控制器作为一个专题，见[需求与接入准备](docs/pump-hil-intake.md)。

搬到另一台电脑时保留目录结构，更新本机安装路径，再执行环境检查、最小仿真及所选实验。软件和许可由设备管理者配置。官方模型与面板通过 `prepare-models` 从目标机器的匹配安装补齐；实体 HIL 与外部控制器按具体设备和任务另行验证。
