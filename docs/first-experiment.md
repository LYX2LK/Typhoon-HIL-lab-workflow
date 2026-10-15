# 首次实验：从模型到可核对的报告

本文面向有电路基础、首次使用 Typhoon 和 Python 的组员。目标是用项目提供的 RLC 模型完成一次基准实验，再扫描一个参数，并能指出报告中的每个结果来自哪个文件。

开始前，按 [环境配置](environment.md) 完成 `doctor` 与 `smoke`。下面的脚本流程已在本机通过 RLC 基准与扫描验收，证据见 [实测记录](validation.md)。重新使用时保留自己电脑上的运行记录。

## 1. 先看懂电路

运行模型检查：

```powershell
.\lab.ps1 inspect
```

项目模型来自官方 `basic electrical circuits/rlc circuit/rlc circuit.tse` 示例的副本。它包含输入源 `Vs1`、输入电阻 `Rin`、电感 `L` 和一个 `R` 串联 `C` 的支路；电感支路与 RC 支路并联。`Va1` 测量并联节点电压，`I` 测量源电流。

在 Schematic Editor 中打开 [rlc_filter.tse](../models/rlc_filter.tse)，沿连线找到这些元件和测量点。双击元件可以查看属性；第一次学习先核对参数名称和单位。具体参数、拓扑和指标见 [实验说明](experiments.md)。

![官方 RLC 示例电路](assets/rlc_filter.svg)

### 先认识一次图形界面

下面流程依据官方 [Quick Start](<../../Typhoon HIL Control Center 2026.3/typhoon/help/t-ug002/concepts/realtime_quick_start_guide.html>) 和所复制的 SCADA 面板编写，GUI 手动路径尚待组员实际操作验收。

1. 在 Schematic Editor 中打开 `models/rlc_filter.tse`，双击 `Rin`、`R`、`L`、`C` 查看参数与单位。
2. 点击 **Compile and load model in HIL SCADA**。出现运行目标选择时，选择 **Virtual HIL**。
3. 在 HIL SCADA 中加载项目的 `models/rlc_filter.cus` 面板；若自动识别到了该面板，也可从模型目录面板列表打开。
4. 将 **Input voltage RMS value** 设为 `10`，将 **Input voltage frequency [Hz]** 设为 `1000`，分别确认输入。
5. 点击 **Run**，在 Capture/Scope 中观察 `I` 与 `Va1`；记录实际看到的信号与时间尺度。
6. 点击 **Stop** 结束手动仿真，再使用下面的脚本入口。

界面中模型标题与 API 组件路径属于不同信息；本项目 API 顶层组件名为 `Rin`、`R`、`L`、`C`，通过 `inspect` 核对。

## 2. 运行基准实验

查看 [基准配置](../configs/rlc_baseline.json)，核对源幅值、频率、元件参数、采集信号和时间设置，再执行：

```powershell
.\lab.ps1 run --config configs/rlc_baseline.json
```

本版教学激励为 10 V RMS、1000 Hz 正弦；实际数值记录在配置和运行清单中。元件参数修改后，脚本保存模型副本、重新编译并加载，再启动仿真和采集。官方 [Schematic API](<../../Typhoon HIL Control Center 2026.3/Documentation/html/schematic_api.html>) 提供属性修改、保存及编译接口；[HIL API](<../../Typhoon HIL Control Center 2026.3/Documentation/html/hil_api.html>) 提供 Virtual HIL 加载与源波形设定接口。

记下终端给出的实际结果目录，其中包含：

| 文件 | 怎样使用 |
|---|---|
| `config.json` | 核对本次实际配置 |
| `model.tse` | 在 Schematic Editor 中复查本次模型副本 |
| `manifest.json` | 查看模式、版本、文件记录和执行状态 |
| `waveforms.csv` | 查 `t_relative_s`、`t_simulation_s`、`I_A`、`Va1_V` 原始列 |
| `metrics.json` | 查 RMS、解析参考值、误差与判据 |
| `waveforms.png` | 观察波形及所标时间范围 |
| `run.log` | 查执行过程和异常 |
| `capture.json` | 查实际采集信号、步长与触发信息 |
| `code_snapshot/` | 查本次运行使用的脚本副本 |
| `verification.json` | 执行 verify 后查看文件摘要检查与指标复算 |
| `report.html`、`report.md` | 阅读图表与结果说明 |

先观察电流和电压随仿真时间的变化，再核对数值。

## 3. 核对报告

将下面命令中的占位路径替换为本次实际目录：

```powershell
.\lab.ps1 verify --run-dir 'results/本次实际目录'
.\lab.ps1 report --run-dir 'results/本次实际目录'
```

`verify` 与 `report` 读取已有结果，不启动新仿真。报告核对顺序如下：

1. 参数和模式：记录的是本次实际参数，模式为 Virtual HIL。
2. 波形：API 信号 `Va1` 和 `I` 在 CSV 中对应 `Va1_V` 和 `I_A`；时间列 `t_relative_s`、`t_simulation_s` 的单位为秒，图表应对应这些原始数据。
3. 指标：RMS 使用报告注明的稳态区间，解析参考值来自本电路拓扑。
4. 判定：`passed`、`failed`、`error` 或 `skipped` 对应实际检查结果；阅读每项判据及阈值。

若 `verify` 报告异常，先保留目录，再按 [故障排查](troubleshooting.md) 处理。验收应包含“原始数据可复查、指标可重算、模型和参数可追溯”。

## 4. 扫描输入电阻

查看 [扫描配置](../configs/rlc_sweep.json)，确认一次只改变 `Rin`，其他条件相同：

```powershell
.\lab.ps1 sweep --config configs/rlc_sweep.json
```

本版扫描值为 1、5、10 Ω，均已实际执行；具体参数以本次保存的配置为准。对比各工况的稳态电流与节点电压 RMS，使用 [实验说明](experiments.md) 的阻抗关系解释变化。各工况记录位于扫描目录的 `cases/<case_id>`，汇总数据和图表为 `comparison.csv` 与 `comparison.png`，总报告应列出全部工况的状态。

## 5. 用自然语言完成同一实验

在项目对应的 Codex 聊天中发送：

> 请读取本项目 README、AGENTS.md 和实验说明。使用教学 RLC 模型，按 rlc_sweep.json 扫描 Rin，保留其他条件，运行并核对每个工况；比较 Va1 与 I 的稳态 RMS，给出原始数据路径和报告路径。若执行异常，请保留日志并说明失败阶段。

对照刚完成的手动流程检查 Agent 的配置和结果。具体协作方式见 [Agent 工作流](agent-workflow.md)。首次交接记录见 [交接验收](handoff.md)。
