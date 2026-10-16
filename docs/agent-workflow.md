# 用 Agent 执行和核对实验

本页供组员使用自然语言提出实验任务，并检查 Agent 的配置、执行和解释。模型操作通过项目脚本完成，实验结论需要对应实际数据。

## 建立任务上下文

在 Agent 中打开包含 `lab.ps1` 的 `lab-workflow` 目录作为项目。若打开的是上一级 `D:\Typhoon`，让 Agent 进入 `lab-workflow` 后再开始；从其他目录执行时使用 `lab.ps1` 的完整路径。

首次对话可直接给出以下任务：

> 先读取当前项目的 AGENTS.md、README.md、docs/agent-workflow.md 和 docs/environment.md，说明你找到的项目根目录、统一入口、支持模型和运行模式。按我选的 RLC、Boost 或单相整流任务阅读对应模型文档与现有配置，列出实际参数、单位、采集窗口和判据。确认命令执行、文件写入和已安装 Typhoon Python 可用后，通过 lab.ps1 执行，保存实际结果并完成 report 与 verify。已有仿真或 GUI 正在运行时保留现场，等待使用时段。

Agent 先用文件和入口帮助确认能力：

```powershell
Get-Location
Test-Path -LiteralPath '.\lab.ps1'
Get-Content -LiteralPath '.\environment.local.json' -Encoding UTF8
.\lab.ps1 --help
```

`--help` 列出当前入口实际支持的命令。`doctor` 检查环境，`smoke`、`inspect`、`run` 与 `sweep` 会使用 Typhoon API；执行前需确认软件使用时段。`report` 与 `verify` 只处理已有记录。文件只读或执行权限受限时，Agent 应明确实际受限操作，按所在工具的授权机制处理；检查输出中的解释器路径应指向本机预期安装。环境步骤见 [环境配置](environment.md)。

一个可执行任务至少要明确模型、参数或事件、保持不变的条件、采集内容和评价指标。采用现有基准配置时，指出配置名称；采用默认值时，让 Agent 列出实际使用的值。条件有歧义时先补齐，再运行。所选模型说明：[RLC](experiments.md)、[Boost](boost-experiments.md) 或 [单相桥整流](rectifier-experiments.md)。

## 从配置到结果

```mermaid
flowchart LR
    A[明确实验问题与工况] --> B[保存配置和预设判据]
    B --> C[通过 lab.ps1 执行]
    C --> D[保留模型 数据 日志和源码]
    D --> E[计算指标并复核记录]
    E --> F[解释结果与未通过项]
    F --> G[组员核对和独立复现]
```

实验执行前确定分析窗口与判据。完成后先查看执行和数据是否有效，再解释指标是否达标；条件修改后保存新的配置和运行记录。

## 任务示例

### 运行 RLC 基准

> 按 rlc_baseline.json 运行基准实验，核对 I 与 Va1 的稳态 RMS。列出实际参数、采集窗口、解析参考、每项误差和判据，给出结果目录与 verify 状态。

### 扫描 RLC 输入电阻

> 使用教学 RLC 模型，把 Rin 设为 1、5、10 Ω，其余条件采用 rlc_sweep.json。分别保存原始数据，比较电流和节点电压 RMS，并按对应拓扑解释差异。

### 运行 Boost 参考阶跃

> 按 boost_reference_step.json，在仿真 0.5 s 把参考从 50 V 改为 60 V。采集输出电压、输入电流、实际参考和输入电压，计算稳态误差、超调和调节时间。核对 events.json 的实际事件检测区间，生成报告并执行 verify。

### 比较 Boost 跟踪与抗扰动

> 按 Boost 教程运行基准、参考阶跃、输入跌落和输入升高四份配置。逐项列出事件、性能判据及记录复算结果；未通过时保留原判据，说明具体越限值，并给出全部实际报告路径。

### 接入示范：单相桥整流三工况

> 读取单相整流教程和三份 rectifier 配置，说明模型来源、运行副本的参数及测量低通改动、独立数值参考的假设和固定判据。依次运行基准、低输入与重载，保存实际目录并逐项 report 与 verify，再用 compare-rectifier 比较三条记录。解释输入同比缩放、重载纹波与电流变化，给出报告、原始 CSV 和复核状态。

### 分析已有记录

> 读取 results 中指定的实验目录，先确认模型、工况、软件环境和记录状态。核对原始数据与指标，重建报告后再次 verify；解释结论适用的模型、激励与观察窗口。

### 定位执行问题

> 我执行的命令是〈完整命令〉，结果目录是〈实际目录〉。请从日志中的首次错误定位编译、加载、采集或分析问题，核对相应配置和本地 API。修复后用同一配置另建运行，比较处理前后的记录。

## 执行命令与定位结果

Agent 应保留原始自然语言任务和实际命令。使用现有扫描与参考阶跃配置的最小命令链为：

```powershell
.\lab.ps1 sweep --config configs/rlc_sweep.json
.\lab.ps1 run --config configs/boost_reference_step.json
```

每条输出中的 `run_dir` 是本次结果的准确位置，后续直接使用该值，不按“最新目录”猜测。扫描的每项原始数据在 `run_dir/cases/`；Boost 的原始数据和事件记录直接位于 `run_dir/`。对两条命令各自得到的目录执行：

```powershell
.\lab.ps1 verify --run-dir '本次输出的完整 run_dir'
.\lab.ps1 report --run-dir '本次输出的完整 run_dir'
.\lab.ps1 verify --run-dir '本次输出的完整 run_dir'
```

Agent 交付时至少列出报告、CSV、配置、指标、事件记录（如有）与最终 `verification.json` 的实际路径。独立复算须直接读取 CSV，记录样本数、公式、窗口和与 `metrics.json` 的差值；仅再次调用项目分析函数不能充当独立复算。新的 Agent 上下文执行、同机目录搬迁、跨电脑与真人组员复现按本次约定分别记录；未纳入任务的项目标明“不在本次范围”。验收范围与证据随附要求见 [交接流程](handoff.md)。

## 接收结果时核对

| 要核对的问题 | Agent 应提供的证据 |
|---|---|
| 执行了什么任务 | 实际配置、命令与模型副本 |
| 波形来自哪里 | 原始 CSV、信号名称、单位和时间范围 |
| 指标能否重算 | 分析窗口、公式、归一化分母和判据 |
| 事件是否按要求生效 | 实际参考／输入信号、检测区间和分辨率 |
| 全部工况是否列出 | 每项状态、实际数值和报告路径 |
| 记录是否一致 | verify 的 record_status 与问题列表 |
| 实验是否达标 | experiment_status、未通过判据和越限值 |
| 是否发生异常 | 失败阶段、首次错误、清理结果和日志 |

区分数值观察、理论解释和待验证判断。例如，某组 Rin 工况的 RMS 随电阻变化，需要对应这组数据；推广到其他频率或模型时需建立相应实验。

超出支持模型或事件范围的任务，先按 [模型接入方法](model-integration.md) 完成适配和验证。人员复现按 [交接流程](handoff.md) 记录。
