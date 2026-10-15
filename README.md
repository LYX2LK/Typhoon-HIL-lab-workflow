# Typhoon HIL 与 AI Agent 教学工作流

读者：有电机或电力电子基础、尚不熟悉 Typhoon 与 Python 的课题组成员。
目的：通过选定教学模型完成改参数、扫工况、采波形、比较结果和报告，学会核对 Agent 的实验输出。

本项目采用 Typhoon HIL Control Center 自带的 Python 和官方示例模型。第一版使用 **Virtual HIL**：模型在电脑上非实时运行，没有外部 I/O。每次实验记录参数、模型副本、代码快照、实际波形、指标和文件哈希。

## 从这里开始

1. 阅读 [环境配置](docs/environment.md)，运行环境检查。
2. 阅读 [首次实验](docs/first-experiment.md)，理解模型和参数。
3. 在项目目录运行回环检查及 RLC 基准实验。
4. 运行三组输入电阻扫描，核对波形和指标。
5. 按 [Agent 使用指南](docs/agent-workflow.md) 用自然语言执行同一任务。
6. 依据 [交接验收](docs/handoff.md) 让另一位组员独立复现。

在 PowerShell 中：
~~~powershell
Set-Location 'D:\Typhoon\lab-workflow'
.\lab.ps1 doctor
.\lab.ps1 smoke
.\lab.ps1 inspect
.\lab.ps1 run --config configs/rlc_baseline.json
.\lab.ps1 sweep --config configs/rlc_sweep.json
~~~

运行结束会输出实际 run_dir。把它填入下列命令：
~~~powershell
.\lab.ps1 verify --run-dir 'results/实际运行目录'
.\lab.ps1 report --run-dir 'results/实际运行目录'
~~~

doctor 检查模块导入与版本；smoke 才运行编译、加载、回环和停止。run 与 sweep 使用实际仿真结果。report 根据已有数据生成报告；verify 核验文件哈希并复算指标。

如果 PowerShell 的本机策略阻止脚本，可在单次进程中运行：
~~~powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\lab.ps1 doctor
~~~
此命令不会修改系统执行策略。

## 对 Agent 说什么

在 Codex 中打开本项目目录，或明确让 Agent 先读取本项目的 AGENTS.md，然后发送：
> 检查环境，运行 RLC 基准实验；把 Rin 分别设为 1、5、10 Ω，保持其他条件一致，采集电流和节点电压，比较 RMS 并生成报告。给出实际结果目录和校验状态。

Agent 将使用统一执行入口。配置保存在 JSON 中，可追溯每次实际参数。自定义任务先复制配置，再修改相关字段，保留基准配置用于复现。

## 教学模型

官方 RLC 示例的真实拓扑为：电压源 Vs1 与 Rin 串联，后接两条并联支路：电感 L 和电阻 R 串电容 C。I 是源电流，Va1 是并联节点对地电压。API 中的组件位于顶层，名称是 Rin、R、L、C。

默认输入 10 V RMS、1000 Hz；Rin=5 Ω，R=0.1 Ω，L=10 µH，C=500 µF。扫描 Rin=1/5/10 Ω。结构参数修改后会保存新模型并重新编译。报告用此拓扑的稳态相量计算核对实际 RMS，默认相对误差容限 3%。

## 文档与结果

- [环境配置](docs/environment.md)
- [首次实验](docs/first-experiment.md)
- [Agent 使用指南](docs/agent-workflow.md)
- [模型、参数与指标](docs/experiments.md)
- [故障排查](docs/troubleshooting.md)
- [交接验收](docs/handoff.md)
- [验收状态](docs/validation.md)
- [Agent 项目指令](AGENTS.md)

每次 run 生成 config.json、model.tse、原始 waveforms.csv、capture.json、metrics.json、run.log、manifest.json、code_snapshot/、waveforms.png 与 report.html/report.md。sweep 另有 cases/、comparison.csv 和 comparison.png。结果目录始终新建，已有记录保留。

状态含义：passed 为本实验检查通过；failed 为指标未达预设标准；error 为执行或数据问题；skipped 为尚未执行的检查。不同运行模式的结果单独记录。

## 搬到另一台电脑

复制本项目源文件和模型模板。按 environment.local.json 的示例填写该电脑的 typhoon_home，或设置 TYPHOON_HOME 环境变量；使用匹配版本的 THCC 与个人/课题组许可。软件和许可由设备管理者配置，项目无需包含许可文件。

再次运行 doctor、smoke、基准实验和扫描。已生成结果可以单独保存供交接，但另一台电脑的独立复现仍应实际执行并记录。

## 当前交付边界

本版覆盖选定 RLC 模型和 Virtual HIL。真实 HIL 仿真器、外部控制器、固件升级、控制器烧写和其他模型的适配需要独立验证。当前机器的实测记录见验收状态；组员独立操作的验收在交接时补充。

## 图表方法参考

本项目图表制作使用 scientific-visualization 技能的原始数据保持、颜色与线型共同编码、带单位坐标轴和输出检查流程。方法来源为 Scientific Agent Skills；论文记录于 2026-10-14 核对，最新版本为 v2（2026-09-02）。

Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026). *Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents*. arXiv:2609.00065. https://doi.org/10.48550/arXiv.2609.00065
