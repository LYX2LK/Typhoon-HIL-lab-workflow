# 自建 RLC 模型到脚本采集

本练习面向有电路基础、刚开始使用 Typhoon Schematic Editor 和 Python 的组员。目标是从空白原理图建立可运行电路，说明每个元件、连线、参数和测量点的作用，再用统一入口取得可复核波形。本页的已执行部分由 Schematic API 建模并在 Virtual HIL 运行；下方图形界面重做步骤留给组员独立操作验收。

## 电路与判据

电压源 `Vs1` 驱动 `Rin` 串联 `[L 并联 (R 串联 C)]`。`I` 测源电流，`Va1` 测并联节点电压，新增的 `V_Rin` 测输入电阻压降。建模脚本从空白图创建 9 个元件、3 个连接点和 15 条连接，初始参数为 Rin=5 Ω、R=0.1 Ω、L=10 µH、C=500 µF。

运行脚本在**本次模型副本**中把 Rin 改为 8 Ω，回读并保存，再编译。源设置为 10 V RMS、1000 Hz；等待至少 0.05 s 后，以 20 kHz 采集 0.02 s。全部 400 个样本用于计算 `I`、`Va1`、`V_Rin` 的 RMS，与 `Rin + [L || (R+C)]` 的独立正弦相量值比较；三项相对误差均须不超过 3%。`V_Rin` 的解析参考为 `I_RMS × 8 Ω`。这检验了新增测量点和参数更改的实际效果。

## 建立和运行

在项目根目录，用 `environment.local.json` 指定的 THCC 2026.3 配套 Python 建立**新的** `.tse` 文件；输出路径换成本次任务目录。脚本拒绝覆盖已有模型。

```powershell
$labSettings = Get-Content -LiteralPath 'environment.local.json' -Raw -Encoding UTF8 | ConvertFrom-Json
$bundledPython = Join-Path $labSettings.typhoon_home 'python3_portable\python.exe'
& $bundledPython -B -X utf8 `
  scripts/build_rlc_practice.py `
  results/agent-tasks/本次任务标识/modeling/rlc_handbuilt.tse
.\lab.ps1 practice-model --model-file results/agent-tasks/本次任务标识/modeling/rlc_handbuilt.tse --json
```

第二条命令返回新的 `run_dir`。该目录含建模源副本、运行副本、代码快照、原始 `waveforms.csv`、`config.json`、`metrics.json`、`report.md` 和 `manifest.json`。从输出目录执行 `verify → report → verify`；最终 `verification.json` 的 `record_status` 表示哈希与全样本 RMS 复算一致性，`experiment_status` 表示 3% 判据结果。`practice-model` 只接受项目 `results/agent-tasks/` 下名为 `rlc_handbuilt.tse` 的模型，不会替换官方模板。

## 在图形界面独立重做

1. 在 Schematic Editor 中新建模型，按上述拓扑放置电压源、电阻、电感、电容、地、电流及两个电压测量点，并逐段检查连线和极性。
2. 先保存 5 Ω 版本，检查各属性的名称与单位；复制到自己的任务目录，再将 Rin 改为 8 Ω，另加 `V_Rin` 测量点并保存。
3. 编译副本，以 Virtual HIL 加载，核对 `Vs1`、`I`、`Va1`、`V_Rin` 可用。按上面的源和采样条件运行，记录界面截图、波形、实际操作者和卡点。
4. 与脚本目录中的三个 RMS 和相量参考比较。若 UI 模型的连接、参数或采集窗口不同，先解释差异，再判断结果；不要把脚本运行记录写成真人 GUI 验收。

同版本安装资料 `Documentation/html/schematic_api.html` 的空白建模示例提供 `create_new_model`、`create_component`、`create_connection`、`save_as` 和 `compile` 的 API 用法。本项目脚本采用顶层 RLC 结构并增添 `V_Rin`；实际拓扑及数值以本页脚本和运行记录为准。

## 本机软件证据

2026-10-20 的 [任务记录](../results/agent-tasks/20261020-modeling-intake-a1c9/task.md) 指向实际模型和命令；[最终练习报告](../results/20261020-152740-modeling-practice-c24cdc/report.md)记录 400 点采样及三项 RMS。[最终复核](../results/20261020-152740-modeling-practice-c24cdc/verification.json)显示记录和教学判据均通过。图形界面人工重做、其他组员和跨电脑操作尚需独立验收。
