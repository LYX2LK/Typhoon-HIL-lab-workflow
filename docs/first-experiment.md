# 首次实验：运行、采集与核对

本页面向有电路基础、首次使用 Typhoon 与 Python 的组员。通过 RLC 基准和输入电阻扫描，学会完整执行一次实验，并能指出报告中每个结果对应的证据。闭环控制实验使用相同入口，熟悉本页流程后可直接阅读 [Boost 教程](boost-experiments.md)。

## 准备并检查模型

先按 [环境配置](environment.md) 完成 doctor 与 smoke，再执行：

```powershell
.\lab.ps1 inspect --model rlc_filter
```

在 Schematic Editor 中打开 [rlc_filter.tse](../models/rlc_filter.tse)。模型由电压源 Vs1、输入电阻 Rin 以及两条对地并联支路组成：一条为 L，另一条为 R 串 C。I 测量源电流，Va1 测量并联节点电压。

沿连线找到这些元件与测量点，查看属性名称和单位。参数、拓扑与计算公式见 [RLC 实验说明](experiments.md)。

![RLC 教学电路](assets/rlc_filter.svg)

## 在图形界面认识模型（可选）

下面流程依据官方 [Quick Start](<../../Typhoon HIL Control Center 2026.3/typhoon/help/t-ug002/concepts/realtime_quick_start_guide.html>) 和所复制的 SCADA 面板编写。操作核对按 [交接流程](handoff.md) 记录。

1. 在 Schematic Editor 中打开 `models/rlc_filter.tse`，双击 `Rin`、`R`、`L`、`C` 查看参数与单位。
2. 点击 **Compile and load model in HIL SCADA**，将模型编译并加载到 HIL SCADA。出现运行目标选择时，选择 **Virtual HIL**。
3. 进入 HIL SCADA 后，确认窗口右下角显示 **VIRTUAL HIL MODE**。如果中央仍显示 **Create new Panel**、**Open Panel** 和 **Panels files found in Model directory**，说明当前处于面板选择页，接下来需要打开操作面板。
4. 点击界面中上方的 **Open Panel**，图标是**带绿色向上箭头的文件夹**，打开已有的 `.cus` 操作面板。在弹出的文件选择窗口中，选择 `rlc_filter.cus`。项目移到其他位置后，按新项目目录查找同名文件。
5. 面板打开后，应能看到 **Input voltage RMS value**、**Input voltage frequency [Hz]** 两个控件，以及 **Capture/Scope** 波形区。看到这些控件，表示操作面板已打开。
6. 将 **Input voltage RMS value** 设为 `10`，将 **Input voltage frequency [Hz]** 设为 `1000`，分别确认输入，并核对控件显示值。对应输入源为 10 V RMS、1000 Hz 正弦电压。
7. 点击**顶部主工具栏中绿色、向右的三角形按钮**，启动仿真。该按钮的悬停提示为 **Start the simulation**。在 **Capture/Scope** 中观察 `I`（源电流）与 `Va1`（节点电压）的周期波形；1000 Hz 对应每周期 **1 ms**。记录实际看到的信号与时间尺度。
8. 观察完成后，点击**启动按钮旁边的方形停止按钮**，停止仿真。该按钮的悬停提示为 **Stop the simulation**。关闭HIL SCADA 窗口，再使用下面的脚本入口。

界面中模型标题与 API 组件路径属于不同信息；本项目 API 顶层组件名为 `Rin`、`R`、`L`、`C`，通过 `inspect` 核对。

## 运行基准实验

打开 [rlc_baseline.json](../configs/rlc_baseline.json)，核对输入、元件值、采集窗口和判据，再执行：

```powershell
.\lab.ps1 run --config configs/rlc_baseline.json
```

脚本将结构参数写入本次模型副本，回读、保存并编译；加载后设置 10 V RMS、1000 Hz 正弦源，等待达到配置的仿真时间，再采集电流和电压。

记下终端输出的 run_dir。这个目录是本次实验的记录，核对时按以下顺序查看：

| 顺序 | 查看文件 | 要确认的内容 |
|---|---|---|
| 1 | config.json、manifest.json | 实际配置、环境、模型与实验状态 |
| 2 | model.tse、capture.json | 运行副本、信号名称、有效采样率与触发时间 |
| 3 | waveforms.csv | 时间、电流和电压的原始样本 |
| 4 | metrics.json、report.html | RMS、解析参考、相对误差与判据 |
| 5 | run.log、code_snapshot/ | 执行过程与所用源码 |

CSV 的 `t_relative_s`、`t_simulation_s` 单位为秒，`I_A` 为电流，`Va1_V` 为节点电压。图表应与这些原始数据对应。

## 复核并重建报告

将占位路径换为本次实际目录：

```powershell
.\lab.ps1 verify --run-dir 'results/本次实际目录'
.\lab.ps1 report --run-dir 'results/本次实际目录'
.\lab.ps1 verify --run-dir 'results/本次实际目录'
```

verify 核对文件哈希、代码快照和指标复算，结果写入 verification.json。report 从已有数据重建报告。阅读报告时确认参数和单位、实际采集窗口、解析拓扑、每项误差及判据。

若记录复核失败，保留目录并按 [故障排查](troubleshooting.md) 定位。实验状态和记录一致性的含义见 [README](../README.md#核对结果)。

## 扫描 Rin 并比较

打开 [rlc_sweep.json](../configs/rlc_sweep.json)，确认 Rin 为 1、5、10 Ω，其他条件相同，再执行：

```powershell
.\lab.ps1 sweep --config configs/rlc_sweep.json
```

扫描逐个修改 Rin、编译并运行。各工况保存在 cases/ 下，比较数据和图表为 comparison.csv、comparison.png，总报告列出全部工况状态。

按同样方式执行 verify、report、verify。选择一个工况，从原始样本独立计算一次 RMS，再对照 metrics.json；使用电路阻抗关系解释工况间差异。比较时明确当前模型、频率及保持不变的条件。

## 用 Agent 复现

在项目聊天中发送：

> 读取项目 README、AGENTS.md 和 RLC 实验说明。按 rlc_sweep.json 扫描 Rin，保持其余条件一致，比较 I 与 Va1 的稳态 RMS。给出实际目录、每项判据与 verify 结果；异常时保留日志和失败状态。

对照自己的操作，核对 Agent 使用的配置、工况与证据。更多任务写法见 [Agent 工作流](agent-workflow.md)，独立操作的验收按 [交接流程](handoff.md) 记录。
