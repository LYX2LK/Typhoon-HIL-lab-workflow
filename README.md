# Typhoon HIL 与 AI Agent 教学工作流

本项目帮助有电机或电力电子基础、尚不熟悉 Typhoon 与 Python 的组员，完成改参数、采波形、比较结果和报告。实验采用官方示例模型和软件自带 Python，通过统一入口执行。

运行模式为 **Virtual HIL**：模型在电脑上按仿真时间推进，以非实时方式运行，没有外部 I/O。每次实验保存配置、模型副本、代码快照、实际数据和判定依据。

## 选择实验

| 想完成的任务 | 使用模型 | 阅读材料 |
|---|---|---|
| 学会模型操作、采集和报告核对 | RLC | [首次实验](docs/first-experiment.md) |
| 改变 Rin，比较稳态 RMS 与解析值 | RLC | [参数与指标](docs/experiments.md) |
| 观察闭环参考阶跃和输入电压扰动 | Boost | [动态实验](docs/boost-experiments.md) |
| 通过自然语言执行或分析实验 | RLC / Boost | [Agent 工作流](docs/agent-workflow.md) |

首次使用建议先做 RLC，再做 Boost。已熟悉统一入口时，可直接选择相应模型的实验配置。

## 准备环境并运行

按 [环境配置](docs/environment.md) 指定 Typhoon 安装目录，在包含 `lab.ps1` 的目录执行：

```powershell
Set-Location 'D:\Typhoon\lab-workflow'
.\lab.ps1 doctor
.\lab.ps1 smoke
.\lab.ps1 inspect --model rlc_filter
.\lab.ps1 run --config configs/rlc_baseline.json
```

`doctor` 检查解释器、版本和模块；`smoke` 实际完成最小编译、加载、运行、读取和停止。`run` 输出本次 `run_dir`，后续核对均使用这个目录。

| 操作 | 命令 |
|---|---|
| 检查 Boost 模型 | `.\lab.ps1 inspect --model boost_closed_loop` |
| 扫描 RLC 输入电阻 | `.\lab.ps1 sweep --config configs/rlc_sweep.json` |
| 运行 Boost 基准 | `.\lab.ps1 run --config configs/boost_baseline.json` |
| 运行参考阶跃 | `.\lab.ps1 run --config configs/boost_reference_step.json` |
| 运行输入跌落 | `.\lab.ps1 run --config configs/boost_vin_drop.json` |
| 运行输入升高 | `.\lab.ps1 run --config configs/boost_vin_rise.json` |

实验配置的相对路径由入口相对于项目根目录解析。更改工况时另存配置，运行前确定参数、单位、采集窗口和判据。

## 核对结果

将占位路径换成本次实际目录：

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
| 动态事件的实际生效证据 | Boost 运行目录的 `events.json` |
| 图表、解释与执行问题 | `report.html` / `report.md`、`run.log` |
| 源码与结果复核 | `code_snapshot/`、`verification.json` |

RLC 扫描另有 `cases/`、`comparison.csv` 和 `comparison.png`。Boost 动态工况同时提供完整启动波形和事件区间细节图。结果始终写入新目录。

实验状态分为 `passed`、`failed`、`error`、`skipped`。复核输出中的 `record_status` 表示记录与复算是否一致，`experiment_status` 表示实验是否满足判据；总状态要求两者均通过。具体已验证能力、未达标项目和证据集中在 [验证状态](docs/validation.md)。

## 继续使用和维护

- 执行异常：按 [故障排查](docs/troubleshooting.md) 根据阶段定位。
- 另一位组员接手：按 [交接验收](docs/handoff.md) 独立复现。
- 接入其他模型：按 [模型接入方法](docs/model-integration.md) 建立参数、信号、判据和实际证据。
- 维护入口、记录或文档：阅读 [实现约定](PROJECT_SPEC.md) 与 [Agent 项目指令](AGENTS.md)。

搬到另一台电脑时保留目录结构，更新本机安装路径，再执行环境检查、最小仿真及所选实验。软件和许可由设备管理者配置。实体 HIL、外部控制器和电机模型的接入，需结合具体设备与任务另行验证。
